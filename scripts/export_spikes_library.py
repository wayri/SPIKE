"""Export data-only library and named shortcut profiles separately from binaries."""
from pathlib import Path
import argparse
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'standalone/spikes_project/studio/python'))
from spikes_studio.component_catalog import catalog
from spikes_studio.library_package import save,load
from spikes_studio.document import Keymap


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    symbols=json.loads((ROOT/'standalone/spikes_project/studio/library/core-symbols-v1.json').read_text(encoding='utf-8'))['symbols']
    path=args.output/'SPIKES-generic-library-v1.spklib';save(path,catalog()['records'],symbols);load(path)
    for name in ('SPIKES','KiCad-inspired','LTspice-inspired'):Keymap.preset(name).save(args.output/(name+'.spkkeys'))
    print(path)


if __name__=='__main__':main()
