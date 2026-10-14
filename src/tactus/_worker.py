"""Private process entry for run.py; protocol files keep author logs off CLI stdout."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from ._contracts import RunError, write_json
from .run import _execute


def main() -> int:
    request, response = map(Path, sys.argv[1:])
    try:
        result = _execute(json.loads(request.read_text(encoding="utf-8")))
    except RunError as exc:
        if exc.code != "invalid_parameters":  # the work's or the binding's own message says it all
            traceback.print_exc(file=sys.stderr)
        write_json(response, exc.to_dict())
        return exc.exit_code
    write_json(response, result)
    return 0
