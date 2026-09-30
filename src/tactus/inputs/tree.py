"""tree — folder material identity: canonical manifest digest, import, and verified
materialization.

A folder material is identified by the SHA-256 of a canonical manifest: one
`<relative posix path>\\t<file sha256>\\n` line per regular file, sorted by path. `add`
stores each file as its own pool blob plus the manifest itself as a blob, keyed by its
own hash — which is the tree digest by construction, so no extra bookkeeping links a
digest to its manifest. `resolve` re-verifies every file against the manifest on each
call and materializes `<pool>/trees/<digest>/` by hardlinking each verified blob into
place (copying when hardlinks are not possible), built in a fresh directory and
atomically swapped in. Symlinks and other non-regular entries are rejected wherever a
folder is scanned, so a tree digest always describes plain file bytes reachable by a
relative path. `pool.py` stays bytes-only; this module is the one place that knows what
a folder material is.

Reads: tactus/inputs/pool.py
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from . import pool

PREFIX = "tree:sha256:"


class TreeError(Exception):
    """A tree resolution failure: `missing` or `corrupt`, mirroring `MaterialError`."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def digest_from_ref(ref: str) -> str:
    """Parse `tree:sha256:<hex>`, raising `ValueError` on any other shape."""
    if not isinstance(ref, str) or not ref.startswith(PREFIX):
        raise ValueError(f"tree ref must be 'tree:sha256:<64 lowercase hex>': {ref!r}")
    digest = ref[len(PREFIX) :]
    if not pool.DIGEST_RE.match(digest):
        raise ValueError(f"tree ref must be 'tree:sha256:<64 lowercase hex>': {ref!r}")
    return digest


# Version-control metadata is not material content: a fetch would change the digest
# without changing a single sample. The full-song dogfood's SFZ bass shipped a 139 MB `.git`.
_IGNORED_DIRS = frozenset({".git", ".hg", ".svn"})


def _scan(root: Path) -> list[tuple[str, Path]]:
    """List `(relative posix path, absolute path)` for every regular file under `root`.

    Skips version-control directories (`.git`, `.hg`, `.svn`). Rejects symlinks (files or directories) and other non-regular entries with a clear
    error, and rejects a root with no files at all so an empty tree is never hashed.
    """
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"tree source must be an existing directory: {root}")
    entries: list[tuple[str, Path]] = []
    for directory, subdirs, files in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        subdirs[:] = [name for name in subdirs if name not in _IGNORED_DIRS]
        for name in subdirs:
            if (directory_path / name).is_symlink():
                raise ValueError(
                    f"tree source contains a symlinked directory: {directory_path / name}"
                )
        for name in files:
            path = directory_path / name
            if path.is_symlink():
                raise ValueError(f"tree source contains a symlink: {path}")
            if not path.is_file():
                raise ValueError(f"tree source contains a non-regular file: {path}")
            relative = path.relative_to(root).as_posix()
            if not relative:
                raise ValueError(f"tree source contains an entry with an empty name: {path}")
            entries.append((relative, path))
    if not entries:
        raise ValueError(f"tree source has no regular files: {root}")
    return entries


def manifest_bytes(entries: list[tuple[str, str]]) -> bytes:
    """Canonical manifest: one sorted `<relpath>\\t<sha256>\\n` line per file, UTF-8."""
    return "".join(f"{relative}\t{digest}\n" for relative, digest in sorted(entries)).encode(
        "utf-8"
    )


def parse_manifest(data: bytes) -> list[tuple[str, str]]:
    """Parse manifest bytes back into `(relative path, file sha256)` pairs."""
    entries = []
    for line in data.decode("utf-8").splitlines():
        if not line:
            continue
        relative, _, digest = line.partition("\t")
        entries.append((relative, digest))
    return entries


def digest_of_tree(root: Path) -> tuple[str, list[tuple[str, str]]]:
    """Hash every file under `root` in place, without touching the pool.

    Returns `(tree digest, sorted manifest entries)`. Used by `tool()` on a folder,
    where nothing is stored.
    """
    entries = sorted((relative, pool.hash_file(path)) for relative, path in _scan(root))
    digest = hashlib.sha256(manifest_bytes(entries)).hexdigest()
    return digest, entries


def add(root: Path, *, pool_root: str | Path | None = None) -> str:
    """Import a folder into the pool: one blob per file, plus the manifest blob.

    Idempotent, like `pool.put`: identical bytes land once. Returns the
    `tree:sha256:...` ref.
    """
    entries = sorted((relative, pool.put(path, root=pool_root)) for relative, path in _scan(root))
    manifest = manifest_bytes(entries)
    with tempfile.NamedTemporaryFile(prefix="tactus-tree-manifest-", delete=False) as handle:
        handle.write(manifest)
        manifest_path = Path(handle.name)
    try:
        digest = pool.put(manifest_path, root=pool_root)
    finally:
        manifest_path.unlink(missing_ok=True)
    return f"{PREFIX}{digest}"


def _path_for(digest: str, pool_root: Path) -> Path | None:
    try:
        return pool.path_for(digest, root=pool_root)
    except ValueError as exc:
        raise TreeError("corrupt", str(exc)) from exc


class _TreeFiles:
    """Verified index with on-demand blob verification; no whole-folder health claim."""

    def __init__(self, entries: dict[str, str], pool_root: Path) -> None:
        self._entries = entries
        self._pool_root = pool_root

    def file(self, relative: str, expected: str | None = None) -> Path:
        digest = self._entries.get(relative)
        if digest is None:
            raise TreeError("missing", f"tree has no file {relative!r}")
        if expected is not None and digest != expected:
            raise TreeError("corrupt", f"tree/checkpoint hash mismatch: {relative}")
        path = _path_for(digest, self._pool_root)
        if path is None:
            raise TreeError("missing", f"tree file {relative!r} (blob {digest}) is not in the pool")
        if path.is_symlink():
            raise TreeError("corrupt", f"tree file blob must not be a symlink: {relative}")
        return path


def _read_files(digest: str) -> _TreeFiles:
    """Read a canonical safe index, leaving individual blobs to the caller's selection."""
    root = pool.default_pool_dir()
    path = _path_for(digest, root)
    if path is None:
        raise TreeError("missing", f"tree index {PREFIX}{digest} is not in the pool ({root})")
    try:
        if path.is_symlink():
            raise ValueError("tree index must not be a symlink")
        data = path.read_bytes()
        entries = parse_manifest(data)
        if not entries or manifest_bytes(entries) != data:
            raise ValueError("tree index must be nonempty and canonical")
        names: set[str] = set()
        for relative, file_digest in entries:
            if (
                relative.startswith("/")
                or "\\" in relative
                or any(part in {"", ".", ".."} for part in relative.split("/"))
                or relative in names
                or not pool.DIGEST_RE.fullmatch(file_digest)
            ):
                raise ValueError(f"invalid tree index entry: {relative!r}")
            names.add(relative)
        return _TreeFiles(dict(entries), root)
    except (ValueError, OSError) as exc:
        raise TreeError("corrupt", f"invalid tree index: {exc}") from exc


def _materialized_tree_matches(target: Path, entries: list[tuple[str, str]]) -> bool:
    """Whether `target` already holds exactly the files `entries` describes, correctly.

    Rehashes every file present (no shortcut on size or mtime), and treats a symlink,
    a non-regular entry, or a file outside the manifest as a mismatch, not a partial
    reuse.
    """
    if not target.is_dir():
        return False
    expected = dict(entries)
    seen: set[str] = set()
    for directory, subdirs, files in os.walk(target, followlinks=False):
        directory_path = Path(directory)
        for name in subdirs:
            if (directory_path / name).is_symlink():
                return False
        for name in files:
            path = directory_path / name
            if path.is_symlink() or not path.is_file():
                return False
            relative = path.relative_to(target).as_posix()
            if relative not in expected or pool.hash_file(path) != expected[relative]:
                return False
            seen.add(relative)
    return seen == set(expected)


def resolve(digest: str, *, pool_root: str | Path | None = None) -> Path:
    """Verify and materialize the tree for `digest`, returning `<pool>/trees/<digest>/`.

    Every call re-verifies every file's hash against the manifest, consistent with a
    file material's re-verified read. A materialized folder that already matches is
    reused as-is; anything else (absent, tampered, or holding extra files) is rebuilt
    from pool blobs into a fresh directory and atomically swapped into place. A missing
    manifest or file blob raises `TreeError("missing", ...)`; a hash mismatch raises
    `TreeError("corrupt", ...)`.
    """
    pool_root_path = Path(pool_root) if pool_root is not None else pool.default_pool_dir()
    ref = f"{PREFIX}{digest}"
    manifest_path = _path_for(digest, pool_root_path)
    if manifest_path is None:
        raise TreeError(
            "missing",
            f"tree material {ref} is not in the pool ({pool_root_path}); "
            f"import it first with: tactus material add <folder>",
        )
    try:
        entries = parse_manifest(manifest_path.read_bytes())
    except UnicodeDecodeError as exc:
        raise TreeError("corrupt", f"tree manifest for {ref} is unreadable: {exc}") from exc

    trees_root = pool_root_path / "trees"
    target = trees_root / digest
    if _materialized_tree_matches(target, entries):
        return target

    trees_root.mkdir(parents=True, exist_ok=True)
    build_path = Path(tempfile.mkdtemp(prefix=f"{digest}.building-", dir=trees_root))
    built = False
    try:
        for relative, file_digest in entries:
            blob = _path_for(file_digest, pool_root_path)
            if blob is None:
                raise TreeError(
                    "missing",
                    f"tree {ref} file {relative!r} (blob {file_digest}) is not in the pool "
                    f"({pool_root_path})",
                )
            destination = build_path / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(blob, destination)
            except OSError:
                shutil.copyfile(blob, destination)
        if target.exists():
            shutil.rmtree(target)
        os.rename(build_path, target)
        built = True
    finally:
        if not built:
            shutil.rmtree(build_path, ignore_errors=True)
    return target


__all__ = [
    "PREFIX",
    "TreeError",
    "add",
    "digest_from_ref",
    "digest_of_tree",
    "manifest_bytes",
    "parse_manifest",
    "resolve",
]
