"""Reproducible original preset catalog generation; no vendor content download."""
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'standalone/spikes_project/studio/python'))
from spikes_studio.component_catalog import materialize

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'standalone/spikes_project/studio/library/generic-components-v1.json')
    args=parser.parse_args();payload=materialize(args.output)
    print(payload['notice']);print(payload['counts']);print(args.output)

if __name__=='__main__':main()
