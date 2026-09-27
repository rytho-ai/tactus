"""Shared decorator for `tactus.analysis` category modules: attaches a `revision` int.

One owner for the "how is an analysis function marked with a revision" decision, so `level.py`
and `spectral.py` (and any category added later) don't each encode it separately.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., dict[str, Any]])


def revision(rev: int) -> Callable[[F], F]:
    """Attach a `revision` int to an analysis function, bumped only when a result's meaning
    changes (never for a pure refactor). Read by the CLI and the consistency test."""

    def wrap(fn: F) -> F:
        fn.revision = rev
        return fn

    return wrap
