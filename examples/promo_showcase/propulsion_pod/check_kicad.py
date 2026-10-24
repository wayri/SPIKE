# SPDX-License-Identifier: Apache-2.0
"""Retain native checks on the unmodified legacy VESC source; do not repair it."""
from pathlib import Path
import hashlib, json, subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'output/promo-propulsion-pod-20261023'
REPORTS = OUT / 'kicad_checks'
BOARD = OUT / 'assembly/KiCad/BLDC_4/BLDC_4.kicad_pcb'
CLI = Path('C:/Program Files/KiCad/10.0/bin/kicad-cli.exe')

def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    original = BOARD.read_bytes()
    commands = [ ['version'], ['pcb', 'export', 'svg', '--layers', 'F.Cu,Edge.Cuts,F.Silkscreen',
        '--page-size-mode', '2', '--exclude-drawing-sheet', '--mode-single',
        '--output', str(REPORTS / 'board.svg'), str(BOARD)],
        ['pcb', 'drc', '--format', 'json', '--severity-all', '--output', str(REPORTS / 'source-drc.json'), str(BOARD)]]
    runs = []
    for arguments in commands:
        try:
            result = subprocess.run([str(CLI), *arguments], capture_output=True, text=True, timeout=120)
            runs.append({'arguments': arguments, 'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        except subprocess.TimeoutExpired:
            runs.append({'arguments': arguments, 'timed_out': True})
    assert BOARD.read_bytes() == original
    drc_path = REPORTS / 'source-drc.json'
    drc = json.loads(drc_path.read_text(encoding='utf-8')) if drc_path.exists() else {}
    summary = {'source_sha256': hashlib.sha256(original).hexdigest(), 'source_unchanged': True,
        'runs': runs, 'violations': len(drc.get('violations', [])),
        'unconnected_items': len(drc.get('unconnected_items', [])),
        'schematic_parity_findings': len(drc.get('schematic_parity', [])),
        'drc_report_present': bool(drc), 'ERC_executed': False,
        'scope': 'Unmodified legacy source imported by KiCad 10; original .pro retained, no converted rules or exclusions added. No clean-DRC or manufacturing qualification claim.'}
    (REPORTS / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: summary[key] for key in ('source_unchanged', 'violations', 'unconnected_items', 'drc_report_present')}))

if __name__ == '__main__':
    main()
