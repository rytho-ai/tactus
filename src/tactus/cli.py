"""JSON command adapters for functional productions, work scaffolding and diagnostics."""

from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path

from . import analysis
from .analysis._image import SUPPORTED as IMAGE_ANALYSES
from .analyze import measure
from .commands import add_flags, registry
from .excerpt import excerpt, parse_outputs, parse_range
from .export import BUILTINS as EXPORTERS
from .export import deliver
from .init import init
from .inputs import pool, tree
from .project import discover
from .run import RunError, parse_params, run
from .takes import export_take, save_take


class _RunParser(argparse.ArgumentParser):
    """Keep run argument failures in the same JSON envelope as execution failures."""

    def error(self, message: str) -> None:
        raise RunError("invalid_request", "request", message)


def _main(argv: Sequence[str] | None = None) -> int:
    """Execute a command; functional runs reserve stdout for one JSON result."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    project = discover(
        Path(os.environ["TACTUS_PROJECT_ROOT"]) if os.environ.get("TACTUS_PROJECT_ROOT") else None
    )
    package_version = version("tactus")
    parser_type = (
        _RunParser
        if arguments[:1]
        in (["run"], ["material"], ["excerpt"], ["init"], ["analyze"], ["take"], ["export"])
        else argparse.ArgumentParser
    )
    parser = parser_type(
        prog="tactus",
        description="Produce music with code. Built for agents.",
        epilog=(
            "Arrange, render, analyze, and refine. "
            "The installed launcher accepts: tactus --project DIR COMMAND ..."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report the installed environment")
    run_command = commands.add_parser("run", help="Execute a Python render() production")
    run_command.add_argument("source", type=Path, help="Python file defining render(*, ...)")
    run_command.add_argument("--out", required=True, type=Path, help="New run directory")
    run_command.add_argument("--params", default="{}", help="JSON object of parameter overrides")
    run_command.add_argument(
        "--reuse",
        action="store_true",
        help="Reuse unchanged @stage results from prior runs on unchanged source",
    )
    take_command = commands.add_parser("take", help="Save and transfer immutable performances")
    take_commands = take_command.add_subparsers(dest="take_command", required=True)
    save_command = take_commands.add_parser(
        "save", help="Save a completed run's named take to the pool"
    )
    save_command.add_argument("run_dir", type=Path)
    save_command.add_argument("name", help="Name in render's takes mapping")
    export_command = take_commands.add_parser("export", help="Export a saved take for transfer")
    export_command.add_argument("ref", help="Saved tree:sha256: reference")
    export_command.add_argument("--out", type=Path, required=True, help="New bundle directory")
    excerpt_command = commands.add_parser(
        "excerpt", help="Slice an existing run's outputs into a new run directory"
    )
    excerpt_command.add_argument("run_dir", type=Path, help="Directory of a completed run")
    excerpt_command.add_argument("--out", required=True, type=Path, help="New run directory")
    excerpt_command.add_argument(
        "--range",
        required=True,
        help="START:END in seconds to publish; END may be empty for each output's end",
    )
    excerpt_command.add_argument("--outputs", help="Comma-separated output names to publish")
    init_command = commands.add_parser(
        "init", help="Scaffold a work as its own uv project depending on a pinned Tactus"
    )
    init_command.add_argument(
        "directory", type=Path, help="New work directory (must not exist or be empty)"
    )
    init_source = init_command.add_mutually_exclusive_group()
    init_source.add_argument(
        "--tactus-path", type=Path, help="Pin an editable local Tactus checkout"
    )
    init_source.add_argument("--tactus", help="Pin an explicit Tactus source as URL@REV")
    material_command = commands.add_parser("material", help="Manage the shared input material pool")
    material_subcommands = material_command.add_subparsers(dest="material_command", required=True)
    add_command = material_subcommands.add_parser(
        "add", help="Import files into the pool, printing their sha256 refs"
    )
    add_command.add_argument("paths", nargs="+", type=Path, help="Files or folders to import")
    builtin_analysis = {
        f"{category}.{fn.__name__}": fn
        for category, module in analysis.CATEGORIES.items()
        for fn in module.ANALYSES
    }
    # Registrations for the other command family do not affect this invocation.
    analyses = registry(
        project if arguments[:1] == ["analyze"] else None, "analysis", builtin_analysis
    )
    exporters = registry(project if arguments[:1] == ["export"] else None, "export", EXPORTERS)
    analyze_command = commands.add_parser("analyze", help="Built-in and project audio analyses")
    category_commands = analyze_command.add_subparsers(dest="category", required=True)
    for category in sorted({name.split(".")[0] for name in analyses}):
        module = analysis.CATEGORIES.get(category)
        description = module.__doc__ if module else f"Project analyses: {category}"
        cat_parser = category_commands.add_parser(
            category, help=description.splitlines()[0].replace("%", "%%"), description=description
        )
        name_commands = cat_parser.add_subparsers(dest="name", required=True)
        for key, command in analyses.items():
            if key.split(".")[0] != category:
                continue
            name = key.split(".")[1]
            selected = arguments[:3] == ["analyze", category, name]
            fn = command.load() if selected else command.function
            name_parser = name_commands.add_parser(
                name,
                help=command.summary.replace("%", "%%"),
                description=inspect.getdoc(fn) if fn else command.summary,
                formatter_class=argparse.RawDescriptionHelpFormatter,
            )
            name_parser.add_argument(
                "paths", nargs="+", type=Path, help="Audio files or completed run directories"
            )
            name_parser.add_argument(
                "--out", type=Path, help="Save result JSON and array attachments"
            )
            image_flags = set()
            if key in IMAGE_ANALYSES and command.project is None:
                name_parser.add_argument(
                    "--image",
                    action="store_true",
                    help="Save a labeled SVG alongside numeric arrays; requires --out",
                )
                name_parser.add_argument(
                    "--image-min", type=float, help="Fixed color scale lower bound"
                )
                name_parser.add_argument(
                    "--image-max", type=float, help="Fixed color scale upper bound"
                )
                image_flags = {"image", "image_min", "image_max"}
            if selected:
                names = add_flags(
                    name_parser,
                    fn,
                    {"paths", "out", "help", "command", "category", "name"} | image_flags,
                )
                name_parser.set_defaults(callable_command=command, param_names=names)
    export_command = commands.add_parser(
        "export", help="Deliver a saved render without regenerating"
    )
    export_commands = export_command.add_subparsers(dest="export_name", required=True)
    for name, command in exporters.items():
        selected = arguments[:2] == ["export", name]
        fn = command.load() if selected else command.function
        sub = export_commands.add_parser(
            name,
            help=command.summary.replace("%", "%%"),
            description=inspect.getdoc(fn) if fn else command.summary,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        sub.add_argument(
            "run_dir", type=Path, help="Source run (render.json, or legacy published WAVs)"
        )
        sub.add_argument("--out", required=True, type=Path, help="New delivery directory")
        if selected:
            names = add_flags(sub, fn, {"out", "run_dir", "help", "command", "export_name"})
            sub.set_defaults(callable_command=command, param_names=names)
    try:
        args = parser.parse_args(arguments)
        if args.command == "run":
            result = run(
                args.source, out=args.out, params=parse_params(args.params), reuse=args.reuse
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "take":
            result = (
                save_take(args.run_dir, args.name)
                if args.take_command == "save"
                else export_take(args.ref, out=args.out)
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "excerpt":
            result = excerpt(
                args.run_dir,
                out=args.out,
                range=parse_range(args.range),
                outputs=parse_outputs(args.outputs) if args.outputs is not None else None,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "init":
            result = init(args.directory, tactus_path=args.tactus_path, tactus=args.tactus)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "material" and args.material_command == "add":
            for path in args.paths:
                if not path.is_file() and not path.is_dir():
                    raise RunError(
                        "invalid_request",
                        "request",
                        f"material path is not a file or directory: {path}",
                    )
            materials: dict[str, str] = {}
            try:
                for path in args.paths:
                    materials[str(path)] = (
                        tree.add(path) if path.is_dir() else f"sha256:{pool.put(path)}"
                    )
            except ValueError as exc:
                raise RunError("invalid_request", "request", str(exc)) from exc
            print(json.dumps({"status": "ok", "materials": materials}, sort_keys=True))
            return 0
        if args.command in ("analyze", "export"):
            params = {name: getattr(args, name) for name in args.param_names}
            # Reuse the finite JSON parameter boundary of render().
            params = parse_params(json.dumps(params))
            if args.command == "export":
                result = deliver(
                    args.run_dir, out=args.out, command=args.callable_command, params=params
                )
                print(json.dumps(result, sort_keys=True))
            else:
                visualization = None
                supports_image = (
                    args.callable_command.name in IMAGE_ANALYSES
                    and args.callable_command.project is None
                )
                wants_image = getattr(args, "image", False) if supports_image else False
                image_min = getattr(args, "image_min", None) if supports_image else None
                image_max = getattr(args, "image_max", None) if supports_image else None
                if wants_image:
                    if args.out is None:
                        raise RunError("invalid_request", "request", "--image requires --out DIR")
                    visualization = {"vmin": image_min, "vmax": image_max}
                elif image_min is not None or image_max is not None:
                    raise RunError("invalid_request", "request", "--image-min/max require --image")
                for result in measure(
                    args.paths, args.callable_command, params, args.out, visualization=visualization
                ):
                    print(json.dumps(result, sort_keys=True))
            return 0
    except RunError as exc:
        print(json.dumps(exc.to_dict(), sort_keys=True))
        return exc.exit_code

    if args.command == "doctor":
        print(
            json.dumps(
                {
                    "package": "tactus",
                    "version": package_version,
                    "python": sys.version.split()[0],
                    "environment": sys.prefix,
                    "project": str(project.root) if project else None,
                    "status": "ok",
                },
                sort_keys=True,
            )
        )
        return 0

    parser.error(f"unknown command: {args.command}")


@contextmanager
def _project_imports(root):
    before = set(sys.modules)
    original = sys.path[:]
    old_cache_prefix, old_dont_write = sys.pycache_prefix, sys.dont_write_bytecode
    cache = tempfile.TemporaryDirectory(prefix="tactus-import-")
    sys.pycache_prefix, sys.dont_write_bytecode = cache.name, True
    if root:
        sys.path.insert(0, str(root))
    try:
        yield
    finally:
        sys.path[:] = original
        sys.pycache_prefix, sys.dont_write_bytecode = old_cache_prefix, old_dont_write
        cache.cleanup()
        # Keep repeated in-process CLI calls from reusing another work's local modules.
        if root:
            for name in set(sys.modules) - before:
                file = getattr(sys.modules[name], "__file__", None)
                if file and Path(file).resolve().is_relative_to(root):
                    sys.modules.pop(name, None)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        project = discover(
            Path(os.environ["TACTUS_PROJECT_ROOT"])
            if os.environ.get("TACTUS_PROJECT_ROOT")
            else None
        )
        with _project_imports(project.root if project else None):
            return _main(argv)
    except RunError as exc:
        print(json.dumps(exc.to_dict(), sort_keys=True))
        return exc.exit_code
    except (ValueError, TypeError, OSError, ImportError, AttributeError) as exc:
        error = RunError("invalid_request", "request", f"{type(exc).__name__}: {exc}")
        print(json.dumps(error.to_dict(), sort_keys=True))
        return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
