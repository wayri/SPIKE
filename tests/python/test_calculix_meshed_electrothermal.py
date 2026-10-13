# SPDX-License-Identifier: Apache-2.0
"""Original analytical circuit/slab oracle through actual CAD, MNA and CCX.

Synthetic 2x2x1 mm boards and package; no measured hardware or production claim.
The package's board-owned resistor is modeled once electrically and its losses
are explicitly deposited in the separately owned promoted package volume.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.assembly_thermal_components import promote_thermal_components
from python.spike_core.assembly_thermal_meshing import run_assembly_thermal_mesh
from python.spike_core.assembly_thermal_autolink import autolink_assembly_thermal_contacts
from python.spike_core.calculix_runtime import probe_calculix_runtime
from python.spike_core.calculix_thermal import run_calculix_thermal
from python.spike_core.multiboard_circuit import compile_multiboard_circuit
from python.spike_core.multiboard_volume_electrothermal import (
    prepare_multiboard_volume_electrothermal, run_multiboard_volume_electrothermal,
    verify_multiboard_volume_electrothermal_result)
from tests.python import test_assembly_joint_thermal_mesh as joint_fixture
from tests.python.test_assembly_thermal_meshing import has_runtime
from tests.python.test_thermal_component_promotion import pure_fixture


@unittest.skipUnless(has_runtime(), 'Requires admitted local Windows CPython 3.11 Gmsh OCC runtime')
class CalculixMeshedElectrothermalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not probe_calculix_runtime()['available']:
            raise unittest.SkipTest('Separately installed CalculiX unavailable')
        # Reuse the original STEP generation fixture, never an external CAD file.
        joint_fixture.RealJointMeshTests.setUpClass()
        cls.addClassCleanup(joint_fixture.RealJointMeshTests.tearDownClass)

    def test_actual_promoted_package_joint_mesh_mna_calculix_feedback_roundtrip(self):
        payload, assignments, options, selection, reader = pure_fixture()
        source = joint_fixture.RealJointMeshTests.step
        payload['models']['models'][0]['digest'] = hashlib.sha256(source).hexdigest()
        transform = selection['component_to_board_transform_mm']
        transform[3], transform[7], transform[11] = 0., 0., 1.
        artifacts = lambda uri: source if uri.startswith('package:models/') else reader(uri)
        promoted = promote_thermal_components(payload, [selection], assignments['materials'], artifact_reader=artifacts)
        package = promoted['promoted_parts'][0]['id']
        assembly = promoted['payload']['assembly_ir']
        assembly['thermal_contacts'] = [{'id': 'package-contact', 'endpoint_a': 'board-a', 'endpoint_b': package,
                                         'contact_area_mm2': 4., 'thermal_resistance_k_per_w': 50.}]
        assembly['harnesses'] = [{'id': 'supply-harness', 'endpoint_a': 'board-b::J', 'endpoint_b': 'board-a::J',
                                  'pin_map': {'1': '1', '2': '2'}}]
        assignments['parts'].update(promoted['part_material_assignments'])
        options.update(min_size_mm=.5, max_size_mm=.5)
        output = Path(joint_fixture.RealJointMeshTests.directory.name)/'electrothermal-acceptance'
        meshed = run_assembly_thermal_mesh(promoted['payload'], assignments, options, output, artifact_reader=artifacts)
        self.assertEqual(meshed['status'], 'completed', meshed.get('blockers'))
        self.assertEqual(meshed['meshing_mode'], 'joint_conformal')
        self.assertFalse(meshed['contacts_inferred'])
        geometry = meshed['request']
        bodies = {body['occurrence_id']: body for body in geometry['bodies']}
        self.assertEqual(set(bodies), {'board-a', 'board-b', package})
        thermal = {'contract': 'spike/assembly-field-thermal-problem/v1', 'heat_sources': [], 'boundaries': [], 'contacts': []}
        for oid in ('board-a', 'board-b'):
            body = bodies[oid]
            for face in body['boundary_faces']:
                if all(math.isclose(body['mesh']['vertices'][v][2], 0., abs_tol=1e-10) for v in face['vertices']):
                    thermal['boundaries'].append({'face': {'occurrence_id': oid, 'face_id': face['id']},
                                                  'type': 'temperature', 'temperature_k': 300.})
        thermal = autolink_assembly_thermal_contacts(geometry, thermal, ['package-contact'])['problem']
        self.assertAlmostEqual(thermal['contacts'][0]['thermal_contact_conductance_w_m2k'], 5000., places=6)
        circuit = {'contract': 'spike/multiboard-circuit-request/v1', 'domain': 'pi',
                   'assembly': copy.deepcopy(assembly), 'thermal_only_part_ids': [package],
                   'board_models': [
                       {'board_id': 'board-b', 'elements': [{'id': 'supply', 'type': 'voltage_source',
                           'positive_node': 'J:1', 'negative_node': 'J:2', 'dc_value': 1.}]},
                       {'board_id': 'board-a', 'elements': [{'id': 'device', 'type': 'resistor',
                           'positive_node': 'J:1', 'negative_node': 'J:2', 'resistance_ohm': 6.}]}],
                   'link_models': [{'link_id': 'supply-harness', 'kind': 'harness', 'pins': [
                       {'source_pin': str(pin), 'target_pin': str(pin), 'resistance_ohm': resistance, 'inductance_h': 0.}
                       for pin, resistance in [(1, .1), (2, .2)]]}],
                   'ground': {'board_id': 'board-b', 'node': 'J:2'}, 'analysis': {'mode': 'operating_point'}}
        compiled = compile_multiboard_circuit(circuit)
        device_id = compiled['element_map']['board-a']['device']

        def distribution(oid):
            body = bodies[oid]
            vertices = np.asarray(body['mesh']['vertices'])
            volumes = [float(abs(np.linalg.det((vertices[c['vertices']][1:]-vertices[c['vertices']][0]).T))/6)
                       for c in body['mesh']['cells']]
            total = math.fsum(volumes)
            return [{'occurrence_id': oid, 'cell_id': cell['id'], 'weight': volume/total}
                    for cell, volume in zip(body['mesh']['cells'], volumes)]

        bindings = [{'element_id': e['id'], 'distribution': distribution(package if e['id'] == device_id else 'board-b'),
                     'temperature_law': {'temperature_coefficient_per_k': .004 if e['id'] == device_id else 0.,
                                        'reference_temperature_k': 300., 'temperature_range_k': [290., 500.]}}
                    for e in compiled['native_request']['elements'] if e['type'] == 'resistor']
        request = {'contract': 'spike/multiboard-volume-electrothermal-request/v1', 'geometry': geometry,
                   'thermal_problem': thermal, 'circuit': circuit, 'loss_bindings': bindings,
                   'loss_accounting': 'exhaustive_resistor_losses', 'thermal_engine': 'calculix',
                   'thermal_engine_options': {'threads': 1, 'timeout_seconds': 60},
                   'iteration': {'initial_temperature_k': 300., 'max_iterations': 30, 'relaxation': .8,
                                 'temperature_tolerance_k': .002, 'power_relative_tolerance': 1e-6}}
        original = copy.deepcopy(request)
        prepared = prepare_multiboard_volume_electrothermal(request)
        # Wrap the real solver to prove every feedback phase invokes CalculiX.
        with patch('python.spike_core.calculix_thermal.run_calculix_thermal', wraps=run_calculix_thermal) as actual_ccx:
            result = run_multiboard_volume_electrothermal(request)
        self.assertEqual(request, original)
        self.assertGreater(len(result['history']), 1)
        self.assertEqual(actual_ccx.call_count, len(result['history']))
        self.assertEqual(result['thermal']['solver_id'], 'external.calculix')
        self.assertTrue(result['thermal']['execution']['solver_reported_finished'])
        self.assertEqual(result['thermal']['handoff_digest'], prepared['handoff']['handoff_digest'])
        self.assertEqual(result['circuit_maps']['excluded_thermal_part_ids'], [package])
        self.assertEqual(result['circuit_maps']['part_element_map'], {})
        self.assertEqual(len(result['electrical']['losses']), 3)
        losses = {row['element_id']: row for row in result['electrical']['losses']}
        device = losses[device_id]
        current = result['electrical']['native_result']['data']['element_current_a'][device_id]
        self.assertGreater(device['temperature_k'], 300.)
        self.assertAlmostEqual(device['resistance_ohm'], 6*(1+.004*(device['temperature_k']-300)), places=12)
        self.assertAlmostEqual(current, 1/(device['resistance_ohm']+.3), places=12)
        self.assertLess(current, 1/6.3)
        self.assertAlmostEqual(device['average_power_w'], current**2*device['resistance_ohm'], places=12)
        self.assertAlmostEqual(result['loss_balance']['deposited_power_w'], current, places=12)
        self.assertLess(abs(result['loss_balance']['mapping_residual_w']), 1e-12)
        self.assertEqual(result['loss_balance']['thermal_balance_status'], 'not_reported')
        self.assertIsNone(result['loss_balance']['thermal_imbalance_w'])
        self.assertLessEqual(result['history'][-1]['unrelaxed_temperature_defect_k'], .002)
        self.assertLessEqual(result['history'][-1]['power_relative_defect'], 1e-6)
        # Uniform package heating: board R=L/kA=125 K/W, contact=50 K/W,
        # package volume-mean rise relative to its bottom is P*L/(3*k*A).
        # 2% accommodates the bounded first-order spatial discretization; the
        # electrical oracle above is independent and uses 1e-12 absolute precision.
        mean_rise = device['temperature_k']-300
        analytical_rise = device['average_power_w']*(125+50+125/3)
        self.assertAlmostEqual(mean_rise, analytical_rise, delta=.02*analytical_rise+.002)
        temperatures = result['thermal']['occurrence_temperatures']
        self.assertGreater(temperatures[package]['minimum_k'], temperatures['board-a']['maximum_k'])
        self.assertGreater(temperatures['board-a']['maximum_k'], 300.)
        traces = result['thermal']['source_traceability']
        ranges = sorted(t['vertex_range'] for t in traces)
        self.assertTrue(all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:])))
        owner_cells = {t['occurrence_id']: set(t['cell_map'].values()) for t in traces}
        self.assertAlmostEqual(math.fsum(result['cell_deposited_power_w'][cid] for cid in owner_cells[package]), device['average_power_w'], places=12)
        self.assertTrue(all(result['cell_deposited_power_w'][cid] == 0 for cid in owner_cells['board-a']))
        saved = json.loads(json.dumps({'request': request, 'result': result}, allow_nan=False))
        with (patch('python.spike_core.calculix_thermal.run_calculix_thermal', side_effect=AssertionError('offline: no CCX')),
              patch('python.spike_core.multiboard_volume_electrothermal.run_native_mna', side_effect=AssertionError('offline: no MNA'))):
            admitted = verify_multiboard_volume_electrothermal_result(saved['request'], saved['result'])
        self.assertEqual(admitted, saved['result'])


if __name__ == '__main__':
    unittest.main()
