"""JSON command adapters for functional productions, work scaffolding and diagnostics."""

from __future__ import annotations

import argparse
import inspect
import json
import math
import sys
import types as _types
import typing
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Any

import soundfile as sf

from . import analysis
from .excerpt import excerpt, parse_outputs, parse_range, read_published
from .init import init
from .inputs import pool, tree
from .run import RunError, parse_params, run
from .takes import export_take, save_take


def _json_safe(value: Any) -> Any:
    """Non-finite floats become `null`, as the manifest reports digital silence."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _analysis_params(fn: Any) -> tuple[list[str], bool]:
    """An analysis function's CLI-facing parameter names (every keyword parameter except
    `audio`/`sample_rate`/`out`) and whether it accepts `out` (large-result file delivery)."""
    names = []
    accepts_out = False
    for name in inspect.signature(fn).parameters:
        if name in ("audio", "sample_rate"):
            continue
        if name == "out":
            accepts_out = True
            continue
        names.append(name)
    return names, accepts_out


def _help_text(text: str) -> str:
    """Escape `%` for `argparse`, which always `%`-expands `help=` strings (e.g. for
    `%(default)s`) — a docstring's own `%` (as in "50% overlap") would otherwise crash
    `--help` with a cryptic `TypeError`."""
    return text.replace("%", "%%")


def _flag_type(annotation: Any) -> Any:
    """An `argparse` `type=` callable for a parameter's type hint: `int`/`float`/`str` map
    directly, `X | None` unwraps to `X`'s type, and anything else (e.g. `band_levels`' tuple of
    bands) falls back to `json.loads`, so a new analysis needs no hand-written CLI code."""
    if annotation is inspect.Parameter.empty:
        return str
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, _types.UnionType):
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _flag_type(args[0])
        return json.loads
    if annotation in (int, float, str):
        return annotation
    return json.loads


def _measure(
    path: Path,
    output: str | None,
    audio: Any,
    rate: int,
    category: str,
    name: str,
    fn: Any,
    params: dict[str, Any],
    accepts_out: bool,
    out_dir: Path | None,
) -> dict[str, Any]:
    call_kwargs = dict(params)
    if accepts_out:
        call_kwargs["out"] = None
        if out_dir is not None:
            identifier = output if output is not None else path.stem
            out_dir.mkdir(parents=True, exist_ok=True)
            call_kwargs["out"] = str(out_dir / f"{identifier}.{category}.{name}.npz")
    result = fn(audio, rate, **call_kwargs)
    header: dict[str, Any] = {"path": str(path)}
    if output is not None:
        header["output"] = output
    header["sample_rate"] = rate
    header["analysis"] = f"{category}.{name}"
    header["revision"] = fn.revision
    header["params"] = params
    header["result"] = result
    return _json_safe(header)


def _analyze_paths(
    paths: list[Path],
    category: str,
    name: str,
    fn: Any,
    params: dict[str, Any],
    accepts_out: bool,
    out_dir: Path | None,
) -> list[dict[str, Any]]:
    """Measure every path: a WAV file directly, or every output of a run/excerpt directory
    (read and verified by `read_published`). The chosen `tactus.analysis` function does the
    measuring."""
    results = []
    for path in paths:
        if path.is_dir():
            if not (path / "manifest.json").is_file():
                raise RunError("invalid_request", "request", f"no manifest.json in {path}")
            _, rate, outputs, files = read_published(path)
            for out_name in sorted(outputs):
                results.append(
                    _measure(
                        path / files[out_name],
                        out_name,
                        outputs[out_name],
                        rate,
                        category,
                        name,
                        fn,
                        params,
                        accepts_out,
                        out_dir,
                    )
                )
        elif path.is_file():
            try:
                audio, rate = sf.read(str(path), dtype="float64")
            except Exception as exc:
                raise RunError(
                    "invalid_request", "request", f"could not read {path}: {exc}"
                ) from exc
            results.append(
                _measure(path, None, audio, rate, category, name, fn, params, accepts_out, out_dir)
            )
        else:
            raise RunError("invalid_request", "request", f"path does not exist: {path}")
    return results


class _RunParser(argparse.ArgumentParser):
    """Keep run argument failures in the same JSON envelope as execution failures."""

    def error(self, message: str) -> None:
        raise RunError("invalid_request", "request", message)


def main(argv: Sequence[str] | None = None) -> int:
    """Execute a command; functional runs reserve stdout for one JSON result."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    package_version = version("tactus")
    parser_type = (
        _RunParser
        if arguments[:1] in (["run"], ["material"], ["excerpt"], ["init"], ["analyze"], ["take"])
        else argparse.ArgumentParser
    )
    parser = parser_type(
        prog="tactus",
        description="Experimental code-first music production framework.",
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
    analyze_command = commands.add_parser(
        "analyze",
        help="Measure audio (level, spectral, ...); see `tactus analyze CATEGORY --help`",
    )
    category_commands = analyze_command.add_subparsers(dest="category", required=True)
    for category_name, category_module in analysis.CATEGORIES.items():
        category_summary = (category_module.__doc__ or category_name).strip().splitlines()[0]
        category_parser = category_commands.add_parser(
            category_name,
            help=_help_text(category_summary),
            description=category_module.__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        name_commands = category_parser.add_subparsers(dest="name", required=True)
        for fn in category_module.ANALYSES:
            fn_summary = (fn.__doc__ or fn.__name__).strip().splitlines()[0]
            name_parser = name_commands.add_parser(
                fn.__name__,
                help=_help_text(fn_summary),
                description=fn.__doc__,
                formatter_class=argparse.RawDescriptionHelpFormatter,
            )
            name_parser.add_argument(
                "paths", nargs="+", type=Path, help="WAV file(s), or run/excerpt directory(-ies)"
            )
            param_names, accepts_out = _analysis_params(fn)
            if accepts_out:
                name_parser.add_argument(
                    "--out", type=Path, help="Directory to write large results (e.g. STFT .npz)"
                )
            sig = inspect.signature(fn)
            for param_name in param_names:
                param = sig.parameters[param_name]
                name_parser.add_argument(
                    "--" + param_name.replace("_", "-"),
                    dest=param_name,
                    type=_flag_type(param.annotation),
                    default=param.default,
                    help=_help_text(f"default: {param.default!r}"),
                )
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
        if args.command == "analyze":
            fn = next(
                f for f in analysis.CATEGORIES[args.category].ANALYSES if f.__name__ == args.name
            )
            param_names, accepts_out = _analysis_params(fn)
            params = {name: getattr(args, name) for name in param_names}
            out_dir = getattr(args, "out", None) if accepts_out else None
            for result in _analyze_paths(
                args.paths, args.category, args.name, fn, params, accepts_out, out_dir
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
                    "status": "ok",
                },
                sort_keys=True,
            )
        )
        return 0

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
