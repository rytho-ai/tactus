"""Private process entry for run.py; protocol files keep author logs off CLI stdout."""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from .run import RunError, _execute, _write_json


def main() -> int:
    request, response = map(Path, sys.argv[1:])
    try:
        result = _execute(json.loads(request.read_text(encoding="utf-8")))
    except RunError as exc:
        traceback.print_exc(file=sys.stderr)
        _write_json(response, exc.to_dict())
        return exc.exit_code
    _write_json(response, result)
    return 0
