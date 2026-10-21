"""JSON command adapters for functional productions, work scaffolding and diagnostics."""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import tempfile
from collections.abc import Sequence
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Any

from ._contracts import RunError, parse_params
from ._source import environment, package_sources
from .commands import add_flags, registry
from .excerpt import excerpt, parse_beats, parse_outputs, parse_range
from .export import BUILTINS as EXPORTERS
from .export import deliver, flag_view
from .init import init
from .inputs import pool, tree
from .project import environment_root, selected_project
from .run import run
from .takes import export_take, save_take


class _RunParser(argparse.ArgumentParser):
    """Keep run argument failures in the same JSON envelope as execution failures."""

    def error(self, message: str) -> None:
        raise RunError("invalid_request", "request", message)



def _summary(value: Any, limit: int = 12) -> Any:
    """Long lists and mappings become their size, so a summary stays a few lines long."""
    if isinstance(value, dict):
        if len(value) > limit:
            return {"count": len(value)}
        return {key: _summary(item, limit) for key, item in value.items()}
    if isinstance(value, list) and len(value) > limit:
        return {"count": len(value)}
    return value


def _brief_run(result: dict) -> dict:
    levels = result.get("levels", {})
    peaks = [entry["peak_dbfs"] for entry in levels.values() if entry.get("peak_dbfs") is not None]
    brief = {
        "status": result["status"],
        "run": str(Path(result["manifest"]).parent),
        "manifest": result["manifest"],
        "receipt": result["receipt"],
        "outputs": len(result.get("outputs", {})),
        "peak_dbfs": max(peaks) if peaks else None,
        "clipped": sorted(n for n, e in levels.items() if e.get("clipped_samples")),
        "render_bytes": result.get("render_bytes"),
    }
    for key in ("map", "takes", "source_changed"):
        if result.get(key) is not None:
            brief[key] = _summary(result[key])
    return brief


def _brief_export(result: dict) -> dict:
    brief = {key: result[key] for key in ("status", "directory", "manifest") if key in result}
    brief["files"] = len(result.get("files", {}))
    brief["result"] = _summary(result.get("result"))
    if result.get("replaced"):
        brief["replaced"] = True
    return brief

def _main(argv: Sequence[str] | None = None) -> int:
    """Execute a command; functional runs reserve stdout for one JSON result."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    project = selected_project(recognize_uv=argv is None)
    package_version = version("tactus")
    parser_type = (
        _RunParser
        if arguments[:1]
        in (
            ["run"],
            ["material"],
            ["excerpt"],
            ["init"],
            ["analyze"],
            ["take"],
            ["export"],
            ["serve"],
        )
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
    mcp_command = commands.add_parser(
        "mcp", help="Expose native DAW tools over stdio (needs tactus[mcp])"
    )
    from ._mcp_args import add_connection_arguments

    add_connection_arguments(mcp_command)
    run_command = commands.add_parser("run", help="Execute a Python render() production")
    run_command.add_argument("source", type=Path, help="Python file defining render(*, ...)")
    run_command.add_argument("--out", required=True, type=Path, help="New run directory")
    run_command.add_argument("--params", default="{}", help="JSON object of parameter overrides")
    run_command.add_argument(
        "--param-file",
        action="append",
        default=[],
        metavar="NAME=FILE",
        help="Bind a JSON file (a performance) to parameter NAME; repeatable. The receipt "
        "records its sha256 and the run keeps a copy in parameters/NAME.json",
    )
    run_command.add_argument(
        "--reuse",
        action="store_true",
        help="Reuse unchanged @stage results from prior runs on unchanged source",
    )
    run_command.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Do not save the original arrays; keep only the published PCM (throwaway candidates)",
    )
    run_command.add_argument(
        "--brief",
        action="store_true",
        help="Print a summary (status, run directory, records, output count, loudest peak, "
        "clipped outputs) instead of every output path",
    )
    serve_work = commands.add_parser(
        "serve",
        help="Keep a work loaded and render requests over local HTTP (needs tactus[serve])",
        description="Load SOURCE once in a resident worker and render each POST /v1/render "
        "({params, param_files, key, checkpoint, deliver}) into OUT/<session>/NNNN, an ordinary "
        "run directory with its own receipt; the answer is the request as a resource (sample "
        "rate, outputs in frames and seconds, map, file URLs; deliver: {codec, bitrate} adds "
        "browser audio and bundle.json). GET /v1/work describes the work; /docs lists the "
        "routes; the unversioned POST /render, /status, /cancel and /reload stay. An edited "
        "source is loaded again before the next request. Local only. Stop with Ctrl-C; the "
        "summary is printed as JSON.",
    )
    serve_work.add_argument("source", type=Path, help="Python file defining render(*, ...)")
    serve_work.add_argument(
        "--out", required=True, type=Path, help="Root for session directories"
    )
    serve_work.add_argument("--host", default="127.0.0.1", help="A loopback address")
    serve_work.add_argument("--port", type=int, default=0, help="Default: chosen by the system")
    serve_work.add_argument(
        "--static",
        type=Path,
        metavar="DIR",
        help="Serve DIR at / (index.html) beside the API, so a page shares its origin",
    )
    serve_work.add_argument(
        "--reuse", action="store_true", help="Reuse unchanged @stage results"
    )
    serve_work.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Do not save requests' original arrays; keep only the published PCM",
    )
    serve_work.add_argument(
        "--retain",
        type=int,
        metavar="N",
        help="Keep only the newest N request directories; older receipts move to retired/",
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
    excerpt_selection = excerpt_command.add_mutually_exclusive_group(required=True)
    excerpt_selection.add_argument(
        "--range",
        help="START:END in seconds to publish; END may be empty for each output's end",
    )
    excerpt_selection.add_argument(
        "--beats", help="START:END 1-based beat-point indices, end exclusive; requires --beat-grid"
    )
    excerpt_command.add_argument(
        "--beat-grid",
        type=Path,
        help="JSON beat times in source-run seconds (array or beats_s result)",
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
    prune_command = commands.add_parser(
        "prune", help="Remove completed runs' original arrays, keeping their published audio"
    )
    prune_command.add_argument("run_dirs", nargs="+", type=Path, help="Completed run directories")
    material_command = commands.add_parser("material", help="Manage the shared input material pool")
    material_subcommands = material_command.add_subparsers(dest="material_command", required=True)
    add_command = material_subcommands.add_parser(
        "add", help="Import files into the pool, printing their sha256 refs"
    )
    add_command.add_argument("paths", nargs="+", type=Path, help="Files or folders to import")
    analyzing = arguments[:1] == ["analyze"]
    if analyzing:
        # Analysis modules import SciPy's signal package; load them only for `analyze`.
        from . import analysis
        from .analysis._image import SUPPORTED as IMAGE_ANALYSES
        from .analyze import measure

        builtin_analysis = {
            f"{category}.{fn.__name__}": fn
            for category, module in analysis.CATEGORIES.items()
            for fn in module.ANALYSES
        }
    else:
        builtin_analysis = {}
    # Registrations for the other command family do not affect this invocation.
    analyses = registry(project if analyzing else None, "analysis", builtin_analysis)
    exporters = registry(project if arguments[:1] == ["export"] else None, "export", EXPORTERS)
    analyze_command = commands.add_parser("analyze", help="Built-in and project audio analyses")
    category_commands = analyze_command.add_subparsers(dest="category", required=True)
    for category in sorted({name.split(".")[0] for name in analyses} if analyzing else ()):
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
            name_parser.add_argument(
                "--brief",
                action="store_true",
                help="Print only path, output, analysis and result (omit params and provenance)",
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
                    {"paths", "out", "brief", "help", "command", "category", "name"} | image_flags,
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
        sub.add_argument(
            "--replace",
            action="store_true",
            help="Rewrite --out if it is an earlier tactus export; the new export is written "
            "beside it and swapped in only when it succeeds",
        )
        sub.add_argument(
            "--brief", action="store_true", help="Print a summary instead of every file path"
        )
        if selected:
            names = add_flags(
                sub,
                flag_view(fn),
                {"out", "run_dir", "help", "command", "export_name", "replace", "brief"},
            )
            sub.set_defaults(callable_command=command, param_names=names)
    try:
        args = parser.parse_args(arguments)
        if args.command == "mcp":
            from ._mcp_args import connection_kwargs
            from .mcp import serve

            try:
                connection = connection_kwargs(daw=args.daw, path=args.path,
                                               resource_path=args.resource_path,
                                               ableton_path=args.ableton_path,
                                               reaper_path=args.reaper_path,
                                               live_path=args.live_path)
            except ValueError as exc:
                mcp_command.error(str(exc))
            return serve(**connection)
        if args.command == "run":
            param_files = {}
            for binding in args.param_file:
                name, separator, path = binding.partition("=")
                if not separator or not name or not path:
                    raise RunError(
                        "invalid_request", "request", f"--param-file needs NAME=FILE: {binding!r}"
                    )
                if name in param_files:
                    raise RunError(
                        "invalid_request", "request", f"--param-file {name} is given twice"
                    )
                param_files[name] = Path(path)
            result = run(
                args.source,
                out=args.out,
                params=parse_params(args.params),
                reuse=args.reuse,
                checkpoint=not args.no_checkpoint,
                param_files=param_files,
            )
            print(json.dumps(_brief_run(result) if args.brief else result, sort_keys=True))
            return 0
        if args.command == "serve":
            from . import _serve_http
            from .serve import Service

            service = Service(
                args.source,
                args.out,
                reuse=args.reuse,
                checkpoint=not args.no_checkpoint,
                retain=args.retain,
            )
            result = _serve_http.serve(
                service,
                host=args.host,
                port=args.port,
                static=args.static,
                announce=lambda url: print(
                    f"tactus serve: {url} (session {service.directory})",
                    file=sys.stderr,
                    flush=True,
                ),
            )
            print(json.dumps({"status": "ok", **result}, sort_keys=True))
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
                range=parse_range(args.range) if args.range is not None else None,
                beat_grid=args.beat_grid,
                beats=parse_beats(args.beats) if args.beats is not None else None,
                outputs=parse_outputs(args.outputs) if args.outputs is not None else None,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "init":
            result = init(args.directory, tactus_path=args.tactus_path, tactus=args.tactus)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "prune":
            from . import render_store

            runs = {str(path): render_store.prune(path) for path in args.run_dirs}
            freed = sum(run["freed_bytes"] for run in runs.values())
            print(json.dumps({"status": "ok", "freed_bytes": freed, "runs": runs}, sort_keys=True))
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
            report = {"status": "ok", "materials": materials, "pool": str(pool.default_pool_dir())}
            print(json.dumps(report, sort_keys=True))
            return 0
        if args.command in ("analyze", "export"):
            params = {name: getattr(args, name) for name in args.param_names}
            # Reuse the finite JSON parameter boundary of render().
            params = parse_params(json.dumps(params))
            if args.command == "export":
                result = deliver(
                    args.run_dir,
                    out=args.out,
                    command=args.callable_command,
                    params=params,
                    replace=args.replace,
                )
                print(json.dumps(_brief_export(result) if args.brief else result, sort_keys=True))
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
                    if args.brief:
                        result = {
                            key: result[key]
                            for key in ("path", "output", "analysis", "result")
                            if key in result
                        }
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
                    "interpreter": sys.executable,
                    "lock": environment()["lock"],
                    "package_source": package_sources(["tactus"]).get("tactus"),
                    "project": str(project.root) if project else None,
                    "environment_matches_project": (
                        Path(sys.prefix).resolve()
                        == (environment_root(project.root) / ".venv").resolve()
                        if project
                        else None
                    ),
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
        project = selected_project(recognize_uv=argv is None)
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
