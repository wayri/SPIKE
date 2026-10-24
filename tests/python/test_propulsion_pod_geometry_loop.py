# SPDX-License-Identifier: Apache-2.0
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import nullcontext,contextmanager
from tests.python.test_propulsion_pod_energy_table import table
from python.spike_core.propulsion_pod_energy_table import PeriodicLinearMagneticPort
from python.spike_core.propulsion_pod_geometry_loop import run_geometry_loop
from python.spike_core.propulsion_pod_three_phase_run import DEFAULT_REQUEST


def nonlinear_port_fixture():
    """Manufactured convex law and geometry; no physical motor qualification."""
    import numpy as np
    from tests.python.test_propulsion_pod_separated_motor import fixture
    from python.spike_core.propulsion_pod_separated_motor import SeparatedMotor
    from python.spike_core.propulsion_pod_nonlinear_p2 import NonlinearP2MagneticOperator
    from python.spike_core.propulsion_pod_nonlinear_motor import NonlinearSeparatedMotor
    from python.spike_core.propulsion_pod_nonlinear_port import DirectNonlinearMagneticPort
    from python.spike_core.propulsion_pod_magnetic_p2 import MU0
    data=fixture();data['rotor']['materials']['steel']={'mu_r':2.}
    data['rotor']['solver_region_ids'][::3]=['steel']*4
    for name in ('rotor','stator'):
        data[name]['winding_chi_per_m2']=(1000*np.asarray(data[name]['winding_chi_per_m2'])).tolist()
    base=SeparatedMotor(data,stack_depth_m=.01,maximum_mode=2)
    nu=1/(2*MU0);curve=[[0.,0.],[.005,.005*nu],[2.,.005*nu+(2.-.005)*nu*5]]
    model=NonlinearSeparatedMotor(base,
        NonlinearP2MagneticOperator(base.rotor.op,{'steel':curve},quadrature_order=4),
        NonlinearP2MagneticOperator(base.stator.op,{'m':curve},quadrature_order=4),
        {name:data[name]['winding_chi_per_m2'] for name in ('rotor','stator')})
    return DirectNonlinearMagneticPort(model,maximum_phase_current_a=100.,maximum_seconds=30.,
        inverse_absolute_tolerance_wb_turn=1e-14,inverse_relative_tolerance=1e-12)


class GeometryLoopTests(unittest.TestCase):
    def test_actual_nonlinear_field_and_compiled_controller_complete_short_loop(self):
        port=nonlinear_port_fixture()
        r=copy.deepcopy(DEFAULT_REQUEST)
        r['transient'].update(duration_s=2e-5,time_step_s=1e-5,controller_period_s=2e-5,wall_budget_s=90.)
        r['drive']['current_limit_a']=100.
        scratch=Path(__file__).resolve().parents[2]/'output/.tmp';scratch.mkdir(exist_ok=True)
        with patch.object(tempfile,'tempdir',str(scratch)),patch.dict(os.environ,{'TMP':str(scratch),'TEMP':str(scratch)}):
            out=run_geometry_loop(port,lambda w:{'torque_nm':1e-6*w,'power_w':1e-6*w*w},
                initial_currents_a=[5.,-2.,-3.],initial_angle_rad=.2,initial_speed_rad_s=30.,
                thermal_spec={},drive=r['drive'],shaft=r['shaft'],transient=r['transient'])
        self.assertEqual(out['accepted_steps'],2)
        self.assertEqual(out['contract'],'spike/geometry-propulsion-direct-loop-result/v1')
        self.assertEqual(out['magnetic_port_sha256'],port.source_sha256)
        self.assertNotIn('field_table_sha256',out)
        self.assertLess(abs(out['energy']['defect_j']),1e-9)
        self.assertFalse(out['physical_load_qualified'])
        self.assertTrue(port.model.operators[0].materials)
        self.assertEqual(len(out['controller_executable_sha256']),64)

    def test_direct_deadline_scope_covers_initialization_and_restores_on_failure(self):
        class FailedInitialization:
            kind='direct-nonlinear-field-port/v1'
            active=False
            @contextmanager
            def bounded_run(self,deadline):
                self.deadline=deadline;self.active=True
                try:yield
                finally:self.active=False
            def phase_flux_angle_derivative(self,*args):raise AssertionError('Unexpected sensor')
            def flux_coordinates(self,*args):
                if not self.active:raise AssertionError('Initialization outside deadline')
                raise ValueError('Deliberate initialization failure')
        port=FailedInitialization()
        r=copy.deepcopy(DEFAULT_REQUEST)
        with self.assertRaisesRegex(ValueError,'Deliberate initialization'):
            run_geometry_loop(port,lambda w:{},initial_currents_a=[0.,0.,0.],initial_angle_rad=.2,
                initial_speed_rad_s=30.,thermal_spec={},drive=r['drive'],shaft=r['shaft'],transient=r['transient'])
        self.assertFalse(port.active)

    def test_explicit_direct_sensor_seam_uses_actual_controller_and_distinct_provenance(self):
        base=PeriodicLinearMagneticPort(table(),[.0002]*3)
        class DirectSensorFixture:
            # Interface fixture only: storage is the known linear Hamiltonian.
            kind='direct-nonlinear-field-port/v1'
            def __getattr__(self,name):
                if name in ('L','psi'):raise AssertionError('Linear sensor interface used')
                return getattr(base,name)
            def phase_flux_angle_derivative(self,currents,theta):
                return [.003,-.002,-.001]
            def bounded_run(self,deadline):return nullcontext()
        r=copy.deepcopy(DEFAULT_REQUEST);r['transient']['duration_s']=.001
        scratch=Path(__file__).resolve().parents[2]/'output/.tmp';scratch.mkdir(exist_ok=True)
        with patch.object(tempfile,'tempdir',str(scratch)),patch.dict(os.environ,{'TMP':str(scratch),'TEMP':str(scratch)}):
            out=run_geometry_loop(DirectSensorFixture(),
                lambda w:{'torque_nm':1e-6*w,'power_w':1e-6*w*w},
                initial_currents_a=[0.,0.,0.],initial_angle_rad=.2,initial_speed_rad_s=30.,
                thermal_spec={},drive=r['drive'],shaft=r['shaft'],transient=r['transient'])
        self.assertEqual(out['contract'],'spike/geometry-propulsion-direct-loop-result/v1')
        self.assertNotIn('field_table_sha256',out)
        self.assertEqual(out['magnetic_port_sha256'],base.source_sha256)
        self.assertEqual(out['accepted_steps'],10)
        self.assertLess(abs(out['energy']['defect_j']),1e-9)
        for tick in out['controller_events']:
            self.assertEqual([tick['sensors']['dpsi_'+name] for name in 'abc'],[.003,-.002,-.001])
        self.assertEqual(len(out['controller_executable_sha256']),64)

    def test_linear_sensor_derivative_and_envelope(self):
        port=PeriodicLinearMagneticPort(table(),[.0002]*3)
        currents=[1.,-.25,-.75];theta=.23
        import numpy as np
        np.testing.assert_allclose(port.phase_flux_angle_derivative(currents,theta),
                                   port.L(theta,1)@currents+port.psi(theta,1),rtol=0,atol=0)
        for invalid in ([1.,0.,0.],[float('nan'),0.,0.],[1e9,-1e9,0.]):
            with self.assertRaises(ValueError):port.phase_flux_angle_derivative(invalid,theta)

    def test_actual_compiled_controller_uses_general_field_port(self):
        scratch=Path(__file__).resolve().parents[2]/'output/.tmp';scratch.mkdir(exist_ok=True)
        before_temp=tempfile.tempdir;before_env={k:os.environ.get(k) for k in ('TMP','TEMP')}
        try:
            tempfile.tempdir=str(scratch)
            for key in before_env:os.environ[key]=str(scratch)
            r=copy.deepcopy(DEFAULT_REQUEST);r['transient']['duration_s']=.001
            out=run_geometry_loop(PeriodicLinearMagneticPort(table(),[.0002]*3),
                lambda w:{'torque_nm':1e-6*w,'power_w':1e-6*w*w},
                initial_currents_a=[0.,0.,0.],initial_angle_rad=.2,initial_speed_rad_s=30.,
                thermal_spec={},drive=r['drive'],shaft=r['shaft'],transient=r['transient'])
            self.assertEqual(out['accepted_steps'],10);self.assertEqual(out['controller_ticks'],2)
            self.assertEqual(len(out['controller_executable_sha256']),64)
            self.assertLess(abs(out['energy']['defect_j']),1e-9)
            self.assertFalse(out['physical_load_qualified'])
            self.assertTrue(all(abs(sum(s['currents_a']))<1e-12 for s in out['history']))
        finally:
            tempfile.tempdir=before_temp
            for key,value in before_env.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value


if __name__=='__main__':unittest.main()
