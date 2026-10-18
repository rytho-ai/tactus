"""Inspect track FX, then apply authored normalized values without rendering or saving."""

import argparse
import json
from pathlib import Path

from tactus.bridges.reaper_support import devices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resource-path', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    read = commands.add_parser('inspect')
    read.add_argument('--track-guid', required=True)
    read.add_argument('--fx-guid', required=True)
    read.add_argument('--parameters', type=json.loads, help='JSON list of zero-based indices')
    read.add_argument('--out', required=True, type=Path)
    apply = commands.add_parser('apply')
    apply.add_argument('snapshot', type=Path)
    apply.add_argument('values', type=Path, help='JSON object: index strings to normalized values')
    args = parser.parse_args()
    if args.command == 'inspect':
        if args.out.exists():
            parser.error(f'Output already exists: {args.out}')
        result = devices.inspect(resource_path=args.resource_path, track_guid=args.track_guid,
                                 fx_guid=args.fx_guid, parameters=args.parameters)
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    else:
        result = devices.configure(json.loads(args.snapshot.read_text()),
                                   json.loads(args.values.read_text()),
                                   resource_path=args.resource_path)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
