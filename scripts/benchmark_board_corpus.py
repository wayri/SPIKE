"""Run provenance-pinned board imports in bounded CLI subprocesses.

No downloading, archive extraction or third-party test-code execution. A corpus
entry is an input fixture, never an oracle for electrical or thermal accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
COLLECTIONS = ('layers', 'nets', 'tracks', 'arcs', 'zones', 'pads', 'vias', 'components')


def validate_entry(entry: dict, corpus: Path) -> Path:
    for field in ('path', 'sha256', 'source_url', 'license'):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            raise ValueError(f'missing {field}')
    path = (corpus / entry['path']).resolve()
    if not path.is_relative_to(corpus.resolve()) or path.suffix.lower() != '.kicad_pcb':
        raise ValueError('fixture must be a .kicad_pcb inside corpus root')
    if not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('fixture missing or exceeds 128 MiB input budget')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != entry['sha256'].lower():
        raise ValueError('fixture SHA-256 mismatch')
    expected = entry.get('expected_counts', {})
    if not isinstance(expected, dict) or any(k not in COLLECTIONS or type(v) is not int or v < 0 for k, v in expected.items()):
        raise ValueError('invalid expected_counts')
    return path


def inspect_import(payload: dict, expected: dict) -> dict:
    design = payload.get('design', {})
    report = payload.get('report', {})
    if design.get('contract') != 'spike/design-ir/v2':
        raise ValueError('missing typed DesignIR v2')
    counts = {key: len(design.get(key, [])) for key in COLLECTIONS}
    mismatches = {key: {'expected': value, 'actual': counts[key]}
                  for key, value in expected.items() if counts[key] != value}
    errors = [issue for issue in report.get('issues', []) if issue.get('severity') == 'error']
    return {'counts': counts, 'mismatches': mismatches, 'import_status': report.get('status'),
            'errors': errors, 'passed': not mismatches and not errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout-s', type=float, default=60)
    args = parser.parse_args()
    if not 1 <= args.timeout_s <= 300:
        parser.error('timeout must be between 1 and 300 seconds')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    entries = manifest.get('boards', [])
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        parser.error('manifest requires 1–100 explicit board entries')
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, entry in enumerate(entries):
        row = {'fixture': entry.get('path'), 'source_url': entry.get('source_url'),
               'license': entry.get('license'), 'sha256': entry.get('sha256')}
        started = time.monotonic()
        try:
            path = validate_entry(entry, args.corpus)
            result_path = (args.output / f'{index:03d}-import.json').resolve()
            # Preserve previous evidence; never mistake it for this run's output.
            if result_path.exists():
                raise ValueError('output exists; select a fresh evidence directory')
            command = [sys.executable, '-m', 'python.spike_core.cli', '--quiet',
                       '--output', str(result_path), 'import', str(path), '--report']
            run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=args.timeout_s)
            row.update(command=command, exit_code=run.returncode, stderr=run.stderr[-2000:])
            if run.returncode != 0:
                raise ValueError('import CLI returned nonzero exit code')
            row.update(inspect_import(json.loads(result_path.read_text(encoding='utf-8')), entry.get('expected_counts', {})))
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            row.update(passed=False, error=str(error))
        row['elapsed_s'] = round(time.monotonic() - started, 3)
        rows.append(row)
        print(json.dumps({k: row.get(k) for k in ('fixture', 'passed', 'elapsed_s', 'error')}), flush=True)
    passed = all(row['passed'] for row in rows)
    summary = {'contract': 'spike/board-corpus-benchmark/v1', 'status': 'passed' if passed else 'failed',
               'production_qualified': False, 'scope': 'CLI import and optional independently supplied counts only; no viewport or physics validation',
               'boards': rows}
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
