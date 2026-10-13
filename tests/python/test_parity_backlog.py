# SPDX-License-Identifier: Apache-2.0
"""Ensure development tracking cannot silently omit capabilities or claim completion."""
import copy
import json
from pathlib import Path
import unittest
import tempfile

from scripts.check_parity_backlog import ROOT, validate_backlog
from scripts.parity_stage_evidence import validate_done_import_stage


class ParityBacklogTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads((ROOT / 'docs/parity-capability-backlog-v1.json').read_text())
        self.roadmap = (ROOT / 'docs/HYPERLYNX_PARITY_AND_MULTIPHYSICS_PLAN.md').read_text()

    def test_current_coverage_and_pinned_fixture(self):
        result = validate_backlog(self.payload, self.roadmap)
        self.assertEqual(result['items'], 34)
        self.assertNotIn('WF01', result['benchmark_definitions_pending'])
        self.assertEqual(result['done_stages'], ['WF01-S01', 'WF01-S02', 'WF01-S03', 'WF01-S04A', 'WF01-S04B', 'WF01-S04C1'])

    def test_duplicate_missing_and_unknown_capabilities_fail(self):
        for mutation in ('duplicate', 'missing', 'unknown'):
            payload = copy.deepcopy(self.payload)
            if mutation == 'duplicate':
                payload['items'].append(payload['items'][0])
            elif mutation == 'missing':
                payload['items'].pop()
            else:
                payload['items'][0]['id'] = 'SI99'
            with self.assertRaisesRegex(ValueError, 'match roadmap'):
                validate_backlog(payload, self.roadmap)

    def test_completion_requires_closed_gaps_and_benchmark(self):
        payload = copy.deepcopy(self.payload)
        payload['items'][0]['status'] = 'complete'
        with self.assertRaisesRegex(ValueError, 'open gaps'):
            validate_backlog(payload, self.roadmap)
        payload['items'][0]['open_gaps'] = []
        with self.assertRaisesRegex(ValueError, 'benchmark definition'):
            validate_backlog(payload, self.roadmap)

    def test_missing_evidence_and_uncontained_fixture_fail(self):
        payload = copy.deepcopy(self.payload)
        payload['items'][0]['baseline_evidence'] = ['missing-document.md']
        with self.assertRaisesRegex(ValueError, 'evidence'):
            validate_backlog(payload, self.roadmap)
        payload = copy.deepcopy(self.payload)
        next(x for x in payload['items'] if x['id'] == 'WF01')['benchmark']['manifest'] = '../outside.json'
        with self.assertRaisesRegex(ValueError, 'inside project'):
            validate_backlog(payload, self.roadmap)

    def test_done_stage_requires_finished_dependencies_and_evidence(self):
        payload = copy.deepcopy(self.payload)
        payload['stages'][0]['depends_on'] = ['WF01-S04']
        with self.assertRaisesRegex(ValueError, 'unfinished dependency'):
            validate_backlog(payload, self.roadmap)
        payload = copy.deepcopy(self.payload)
        payload['stages'][0]['evidence'] = None
        with self.assertRaisesRegex(ValueError, 'project path'):
            validate_backlog(payload, self.roadmap)

    def test_stage_cycles_and_duplicate_ids_are_rejected(self):
        payload = copy.deepcopy(self.payload)
        for stage in payload['stages']:
            stage['status'] = 'planned'
        payload['stages'][0]['depends_on'] = ['WF01-S02']
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            validate_backlog(payload, self.roadmap)
        payload['stages'][0]['depends_on'] = []
        payload['stages'].append(payload['stages'][0])
        with self.assertRaisesRegex(ValueError, 'unique'):
            validate_backlog(payload, self.roadmap)

    def test_failed_stale_or_incomplete_receipts_cannot_mark_stage_done(self):
        stage = copy.deepcopy(self.payload['stages'][0])
        original = json.loads((ROOT / stage['evidence']).read_text())
        with tempfile.TemporaryDirectory(dir=ROOT / 'build/parity-test-temp') as directory:
            path = Path(directory) / 'receipt.json'
            stage['evidence'] = path.relative_to(ROOT).as_posix()
            for mutation in ('failed', 'stale_manifest', 'stale_runner', 'partial_assertions', 'wrong_source'):
                receipt = copy.deepcopy(original)
                summary = receipt['summary']
                if mutation == 'failed':
                    summary['status'] = 'failed'
                elif mutation == 'stale_manifest':
                    summary['manifest_sha256'] = '0' * 64
                elif mutation == 'stale_runner':
                    summary['runner_sources']['scripts/benchmark_board_corpus.py'] = '0' * 64
                elif mutation == 'partial_assertions':
                    summary['boards'][0]['entity_assertions_checked'] = 0
                else:
                    summary['boards'][0]['sha256'] = '0' * 64
                path.write_text(json.dumps(receipt))
                with self.assertRaises(ValueError, msg=mutation):
                    validate_done_import_stage(stage, ROOT)

    def test_exact_arc_stage_recomputes_cutout_geometry_instead_of_trusting_a_pass_flag(self):
        stage = copy.deepcopy(next(s for s in self.payload['stages'] if s['id'] == 'WF01-S03'))
        original = json.loads((ROOT / stage['evidence']).read_text())
        validate_done_import_stage(stage, ROOT)
        with tempfile.TemporaryDirectory(dir=ROOT / 'build/parity-test-temp') as directory:
            path = Path(directory) / 'receipt.json'
            stage['evidence'] = path.relative_to(ROOT).as_posix()
            receipt = copy.deepcopy(original)
            receipt['geometry_gate']['expected']['board_area_mm2'] = 600.
            path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'Geometry gate mismatch'):
                validate_done_import_stage(stage, ROOT)
            receipt = copy.deepcopy(original)
            del receipt['geometry_gate']
            path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, 'requires geometry consumer'):
                validate_done_import_stage(stage, ROOT)
