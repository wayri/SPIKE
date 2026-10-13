# SPDX-License-Identifier: Apache-2.0
"""Independent three-layer conduction fixture for SU2 CHT result admission."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from python.spike_core.su2_cht import compile_su2_cht, parse_su2_cht, prepare_su2_cht, validate_su2_cht_request
from python.spike_core.su2_airflow import _sha256
from scripts.benchmark_su2_cht import _resume


class Su2ChtTests(unittest.TestCase):
    def test_rejects_invalid_request(self):
        for request in ({'cells':10},{'cells':True},{'lid_speed':float('nan')},{'lid_speed':2},
                        {'executable':'bad'},{'outer_iterations':1},{'timeout_s':1801}):
            with self.subTest(request=request),self.assertRaises(ValueError):
                validate_su2_cht_request(request)

    def test_compiler_pairs_interface_and_enables_energy(self):
        files = compile_su2_cht({'cells':8})
        self.assertIn('NZONE= 3\nIZONE= 1',files['cht.su2'])
        self.assertIn('IZONE= 2',files['cht.su2'])
        self.assertIn('MARKER_ZONE_INTERFACE= (fluid_join, solid_join, cold_lid, cold_join)',files['cht.cfg'])
        self.assertIn('INC_ENERGY_EQUATION= YES',files['fluid.cfg'])
        self.assertNotIn('MARKER_ISOTHERMAL',files['fluid.cfg'])
        self.assertIn('MARKER_ISOTHERMAL= (cold_top, 300.0)',files['cold_solid.cfg'])
        self.assertIn('BGS_ENTHALPY[0]',files['cht.cfg'])
        self.assertIn('BGS_TEMPERATURE[1]',files['cht.cfg'])
        self.assertIn('BGS_TEMPERATURE[2]',files['cht.cfg'])
        self.assertIn('SOLVER= HEAT_EQUATION',files['solid.cfg'])
        self.assertIn('FREESTREAM_TEMPERATURE= 1',files['solid.cfg'])
        self.assertEqual(prepare_su2_cht({})['materials']['solid']['conductivity_w_m_k'],.1)
        self.assertEqual(prepare_su2_cht({})['geometry']['cold_solid_bounds_m'],[[0,1],[1,1.25]])

    def _fixture(self,directory,n=8):
        q = 10/(2*.25/.1+1/.01)
        fluid = []
        for zone,ny,y0 in [('fluid',n,0),('solid',n//4,-.25),('cold_solid',n//4,1)]:
            rows = []
            for j in range(ny+1):
                for i in range(n+1):
                    x,y = i/n,y0+j/n
                    t = (300+q*(.25/.1+(1-y)/.01) if zone=='fluid' else
                         310-q*(y+.25)/.1 if zone=='solid' else 300+q*(1.25-y)/.1)
                    rows.append([j*(n+1)+i,x,y,0,0,t] if zone=='fluid' else [j*(n+1)+i,x,y,t])
            path = Path(directory)/{'fluid':'fluid_0.csv','solid':'solid_1.csv','cold_solid':'cold_solid_2.csv'}[zone]
            with path.open('w',newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(['PointID','x','y','Velocity_x','Velocity_y','Temperature'] if zone=='fluid' else
                                ['PointID','x','y','Temperature'])
                writer.writerows(rows)
            if zone=='fluid':
                fluid = rows
        vtk = f'POINTS {len(fluid)} double\n'+' '.join(f'{row[1]} {row[2]} 0' for row in fluid)
        vtk += '\nCELLS 0 0\nSCALARS Temperature double 1\nLOOKUP_TABLE default\n'
        vtk += ' '.join(str(row[-1]) for row in fluid)
        (Path(directory)/'fluid_fields_0.vtk').write_text(vtk)
        (Path(directory)/'cht.csv').write_text('"bgs[P][0]","bgs[U][0]","bgs[V][0]","bgs[h][0]","bgs[T][1]","bgs[T][2]"\n-12,-12,-12,-12,-12,-12\n')

    def test_exact_conduction_flux_and_temperature_continuity(self):
        with tempfile.TemporaryDirectory() as directory:
            self._fixture(directory)
            result = parse_su2_cht(directory,{'cells':8})
            d = result['diagnostics']
            self.assertAlmostEqual(d['heat_input_w_per_m'],10/105,places=11)
            self.assertLess(d['interface_temperature_jump_k'],1e-10)
            self.assertLess(d['interface_flux_relative_error'],1e-10)
            self.assertLess(d['cold_interface_temperature_jump_k'],1e-10)
            self.assertLess(d['cold_interface_flux_relative_error'],1e-10)
            self.assertLess(d['global_energy_relative_error'],1e-10)
            self.assertTrue(result['convergence']['converged'])
            self.assertTrue(result['validation']['passed'])

    def test_converged_bad_cold_boundary_is_not_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            self._fixture(directory)
            path = Path(directory)/'cold_solid_2.csv'
            path.write_text(path.read_text().replace('300.0','299.9'))
            result = parse_su2_cht(directory,{'cells':8})
            self.assertTrue(result['convergence']['converged'])
            self.assertFalse(result['validation']['passed'])
            self.assertGreaterEqual(len(result['validation']['violations']),2)

    def test_thermal_residual_failure_is_not_hidden_by_converged_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            self._fixture(directory)
            path = Path(directory)/'cht.csv'
            path.write_text(path.read_text().replace('-12,-12,-12,-12,-12','-12,-12,-12,-2,-12'))
            self.assertFalse(parse_su2_cht(directory,{'cells':8})['convergence']['converged'])

    def test_resume_revalidates_and_rejects_changed_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._fixture(root)
            request = validate_su2_cht_request({'cells':8,'lid_speed':0})
            compiled = compile_su2_cht(request)
            for name,content in compiled.items():
                (root/name).write_text(content,encoding='ascii')
            executable = root/'synthetic-runtime'
            executable.write_bytes(b'identity only, never executed')
            outputs = ['fluid_0.csv','solid_1.csv','cold_solid_2.csv','fluid_fields_0.vtk','cht.csv']
            result = {'request':request,'provenance':{'run_directory':str(root),
                      'executable_sha256':_sha256(executable),
                      'input_sha256':{name:_sha256(root/name) for name in compiled},
                      'output_sha256':{name:_sha256(root/name) for name in outputs}}}
            path = root/'result.json'
            path.write_text(json.dumps(result))
            self.assertEqual(_resume(path,8,0,executable)['status'],'completed')
            (root/'cht.csv').write_text('changed output')
            with self.assertRaisesRegex(ValueError,'output changed'):
                _resume(path,8,0,executable)

    def test_rejects_malformed_or_mismatched_thermal_fields(self):
        for defect in ('nonfinite','missing','mesh','scale'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as directory:
                self._fixture(directory)
                vtk = Path(directory)/'fluid_fields_0.vtk'
                if defect=='nonfinite':
                    vtk.write_text(vtk.read_text()+' nan')
                elif defect=='missing':
                    vtk.write_text(vtk.read_text().replace('SCALARS Temperature','SCALARS Unknown'))
                elif defect=='mesh':
                    vtk.write_text(vtk.read_text().replace('0.0 0.0 0','0.1 0.0 0',1))
                else:
                    path = Path(directory)/'solid_1.csv'
                    path.write_text(path.read_text().replace('310.0','1.075'))
                with self.assertRaises(ValueError):
                    parse_su2_cht(directory,{'cells':8})


if __name__=='__main__':
    unittest.main()
