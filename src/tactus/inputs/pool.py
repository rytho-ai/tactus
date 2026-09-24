"""pool — machine-local, content-addressed byte store for resolved input materials.

One pool per machine, shared across every Tactus source tree: `$TACTUS_POOL`, or
`$XDG_DATA_HOME/tactus/pool` (default `~/.local/share/tactus/pool`), with two-level
fan-out `<digest[:2]>/<digest>` so tens of thousands of entries never sit flat in one
directory. The pool only stores bytes; it has no notion of what kind of material an
entry is. Adapted near-verbatim from `tactus-daw`'s `assets/pool.py`, without that
package's kernel imports: hashing here uses `hashlib.file_digest` directly, and the
default root is derived inline rather than through a shared `platform` module. The
on-disk layout stays byte-compatible with the tactus-daw pool, so identical bytes are
shared and moving a work directory needs no re-import. `put` is idempotent: identical
bytes land once, staged through a `.incoming` file and atomically renamed into place, so
a crash mid-write never leaves a partial file on the real path. Reads (`path_for`) always
re-verify the hash; a mismatch is corruption, not a fallback case.

Reads: (stdlib only)
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path

# Hex form of a sha256 digest. Also the path-safety gate: since the digest becomes a
# path segment, this regex keeps things like `../` from ever being accepted.
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def default_pool_dir() -> Path:
    """`$TACTUS_POOL`, else `$XDG_DATA_HOME/tactus/pool`, else `~/.local/share/tactus/pool`."""
    override = os.environ.get("TACTUS_POOL")
    if override:
        return Path(override).expanduser()
    data_home = os.environ.get("XDG_DATA_HOME")
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "tactus" / "pool"


def hash_file(path: Path) -> str:
    """SHA-256 hex digest of a file's bytes; the identity used for pool entries and tools."""
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _entry_path(root: Path, digest: str) -> Path:
    """`<root>/<digest[:2]>/<digest>` — digest must be a valid sha256 hex string."""
    if not DIGEST_RE.match(digest):
        raise ValueError(f"not a sha256 hex digest: {digest!r}")
    return root / digest[:2] / digest


def has(digest: str, *, root: str | Path | None = None) -> bool:
    """Whether this digest's bytes are in the pool (existence only, no re-hash)."""
    pool_root = Path(root) if root is not None else default_pool_dir()
    return _entry_path(pool_root, digest).is_file()


def path_for(digest: str, *, root: str | Path | None = None) -> Path | None:
    """Return this digest's file path, or `None` if it is not in the pool.

    If present, re-hashes and compares: a mismatch raises (tamper or bit rot is not a
    fallback case). Absent and corrupt are different outcomes: absent returns `None`
    and lets the caller decide whether that is an error; corrupt always raises.
    """
    pool_root = Path(root) if root is not None else default_pool_dir()
    path = _entry_path(pool_root, digest)
    if not path.is_file():
        return None
    actual = hash_file(path)
    if actual != digest:
        raise ValueError(f"pool entry is corrupt: {path} hashes to {actual}, expected {digest}")
    return path


def put(source: str | Path, *, root: str | Path | None = None) -> str:
    """Copy a file's bytes into the pool, returning its sha256.

    Idempotent: identical bytes arriving a second time just return the digest without
    rewriting anything, a direct consequence of content addressing. Landing goes through
    a staging file and a rename, so a crash mid-copy never leaves a partial file on the
    real path.
    """
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"pool source does not exist: {source_path}")
    pool_root = Path(root) if root is not None else default_pool_dir()
    digest = hash_file(source_path)
    target = _entry_path(pool_root, digest)
    if target.is_file():
        return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f"{digest}.incoming")
    shutil.copyfile(source_path, staging)
    staging.replace(target)
    return digest


__all__ = ["default_pool_dir", "has", "path_for", "put"]
