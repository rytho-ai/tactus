"""Inspect a Live device, then apply authored native values without rendering or saving."""

import argparse
import json
from pathlib import Path

from tactus.bridges.ableton_support import devices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bridge-path', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    read = commands.add_parser('inspect')
    read.add_argument('--track-id', required=True)
    read.add_argument('--device-id', required=True)
    read.add_argument('--parameters', type=json.loads, help='JSON list of names or native IDs')
    read.add_argument('--out', required=True, type=Path)
    apply = commands.add_parser('apply')
    apply.add_argument('snapshot', type=Path)
    apply.add_argument('values', type=Path, help='JSON object of chosen native parameter values')
    args = parser.parse_args()
    if args.command == 'inspect':
        if args.out.exists():
            parser.error(f'Output already exists: {args.out}')
        result = devices.inspect(bridge_path=args.bridge_path, track_id=args.track_id,
                                 device_id=args.device_id, parameters=args.parameters)
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    else:
        result = devices.configure(json.loads(args.snapshot.read_text()),
                                   json.loads(args.values.read_text()), bridge_path=args.bridge_path)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
