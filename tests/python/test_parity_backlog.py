# SPDX-License-Identifier: Apache-2.0
"""Ensure development tracking cannot silently omit capabilities or claim completion."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
import tempfile

from scripts.check_parity_backlog import ROOT, validate_backlog
from scripts.parity_stage_evidence import validate_done_import_stage


class ParityBacklogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The archival owned-pad receipt references unbundled local board
        # artifacts. Exercise the real generators once in this checkout.
        temporary_root = ROOT / '.local' / 'test-temp'
        temporary_root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='owned-pad-backlog-', dir=temporary_root)
        cls.addClassCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        board = directory / 'board'
        cls.owned_receipt = directory / 'receipt.json'
        log = directory / 'tests.log'

        def execute(script, arguments, accepted, timeout):
            result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *arguments],
                                    cwd=ROOT, capture_output=True, text=True, timeout=timeout)
            if result.returncode not in accepted:
                raise AssertionError(result.stdout + result.stderr)

        # Exit 2 preserves the original diagnostic's failed convergence status;
        # the unchanged acceptance gate still requires completed CLI/four meshes.
        execute('check_ebrake_owned_dc.py', ['--output-dir', str(board)], (0, 2), 300)
        execute('parity_owned_pad_gate.py', ['--output', str(cls.owned_receipt),
                '--log', str(log), '--board-dir', str(board)], (0,), 180)
        validate_done_import_stage({'id': 'PI01-S01',
                                    'evidence': cls.owned_receipt.relative_to(ROOT).as_posix()}, ROOT)

    def setUp(self):
        self.payload = json.loads((ROOT / 'docs/parity-capability-backlog-v1.json').read_text())
        owned = [stage for stage in self.payload['stages'] if stage['id'] == 'PI01-S01']
        self.assertEqual(len(owned), 1)
        owned[0]['evidence'] = self.owned_receipt.relative_to(ROOT).as_posix()
        self.roadmap = (ROOT / 'docs/HYPERLYNX_PARITY_AND_MULTIPHYSICS_PLAN.md').read_text()

    def test_owned_pad_replay_preserves_scope_and_rejects_tampering(self):
        original = json.loads(self.owned_receipt.read_text())
        self.assertFalse(original['production_qualified'])
        archived = json.loads((ROOT / 'docs/parity-capability-backlog-v1.json').read_text())
        replay = copy.deepcopy(self.payload)
        next(stage for stage in replay['stages'] if stage['id'] == 'PI01-S01')['evidence'] = next(
            stage for stage in archived['stages'] if stage['id'] == 'PI01-S01')['evidence']
        self.assertEqual(replay, archived)
        path = self.owned_receipt.parent / 'rejected.json'
        stage = {'id': 'PI01-S01', 'evidence': path.relative_to(ROOT).as_posix()}
        for mutation in ('source', 'qualified', 'count', 'skipped', 'board_artifact'):
            receipt = copy.deepcopy(original)
            if mutation == 'source': receipt['sources_before']['scripts/parity_owned_pad_gate.py'] = '0' * 64
            if mutation == 'qualified': receipt['production_qualified'] = True
            if mutation == 'count': receipt['tests']['run'] -= 1
            if mutation == 'skipped': receipt['tests']['skipped'] = ['omitted']
            if mutation == 'board_artifact': receipt['board_artifacts']['report.json']['sha256'] = '0' * 64
            path.write_text(json.dumps(receipt), encoding='utf-8')
            with self.assertRaises(ValueError, msg=mutation):
                validate_done_import_stage(stage, ROOT)

    def test_current_coverage_and_pinned_fixture(self):
        result = validate_backlog(self.payload, self.roadmap)
        self.assertEqual(result['items'], 68)
        self.assertNotIn('WF01', result['benchmark_definitions_pending'])
        self.assertTrue({'RF01', 'RF02', 'PW01', 'PW02', 'PW03', 'PW04', 'PW05'}.issubset(
                            result['benchmark_definitions_pending']))
        self.assertTrue({'GP01', 'GP04', 'OP01', 'OP02', 'OP03', 'OP04', 'OP05',
                         'VF01', 'VF02', 'AX01', 'AX02', 'LB01', 'LB02'}.issubset(
                             result['benchmark_definitions_pending']))
        self.assertEqual(result['done_stages'], ['WF01-S01', 'WF01-S02', 'WF01-S03', 'WF01-S04A', 'WF01-S04B', 'WF01-S04C1', 'WF01-S04C2', 'WF01-S04C3', 'WF01-S04C4', 'WF01-S04C5', 'WF01-S04C6', 'SI08-S01', 'PI04-S01', 'PI04-S02', 'PI02-S01', 'PI02-S02', 'PI02-S03', 'PI02-S04', 'PI03-S01', 'PI03-S02', 'SI08-S02', 'SI08-S03', 'SI08-S04', 'SI07-S01', 'SI07-S02', 'GP07-S01', 'SI07-S03', 'SI07-S04', 'SI07-S05', 'SI07-S06', 'SI07-S07', 'SI07-S08', 'SI07-S09', 'SI07-S10', 'SI02-S01', 'SI02-S02', 'SI02-S03', 'SI02-S04', 'SI02-S05', 'SI02-S06', 'PI01-S01', 'SI01-S01', 'SI02-S07', 'SI02-S08', 'SI02-S09', 'SI02-S10', 'SI02-S11', 'SI02-S12', 'SI02-S13', 'PI01-S02A'])

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

    def test_post_parity_work_cannot_start_before_parity(self):
        for mutation in ('item', 'radio', 'hvdc', 'stage', 'phase', 'scope'):
            payload = copy.deepcopy(self.payload)
            if mutation == 'item':
                next(x for x in payload['items'] if x['id'] == 'OP02')['status'] = 'in_progress'
            elif mutation == 'radio':
                next(x for x in payload['items'] if x['id'] == 'RF01')['status'] = 'in_progress'
            elif mutation == 'hvdc':
                next(x for x in payload['items'] if x['id'] == 'PW01')['status'] = 'in_progress'
            elif mutation == 'stage':
                payload['stages'].append({'id': 'OP02-S99', 'capability_id': 'OP02', 'status': 'in_progress'})
            elif mutation == 'phase':
                payload['execution_policy']['active_phase'] = 'post_parity'
            else:
                payload['execution_policy']['parity_capabilities'].append('GP01')
            with self.assertRaisesRegex(ValueError, 'post.parity'):
                validate_backlog(payload, self.roadmap)

    def test_explicit_parallel_scope_preserves_other_deferrals(self):
        payload = copy.deepcopy(self.payload)
        next(x for x in payload['items'] if x['id'] == 'GP10')['status'] = 'in_progress'
        self.assertIn('GP10', validate_backlog(payload, self.roadmap)['parallel_expansion'])
        for mutation in ('disabled', 'smuggled', 'missing', 'duplicate'):
            other = copy.deepcopy(payload)
            if mutation == 'disabled': other['execution_policy']['parallel_expansion']['enabled'] = False
            if mutation == 'smuggled': other['execution_policy']['parallel_expansion']['capability_ids'].append('OP02')
            if mutation == 'missing': other['execution_policy'].pop('parallel_expansion')
            if mutation == 'duplicate': other['execution_policy']['parallel_expansion']['capability_ids'].append('GP10')
            with self.assertRaises(ValueError): validate_backlog(other, self.roadmap)

    def test_pi_si_priority_cannot_omit_a_family(self):
        payload=copy.deepcopy(self.payload)
        payload['execution_policy']['priority_capabilities'].remove('PI06')
        with self.assertRaisesRegex(ValueError, 'PI/SI priority'):
            validate_backlog(payload,self.roadmap)

    def test_requested_vehicle_and_mechanism_scope_is_tracked_without_false_completion(self):
        requested = {'GP12', 'GP13', 'GP14', 'GP15', 'GP16'}
        self.assertTrue(requested <= set(self.payload['execution_policy']['parallel_expansion']['capability_ids']))
        for item in self.payload['items']:
            if item['id'] in requested:
                self.assertEqual(item['status'], 'planned')
                self.assertTrue(item['open_gaps'])
        expected_stages = {'GP12-S01', 'GP12-S02', 'GP12-S03', 'GP13-S01', 'GP13-S02',
                           'GP14-S01', 'GP14-S02', 'GP14-S03', 'GP15-S01', 'GP15-S02',
                           'GP15-S03', 'GP15-S04', 'GP15-S05', 'GP16-S01', 'GP16-S02', 'GP16-S03'}
        by_id = {s['id']: s for s in self.payload['stages']}
        self.assertTrue(expected_stages <= set(by_id))
        self.assertTrue(all(by_id[name]['status'] == 'planned' for name in expected_stages))
        self.assertIn('GP15-S03', by_id['GP15-S05']['depends_on'])
        self.assertIn('GP13-S02', by_id['GP15-S05']['depends_on'])

    def test_vehicle_aerodynamics_permission_does_not_open_general_cfd(self):
        payload = copy.deepcopy(self.payload)
        stage = next(s for s in payload['stages'] if s['id'] == 'GP05-S01')
        stage['status'] = 'in_progress'
        result = validate_backlog(payload, self.roadmap)
        self.assertEqual(result['restricted_expansion_scopes'], {'GP05': 'vehicle_aerodynamics'})
        for mutation in ('stage', 'missing', 'expanded'):
            other = copy.deepcopy(payload)
            if mutation == 'stage': next(s for s in other['stages'] if s['id'] == 'GP05-S01')['scope'] = 'building_cfd'
            if mutation == 'missing': other['execution_policy']['parallel_expansion'].pop('restricted_scopes')
            if mutation == 'expanded': other['execution_policy']['parallel_expansion']['restricted_scopes']['GP05'] = 'all_cfd'
            with self.assertRaises(ValueError): validate_backlog(other, self.roadmap)

    def test_structural_done_rejects_failed_skipped_stale_or_overclaimed_receipt(self):
        stage = {'id': 'GP07-S01', 'evidence': 'docs/validation/parity/GP07-S01.json'}
        original = json.loads((ROOT/stage['evidence']).read_text(encoding='utf-8'))
        validate_done_import_stage(stage, ROOT)
        with tempfile.TemporaryDirectory(dir=ROOT/'build/parity-test-temp') as directory:
            path = Path(directory)/'receipt.json'
            stage['evidence'] = path.relative_to(ROOT).as_posix()
            for mutation in ('failed', 'skipped', 'stale', 'overclaimed', 'count', 'log'):
                receipt = copy.deepcopy(original)
                if mutation == 'failed': receipt['status'] = 'failed'
                if mutation == 'skipped': receipt['tests']['skipped'] = [receipt['tests']['names'][0]]
                if mutation == 'stale': receipt['sources']['python/spike_core/assembly_tetra_structural.py'] = '0'*64
                if mutation == 'overclaimed': receipt['production_qualified'] = True
                if mutation == 'count': receipt['tests']['run'] -= 1
                if mutation == 'log': receipt['log_sha256'] = '0'*64
                path.write_text(json.dumps(receipt), encoding='utf-8')
                with self.assertRaises(ValueError, msg=mutation): validate_done_import_stage(stage, ROOT)

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
            for mutation in ('failed', 'stale_manifest', 'manifest_drift', 'stale_runner',
                             'runner_drift', 'stale_import', 'partial_assertions', 'wrong_source'):
                receipt = copy.deepcopy(original)
                summary = receipt['summary']
                if mutation == 'failed':
                    summary['status'] = 'failed'
                elif mutation == 'stale_manifest':
                    summary['manifest_sha256'] = '0' * 64
                elif mutation == 'manifest_drift':
                    summary['manifest_sha256_after'] = '0' * 64
                elif mutation == 'stale_runner':
                    summary['runner_sources']['scripts/benchmark_board_corpus.py'] = '0' * 64
                    summary['runner_sources_after']['scripts/benchmark_board_corpus.py'] = '0' * 64
                elif mutation == 'runner_drift':
                    summary['runner_sources_after']['scripts/benchmark_board_corpus.py'] = '0' * 64
                elif mutation == 'stale_import':
                    receipt['import_evidence']['sha256'] = '0' * 64
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
