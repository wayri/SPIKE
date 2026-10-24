# SPDX-License-Identifier: Apache-2.0
"""Actual compiled-controller output crosses the saved-result UI boundary.

Magnetic/CFD ports below are explicit test fixtures, not real-hardware studies.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from tests.python.test_propulsion_pod_energy_table import table
from python.spike_core.propulsion_pod_energy_table import PeriodicLinearMagneticPort
from python.spike_core.propulsion_pod_load_table import CfdLoadTable,CONTRACT
from python.spike_core.service_propulsion_pod import handle_propulsion_pod_request
from python.spike_core.propulsion_pod_three_phase_run import DEFAULT_REQUEST


class CaptureBridgeTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node is required for the actual UI admission check')
    def test_compiled_controller_multistep_output_is_admitted_by_actual_ui_parser(self):
        root=Path(__file__).resolve().parents[2]
        scratch=root/'output/.tmp';scratch.mkdir(exist_ok=True)
        old_temp=tempfile.tempdir;old_env={key:os.environ.get(key) for key in ('TMP','TEMP')}
        try:
            tempfile.tempdir=str(scratch)
            for key in old_env:os.environ[key]=str(scratch)
            request=copy.deepcopy(DEFAULT_REQUEST);request['transient']['duration_s']=.003
            load=CfdLoadTable({'contract':CONTRACT,'geometry_sha256':'a'*64,'physics_sha256':'b'*64,
                'evidence':{'test_fixture_only':True},'anchors':[{'omega_rad_s':w,'torque_nm':w*1e-6,
                'thrust_n':w*1e-5,'case_sha256':str(j)*64} for j,w in enumerate((0.,30.,60.))]})
            request['transient'].update(target_speed_rad_s=35.,maximum_speed_rad_s=50.)
            request['transient'].pop('field_output_interval_s')
            magnetic=PeriodicLinearMagneticPort(table(),[.0002]*3)
            response=handle_propulsion_pod_request('run_propulsion_pod_geometry',{
                'request':{'initial_currents_a':[0.,0.,0.],'initial_angle_rad':.2,'initial_speed_rad_s':30.,
                    'thermal':{},'drive':request['drive'],'shaft':{k:request['shaft'][k] for k in ('inertia_kg_m2','damping_n_m_s')},
                    'transient':request['transient']},'magnetic_table':magnetic.table,'cfd_table':load.table,
                'expected_field_sha256':magnetic.source_sha256,'expected_fluid_sha256':load.source_sha256})
            self.assertTrue(response['ok'],response)
            out=response['result']
            self.assertEqual(out['accepted_steps'],30)
            self.assertLess(abs(out['energy']['defect_j']),1e-9)
            with tempfile.TemporaryDirectory(prefix='capture-bridge-',dir=scratch) as temporary:
                path=Path(temporary)/'fixture-controller-result.json'
                path.write_text(json.dumps(out,allow_nan=False),encoding='utf-8')
                checked=subprocess.run([shutil.which('node'),str(root/'app/scripts/check-geometry-pod-capture.mjs'),str(path)],
                    cwd=root,capture_output=True,text=True,timeout=60,check=True)
                receipt=json.loads(checked.stdout)
                self.assertEqual(receipt['capture_admission'],'passed')
                self.assertEqual(receipt['accepted_steps'],30)
                self.assertFalse(receipt['gui_verified'])
        finally:
            tempfile.tempdir=old_temp
            for key,value in old_env.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value


if __name__=='__main__':unittest.main()
