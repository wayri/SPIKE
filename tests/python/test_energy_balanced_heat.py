# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original first-law and polynomial analytical heat fixtures."""
import copy
import unittest

from python.spike_core.electrical_heat_sources import ElectricalHeatSourceError, evaluate_electrical_heat_source
from tests.python.test_electrical_heat_sources import request


def model():
    # p=(1+2t)(2+3t)=2+7t+6t²; integral 7.5 J.
    # Stored energy increases 1 J => dissipated heat 6.5 J.
    return {'kind': 'energy_balanced_terminal_waveform', 'time_s': [0, 1],
            'ports': [{'id': 'drain', 'voltage_v': [1, 3], 'current_a': [2, 5]}],
            'stored_energy_j': [2, 3], 'energy_policy': 'passive_ports_minus_stored_energy'}


class EnergyBalancedHeatTests(unittest.TestCase):
    def evaluate(self, raw):
        return evaluate_electrical_heat_source(request(raw), 350)

    def test_first_law_quadratic_power(self):
        import json
        from pathlib import Path
        import jsonschema
        schema = json.loads((Path(__file__).resolve().parents[2]/'schemas/electrical-heat-source-v1.schema.json').read_text())
        jsonschema.Draft202012Validator(schema).validate(request(model()))
        raw = model()
        before = copy.deepcopy(raw)
        result = self.evaluate(raw)
        self.assertEqual(raw, before)
        self.assertEqual(result['average_power_w'], 6.5)
        self.assertEqual(result['terminal_energy_j'], 7.5)
        self.assertEqual(result['stored_energy_change_j'], 1)
        self.assertEqual(result['temporal_scope'], 'steady_average_only')

    def test_multiterminal_signed_power_and_stored_energy_release(self):
        raw = model()
        raw['ports'] = [{'id': 'input', 'voltage_v': [10, 10], 'current_a': [1, 1]},
                        {'id': 'output', 'voltage_v': [2, 2], 'current_a': [-2, -2]}]
        raw['stored_energy_j'] = [2, 1]
        self.assertEqual(self.evaluate(raw)['average_power_w'], 7)

    def test_pure_storage_not_heat(self):
        raw = model()
        raw['ports'][0].update(voltage_v=[2, 2], current_a=[3, 3])
        raw['stored_energy_j'] = [0, 6]
        self.assertEqual(self.evaluate(raw)['total_energy_j'], 0)

    def test_negative_between_positive_endpoints_rejected(self):
        raw = model()
        raw['ports'][0].update(voltage_v=[-1, 1], current_a=[-1, 1])
        raw['stored_energy_j'] = [0, .1]
        with self.assertRaisesRegex(ElectricalHeatSourceError, 'nondissipative_power'):
            self.evaluate(raw)

    def test_exact_admission_cannot_lose_subnormal_or_cancelled_negative_heat(self):
        import math
        cases = [([1e-200, 1e-200], [-1e-200, -1e-200], [0, 0]),
                 ([-1, 1], [-1, math.nextafter(1, 2)], [0, 0]),
                 ([1+2**-52]*2, [1-2**-52]*2, [0, 1])]
        for voltage, current, energy in cases:
            raw = model()
            raw['ports'][0].update(voltage_v=voltage, current_a=current)
            raw['stored_energy_j'] = energy
            with self.subTest(voltage=voltage), self.assertRaisesRegex(ElectricalHeatSourceError, 'nondissipative_power'):
                self.evaluate(raw)

    def test_subdivision_preserves_energy(self):
        raw = model()
        raw['time_s'] = [0, .25, 1]
        raw['ports'][0].update(voltage_v=[1, 1.5, 3], current_a=[2, 2.75, 5])
        raw['stored_energy_j'] = [2, 2.25, 3]
        self.assertAlmostEqual(self.evaluate(raw)['total_energy_j'], 6.5, places=14)

    def test_positive_underflow_is_not_silently_zero(self):
        raw = model()
        raw['time_s'] = [0, 1e308]
        raw['ports'][0].update(voltage_v=[1e-200]*2, current_a=[1e-200]*2)
        raw['stored_energy_j'] = [0, 0]
        with self.assertRaisesRegex(ElectricalHeatSourceError, 'numeric_range'):
            self.evaluate(raw)

    def test_invalid_ledger_and_resource_cases(self):
        changes = [lambda r: r.update(energy_policy='ignore_storage'),
                   lambda r: r.update(stored_energy_j=[0]),
                   lambda r: r.update(time_s=[0, 0]),
                   lambda r: r.update(ports=[]),
                   lambda r: r['ports'].append(copy.deepcopy(r['ports'][0])),
                   lambda r: r['ports'][0].update(current_a=[float('nan'), 1]),
                   lambda r: r['ports'][0].update(voltage_v=[1e308, 1e308]),
                   lambda r: r.update(extra=0)]
        for change in changes:
            raw = model()
            change(raw)
            with self.subTest(change=change), self.assertRaises(ElectricalHeatSourceError):
                self.evaluate(raw)

    def test_actual_coupled_field_deposition(self):
        from tests.python.test_assembly_electrothermal import request as coupled_request
        from python.spike_core.assembly_electrothermal import run_assembly_electrothermal
        raw = coupled_request(multi_board=True)
        source = request(model())
        source['distribution'] = [{'occurrence_id': 'board', 'cell_id': '0', 'weight': .25},
                                  {'occurrence_id': 'case', 'cell_id': '0', 'weight': .75}]
        raw['heat_sources'] = [source]
        result = run_assembly_electrothermal(raw)
        self.assertAlmostEqual(sum(result['cell_deposited_power_w'].values()), 9.7, places=8)
        self.assertLess(abs(result['conservation']['thermal_imbalance_w']), 1e-8)

    def test_operating_table_schema_worker_and_coupled_field(self):
        import json
        from pathlib import Path
        import jsonschema
        from tests.python.test_semiconductor_operating_losses import table
        from tests.python.test_assembly_electrothermal import request as coupled_request
        from python.spike_core.service_assembly_field import handle_assembly_field_request
        raw = coupled_request(multi_board=True)
        device = table()
        device['temperature_k'] = [200, 325, 1000]
        # Constant original 2 W total loss: 1 W conduction + 1 W switching.
        for column, value in [('conduction_power_w', 1), ('turn_on_energy_j', .0005),
                              ('turn_off_energy_j', .0005), ('reverse_recovery_energy_j', 0)]:
            device[column] = [[[value]*3 for _ in range(3)] for _ in range(3)]
        source = request(device)
        source['distribution'] = [{'occurrence_id': 'board', 'cell_id': '0', 'weight': 1}]
        schema = json.loads((Path(__file__).resolve().parents[2]/'schemas/electrical-heat-source-v1.schema.json').read_text())
        jsonschema.Draft202012Validator(schema).validate(source)
        raw['heat_sources'] = [source]
        answer = handle_assembly_field_request('run_assembly_electrothermal', {'request': raw})
        self.assertTrue(answer['ok'], answer)
        self.assertAlmostEqual(sum(answer['result']['cell_deposited_power_w'].values()), 5.2, places=8)
        self.assertLess(abs(answer['result']['conservation']['thermal_imbalance_w']), 1e-8)
        device['operating_voltage_v'] = 201
        failed = handle_assembly_field_request('evaluate_electrical_heat_source', {'request': source, 'temperature_k': 350})
        self.assertFalse(failed['ok'])

    def test_json_subprocess_worker_supports_new_heat_model(self):
        import json
        import subprocess
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        payload = {'id': 'first-law', 'method': 'evaluate_electrical_heat_source',
                   'params': {'request': request(model()), 'temperature_k': 350}}
        completed = subprocess.run([sys.executable, '-W', 'error', '-m', 'python.spike_core.service'],
            input=json.dumps(payload)+'\n', text=True, capture_output=True, cwd=root, timeout=30, check=True)
        answer = json.loads(completed.stdout)
        self.assertTrue(answer['ok'], answer)
        self.assertEqual(answer['result']['average_power_w'], 6.5)

    def test_pcb_mesh_bridge_schema_and_worker(self):
        import json
        from pathlib import Path
        import jsonschema
        from referencing import Registry, Resource
        from tests.python.test_pcb_electrothermal_geometry import mesh
        from python.spike_core.service_assembly_field import handle_assembly_field_request
        root = Path(__file__).resolve().parents[2]
        source = {'contract': 'spike/pcb-electrothermal-geometry-request/v1',
                  'occurrence_id': 'board', 'reference_id': 'design', 'source_sha256': 'a'*64,
                  'stack_binding': {'id': 'stack', 'source_sha256': 'b'*64},
                  'material_map': {'local-copper': 'copper', 'local-fr4': 'fr4'}, 'mesh': mesh()}
        schema = json.loads((root/'schemas/pcb-electrothermal-geometry-request-v1.schema.json').read_text())
        mesh_schema = json.loads((root/'schemas/solver-mesh-v1.schema.json').read_text())
        registry = Registry().with_resource(mesh_schema['$id'], Resource.from_contents(mesh_schema))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema, registry=registry).validate(source)
        answer = handle_assembly_field_request('prepare_pcb_electrothermal_geometry', {'request': source})
        self.assertTrue(answer['ok'], answer)
        self.assertEqual(answer['result']['body']['mesh'], source['mesh'])
        self.assertEqual(len(answer['result']['boundary_face_ownership']), 8)
