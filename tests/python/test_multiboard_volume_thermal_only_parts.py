# SPDX-License-Identifier: Apache-2.0
"""Explicit thermal package exclusion without duplicate circuit device losses."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from examples.assembly_field.run_multiboard_volume import request
from python.spike_core.assembly_frames import IDENTITY
from python.spike_core.assembly_thermal_components import promote_thermal_components
from python.spike_core.multiboard_circuit import compile_multiboard_circuit, run_multiboard_circuit
from python.spike_core.multiboard_volume_electrothermal import (
    run_multiboard_volume_electrothermal, verify_multiboard_volume_electrothermal_result)


def fixture():
    raw = request()
    data = b'Original synthetic retained package reference for supplied tetra fixture'
    source_hash = hashlib.sha256(data).hexdigest()
    model = {'id': 'package-model', 'model_type': 'step', 'uri': 'package:models/artifacts/package.step',
             'digest': source_hash, 'transform': list(IDENTITY)}
    payload = {'assembly_ir': raw['geometry']['assembly'],
               'design_ir': {'design_id': 'original-case', 'source': {'source_digest': 'a'*64},
                             'components': [{'id': 'device', 'reference': 'Rload', 'model_ids': ['package-model']}]},
               'models': {'models': [model]}}
    transform = list(IDENTITY)
    transform[7] = 3000.
    selected = {'board_occurrence_id': 'case', 'component_id': 'device', 'model_id': 'package-model',
                'component_to_board_transform_mm': transform, 'material_id': 'k', 'placement_reviewed': True}
    promoted = promote_thermal_components(payload, [selected], raw['geometry']['materials'], artifact_reader=lambda uri: data)
    part_id = promoted['promoted_parts'][0]['id']
    raw['geometry']['assembly'] = promoted['payload']['assembly_ir']
    raw['circuit']['assembly'] = copy.deepcopy(raw['geometry']['assembly'])
    raw['circuit']['thermal_only_part_ids'] = [part_id]
    body = copy.deepcopy(raw['geometry']['bodies'][1])
    body.pop('stack_binding')
    body.update(occurrence_id=part_id, reference_id='package-model', source_sha256=source_hash)
    raw['geometry']['bodies'].append(body)
    for face in body['boundary_faces']:
        if all(body['mesh']['vertices'][v][0] == 0 for v in face['vertices']):
            raw['thermal_problem']['boundaries'].append({'face': {'occurrence_id': part_id, 'face_id': face['id']},
                                                        'type': 'temperature', 'temperature_k': 300})
    load_id = compile_multiboard_circuit(raw['circuit'])['element_map']['case']['load']
    for binding in raw['loss_bindings']:
        if binding['element_id'] == load_id:
            binding['distribution'] = [{'occurrence_id': part_id, 'cell_id': cell['id'], 'weight': 1/6}
                                       for cell in body['mesh']['cells']]
    return raw, part_id


class ThermalOnlyCircuitPartsTests(unittest.TestCase):
    def test_board_device_loss_heats_real_package_body_without_duplicate_electrical_model(self):
        raw, pid = fixture()
        circuit = run_multiboard_circuit(raw['circuit'])
        self.assertEqual(circuit['excluded_thermal_part_ids'], [pid])
        self.assertEqual(circuit['part_element_map'], {})
        coupled = run_multiboard_volume_electrothermal(raw)
        self.assertGreater(coupled['thermal']['occurrence_temperatures'][pid]['maximum_k'], 300.)
        self.assertAlmostEqual(coupled['loss_balance']['deposited_power_w'], 144/6.3, places=10)
        self.assertEqual(len(coupled['electrical']['losses']), 3)
        self.assertLess(abs(coupled['loss_balance']['thermal_imbalance_w']), 1e-8)
        self.assertEqual(coupled['circuit_maps']['excluded_thermal_part_ids'], [pid])
        verify_multiboard_volume_electrothermal_result(raw, json.loads(json.dumps(coupled)))

    def test_missing_exclusion_and_duplicate_device_part_model_fail(self):
        raw, pid = fixture()
        omitted = copy.deepcopy(raw['circuit'])
        omitted.pop('thermal_only_part_ids')
        with self.assertRaisesRegex(ValueError, 'part_models'):
            compile_multiboard_circuit(omitted)
        raw['circuit']['part_models'] = [{'part_id': pid, 'elements': [
            {'id': 'duplicate-device', 'type': 'resistor', 'positive_node': 'p', 'negative_node': 'n', 'resistance_ohm': 6}]}]
        with self.assertRaisesRegex(ValueError, 'part_models'):
            compile_multiboard_circuit(raw['circuit'])

    def test_untrusted_scope_parent_and_bond_exclusions_rejected(self):
        for mutation in [lambda r, pid: r.update(thermal_only_part_ids=[pid, pid]),
                         lambda r, pid: r.update(thermal_only_part_ids=['unknown']),
                         lambda r, pid: r['assembly']['parts'][0].update(part_type='enclosure'),
                         lambda r, pid: r['assembly']['parts'][0]['extensions'].clear(),
                         lambda r, pid: r['assembly']['parts'][0]['frame'].update(parent_frame_id='board-frame'),
                         lambda r, pid: r['assembly']['parts'][0]['extensions']['spike.thermal-component'].update(source_sha256='x'),
                         lambda r, pid: r['assembly'].update(electrical_bonds=[{'id': 'bond', 'endpoint_a': pid+'::pad', 'endpoint_b': 'case'}])]:
            raw, pid = fixture()
            mutation(raw['circuit'], pid)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                compile_multiboard_circuit(raw['circuit'])

    def test_schema_admits_explicit_list_and_rejects_duplicate_ids(self):
        from jsonschema import Draft202012Validator
        schema = json.loads((Path(__file__).resolve().parents[2]/'schemas/multiboard-circuit-request-v1.schema.json').read_text())
        validator = Draft202012Validator(schema)
        raw, pid = fixture()
        validator.validate(raw['circuit'])
        raw['circuit']['thermal_only_part_ids'].append(pid)
        self.assertTrue(list(validator.iter_errors(raw['circuit'])))


if __name__ == '__main__':
    unittest.main()
