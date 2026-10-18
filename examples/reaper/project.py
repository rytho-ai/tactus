"""CLI for shared native capture/rebuild; adopt returned refs in authored source."""

import argparse
import json
from pathlib import Path

from tactus.bridges.reaper_support.project import capture, inspect, render_project

__all__ = ['capture', 'inspect', 'render_project']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resource-path', required=True)
    parser.add_argument('command', choices=('inspect', 'capture'))
    parser.add_argument('--out', type=Path)
    opts = parser.parse_args()
    if opts.command == 'capture' and opts.out is None:
        parser.error('capture needs --out NEW_DIRECTORY')
    result = (inspect(resource_path=opts.resource_path) if opts.command == 'inspect'
              else capture(resource_path=opts.resource_path, out=opts.out))
    print(json.dumps(result, indent=2))
