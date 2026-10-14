"""Which work source a `@stage` function reaches, for its reuse key.

The walk starts at the stage function's code and follows the names that code uses,
resolved in its globals, closure and defaults, through work-local functions, classes
and modules (for a module, only the attributes the referencing code names). A file
counts as work source when it is in the run's inventory; anything else (installed
packages, the standard library, Tactus) is identified by the dependency lock instead.
Plain values reached (constants, arrays, containers) are also canonicalised into the
key, so a value imported from another file or reassigned at runtime still counts.

When the walk meets something it cannot attribute — an import inside a reached
function body, dynamic lookup (`getattr`, `exec`, `eval`, `__import__`, `globals`,
`vars`, `importlib`), or an object it cannot canonicalise — it raises `Unreachable`
and the caller keys the stage on every inventoried file, which is always safe.

Reads: stage._canon (the shared canonical encoder, passed in)
"""

from __future__ import annotations

import dis
import functools
import sys
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

DYNAMIC = frozenset(
    {
        "__import__",
        "__dict__",
        "__globals__",
        "compile",
        "delattr",
        "eval",
        "exec",
        "getattr",
        "globals",
        "import_module",
        "locals",
        "reload",
        "run_module",
        "run_path",
        "setattr",
        "vars",
    }
)
DYNAMIC_MODULES = frozenset({"importlib", "runpy"})
# Run namespace name of the entry file (`runpy.run_path(..., run_name=...)` in run.py).
ENTRY_MODULE = "__tactus__"


class Unreachable(Exception):
    """The walk cannot attribute something; key on every file. Message is the reason."""


def _codes(code: types.CodeType) -> Iterator[types.CodeType]:
    yield code
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            yield from _codes(constant)


class _Walk:
    def __init__(
        self, root: Path, inventory: set[str], entry: Path, canon: Callable[[Any], Any]
    ) -> None:
        self.root = root
        self.inventory = inventory
        self.entry = entry.relative_to(root).as_posix()
        self.canon = canon
        self.files: set[str] = set()
        self.values: dict[str, Any] = {}
        self.seen: set[Any] = set()
        self.keep: list[Any] = []  # keep visited objects alive so their ids stay unique

    def work_file(self, filename: str | None) -> str | None:
        if not filename:
            return None
        path = Path(filename).resolve()
        if not path.is_relative_to(self.root):
            return None
        relative = path.relative_to(self.root).as_posix()
        return relative if relative in self.inventory else None

    def visit(self, key: Any, obj: Any) -> bool:
        if key in self.seen:
            return False
        self.seen.add(key)
        self.keep.append(obj)
        return True

    def value(self, value: Any, label: str, names: frozenset[str]) -> None:
        if isinstance(value, types.ModuleType):
            self.module(value, names)
        elif isinstance(value, types.FunctionType):
            self.function(value)
        elif isinstance(value, type):
            self.cls(value)
        elif isinstance(value, types.MethodType):
            self.value(value.__func__, label, names)
            self.value(value.__self__, f"{label}.__self__", names)
        elif isinstance(value, functools.partial):
            self.value(value.func, f"{label}.func", names)
            self.value(value.args, f"{label}.args", names)
            self.value(value.keywords, f"{label}.keywords", names)
        elif isinstance(value, (types.BuiltinFunctionType, types.BuiltinMethodType)):
            owner = value.__self__
            if owner is not None and not isinstance(owner, types.ModuleType):
                self.value(owner, f"{label}.__self__", names)
        elif callable(value) and hasattr(value, "__wrapped__"):
            self.value(value.__wrapped__, f"{label}.__wrapped__", names)
        else:
            try:
                self.values[label] = self.canon(value)
            except Exception as exc:
                # A container may hold code (a dispatch table): walk its items instead.
                if type(value) in (list, tuple):
                    for index, item in enumerate(value):
                        self.value(item, f"{label}[{index}]", names)
                elif type(value) is dict and all(type(key) is str for key in value):
                    for key, item in sorted(value.items()):
                        self.value(item, f"{label}[{key!r}]", names)
                else:
                    raise Unreachable(f"{label} is a {type(value).__name__}: {exc}") from exc

    def function(self, func: types.FunctionType) -> None:
        if not self.visit(id(func), func):
            return
        wrapped = getattr(func, "__wrapped__", None)
        if wrapped is not None:
            self.value(wrapped, f"{func.__qualname__}.__wrapped__", frozenset())
        file = self.work_file(func.__code__.co_filename)
        cells = zip(func.__code__.co_freevars, func.__closure__ or ())
        if file is None:
            # Installed code is pinned by the lock; follow only code it closes over.
            for _, cell in cells:
                try:
                    contents = cell.cell_contents
                except ValueError:
                    continue
                if isinstance(contents, (types.FunctionType, type, functools.partial)):
                    self.value(contents, func.__qualname__, frozenset())
            return
        self.files.add(file)
        label = f"{file}:{func.__qualname__}"
        names: set[str] = set()
        for code in _codes(func.__code__):
            names.update(code.co_names)
            for instruction in dis.get_instructions(code):
                if instruction.opname in ("IMPORT_NAME", "IMPORT_FROM"):
                    raise Unreachable(f"{label} imports inside its body")
        dynamic = names & DYNAMIC
        if dynamic:
            raise Unreachable(f"{label} uses {', '.join(sorted(dynamic))}")
        frozen = frozenset(names)
        namespace = func.__globals__
        for name in sorted(names):
            if name in namespace:
                self.value(namespace[name], f"{file}:{name}", frozen)
        for variable, cell in cells:
            try:
                contents = cell.cell_contents
            except ValueError:
                continue
            self.value(contents, f"{label}:<closure {variable}>", frozen)
        for index, default in enumerate(func.__defaults__ or ()):
            self.value(default, f"{label}:<default {index}>", frozen)
        for name, default in sorted((func.__kwdefaults__ or {}).items()):
            self.value(default, f"{label}:<default {name}>", frozen)

    def cls(self, cls: type) -> None:
        if not self.visit(id(cls), cls):
            return
        if cls.__module__ == ENTRY_MODULE:
            file: str | None = self.entry
        else:
            module = sys.modules.get(cls.__module__)
            if module is None:
                raise Unreachable(f"class {cls.__qualname__} has no loaded module")
            file = self.work_file(getattr(module, "__file__", None))
        if file is None:
            return
        self.files.add(file)
        for base in cls.__mro__[1:]:
            self.cls(base)
        label = f"{file}:{cls.__qualname__}"
        code_like = (types.FunctionType, staticmethod, classmethod, property)
        descriptors = (types.MemberDescriptorType, types.GetSetDescriptorType)
        for name, attribute in vars(cls).items():
            dunder = name.startswith("__") and name.endswith("__")
            if (dunder and not isinstance(attribute, code_like)) or name.startswith("_abc_"):
                continue  # interpreter-made class metadata, not author values
            if isinstance(attribute, descriptors):
                continue
            if isinstance(attribute, (staticmethod, classmethod)):
                attribute = attribute.__func__
            if isinstance(attribute, property):
                for accessor in (attribute.fget, attribute.fset, attribute.fdel):
                    if accessor is not None:
                        self.value(accessor, f"{label}.{name}", frozenset())
                continue
            self.value(attribute, f"{label}.{name}", frozenset())

    def module(self, module: types.ModuleType, names: frozenset[str]) -> None:
        if module.__name__.split(".", 1)[0] in DYNAMIC_MODULES:
            raise Unreachable(f"uses {module.__name__}")
        file = self.work_file(getattr(module, "__file__", None))
        if file is None:
            locations = getattr(module, "__path__", None) or ()
            if not any(Path(path).resolve().is_relative_to(self.root) for path in locations):
                return  # installed or standard-library module: the lock identifies it
            if getattr(module, "__file__", None):
                return  # under the root but not inventoried (.venv and other exclusions)
        else:
            self.files.add(file)
        namespace = vars(module)
        for name in sorted(names):
            if name in namespace and self.visit((id(module), name), module):
                self.value(namespace[name], f"{file or module.__name__}:{name}", names)


def reach(
    func: types.FunctionType,
    *,
    root: Path,
    inventory: set[str],
    entry: Path,
    canon: Callable[[Any], Any],
) -> tuple[set[str], dict[str, Any]]:
    """The work files and canonical plain values `func` can reach; raises `Unreachable`."""
    walk = _Walk(root, inventory, entry, canon)
    walk.function(func)
    if not walk.files:
        raise Unreachable("the stage function is not in an inventoried work file")
    return walk.files, walk.values


__all__ = ["Unreachable", "reach"]
