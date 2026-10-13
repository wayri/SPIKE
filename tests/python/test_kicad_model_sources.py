# SPDX-License-Identifier: Apache-2.0
"""Model occurrences and source placement must survive without invented matrices."""
from pathlib import Path
import copy
import json
import tempfile
import unittest

from python.core.kicad_model_sources import model_sources
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.spider_v2 import SpiDeRV2
from scripts.parity_model_gate import validate_model_gate

ROOT = Path(__file__).resolve().parents[2]


class ModelSourceTests(unittest.TestCase):
    def load(self):
        return SpiDeRV2.from_v1(import_kicad_design(str(ROOT / 'benchmarks/parity-import/models.kicad_pcb')))

    def test_all_occurrences_and_declared_vectors_retained(self):
        design = self.load()
        self.assertEqual(len(design.models), 3)
        self.assertEqual(len({m.id for m in design.models}), 3)
        self.assertEqual(design.components[0].model_ids, [m.id for m in design.models])
        self.assertEqual([m.uri for m in design.models], ['models/body.step', 'models/lid.step', 'models/body.step'])
        first = design.models[0].extensions['spike.v1']['source_placement']
        self.assertEqual(first['declared_vectors'], {'offset': [1.25, -2.5, 3], 'scale': [2, 1, .5], 'rotate': [15, 30, 45]})
        self.assertTrue(first['valid_source_vectors'])
        self.assertTrue(all(m.transform == [] for m in design.models))
        self.assertEqual(first['projection'], 'forbidden')
        self.assertIn('KICAD_MODEL_PLACEMENT_UNAPPLIED', [i.code for i in design.to_v1().issues])

    def test_json_and_legacy_roundtrip_no_duplicate_models(self):
        design = self.load()
        restored = SpiDeRV2.from_dict(design.to_dict())
        replay = SpiDeRV2.from_v1(restored.to_v1())
        self.assertEqual([(m.id, m.uri, m.transform, m.extensions['spike.v1']['source_placement']) for m in replay.models],
                         [(m.id, m.uri, m.transform, m.extensions['spike.v1']['source_placement']) for m in design.models])
        self.assertEqual(replay.components[0].model_ids, design.components[0].model_ids)

    def test_unknown_fields_and_absent_vectors_retained_without_defaults(self):
        row = model_sources(['footprint', ['model', 'part.step', ['hide', 'yes'], ['vendor', 'opaque']]])[0]
        self.assertEqual(row['declared_vectors'], {})
        self.assertEqual(row['source_node'][-1], ['vendor', 'opaque'])

    def test_bad_vectors_diagnostic_without_losing_component_or_pad(self):
        source = (ROOT / 'benchmarks/parity-import/models.kicad_pcb').read_text()
        for replacement in ('(xyz nan 0 0)', '(xyz 1 2)', '(xyz bad 2 3)'):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'bad.kicad_pcb'
                path.write_text(source.replace('(xyz 1.25 -2.5 3)', replacement))
                legacy = import_kicad_design(str(path))
                self.assertEqual(len(legacy.components), 1)
                self.assertEqual(len(legacy.pads), 1)
                self.assertIn('KICAD_MODEL_SOURCE_INVALID', [i.code for i in legacy.issues])
                first = SpiDeRV2.from_v1(legacy).models[0].extensions['spike.v1']['source_placement']
                self.assertFalse(first['valid_source_vectors'])
                self.assertNotIn('offset', first['declared_vectors'])

    def test_duplicate_vectors_and_missing_uri_remain_explicit(self):
        row = model_sources(['footprint', ['model', '', ['offset', ['xyz', '1', '2', '3']], ['offset', ['xyz', '4', '5', '6']]]])[0]
        self.assertEqual(len(row['errors']), 2)
        self.assertEqual(row['declared_vectors'], {})

    def test_native_gate_rejects_stale_or_incomplete_model_facts(self):
        payload = json.loads((ROOT / 'docs/validation/parity/WF01-S04A-import.json').read_text())
        native = json.loads((ROOT / 'docs/validation/parity/WF01-S04A-native.json').read_text())
        validate_model_gate(payload, native)
        for mutation in ('digest', 'missing', 'vector', 'uri', 'owner', 'projection'):
            with self.subTest(mutation=mutation):
                altered = copy.deepcopy(native)
                changed = copy.deepcopy(payload)
                if mutation == 'digest': altered['source_sha256'] = '0' * 64
                elif mutation == 'missing': altered['models'].pop()
                elif mutation == 'vector': altered['models'][0]['vectors']['offset'][0] = 99
                elif mutation == 'uri': altered['models'][0]['uri'] = 'other.step'
                elif mutation == 'owner': altered['models'][0]['component_source_id'] = 'missing'
                else: changed['design']['models'][0]['transform'] = [1] * 16
                with self.assertRaises(ValueError):
                    validate_model_gate(changed, altered)


if __name__ == '__main__':
    unittest.main()
