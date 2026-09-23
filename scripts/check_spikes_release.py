"""Print release blockers; absent evidence always produces a failing exit code."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'standalone/spikes_project/studio/python'))
from spikes_studio.release_policy import evaluate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path)
    parser.add_argument('--candidate-sha256')
    args=parser.parse_args()
    evidence=json.loads(args.evidence.read_text(encoding='utf-8')) if args.evidence else {}
    report=evaluate(evidence,args.evidence.parent if args.evidence else ROOT,candidate_sha256=args.candidate_sha256)
    print(json.dumps(report,indent=2))
    return 0 if report['releasable'] else 1


if __name__=='__main__':raise SystemExit(main())
