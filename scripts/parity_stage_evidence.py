# SPDX-License-Identifier: Apache-2.0
"""Verify done development stages against source-bound import evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

if __package__:
    from .benchmark_board_corpus import validate_entry
else:
    from benchmark_board_corpus import validate_entry


def _path(root: Path, name: object) -> Path:
    if not isinstance(name, str) or not name:
        raise ValueError('stage evidence requires a project path')
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('stage evidence file must exist inside project')
    return path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_done_import_stage(stage: dict, root: Path) -> None:
    receipt = json.loads(_path(root, stage.get('evidence')).read_text(encoding='utf-8'))
    if (receipt.get('contract') != 'spike/parity-stage-evidence/v1'
            or receipt.get('stage_id') != stage['id']):
        raise ValueError('stage receipt identity mismatch')
    manifest_path = _path(root, receipt.get('manifest'))
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    summary = receipt.get('summary')
    if (not isinstance(summary, dict) or summary.get('contract') != 'spike/board-corpus-benchmark/v1'
            or summary.get('status') != 'passed' or summary.get('production_qualified') is not False):
        raise ValueError('done stage requires a passed bounded import summary')
    if summary.get('manifest_sha256') != _digest(manifest_path):
        raise ValueError('stage manifest evidence is stale')
    sources = summary.get('runner_sources')
    required = {'scripts/benchmark_board_corpus.py', 'scripts/board_corpus_assertions.py',
                'python/spike_core/kicad_importer.py', 'python/core/board_parser.py',
                'python/spike_core/spider_v2.py', 'python/spike_core/arc_legacy_projection.py',
                'python/spike_core/board_outline_geometry.py', 'python/spike_core/mcad_export_design.py',
                'python/spike_core/assembly_thermal_meshing.py', 'python/spike_core/pcb_volume_compiler.py'}
    required.add('python/core/kicad_model_sources.py')
    required.update({'python/spike_core/mcad_component_models.py', 'scripts/parity_component_model_gate.py'})
    if not isinstance(sources, dict) or not required.issubset(sources):
        raise ValueError('stage runner source bindings are missing')
    for name, digest in sources.items():
        if digest != _digest(_path(root, name)):
            raise ValueError('stage runner evidence is stale')
    entries, rows = manifest.get('boards'), summary.get('boards')
    if not isinstance(entries, list) or not entries or not isinstance(rows, list) or len(rows) != len(entries):
        raise ValueError('stage fixture coverage differs from manifest')
    for entry, row in zip(entries, rows):
        fixture = validate_entry(entry, manifest_path.parent)
        if (not isinstance(row, dict) or row.get('passed') is not True or row.get('fixture') != entry['path']
                or row.get('import_status') not in ('completed', 'completed_with_warnings')
                or row.get('sha256') != _digest(fixture) or row.get('source_digest_checked') is not True
                or any(row.get(field) != [] for field in ('geometry_mismatches', 'errors'))
                or row.get('mismatches') != {}
                or row.get('entity_assertions_checked') != len(entry.get('expected_entities', []))
                or any(row.get('counts', {}).get(key) != value for key, value in entry.get('expected_counts', {}).items())):
            raise ValueError('done stage retains failed or incomplete fixture evidence')
    if stage['id'] == 'WF01-S04C1' and 'component_model_gate' not in receipt:
        raise ValueError('Explicit component-solid stage requires native mechanical evidence.')
    if 'component_model_gate' in receipt:
        if __package__:
            from .parity_component_model_gate import validate_receipt
        else:
            from parity_component_model_gate import validate_receipt
        validate_receipt(receipt['component_model_gate'], root)
        component_payload = json.loads(_path(root, receipt['component_model_gate']['import_file']).read_text(encoding='utf-8'))
        if len(entries) != 1 or component_payload.get('report', {}).get('source_sha256') != entries[0]['sha256']:
            raise ValueError('Component-solid gate source binding differs from import fixture.')
    if stage['id'] == 'WF01-S03' and 'geometry_gate' not in receipt:
        raise ValueError('Exact arc/cutout stage requires geometry consumer evidence.')
    if stage['id'] in ('WF01-S02', 'WF01-S03', 'WF01-S04A') and 'native_source_gate' not in receipt:
        raise ValueError('Pad fidelity stage requires native source geometry evidence.')
    if 'native_source_gate' in receipt or stage['id'] == 'WF01-S04B':
        export_mode = stage['id'] == 'WF01-S04B'
        gate = receipt.get('native_export_gate' if export_mode else 'native_source_gate', {})
        native_path = _path(root, gate.get('native_file'))
        imported_path = _path(root, gate.get('import_file'))
        source_path = _path(root, gate.get('source'))
        if (gate.get('native_sha256') != _digest(native_path)
                or gate.get('import_sha256') != _digest(imported_path)
                or gate.get('gate_runner_sha256') != _digest(_path(root, 'scripts/parity_native_geometry_gate.py'))):
            raise ValueError('Native source/export gate evidence is stale.')
        native = json.loads(native_path.read_text(encoding='utf-8'))
        payload = json.loads(imported_path.read_text(encoding='utf-8'))
        if len(entries) != 1 or payload['report']['source_sha256'] != entries[0]['sha256']:
            raise ValueError('Native gate CLI source differs from stage fixture.')
        if __package__:
            from .parity_native_geometry_gate import validate_native_facts, validate_kicad_source_geometry, validate_pad_cohort, validate_native_export_geometry
        else:
            from parity_native_geometry_gate import validate_native_facts, validate_kicad_source_geometry, validate_pad_cohort, validate_native_export_geometry
        validate_native_facts(native, source_path)
        validate_pad_cohort(native, source_path)
        if export_mode:
            validate_native_export_geometry(payload, native, validate_entry(entries[0], manifest_path.parent))
        else:
            validate_kicad_source_geometry(payload, native)
    if stage['id'] == 'WF01-S04A':
        gate = receipt.get('model_gate', {})
        native_path = _path(root, gate.get('native_file'))
        import_path = _path(root, gate.get('import_file'))
        runner = _path(root, 'scripts/parity_model_gate.py')
        if (gate.get('native_sha256') != _digest(native_path)
                or gate.get('import_sha256') != _digest(import_path)
                or gate.get('runner_sha256') != _digest(runner)):
            raise ValueError('Native model gate evidence is stale.')
        payload = json.loads(import_path.read_text(encoding='utf-8'))
        if len(entries) != 1 or payload.get('report', {}).get('source_sha256') != entries[0]['sha256']:
            raise ValueError('Model gate source binding differs from fixture.')
        if __package__:
            from .parity_model_gate import validate_model_gate
        else:
            from parity_model_gate import validate_model_gate
        validate_model_gate(payload, json.loads(native_path.read_text(encoding='utf-8')))
    if 'geometry_gate' in receipt:
        gate = receipt['geometry_gate']
        if not isinstance(gate, dict):
            raise ValueError('Geometry gate must be an object.')
        path = _path(root, gate.get('import_file'))
        if gate.get('import_sha256') != _digest(path):
            raise ValueError('Geometry gate import evidence is stale.')
        payload = json.loads(path.read_text(encoding='utf-8'))
        if len(entries) != 1 or payload.get('report', {}).get('source_sha256') != entries[0]['sha256']:
            raise ValueError('Geometry gate source binding differs from import fixture.')
        if __package__:
            from .parity_geometry_gate import validate_geometry_gate
        else:
            from parity_geometry_gate import validate_geometry_gate
        validate_geometry_gate(payload, gate.get('expected'))


def validate_stages(stages: object, capability_ids: list[str], root: Path) -> list[str]:
    if not isinstance(stages, list):
        raise ValueError('development stages must be a list')
    identifiers = []
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get('id'), str) or not stage['id']:
            raise ValueError('stage requires an ID')
        identifiers.append(stage['id'])
        if stage.get('capability_id') not in capability_ids or stage.get('status') not in ('planned', 'in_progress', 'done', 'blocked'):
            raise ValueError('invalid stage capability or status')
        if not isinstance(stage.get('title'), str) or not stage['title'].strip():
            raise ValueError('stage title is required')
        acceptance = stage.get('acceptance')
        if not isinstance(acceptance, list) or not acceptance or any(not isinstance(x, str) or not x.strip() for x in acceptance):
            raise ValueError('stage acceptance conditions are required')
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('stage IDs must be unique')
    by_id = {stage['id']: stage for stage in stages}
    done = []
    for stage in stages:
        dependencies = stage.get('depends_on', [])
        if (not isinstance(dependencies, list) or any(not isinstance(x, str) or x not in by_id or x == stage['id'] for x in dependencies)
                or len(set(dependencies)) != len(dependencies)):
            raise ValueError('stage dependencies must name unique other stages')
        if stage['status'] == 'done':
            if any(by_id[x]['status'] != 'done' for x in dependencies):
                raise ValueError('done stage has an unfinished dependency')
            validate_done_import_stage(stage, root)
            done.append(stage['id'])
    # Reject cycles even when the participating stages have not yet started.
    visited, active = set(), set()
    def visit(identifier: str) -> None:
        if identifier in active:
            raise ValueError('cyclic stage dependencies')
        if identifier in visited:
            return
        active.add(identifier)
        for dependency in by_id[identifier].get('depends_on', []):
            visit(dependency)
        active.remove(identifier)
        visited.add(identifier)
    for identifier in identifiers:
        visit(identifier)
    return done
