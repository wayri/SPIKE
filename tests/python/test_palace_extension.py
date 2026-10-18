# SPDX-License-Identifier: Apache-2.0
"""Original Palace adapter behavior checks; no solver accuracy assertions."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from extensions.palace_suite import runtime
from extensions.palace_suite.extension import execute

class PalaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.mesh=self.root/'owned.mesh'
        self.mesh.write_text('SPIKE test-owned mesh token; not a numerical mesh')
        self.params={'config':{'Problem':{'Type':'Driven'},'Model':{'Mesh':'ignored','L0':0.001},
            'Domains':{'Materials':[{'Attributes':[1],'Permittivity':2.5}]},'Boundaries':{},'Solver':{}},
            'mesh_path':str(self.mesh)}
        self.binding={'design_id':'test','digest_sha256':'d'*64}
        self.state=patch.object(runtime,'_state_root',return_value=self.root/'state')
        self.state.start()
    def tearDown(self):
        self.state.stop()
        self.temp.cleanup()
    def request(self,op,params=None):
        return {'contract':'spike/extension/v1','contribution_id':'palace-'+op,
            'context':{'parameters':params or self.params,'design_binding':self.binding}}
    def test_all_documented_types_and_units(self):
        for mode in runtime.PROBLEM_TYPES:
            self.params['config']['Problem']['Type']=mode
            self.assertEqual(runtime.validate(self.params)['status'],'ready_to_run')
        del self.params['config']['Model']['L0']
        with self.assertRaisesRegex(ValueError,'PALACE_UNITS'):
            runtime.validate(self.params)
    def test_stale_mesh_and_unknown_parameters(self):
        self.params['expected_mesh_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'PALACE_SOURCE'):
            runtime.validate(self.params)
        with self.assertRaisesRegex(ValueError,'unknown parameters'):
            execute(self.request('discover',{'command':'evil'}))
    def test_unsupported_assets_and_problem(self):
        self.params['config']['Model']['Partitioning']='outside.dat'
        self.assertEqual(runtime.validate(self.params)['status'],'unsupported')
        del self.params['config']['Model']['Partitioning']
        self.params['config']['Problem']['Type']='Unknown'
        self.assertEqual(runtime.validate(self.params)['status'],'unsupported')
    def test_prepared_inputs_bound_and_output_preserved(self):
        case=runtime.prepare(self.params,self.binding)
        job=runtime.job_path(case['job_id'])
        config=json.loads((job/'config.json').read_text())
        self.assertEqual(config['Problem']['Output'],'output')
        self.assertEqual(config['Model']['Mesh'],'input.mesh')
        output=job/'output'
        output.mkdir()
        (output/'port-S.csv').write_text('f [GHz],S dB,phase deg\n1,-3.5,45\n2,NaN,90\n')
        (output/'field.vtu').write_bytes(b'test-owned binary field artifact')
        (job/'completion.json').write_text('{"return_code":0}')
        result=runtime.import_outputs(case['job_id'],self.binding)
        self.assertEqual(result['tables'][0]['rows'][1][1],'NaN')
        self.assertEqual(result['model_status'],'experimental')
        self.assertTrue(any(item['kind']=='field' for item in result['artifacts']))
        with self.assertRaisesRegex(ValueError,'another design'):
            runtime.import_outputs(case['job_id'],{'design_id':'other','digest_sha256':'e'*64})
        (job/'input.mesh').write_text('changed')
        with self.assertRaisesRegex(ValueError,'input changed'):
            runtime.import_outputs(case['job_id'],self.binding)
    def test_failed_empty_and_malformed_csv(self):
        case=runtime.prepare(self.params,self.binding)
        job=runtime.job_path(case['job_id'])
        (job/'completion.json').write_text('{"return_code":1}')
        with self.assertRaisesRegex(ValueError,'incomplete'):
            runtime.import_outputs(case['job_id'],self.binding)
        (job/'completion.json').write_text('{"return_code":0}')
        output=job/'output'
        output.mkdir()
        with self.assertRaisesRegex(ValueError,'no scalar'):
            runtime.import_outputs(case['job_id'],self.binding)
        (output/'owned.csv').write_text('a,b\n1\n')
        with self.assertRaisesRegex(ValueError,'column count'):
            runtime.import_outputs(case['job_id'],self.binding)
    def test_safe_contained_command_and_cancellation(self):
        self.params['runtime_path']=str(Path(__import__('sys').executable))
        self.params['expected_mesh_sha256']=runtime.digest(self.mesh.read_bytes())
        event=threading.Event()
        event.set()
        with patch.object(runtime,'run_adapter_process',side_effect=RuntimeError('cancelled')) as process:
            result=runtime.run(self.params,self.binding,event)
        self.assertEqual(result['status'],'cancelled')
        self.assertEqual(process.call_args.args[0], [self.params['runtime_path'],'config.json'])
        self.assertIs(process.call_args.kwargs['cancellation_event'],event)
    def test_strict_json_and_job_traversal(self):
        for text in ['{"a":1,"a":2}','{"a":NaN}']:
            with self.assertRaises(ValueError):
                runtime.strict_json(text)
        with self.assertRaisesRegex(ValueError,'invalid job'):
            runtime.job_path('../escape')

if __name__=='__main__':
    unittest.main()

class PalaceProcessTests(unittest.TestCase):
    def test_native_vtk_exact_point_values(self):
        try:
            from vtkmodules.vtkCommonCore import vtkPoints, vtkDoubleArray
            from vtkmodules.vtkCommonDataModel import vtkUnstructuredGrid, vtkVertex
            from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridWriter
        except ImportError:
            self.skipTest('VTK not installed')
        from extensions.palace_suite.field_preview import preview
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'owned.vtu'
            points=vtkPoints()
            points.InsertNextPoint(1,2,3)
            points.InsertNextPoint(4,5,6)
            grid=vtkUnstructuredGrid()
            grid.SetPoints(points)
            field=vtkDoubleArray()
            field.SetName('E_real')
            field.SetNumberOfComponents(3)
            field.InsertNextTuple3(2,3,4)
            field.InsertNextTuple3(5,6,7)
            grid.GetPointData().AddArray(field)
            for index in range(2):
                vertex=vtkVertex()
                vertex.GetPointIds().SetId(0,index)
                grid.InsertNextCell(vertex.GetCellType(),vertex.GetPointIds())
            writer=vtkXMLUnstructuredGridWriter()
            writer.SetFileName(str(path))
            writer.SetInputData(grid)
            writer.SetDataModeToAppended()
            writer.EncodeAppendedDataOff()
            self.assertEqual(writer.Write(),1)
            result=preview(path)
            self.assertEqual(result['status'],'available')
            self.assertEqual(result['points'],[[1.0,2.0,3.0],[4.0,5.0,6.0]])
            self.assertEqual(result['arrays'][0]['values'],[[2.0,3.0,4.0],[5.0,6.0,7.0]])
            self.assertEqual(result['arrays'][0]['units'],'V/m')
    def test_guardian_reaps_native_child_when_wrapper_dies(self):
        import subprocess
        import sys
        import time
        project=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            control=Path(directory)
            driver=control/'driver.py'
            driver.write_text('import sys\nsys.path.insert(0,'+repr(str(project))+')\n'
                'from extensions.palace_suite import guardian\n'
                'from python.spike_core.sparselizard_process import run_adapter_process\n'
                'from pathlib import Path\n'
                'def owned_fixture(params,binding,event):\n'
                ' try:\n'
                '  run_adapter_process([sys.executable,"-c","import time; time.sleep(60)"],cwd=Path(sys.argv[1]),timeout_s=30,memory_limit_mb=256,output_limit_bytes=1024,stream_limit_bytes=1024,cancellation_event=event,windows_active_process_limit=8)\n'
                ' except RuntimeError:\n'
                '  return {"status":"cancelled" if event.is_set() else "failed"}\n'
                ' return {"status":"completed"}\n'
                'guardian.runtime.run=owned_fixture\nguardian.main()\n')
            wrapper=control/'wrapper.py'
            wrapper.write_text('import os,json,subprocess,sys,time\nfrom pathlib import Path\n'
                'control=Path(sys.argv[1])\n'
                '(control/"request.json").write_text(json.dumps({"owner_pid":os.getpid(),"parameters":{},"binding":{}}))\n'
                'p=subprocess.Popen([sys.executable,str(control/"driver.py"),str(control)],start_new_session=os.name!="nt")\n'
                '(control/"guardian.pid").write_text(str(p.pid))\ntime.sleep(60)\n')
            process=subprocess.Popen([sys.executable,str(wrapper),str(control)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                deadline=time.monotonic()+10
                while not (control/'guardian.pid').exists() and time.monotonic()<deadline:
                    time.sleep(0.05)
                self.assertTrue((control/'guardian.pid').exists())
                time.sleep(1)
                process.terminate()
                process.wait(timeout=5)
                deadline=time.monotonic()+15
                while not (control/'result.json').exists() and time.monotonic()<deadline:
                    time.sleep(0.1)
                self.assertTrue((control/'result.json').exists(),'Guardian did not reap its native child after parent death')
                self.assertEqual(json.loads((control/'result.json').read_text())['status'],'cancelled')
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)


class PalaceDispatchTests(unittest.TestCase):
    def test_frozen_child_uses_supported_worker_extension_host(self):
        import sys
        with patch.object(sys,'frozen',True,create=True):
            self.assertEqual(runtime.python_command(Path('guardian.py'),'owned'),
                [sys.executable,'--extension-host','guardian.py','owned'])
    def test_native_dry_run_never_imports_solved_data(self):
        with tempfile.TemporaryDirectory() as directory:
            mesh=Path(directory)/'own.mesh'
            mesh.write_bytes(b'original inert mesh fixture')
            binding={'design_id':'test','digest_sha256':'d'*64}
            params={'config':{'Problem':{'Type':'Electrostatic'},'Model':{'L0':1},
                'Domains':{'Materials':[{'Attributes':[1]}]},'Boundaries':{},'Solver':{}},'mesh_path':str(mesh)}
            with patch.object(runtime,'_state_root',return_value=Path(directory)/'state'), \
                 patch.object(runtime,'runtime_info',return_value={'available':True,'path':str(Path(directory)/'palace.exe')}), \
                 patch.object(runtime,'run_adapter_process',return_value={'return_code':0,'stdout':'owned resolved config','stderr':''}) as process:
                result=runtime.native_validate(params,binding)
            self.assertFalse(result['solved'])
            self.assertEqual(result['status'],'ready_to_run')
            self.assertIn('--dry-run',process.call_args.args[0])
            self.assertLessEqual(process.call_args.kwargs['timeout_s'],120)
            self.assertNotIn('tables',result)

if __name__=='__main__':
    unittest.main()

