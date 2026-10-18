# SPDX-License-Identifier: Apache-2.0
"""Original analytical half-cube source mapping and refinement oracles."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.assembly_airflow import prepare_airflow_case, run_assembly_airflow
from python.spike_core.assembly_airflow_admission import admit_airflow_mesh
from tests.python.test_assembly_airflow import request
from tests.python.test_assembly_tetra_thermal import cube


def fixture(n=2):
    job = request()
    shape = job['geometry']['solids'][0]['shape']
    shape['outer_mm'] = [[0, 0], [.5, 0], [.5, 1], [0, 1]]
    job['geometry']['air_domain'] = {**copy.deepcopy(shape),
        'outer_mm': [[0, 0], [1, 0], [1, 1], [0, 1]]}
    job['region_properties']['board']['power_w'] = 3.25
    mesh = cube(n, unit='mm')
    for cell in mesh['cells']:
        x = sum(mesh['vertices'][v][0] for v in cell['vertices']) / 4
        cell['material_id'] = 'solid_0' if x < .5 else 'air'
    mesh.update(source_ids={'solid_0': 'board'}, cad_volumes_mm3={'solid_0': .5},
                volumes_mm3={'solid_0': .5, 'air': .5})
    return job, mesh


class AirflowSourceConservationTests(unittest.TestCase):
    def test_analytical_volume_and_watts_are_invariant_on_three_refinements(self):
        for n in (2, 4, 8):
            with self.subTest(cells_per_axis=n), tempfile.TemporaryDirectory() as directory:
                job, mesh = fixture(n)
                original = copy.deepcopy(mesh)
                result = prepare_airflow_case(job, mesh, directory)
                self.assertEqual(result['status'], 'prepared_runnable_case')
                report = result['source_coupling']
                self.assertAlmostEqual(report['region_volumes_m3']['solid_0'], .5e-9, delta=1e-23)
                self.assertAlmostEqual(report['sources'][0]['integrated_power_w'], 3.25, delta=1e-13)
                translated = json.loads((Path(directory) / 'translated-request.json').read_text())
                density = translated['heat_sources'][0]['fv_option']['volumetric_power_w_m3']
                self.assertAlmostEqual(density, 6.5e9, delta=1e-5)
                self.assertEqual(report['solver_convergence'], 'not_evaluated')
                self.assertEqual(report['heat_flow_balance'], 'not_evaluated')
                self.assertEqual(mesh, original)

    def test_tolerated_volume_roundoff_never_changes_applied_power(self):
        job, mesh = fixture()
        mesh['volumes_mm3']['solid_0'] *= 1 + 5e-10
        self.assertEqual(admit_airflow_mesh(job, mesh)['solid_0'], .5)

    def test_failed_admission_writes_no_case(self):
        def invert(mesh):
            nodes = mesh['cells'][0]['vertices']
            nodes[0], nodes[1] = nodes[1], nodes[0]

        mutations = {
            'stale source': lambda m: m['source_ids'].update(solid_0='another_board'),
            'missing source': lambda m: m.pop('source_ids'),
            'wrong units': lambda m: m.update(units='m'),
            'wrong volume': lambda m: m['volumes_mm3'].update(solid_0=1),
            'bad cad fit': lambda m: m['cad_volumes_mm3'].update(solid_0=.7),
            'missing solid': lambda m: m.update(cells=[c for c in m['cells'] if c['material_id'] == 'air']),
            'unknown region': lambda m: m['cells'][0].update(material_id='solid_1'),
            'duplicate cell': lambda m: m['cells'].append({**m['cells'][0], 'id': 'different'}),
            'bad vertex': lambda m: m['cells'][0]['vertices'].__setitem__(0, True),
            'nonfinite point': lambda m: m['vertices'][0].__setitem__(0, float('nan')),
            'inverted': invert,
            'degenerate': lambda m: m['cells'][0]['vertices'].__setitem__(0, m['cells'][0]['vertices'][1]),
            'extra region volume': lambda m: m['volumes_mm3'].update(solid_1=1),
            'nonfinite volume': lambda m: m['volumes_mm3'].update(air=float('inf')),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                job, mesh = fixture()
                mutate(mesh)
                with self.assertRaises(ValueError):
                    prepare_airflow_case(job, mesh, directory)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_nonconverged_native_result_retains_failure_and_source_evidence(self):
        job, mesh = fixture()
        with tempfile.TemporaryDirectory() as directory, \
             patch('python.spike_core.assembly_airflow.run_air_mesh', return_value=mesh), \
             patch('python.spike_core.assembly_airflow.run_multiregion_case',
                   return_value={'status': 'failed_to_converge', 'fields': {}}):
            result = run_assembly_airflow(job, Path(directory) / 'run')
            self.assertEqual(result['status'], 'failed_to_converge')
            self.assertEqual(result['fields'], {})
            self.assertFalse(result['production_qualified'])
            self.assertAlmostEqual(result['source_coupling']['sources'][0]['integrated_power_w'], 3.25)


if __name__ == '__main__':
    unittest.main()
