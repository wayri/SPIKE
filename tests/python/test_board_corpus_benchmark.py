import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.benchmark_board_corpus import inspect_import, validate_entry


class CorpusBenchmarkTests(unittest.TestCase):
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
        payload = {'design': {'contract': 'spike/design-ir/v2', 'layers': [{}, {}]},
                   'report': {'status': 'completed', 'issues': []}}
        self.assertTrue(inspect_import(payload, {'layers': 2})['passed'])
        self.assertFalse(inspect_import(payload, {'layers': 4})['passed'])
        payload['report']['issues'] = [{'severity': 'error', 'message': 'lost geometry'}]
        self.assertFalse(inspect_import(payload, {})['passed'])
        with self.assertRaisesRegex(ValueError, 'typed DesignIR'):
            inspect_import({}, {})
