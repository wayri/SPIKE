# SPDX-License-Identifier: Apache-2.0
"""Archive packaging evidence stays distinct from native-export qualification."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.benchmark_board_corpus import inspect_import
from scripts.pack_parity_odb_candidate import pack
from scripts.parity_stage_evidence import validate_done_import_stage

ROOT = Path(__file__).resolve().parents[2]


class OdbCandidateTests(unittest.TestCase):
    def test_checked_archive_is_reproducible_from_owned_source_records(self):
        source = ROOT / 'benchmarks/parity-import/odb-candidate'
        archive = ROOT / 'benchmarks/parity-import/odb-candidate.zip'
        with tempfile.TemporaryDirectory() as directory:
            replay = Path(directory) / 'replay.zip'
            pack(source, replay)
            self.assertEqual(hashlib.sha256(replay.read_bytes()).digest(),
                             hashlib.sha256(archive.read_bytes()).digest())
        with zipfile.ZipFile(archive) as package:
            self.assertIn(b'not a native KiCad export', package.read('job/README.md'))

    def test_candidate_import_preserves_declared_facts_without_solver_promotion(self):
        manifest = json.loads((ROOT / 'benchmarks/parity-import/odb-candidate-manifest.json').read_text())
        entry = manifest['boards'][0]
        payload = json.loads((ROOT / 'docs/validation/parity/WF01-S04B-candidate-import.json').read_text())
        result = inspect_import(payload, entry['expected_counts'], entry['expected_entities'], entry['sha256'])
        self.assertTrue(result['passed'])
        self.assertEqual(result['entity_assertions_checked'], 14)
        self.assertTrue(all(row['ready'] is False for row in result['solver_readiness'].values()))
        self.assertIn('ODB_STACKUP_MISSING', [row['code'] for row in result['source_issues']])

    def test_candidate_progress_receipt_cannot_claim_a_done_native_export_stage(self):
        stage = {'id': 'WF01-S04B', 'evidence': 'docs/validation/parity/WF01-S04B-progress.json'}
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            validate_done_import_stage(stage, ROOT)


if __name__ == '__main__':
    unittest.main()
