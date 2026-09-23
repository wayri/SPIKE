# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Run the installed, hash-pinned development OCC meshing process."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.gmsh_occ_runtime import run_occ_case, MAX_REQUEST, _unique


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    path = Path(args.request)
    if not path.is_file() or path.stat().st_size > MAX_REQUEST:
        parser.error('request missing or exceeds 8 MiB')
    request = json.loads(path.read_bytes(), object_pairs_hook=_unique)
    result = run_occ_case(request, args.output)
    print(json.dumps({'status': result['status'], 'counts': result['mesh']['counts'],
        'interface_triangles': len(result['interface_faces']), 'metrics': result['metrics'],
        'production_qualified': False}, allow_nan=False))


if __name__ == '__main__':
    main()
