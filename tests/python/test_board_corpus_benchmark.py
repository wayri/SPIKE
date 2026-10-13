import hashlib
import copy
from pathlib import Path
import tempfile
import unittest

from scripts.benchmark_board_corpus import inspect_import, validate_entry


class CorpusBenchmarkTests(unittest.TestCase):
    def payload(self):
        return {'design': {'contract': 'spike/design-ir/v2',
                           'frame': {'units': 'mm', 'handedness': 'right'},
                           'layers': [{'id': 'front'}, {'id': 'back'}],
                           'tracks': [{'id': 'track', 'source_id': 'source-track',
                                       'start_mm': [2.5, -3.0], 'width_mm': 0.25}]},
                'report': {'status': 'completed', 'issues': []}}

    def test_pinned_input_and_provenance_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            board = root / 'board.kicad_pcb'
            board.write_bytes(b'(kicad_pcb)')
            entry = {'path': board.name, 'sha256': hashlib.sha256(board.read_bytes()).hexdigest(),
                     'source_url': 'https://example.test/fixture', 'license': 'test-only'}
            self.assertEqual(validate_entry(entry, root), board)
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                validate_entry({**entry, 'sha256': '0' * 64}, root)
            with self.assertRaisesRegex(ValueError, 'license'):
                validate_entry({**entry, 'license': ''}, root)
            with self.assertRaisesRegex(ValueError, 'inside corpus'):
                validate_entry({**entry, 'path': '../outside.kicad_pcb'}, root)

    def test_count_mismatch_and_import_error_fail(self):
        payload = self.payload()
        self.assertTrue(inspect_import(payload, {'layers': 2})['passed'])
        self.assertFalse(inspect_import(payload, {'layers': 4})['passed'])
        payload['report']['issues'] = [{'severity': 'error', 'message': 'lost geometry'}]
        self.assertFalse(inspect_import(payload, {})['passed'])
        with self.assertRaisesRegex(ValueError, 'typed SpiDeR'):
            inspect_import({}, {})

    def test_archive_requires_explicit_admitted_format_and_pinned_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'board.zip'
            archive.write_bytes(b'not a real package; validation checks bytes, adapter checks content')
            entry = {'path': archive.name, 'format': 'odb++',
                     'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                     'source_url': 'repository:original-test', 'license': 'Apache-2.0'}
            self.assertEqual(validate_entry(entry, root), archive)
            for changed in ({**entry, 'format': 'unknown'}, {**entry, 'format': 'kicad'}):
                with self.assertRaisesRegex(ValueError, 'format/suffix'):
                    validate_entry(changed, root)
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                validate_entry({**entry, 'sha256': '0' * 64}, root)

    def test_failed_or_incomplete_report_cannot_pass_counts(self):
        for status in ('failed', 'completed_with_errors', 'running', None):
            payload = self.payload()
            payload['report']['status'] = status
            self.assertFalse(inspect_import(payload, {'layers': 2})['passed'])

    def test_current_report_errors_are_not_ignored(self):
        for field in ('unsupported', 'geometry_errors', 'diagnostics'):
            payload = self.payload()
            payload['report'][field] = [{'severity': 'error', 'message': 'lost copper'}]
            self.assertFalse(inspect_import(payload, {})['passed'], field)
        payload = self.payload()
        payload['report'].update(status='completed_with_warnings', diagnostics=[{'severity': 'warning'}],
                                 solver_readiness={'si': {'ready': False}})
        result = inspect_import(payload, {})
        self.assertTrue(result['passed'])
        self.assertFalse(result['solver_readiness']['si']['ready'])

    def test_canonical_source_issues_are_retained_even_when_report_omits_them(self):
        payload = self.payload()
        issue = {'code': 'MATERIAL_MISSING', 'severity': 'warning', 'message': 'No stackup declared'}
        payload['design']['issues'] = [issue]
        result = inspect_import(payload, {})
        self.assertEqual(result['source_issues'], [issue])
        self.assertTrue(result['passed'])
        issue['severity'] = 'error'
        self.assertFalse(inspect_import(payload, {})['passed'])

    def test_scale_and_mirror_errors_fail_even_with_correct_counts(self):
        assertion = {'collection': 'tracks', 'source_id': 'source-track', 'field': 'start_mm',
                     'value': [2.5, -3.0], 'tolerance': 1e-9}
        self.assertTrue(inspect_import(self.payload(), {'tracks': 1}, [assertion])['passed'])
        for value in ([2500, -3000], [-2.5, -3.0], [2.5, float('nan')], [True, -3.0]):
            payload = self.payload()
            payload['design']['tracks'][0]['start_mm'] = value
            result = inspect_import(payload, {'tracks': 1}, [assertion])
            self.assertFalse(result['passed'])
            self.assertEqual(result['geometry_mismatches'][0]['check'], 'entity_value')

    def test_missing_or_ambiguous_source_and_duplicate_ids_fail(self):
        assertion = {'collection': 'tracks', 'source_id': 'source-track', 'field': 'width_mm', 'value': 0.25}
        for mode in ('missing', 'ambiguous', 'duplicate_id', 'units'):
            payload = self.payload()
            if mode == 'missing':
                payload['design']['tracks'][0]['source_id'] = 'other'
            elif mode == 'ambiguous':
                twin = copy.deepcopy(payload['design']['tracks'][0])
                twin['id'] = 'twin'
                payload['design']['tracks'].append(twin)
            elif mode == 'duplicate_id':
                payload['design']['tracks'][0]['id'] = 'front'
            else:
                payload['design']['frame']['units'] = 'm'
            self.assertFalse(inspect_import(payload, {}, [assertion])['passed'], mode)

    def test_expected_source_binding_is_checked_in_both_outputs(self):
        digest = 'a' * 64
        payload = self.payload()
        payload['design']['source'] = {'source_digest': digest}
        payload['report']['source_sha256'] = digest
        self.assertTrue(inspect_import(payload, {}, expected_sha256=digest)['passed'])
        for location in ('design', 'report'):
            damaged = copy.deepcopy(payload)
            if location == 'design':
                damaged['design']['source']['source_digest'] = 'b' * 64
            else:
                damaged['report']['source_sha256'] = 'b' * 64
            self.assertFalse(inspect_import(damaged, {}, expected_sha256=digest)['passed'])

    def test_invalid_or_vacuous_assertions_are_rejected(self):
        row = {'collection': 'tracks', 'source_id': 'source-track', 'field': 'width_mm', 'value': 0.25}
        for bad in ({**row, 'tolerance': float('inf')}, {**row, 'tolerance': -1},
                    {**row, 'value': True}, {**row, 'value': []}, {**row, 'collection': 'unknown'}):
            with self.assertRaises(ValueError):
                inspect_import(self.payload(), {}, [bad])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            inspect_import(self.payload(), {}, [row, row])

    def test_reference_checks_net_or_layer_binding_without_generated_uuid_oracle(self):
        payload = self.payload()
        payload['design']['layers'][0]['source_id'] = 'front-layer'
        payload['design']['tracks'][0]['layer_id'] = 'front'
        assertion = {'collection': 'tracks', 'source_id': 'source-track', 'field': 'layer_id',
                     'reference': {'collection': 'layers', 'source_id': 'front-layer'}}
        self.assertTrue(inspect_import(payload, {}, [assertion])['passed'])
        payload['design']['tracks'][0]['layer_id'] = 'back'
        self.assertFalse(inspect_import(payload, {}, [assertion])['passed'])
        payload['design']['layers'][0]['source_id'] = 'lost-source'
        self.assertFalse(inspect_import(payload, {}, [assertion])['passed'])

    def test_malformed_output_is_reported_as_failure(self):
        for payload in ([], {'design': None}, {'design': {}},
                        {**self.payload(), 'report': {'status': 'completed', 'diagnostics': None}}):
            with self.assertRaises(ValueError):
                inspect_import(payload, {})
        with self.assertRaises(ValueError):
            inspect_import(self.payload(), {}, {})

    def test_named_material_and_nested_geometry_are_checked(self):
        payload = self.payload()
        payload['design']['materials'] = [{'id': 'core', 'name': 'FR4', 'relative_permittivity': 4.2}]
        payload['design']['tracks'][0]['extensions'] = {'spike.v1': {'rotation': 90}}
        assertions = [{'collection': 'materials', 'name': 'FR4', 'field': 'relative_permittivity', 'value': 4.2},
                      {'collection': 'tracks', 'source_id': 'source-track',
                       'field': '/extensions/spike.v1/rotation', 'value': 90},
                      {'collection': 'tracks', 'source_id': 'source-track', 'field': 'start_mm.1', 'value': -3.0}]
        self.assertTrue(inspect_import(payload, {}, assertions)['passed'])
        payload['design']['tracks'][0]['start_mm'][1] = 3.0
        self.assertFalse(inspect_import(payload, {}, assertions)['passed'])
        payload['design']['materials'].append({'id': 'core2', 'name': 'FR4'})
        self.assertFalse(inspect_import(payload, {}, assertions)['passed'])

    def test_field_paths_and_reference_selectors_are_bounded(self):
        row = {'collection': 'tracks', 'source_id': 'source-track', 'field': 'width_mm', 'value': 0.25}
        for field in ('start_mm.-1', '__import__(x)', 'start_mm..0', '.'.join(['a'] * 9)):
            with self.assertRaises(ValueError):
                inspect_import(self.payload(), {}, [{**row, 'field': field}])
        with self.assertRaises(ValueError):
            inspect_import(self.payload(), {}, [{**row, 'name': 'duplicate-selector'}])
