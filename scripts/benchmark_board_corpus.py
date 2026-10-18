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

if __package__:
    from .board_corpus_assertions import COLLECTIONS, inspect_geometry, validate_assertions
else:
    from board_corpus_assertions import COLLECTIONS, inspect_geometry, validate_assertions

ROOT = Path(__file__).resolve().parents[1]
RUNNER_SOURCE_PATHS = (
    'scripts/benchmark_board_corpus.py',
    'scripts/board_corpus_assertions.py',
    'python/spike_core/contracts.py',
    'python/spike_core/importers.py',
    'python/spike_core/source_package.py',
    'python/spike_core/spider_v2.py',
    'python/spike_core/kicad_importer.py',
    'python/core/board_parser.py',
    'python/core/filled_polygon_offset.py',
    'python/core/simple_polygon_union.py',
    'python/core/kicad_model_sources.py',
    'python/spike_core/odb_importer.py',
    'python/spike_core/odb_features.py',
    'python/spike_core/odb_stackup.py',
    'python/spike_core/odb_source_inspection.py',
    'schemas/board-enrichment-v1.schema.json',
    'extensions/odb-import/extension.py',
    'python/spike_core/arc_legacy_projection.py',
    'python/spike_core/board_outline_geometry.py',
    'python/spike_core/mcad_export_design.py',
    'python/spike_core/mcad_export_contract.py',
    'python/spike_core/assembly_frames.py',
    'schemas/mcad-assembly-v1.schema.json',
    'python/spike_core/assembly_thermal_meshing.py',
    'python/spike_core/pcb_volume_compiler.py',
    'python/spike_core/geometry_arrow.py',
    'python/spike_core/spikes_layout_geometry_handoff.py',
    'scripts/parity_geometry_gate.py',
    'scripts/capture_parity_native_geometry.py',
    'scripts/parity_native_geometry_gate.py',
    'app/src/boardParser.ts',
    'app/src/normalizedBoard.ts',
    'python/spike_core/mcad_component_models.py',
    'scripts/parity_component_model_gate.py',
)


def source_snapshot(root: Path = ROOT) -> dict[str, str]:
    """Hash the complete bounded import/gate source set in stable path order."""

    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in RUNNER_SOURCE_PATHS}


def validate_source_snapshots(summary: dict, root: Path = ROOT) -> None:
    """Reject incomplete, mixed-revision, or stale importer evidence."""

    before = summary.get('runner_sources')
    after = summary.get('runner_sources_after')
    required = set(RUNNER_SOURCE_PATHS)
    if (not isinstance(before, dict) or not isinstance(after, dict)
            or set(before) != required or set(after) != required):
        raise ValueError('stage runner source coverage differs')
    if before != after:
        raise ValueError('stage runner sources changed during import')
    if before != source_snapshot(root):
        raise ValueError('stage runner evidence is stale')


def _write_json_new(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(payload, stream, indent=2)
        stream.write('\n')


def _write_receipt(args: argparse.Namespace, summary: dict, imported: Path) -> None:
    requested = (args.stage_id, args.receipt_template, args.receipt_output, args.receipt_import_output)
    if not any(requested):
        return
    if not all(requested):
        raise ValueError('receipt generation requires stage, template, receipt, and retained import paths')
    template = args.receipt_template.resolve()
    receipt_path = args.receipt_output.resolve()
    import_path = args.receipt_import_output.resolve()
    for path in (template, receipt_path, import_path):
        if not path.is_relative_to(ROOT):
            raise ValueError('receipt paths must stay inside the project')
    if receipt_path.exists() or import_path.exists():
        raise ValueError('receipt outputs must be new paths')
    receipt = json.loads(template.read_text(encoding='utf-8'))
    if receipt.get('stage_id') != args.stage_id:
        raise ValueError('receipt template stage differs')
    receipt['contract'] = 'spike/parity-stage-evidence/v2'
    receipt['manifest'] = args.manifest.resolve().relative_to(ROOT).as_posix()
    receipt['summary'] = summary
    import_relative = import_path.relative_to(ROOT).as_posix()
    import_bytes = imported.read_bytes()
    import_digest = hashlib.sha256(import_bytes).hexdigest()
    receipt['import_evidence'] = {'file': import_relative, 'sha256': import_digest}
    for name in ('geometry_gate', 'native_source_gate', 'native_export_gate',
                 'model_gate', 'component_model_gate'):
        gate = receipt.get(name)
        if isinstance(gate, dict) and 'import_file' in gate:
            gate['import_file'] = import_relative
            gate['import_sha256'] = import_digest
    import_path.parent.mkdir(parents=True, exist_ok=True)
    with import_path.open('xb') as stream:
        stream.write(import_bytes)
    _write_json_new(receipt_path, receipt)


def validate_entry(entry: dict, corpus: Path) -> Path:
    for field in ('path', 'sha256', 'source_url', 'license'):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            raise ValueError(f'missing {field}')
    path = (corpus / entry['path']).resolve()
    format_id = entry.get('format', 'kicad')
    suffixes = {'kicad': {'.kicad_pcb'}, 'odb++': {'.zip', '.tgz', '.tar', '.gz'}}
    if (not path.is_relative_to(corpus.resolve()) or not isinstance(format_id, str) or format_id not in suffixes
            or path.suffix.lower() not in suffixes[format_id]):
        raise ValueError('fixture must have an admitted format/suffix inside corpus root')
    if not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError('fixture missing or exceeds 128 MiB input budget')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != entry['sha256'].lower():
        raise ValueError('fixture SHA-256 mismatch')
    expected = entry.get('expected_counts', {})
    if not isinstance(expected, dict) or any(k not in COLLECTIONS or type(v) is not int or v < 0 for k, v in expected.items()):
        raise ValueError('invalid expected_counts')
    validate_assertions(entry.get('expected_entities', []))
    return path


def inspect_import(payload: dict, expected: dict, assertions: list[dict] | None = None,
                   expected_sha256: str | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError('import payload must be an object')
    design = payload.get('design', {})
    report = payload.get('report', {})
    if not isinstance(design, dict) or not isinstance(report, dict):
        raise ValueError('import payload requires design and report objects')
    if design.get('contract') != 'spike/design-ir/v2':
        raise ValueError('missing typed SpiDeR v2')
    geometry = inspect_geometry(design, report, [] if assertions is None else assertions, expected_sha256)
    counts = {key: len(design.get(key, [])) for key in COLLECTIONS}
    mismatches = {key: {'expected': value, 'actual': counts[key]}
                  for key, value in expected.items() if counts[key] != value}
    errors = []
    source_issues = design.get('issues', [])
    if not isinstance(source_issues, list) or any(not isinstance(item, dict) for item in source_issues):
        raise ValueError('design.issues must contain diagnostic objects')
    errors.extend(item for item in source_issues if str(item.get('severity', '')).lower() == 'error')
    for field in ('issues', 'diagnostics', 'unsupported', 'geometry_errors'):
        rows = report.get(field, [])
        if not isinstance(rows, list) or any(not isinstance(item, dict) for item in rows):
            raise ValueError(f'report.{field} must contain diagnostic objects')
        errors.extend(item for item in rows if field in ('unsupported', 'geometry_errors')
                      or str(item.get('severity', '')).lower() == 'error')
    completed = report.get('status') in ('completed', 'completed_with_warnings')
    return {'counts': counts, 'mismatches': mismatches, 'import_status': report.get('status'),
            'errors': errors, 'diagnostics': report.get('diagnostics', []), 'source_issues': source_issues,
            'inferred': report.get('inferred', []), 'solver_readiness': report.get('solver_readiness', {}),
            **geometry, 'passed': completed and not mismatches and not errors and not geometry['geometry_mismatches']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout-s', type=float, default=60)
    parser.add_argument('--stage-id')
    parser.add_argument('--receipt-template', type=Path)
    parser.add_argument('--receipt-output', type=Path)
    parser.add_argument('--receipt-import-output', type=Path)
    args = parser.parse_args()
    if not 1 <= args.timeout_s <= 300:
        parser.error('timeout must be between 1 and 300 seconds')
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes.decode('utf-8-sig'))
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    provenance = source_snapshot()
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
            if entry.get('format'):
                command.extend(['--format', entry['format']])
            run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=args.timeout_s)
            row.update(command=command, exit_code=run.returncode, stderr=run.stderr[-2000:])
            if run.returncode != 0:
                raise ValueError('import CLI returned nonzero exit code')
            row.update(inspect_import(json.loads(result_path.read_text(encoding='utf-8')),
                                      entry.get('expected_counts', {}), entry.get('expected_entities', []), entry['sha256'].lower()))
            after_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            row['source_sha256_after'] = after_digest
            if after_digest != entry['sha256'].lower():
                raise ValueError('fixture changed while it was being imported')
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            row.update(passed=False, error=str(error))
        row['elapsed_s'] = round(time.monotonic() - started, 3)
        rows.append(row)
        print(json.dumps({k: row.get(k) for k in ('fixture', 'passed', 'elapsed_s', 'error')}), flush=True)
    provenance_after = source_snapshot()
    manifest_digest_after = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    stable = provenance == provenance_after and manifest_digest == manifest_digest_after
    passed = all(row['passed'] for row in rows) and stable
    summary = {'contract': 'spike/board-corpus-benchmark/v2', 'status': 'passed' if passed else 'failed',
               'runner_sources': provenance, 'runner_sources_after': provenance_after,
               'source_snapshot_stable': stable, 'python_version': sys.version,
               'manifest_sha256': manifest_digest, 'manifest_sha256_after': manifest_digest_after,
               'production_qualified': False, 'scope': 'CLI import status, canonical units/identity, pinned source and optional independent counts/entity values; no viewport or physics validation',
               'boards': rows}
    _write_json_new(args.output / 'summary.json', summary)
    if passed and rows:
        try:
            _write_receipt(args, summary, args.output / '000-import.json')
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f'Receipt generation failed: {error}', file=sys.stderr)
            return 2
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
