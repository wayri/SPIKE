# SPDX-License-Identifier: Apache-2.0
"""Admission and cancellation checks for the experimental assembly CFD route."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from python.spike_core.assembly_airflow import validate_request, run_assembly_airflow, prepare_airflow_case


def request():
    shape = {'kind': 'polygon_prism', 'outer_mm': [[0,0],[1,0],[1,1],[0,1]],
             'holes_mm': [], 'z_min_mm': 0, 'z_max_mm': 1}
    air = copy.deepcopy(shape)
    air.update(outer_mm=[[-1,-1],[2,-1],[2,2],[-1,2]], z_min_mm=-1, z_max_mm=2)
    return {'contract': 'spike/assembly-airflow-request/v1',
        'geometry': {'solids': [{'id': 'board', 'material_id': 'board', 'priority': 0, 'shape': shape}],
                     'air_domain': air, 'mesh': {'min_size_mm': .5, 'max_size_mm': 1, 'max_cells': 10000, 'max_vertices': 10000}},
        'materials': [{'id':'board','phase':'solid','conductivity_w_mk':1,'density_kg_m3':1000,'specific_heat_j_kgk':1000},
                      {'id':'air','phase':'fluid','conductivity_w_mk':.026,'density_kg_m3':1.2,'specific_heat_j_kgk':1006,'dynamic_viscosity_pa_s':1.8e-5}],
        'region_properties': {'board': {'role': 'board', 'power_w': 1}}, 'mode': 'static',
        'ambient_temperature_k':298.15,'numerics':{'end_time_s':1,'delta_t_s':.1,'write_interval_steps':10,'validation_interval_steps':1}}


class AssemblyAirflowTest(unittest.TestCase):
    def test_compact_region_points_and_explicit_heatsink_mount(self):
        from tests.python.test_assembly_tetra_thermal import cube
        from python.spike_core.openfoam_polymesh import write_polymesh
        r = request()
        r['geometry']['solids'].append({**copy.deepcopy(r['geometry']['solids'][0]), 'id': 'sink'})
        r['region_properties']['sink'] = {'role': 'heatsink', 'power_w': 0}
        mesh = cube(unit='mm')
        for index, cell in enumerate(mesh['cells']):
            cell['material_id'] = ('solid_0', 'solid_1', 'air')[index // 2]
        mesh['volumes_mm3'] = {'solid_0': 1/3, 'solid_1': 1/3, 'air': 1/3}
        mesh['cad_volumes_mm3'] = {'solid_0': 1/3, 'solid_1': 1/3}
        mesh['source_ids'] = {'solid_0': 'board', 'solid_1': 'sink'}
        before = copy.deepcopy(mesh)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'acknowledge perfect'):
                prepare_airflow_case(r, mesh, folder)
            r['perfect_solid_contact_acknowledged'] = True
            with patch('python.spike_core.assembly_airflow.write_polymesh', wraps=write_polymesh) as write:
                result = prepare_airflow_case(r, mesh, folder)
            self.assertEqual(result['status'], 'prepared_runnable_case')
            for call in write.call_args_list:
                job = call.args[0]
                points = job['mesh']['vertices']
                self.assertLess(len(points), len(mesh['vertices']))
                self.assertEqual({v for c in job['mesh']['cells'] for v in c['vertices']}, set(range(len(points))))
                self.assertTrue(all(0 <= v < len(points) for p in job['boundary_patches'] for f in p['faces'] for v in f))
            translated = json.loads((Path(folder)/'translated-request.json').read_text())
            mounts = translated['heatsinks']
            self.assertEqual(len(mounts), 1)
            self.assertEqual(mounts[0]['region_id'], 'solid_1')
            interface = next(i for i in translated['interfaces'] if i['id'] == mounts[0]['mount_interface_id'])
            self.assertEqual({interface['region_a'], interface['region_b']}, {'solid_0', 'solid_1'})
        self.assertEqual(mesh, before)

    def test_heatsink_without_solid_mount_fails(self):
        from tests.python.test_assembly_tetra_thermal import cube
        r = request()
        r['region_properties']['board']['role'] = 'heatsink'
        mesh = cube(unit='mm')
        for index, cell in enumerate(mesh['cells']):
            cell['material_id'] = 'solid_0' if index < 3 else 'air'
        mesh['volumes_mm3'] = {'solid_0': 0.5, 'air': 0.5}
        mesh['cad_volumes_mm3'] = {'solid_0': .5}
        mesh['source_ids'] = {'solid_0': 'board'}
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError, 'shared solid mounting'):
            prepare_airflow_case(r, mesh, folder)

    def test_natural_requires_density(self):
        r=request(); r['mode']='natural'
        with self.assertRaisesRegex(ValueError, 'density'):
            validate_request(r)

    def test_forced_requires_distinct_planes(self):
        r=request(); r.update(mode='forced', flow_rate_m3_s=1e-6,
            inlet={'axis':0,'coordinate_mm':-1}, outlet={'axis':0,'coordinate_mm':-1})
        with self.assertRaisesRegex(ValueError, 'differ'):
            validate_request(r)

    def test_material_power_and_identity_admission(self):
        for mutate in (lambda r:r['region_properties']['board'].update(power_w=float('nan')),
                       lambda r:r['materials'].append(r['materials'][0]),
                       lambda r:r['geometry']['solids'].append(r['geometry']['solids'][0])):
            r=request(); mutate(r)
            with self.assertRaises(ValueError):
                validate_request(r)

    def test_precancel_creates_no_artifacts(self):
        event=threading.Event(); event.set()
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'case'
            result=run_assembly_airflow(request(), target, cancellation_event=event)
            self.assertEqual(result['status'], 'cancelled')
            self.assertFalse(target.exists())

    def test_rigid_transform_admitted(self):
        r=request()
        r['geometry']['solids'][0]['transform']=[1,0,0,1,0,1,0,2,0,0,1,3,0,0,0,1]
        validate_request(r)
        r['geometry']['solids'][0]['transform'][0]=2
        with self.assertRaises(ValueError):
            validate_request(r)
