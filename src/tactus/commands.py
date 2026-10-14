"""Named built-in/project callables and their shared signature-to-CLI contract.

Only the selected project callable is imported. Registry discovery reads TOML, so
unrelated help and built-ins work when an unselected plugin has missing dependencies.
Project modules are ordinary Python imports, with root precedence scoped by the CLI.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import re
import sys
import types
import typing
from collections.abc import Callable
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from ._source import FileIdentity
from .project import Project

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class CommandIdentity(TypedDict):
    name: str
    callable: str
    source: FileIdentity | None


@dataclass
class Command:
    name: str
    kind: str
    function: Callable | None = None
    target: str | None = None
    project: Project | None = None

    def load(self) -> Callable:
        if self.function is None:
            if self.target is None:
                raise ValueError(f"{self.name} requires a function or module:function target")
            module, name = self.target.split(":")
            try:
                with redirect_stdout(sys.stderr):
                    imported = importlib.import_module(module)
                    self.function = getattr(imported, name)
            except (Exception, SystemExit) as exc:
                raise ValueError(f"cannot load {self.target}: {type(exc).__name__}: {exc}") from exc
        fn = self.function
        if (
            not inspect.isfunction(fn)
            or inspect.iscoroutinefunction(fn)
            or inspect.isgeneratorfunction(fn)
            or inspect.isasyncgenfunction(fn)
        ):
            raise ValueError(f"{self.name} must be a synchronous function returning a dict")
        params = list(inspect.signature(fn).parameters.values())
        expected = (
            ["audio", "sample_rate"] if self.kind == "analysis" else ["outputs", "sample_rate"]
        )
        if [p.name for p in params[:2]] != expected or any(
            p.kind not in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) for p in params[:2]
        ):
            raise ValueError(f"{self.name} must start with ({', '.join(expected)}, *, ...)")
        if any(p.kind != p.KEYWORD_ONLY for p in params[2:]):
            raise ValueError(f"{self.name}: custom parameters must be keyword-only")
        if self.kind == "export" and "out" not in inspect.signature(fn).parameters:
            raise ValueError(f"{self.name}: exporter requires keyword-only out")
        return fn

    @property
    def summary(self) -> str:
        if self.function:
            return (inspect.getdoc(self.function) or self.name).splitlines()[0]
        return f"Project {self.kind}: {self.target}"


def registry(
    project: Project | None, kind: str, builtins: dict[str, Callable]
) -> dict[str, Command]:
    result = {name: Command(name, kind, fn) for name, fn in builtins.items()}
    custom = project.settings.get(kind, {}) if project else {}
    if not isinstance(custom, dict):
        raise TypeError(f"[tool.tactus.{kind}] must map names to module:function strings")
    for name, target in custom.items():
        parts = name.split(".")
        if len(parts) != (2 if kind == "analysis" else 1) or not all(
            _NAME.fullmatch(p) for p in parts
        ):
            raise ValueError(f"invalid {kind} command name: {name!r}")
        if name in result:
            raise ValueError(f"project {kind} conflicts with built-in: {name}")
        if not isinstance(target, str) or not re.fullmatch(
            r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", target
        ):
            raise ValueError(f"{name}: registration must be module:function")
        result[name] = Command(name, kind, target=target, project=project)
    return result


def flag_type(annotation: Any):
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return flag_type(args[0]) if len(args) == 1 else json.loads
    if annotation in (str, int, float):
        return annotation
    if annotation is inspect.Parameter.empty:
        return str
    return json.loads


def add_flags(parser: argparse.ArgumentParser, fn: Callable, reserved: set[str]) -> list[str]:
    try:
        hints = typing.get_type_hints(fn)
    except Exception as exc:
        raise ValueError(f"cannot resolve {fn.__name__} parameter annotations: {exc}") from exc
    names = []
    for name, param in list(inspect.signature(fn).parameters.items())[2:]:
        if name == "out":
            continue
        if (
            name in reserved | {"callable_command", "param_names"}
            or name.replace("_", "-") in reserved
        ):
            raise ValueError(f"parameter {name!r} conflicts with a CLI argument")
        names.append(name)
        annotation = hints.get(name, param.annotation)
        kwargs: dict[str, Any] = {
            "dest": name, "help": f"default: {param.default!r}".replace("%", "%%")
        }
        if annotation is bool:
            kwargs["action"] = argparse.BooleanOptionalAction
        else:
            kwargs["type"] = flag_type(annotation)
        if param.default is inspect.Parameter.empty:
            kwargs["required"] = True
            kwargs["help"] = "required"
        else:
            kwargs["default"] = param.default
        try:
            parser.add_argument("--" + name.replace("_", "-"), **kwargs)
        except argparse.ArgumentError as exc:
            raise ValueError(f"parameter {name!r} conflicts with a CLI argument: {exc}") from exc
    return names


def identity(command: Command) -> CommandIdentity:
    from .inputs.pool import hash_file

    fn = command.load()
    path = inspect.getsourcefile(inspect.unwrap(fn))
    return {
        "name": command.name,
        "callable": command.target or f"{fn.__module__}:{fn.__name__}",
        "source": {"path": path, "sha256": hash_file(Path(path))} if path else None,
    }
