#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproducible CFD worker CLI; runtime paths use trusted host configuration."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.service_cfd import handle_cfd_request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('native', 'su2', 'su2-cht'))
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--capabilities', action='store_true')
    args = parser.parse_args()
    if args.capabilities:
        response = handle_cfd_request('cfd_capabilities', {})
    else:
        if args.engine is None or args.request is None or args.output is None:
            parser.error('--engine, --request and --output are required for execution')
        if args.request.stat().st_size > 65536:
            parser.error('request exceeds 64 KiB')
        request = json.loads(args.request.read_text(encoding='utf-8'),
                             parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
        method = 'run_su2_cht' if args.engine == 'su2-cht' else 'run_' + args.engine + '_cfd'
        response = handle_cfd_request(method, {'request': request})
    encoded = json.dumps(response, indent=2, allow_nan=False)
    if args.output:
        destination = args.output.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replacement keeps a prior result intact on interrupted writes.
        fd, temporary = tempfile.mkstemp(prefix=destination.name + '.', dir=destination.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    else:
        print(encoded)
    if not response.get('ok'):
        return 2
    if response.get('result', {}).get('status') in ('failed', 'failed_to_converge', 'failed_validation'):
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
