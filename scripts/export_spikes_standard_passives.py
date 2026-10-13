# SPDX-License-Identifier: Apache-2.0
"""Export original configurable preferred-value passives as a data-only library."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='New .spklib file; refuses replacement')
    args=parser.parse_args()
    if args.output.exists():parser.error('Output exists; choose a new path to preserve it')
    from spikes_studio.passive_catalog import records
    from spikes_studio.library_package import save
    rows=records();save(args.output,rows,[])
    print(f'Exported {len(rows)} configurable templates to {args.output}; no manufacturer qualification or vendor models.')
    return 0


if __name__=='__main__':raise SystemExit(main())
