# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original energy, exact single-DOF decay and retained mixed-body oracles."""
import copy
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.assembly_tetra_transient import (
    AssemblyTetraThermalError, run_assembly_tetra_transient,
)
from python.spike_core.assembly_field_transient import (
    run_assembly_field_transient, validate_field_transient_settings, verify_assembly_field_transient_result,
)
from python.spike_core.multiboard_identity import canonical_json_digest
from tests.python.test_assembly_tetra_thermal import cube, request, contact_request, boundary, exterior
from tests.python.test_assembly_field_handoff import fixture


def settings(duration=1., step=.1, output=.2, initial=300., material='k'):
    return {'contract': 'spike/assembly-tetra-transient-settings/v1', 'duration_s': duration,
            'time_step_s': step, 'output_interval_s': output, 'initial_temperature_k': initial,
            'material_heat_capacity': [{'material_id': material, 'density_kg_m3': 2.,
                                         'specific_heat_j_kgk': 10.}]}


def insulated():
    raw = request()
    raw['boundaries'] = []
    raw['heat_sources_w_m3'] = {c['id']: 40. for c in raw['mesh']['cells']}
    return raw


def one_dof():
    mesh = {'contract': 'spike/solver-mesh/v1', 'units': 'm', 'coordinate_system': 'right_handed_xyz',
            'vertices': [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
            'cells': [{'id': 'c', 'kind': 'tetrahedron', 'vertices': [0, 1, 2, 3],
                       'material_id': 'k', 'source_object_ids': ['body']}],
            'counts': {'vertices': 4, 'cells': 1}, 'object_map': {'body': {'kind': 'solid'}}}
    raw = request(mesh)
    raw['boundaries'] = boundary([[0, 1, 2]], 'temperature', temperature_k=300.)
    return raw


class AssemblyTetraTransientTests(unittest.TestCase):
    def test_uniform_insulated_heating_exact_frames_and_energy(self):
        raw, setup = insulated(), settings()
        original = copy.deepcopy((raw, setup))
        callbacks = []
        def receive(frame):
            callbacks.append(copy.deepcopy(frame))
            frame['node_temperatures_k'][0] = -1
        out = run_assembly_tetra_transient(raw, setup, progress_callback=receive)
        self.assertEqual((raw, setup), original)
        self.assertEqual(out['frames'], callbacks)
        self.assertEqual(out['frames'][-1]['time_s'], 1.)
        for frame in out['frames']:
            np.testing.assert_allclose(frame['node_temperatures_k'], 300 + 2 * frame['time_s'], atol=1e-9)
            self.assertAlmostEqual(frame['stored_energy_change_j'], 40 * frame['time_s'], places=8)
        self.assertAlmostEqual(out['energy_balance']['source_j'], 40., places=8)
        self.assertLess(abs(out['energy_balance']['imbalance_j']), 1e-8)
        self.assertFalse(out['diagnostics']['temporal_convergence_verified'])

    def test_consistent_capacity_exact_single_dof_and_first_order_decay(self):
        # Single free vertex z=1: int(N_z^2)dV=V/10, int(|grad N_z|^2)dV=V.
        # tau=rho*cp/(10*k)=1 s, so continuous semidiscrete T=300+10*exp(-t).
        errors = []
        for dt in (.2, .1, .05):
            result = run_assembly_tetra_transient(one_dof(), settings(step=dt, output=1., initial=[300]*3 + [310]))
            expected_be = 300 + 10 * (1 + dt) ** (-round(1 / dt))
            self.assertAlmostEqual(result['node_temperatures_k'][3], expected_be, places=9)
            errors.append(abs(result['node_temperatures_k'][3] - (300 + 10 / math.e)))
            self.assertLess(abs(result['energy_balance']['imbalance_j']), 1e-8)
            self.assertLess(result['energy_balance']['temperature_reaction_inward_j'], 0)
        self.assertTrue(all(1.8 < a / b < 2.1 for a, b in zip(errors, errors[1:])), errors)

    def test_schedule_endpoint_integration_and_exact_nonregular_output(self):
        setup = settings(step=.3, output=.4)
        setup['power_schedule'] = [{'time_s': 0., 'scale': 0.}, {'time_s': .35, 'scale': 2.},
                                    {'time_s': 1., 'scale': 1.}]
        out = run_assembly_tetra_transient(insulated(), setup)
        times = [0., .3, .35, .4, .6, .8, .9, 1.]
        expected_j = sum(40 * np.interp(t, [0, .35, 1], [0, 2, 1]) * (t - a)
                         for a, t in zip(times, times[1:]))
        self.assertEqual([f['time_s'] for f in out['frames']], [0., .4, .8, 1.])
        self.assertAlmostEqual(out['energy_balance']['source_j'], expected_j, places=9)
        np.testing.assert_allclose(out['node_temperatures_k'], 300 + expected_j / 20, atol=1e-9)

    def test_disconnected_bodies_and_contact_exchange_conserve_energy(self):
        raw = contact_request()
        raw['boundaries'] = []
        setup = settings(duration=2., step=.1, output=.5, initial=[310.] * 8 + [300.] * 8)
        result = run_assembly_tetra_transient(raw, setup)
        self.assertLess(np.mean(result['node_temperatures_k'][:8]), 310.)
        self.assertGreater(np.mean(result['node_temperatures_k'][8:]), 300.)
        self.assertGreater(sum(c['left_to_right_heat_w'] for c in result['contacts']), 0)
        self.assertLess(abs(result['energy_balance']['stored_energy_change_j']), 1e-8)
        raw['contacts'] = []
        isolated = run_assembly_tetra_transient(raw, setup)
        np.testing.assert_allclose(isolated['node_temperatures_k'], setup['initial_temperature_k'], atol=1e-10)

    def test_roundoff_coincident_output_and_source_events(self):
        setup = settings(duration=.7, output=.2)
        setup['power_schedule'] = [{'time_s': 0., 'scale': 1.}, {'time_s': .6, 'scale': 2.},
                                    {'time_s': .7, 'scale': 1.}]
        out = run_assembly_tetra_transient(insulated(), setup)
        self.assertEqual([f['time_s'] for f in out['frames']], [0., .2, .4, .6, .7])
        out = run_assembly_tetra_transient(insulated(), settings(duration=.28, step=.04, output=.04))
        self.assertEqual(len(out['frames']), 8)

    def test_symmetric_tetra_radiation_matches_independent_scalar_heat_balance(self):
        raw = one_dof()
        raw['mesh']['vertices'] = [[0., 0., 0.], [1., 0., 0.], [.5, math.sqrt(3)/2, 0.],
                                    [.5, math.sqrt(3)/6, math.sqrt(2/3)]]
        raw['boundaries'] = boundary(exterior(raw['mesh']), 'radiation',
                                      emissivity=.8, radiation_temperature_k=300.)
        dt, duration = .005, .05
        volume, area = math.sqrt(2)/12, math.sqrt(3)
        expected = 400.
        for _ in range(round(duration/dt)):
            old, low, high = expected, 300., expected
            for _ in range(60):
                mid = (low + high)/2
                balance = 20*volume*(mid-old)/dt + .8*5.670374419e-8*area*(mid**4-300**4)
                if balance > 0:
                    high = mid
                else:
                    low = mid
            expected = (low+high)/2
        result = run_assembly_tetra_transient(raw, settings(duration=duration, step=dt, output=duration, initial=400.))
        np.testing.assert_allclose(result['node_temperatures_k'], expected, atol=1e-8, rtol=0)

    def test_convection_radiation_and_flux_full_energy_accounting(self):
        raw = insulated()
        faces = exterior(raw['mesh'])
        raw['boundaries'] = boundary(faces[:1], 'heat_flux', heat_flux_w_m2=2.)
        raw['boundaries'] += boundary(faces[1:], 'convection_radiation',
                                      heat_transfer_coefficient_w_m2k=2., ambient_temperature_k=300.,
                                      emissivity=.8, radiation_temperature_k=300.)
        out = run_assembly_tetra_transient(raw, settings(duration=.1, step=.01, output=.02, initial=400.))
        energy = out['energy_balance']
        # Consistent capacity has no nodal maximum principle on this coarse mesh.
        self.assertLess(np.mean(out['node_temperatures_k']), 400.)
        for key in ('source_j', 'prescribed_flux_inward_j', 'convection_outward_j', 'radiation_outward_j'):
            self.assertGreater(energy[key], 0., key)
        self.assertLess(energy['stored_energy_change_j'], 0.)
        self.assertLess(abs(energy['imbalance_j']), energy['acceptance_tolerance_j'])
        self.assertGreater(out['diagnostics']['newton_iterations'], 0)

    def test_input_and_work_budgets_fail_before_assembly(self):
        changes = [lambda s: s.update(duration_s=float('nan')), lambda s: s.update(time_step_s=0),
                   lambda s: s.update(time_step_s=1e-9), lambda s: s.update(output_interval_s=1e-9),
                   lambda s: s.update(initial_temperature_k=True), lambda s: s.update(initial_temperature_k=[300]),
                   lambda s: s.update(extra=True), lambda s: s['material_heat_capacity'][0].update(density_kg_m3=0),
                   lambda s: s['material_heat_capacity'][0].update(material_id='wrong'),
                   lambda s: s.update(power_schedule=[{'time_s': 0, 'scale': 1}, {'time_s': .5, 'scale': 2}]),
                   lambda s: s.update(power_schedule=[{'time_s': 0, 'scale': 1}, {'time_s': 1, 'scale': -1}])]
        for change in changes:
            setup = settings()
            change(setup)
            with self.subTest(change=change), patch('python.spike_core.assembly_tetra_transient._assemble') as assembly:
                with self.assertRaises(AssemblyTetraThermalError):
                    run_assembly_tetra_transient(insulated(), setup)
                assembly.assert_not_called()
        with self.assertRaisesRegex(AssemblyTetraThermalError, 'fixed boundary'):
            run_assembly_tetra_transient(one_dof(), settings(initial=301))
        with patch('python.spike_core.assembly_tetra_transient.MAX_FRAME_VALUES', 10):
            with self.assertRaisesRegex(AssemblyTetraThermalError, 'memory budget'):
                run_assembly_tetra_transient(insulated(), settings())

    def test_cancellation_and_nonconvergence_never_return_partial(self):
        with self.assertRaisesRegex(AssemblyTetraThermalError, 'cancelled'):
            run_assembly_tetra_transient(insulated(), settings(), cancel_check=lambda: True)
        frames = []
        with self.assertRaisesRegex(AssemblyTetraThermalError, 'cancelled'):
            run_assembly_tetra_transient(insulated(), settings(), progress_callback=frames.append,
                                          cancel_check=lambda: len(frames) >= 2)
        self.assertEqual(len(frames), 2)
        with patch('python.spike_core.assembly_tetra_transient.cg', return_value=(np.zeros(8), 1)):
            with self.assertRaisesRegex(AssemblyTetraThermalError, 'CG did not converge'):
                run_assembly_tetra_transient(insulated(), settings())

    def test_mixed_board_case_binding_and_saved_result_admission(self):
        raw, problem = fixture()
        problem['boundaries'] = []
        problem['heat_sources'] = [{'occurrence_id': 'board', 'cell_id': cell['id'], 'heat_source_w_m3': 40.}
                                    for cell in raw['bodies'][0]['mesh']['cells']]
        setup = settings(material='slab')
        remapped = validate_field_transient_settings(raw, problem, setup)
        self.assertEqual(len(remapped['material_heat_capacity']), 2)
        out = run_assembly_field_transient(raw, problem, setup)
        self.assertEqual(out['transient_settings'], setup)
        self.assertEqual(verify_assembly_field_transient_result(raw, problem, out), out)
        self.assertEqual(set(out['occurrence_temperatures']), {'board', 'case'})
        self.assertGreater(out['occurrence_temperatures']['case']['maximum_k'], 300.)
        for change in [lambda r: r['field_result']['frames'][1].update(time_s=.19),
                       lambda r: r['field_result']['frames'][0]['node_temperatures_k'].__setitem__(0, 301),
                       lambda r: r['field_result']['energy_balance'].update(imbalance_j=1e6),
                       lambda r: r['source_traceability'][0].update(occurrence_id='wrong'),
                       lambda r: r['transient_settings'].update(duration_s=2.),
                       lambda r: r['field_result'].update(temperature_units='C')]:
            altered = copy.deepcopy(out)
            change(altered)
            altered['result_digest'] = canonical_json_digest({k: v for k, v in altered.items() if k != 'result_digest'})
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_assembly_field_transient_result(raw, problem, altered)


if __name__ == '__main__':
    unittest.main()
