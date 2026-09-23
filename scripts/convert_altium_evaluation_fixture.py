# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Local KiCad API conversion for evaluation, not a losslessness assertion.

Run with KiCad's Python. Original files are never modified. Retain upstream
licenses beside derived files; converted files are not release/package input.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    import pcbnew
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.input.resolve()
    if source.stat().st_size > 32*1024**2:
        raise ValueError('Source exceeds 32 MiB fixture budget')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != args.sha256:
        raise ValueError('Source hash mismatch')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    print('Loading Altium fixture through KiCad', flush=True)
    board = pcbnew.LoadBoard(str(source), pcbnew.PCB_IO_MGR.ALTIUM_DESIGNER)
    if board is None:
        raise ValueError('KiCad did not load the Altium board')
    target = output/'board.kicad_pcb'
    if not pcbnew.SaveBoard(str(target), board):
        raise ValueError('KiCad did not save the converted board')
    footprints = list(board.GetFootprints())
    tracks = list(board.GetTracks())
    report = {'source': str(source), 'source_sha256': digest,
              'reader': pcbnew.GetBuildVersion(), 'format': 'ALTIUM_DESIGNER',
              'converted_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
              'counts': {'components': len(footprints),
                         'pads': sum(len(list(f.Pads())) for f in footprints),
                         'tracks': sum(t.GetClass() == 'PCB_TRACK' for t in tracks),
                         'vias': sum(t.GetClass() == 'PCB_VIA' for t in tracks),
                         'zones': len(list(board.Zones())),
                         'copper_layers': board.GetCopperLayerCount()},
              'conversion_losslessness_verified': False, 'solver_qualified': False,
              'redistribution_reviewed': False}
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise ValueError('Source changed during conversion')
    (output/'conversion.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    if '--worker' in sys.argv:
        sys.argv.remove('--worker')
        main()
    else:
        # KiCad import plugins are native code; never allow an unattended hang.
        try:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                                     '--worker', *sys.argv[1:]], timeout=90,
                                    capture_output=True, text=True)
            print(result.stdout, end='')
            print(result.stderr, end='', file=sys.stderr)
            raise SystemExit(result.returncode)
        except subprocess.TimeoutExpired:
            print(json.dumps({'status': 'conversion_timeout',
                              'solver_qualified': False}), file=sys.stderr)
            raise SystemExit(2)
