# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Publish a three-level numerical mesh screen without relaxing its threshold."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.crossboard_field_screen import compare_mesh_cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',nargs='+',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    report=compare_mesh_cases(args.cases)
    report['cases']=[str(path.resolve()) for path in args.cases]
    report['input_sha256']={str(path.resolve()/name):hashlib.sha256((path/name).read_bytes()).hexdigest()
        for path in args.cases for name in ('execution.json','geometry.json','field-result.json')}
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(report,indent=2));return 0 if report['screen_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
