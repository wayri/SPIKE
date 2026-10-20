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
    parser.add_argument('--engine', choices=('native', 'su2', 'su2-cht', 'native-cht',
                        'surface-exchange', 'enclosure-cht', 'enclosure-cht-v2'))
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--capabilities', action='store_true')
    args = parser.parse_args()
    if args.capabilities:
        response = handle_cfd_request('cfd_capabilities', {})
    else:
        if args.engine is None or args.request is None or args.output is None:
            parser.error('--engine, --request and --output are required for execution')
        request_limit = 8*1024**2 if args.engine in ('enclosure-cht', 'enclosure-cht-v2') else 65536
        if args.request.stat().st_size > request_limit:
            parser.error(f'request exceeds {request_limit} bytes')
        request = json.loads(args.request.read_text(encoding='utf-8'),
                             parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
        method = {'su2-cht': 'run_su2_cht', 'native-cht': 'run_native_cht',
                  'surface-exchange': 'run_coupled_surface_exchange',
                  'enclosure-cht': 'run_enclosure_cht',
                  'enclosure-cht-v2': 'run_enclosure_cht_v2'}.get(args.engine,
                        'run_' + args.engine + '_cfd')
        response = handle_cfd_request(method, {'request': request})
    encoded = json.dumps(response, indent=2, allow_nan=False)
    if args.engine in ('enclosure-cht', 'enclosure-cht-v2') and len(encoded.encode('utf-8')) > 8*1024**2:
        # The pretty-printed process envelope is larger than canonical domain
        # JSON. Enforce the wire budget too, without publishing partial fields.
        response = {'ok': True, 'result': {
            'contract': 'spike/enclosure-cht-result/v2' if args.engine == 'enclosure-cht-v2'
                        else 'spike/enclosure-cht-result/v1', 'status': 'blocked',
            'model_status': 'experimental', 'production_qualified': False,
            'issues': [{'code': 'ENCLOSURE_CHT_REJECTED',
                        'message': 'Enclosure process result exceeds 8 MiB'}]}}
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
    if response.get('result', {}).get('status') in ('failed', 'failed_to_converge', 'failed_validation', 'blocked', 'cancelled'):
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
