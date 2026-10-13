# SPDX-License-Identifier: Apache-2.0
import copy
from contextlib import redirect_stdout,redirect_stderr
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from python.spikes.equation_device import CONTRACT,build
from python.spikes.netlist import parse_netlist
from python.spikes.native_abi import load_native_library
from python.spikes.native_runner import _populate
from python.spikes.cli import main
from python.spikes.device_parasitics import compose_device_parasitics


def specification():
    return dict(contract=CONTRACT,name='FUTURE',material='illustrative diamond candidate, not qualified',
                pins=['P','N'],parameters={'g':dict(value=.001,unit='S'),'c':dict(value=1e-9,unit='F')},
                branches=[dict(name='channel',positive='P',negative='N',
                               current_a='g*V(P,N)+0.0001*V(P,N)^3',
                               charge_c='c*(V(P,N)+V(P,N)^3/3)')])


class EquationDeviceContracts(unittest.TestCase):
    def test_cli_inert_export_and_input_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            definition=Path(directory)/'model.json';library=Path(directory)/'model.lib'
            original=json.dumps(specification());definition.write_text(original,encoding='utf-8')
            with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
                self.assertEqual(main(['device-build',str(definition),'--spice-output',str(library)]),0)
                self.assertEqual(main(['device-build',str(definition),'--spice-output',str(library)]),2)
                self.assertEqual(main(['device-build',str(definition),'-o',str(definition)]),2)
            self.assertEqual(definition.read_text(encoding='utf-8'),original)
            self.assertIn('.subckt FUTURE',library.read_text(encoding='utf-8'))

    def test_inert_library_and_conservative_pairs(self):
        spec=specification();before=copy.deepcopy(spec);part=build(spec)
        self.assertEqual(spec,before)
        self.assertEqual(part['pins'],['P','N'])
        self.assertIn('BQ0',part['source']);self.assertIn('I(VQ0)',part['source'])
        project=parse_netlist(part['source']+'X1 p 0 FUTURE\nV1 p 0 1\n.op\n')
        self.assertEqual(len(project.elements),6)
        self.assertEqual(part['model_status'],'user_defined_unqualified')

    def test_reject_injection_external_references_unknown_fields(self):
        for expression in ['V(P,OUTSIDE)','I(VOUTSIDE)','V(P,N)\n.end','__import__(1)','ddt(V(P,N))']:
            spec=specification();spec['branches'][0]['charge_c']=expression
            with self.subTest(expression=expression),self.assertRaises(ValueError):build(spec)
        for value in [0,-1,True,float('nan')]:
            spec=specification();spec['branches'][0]['charge_scale_f']=value
            with self.assertRaises(ValueError):build(spec)
        spec=specification();spec['noise']='pretend supported'
        with self.assertRaises(ValueError):build(spec)


@unittest.skipUnless(os.environ.get('SPIKES_TEST_LIBRARY'),'native DLL required')
class NativeEquationDevice(unittest.TestCase):
    def test_hemt_interface_package_and_voltage_dependent_miller_charge(self):
        path=Path(__file__).resolve().parents[2]/'examples/spikes/equation_devices/hemt_illustrative.json'
        part=build(json.loads(path.read_text(encoding='utf-8')))
        package=compose_device_parasitics(part['name'],part['pins'],name='PACKAGED',
            pin_parasitics={'D':dict(resistance_ohm=.01,inductance_h=1e-9),
                            'G':dict(resistance_ohm=1.,inductance_h=1e-9),
                            'S':dict(resistance_ohm=.01,inductance_h=1e-9)})
        library=load_native_library(os.environ['SPIKES_TEST_LIBRARY'])
        circuit=library.circuit();self.addCleanup(circuit.close)
        source=part['source']+package['source']+'X1 d g s fp PACKAGED\nVD d 0 5\nVG g 0 PULSE(0 2 0 1u 1u 2u 6u)\nVS s 0 0\nVFP fp 0 0\n.op\n'
        _populate(circuit,parse_netlist(source,native_extensions=True))
        with circuit.solve_transient(time_step_s=1e-8,stop_time_s=1e-6) as result:
            self.assertEqual(result.status,'converged',result.message)
            for index in range(result.point_count):
                self.assertAlmostEqual(sum(result.element_current(index,label) for label in ('VD','VG','VS','VFP')),0,delta=2e-9)
            self.assertGreater(-result.element_current(result.point_count-1,'VD'),1e-5)

    def circuit(self,spec,wiring):
        library=load_native_library(os.environ['SPIKES_TEST_LIBRARY'])
        circuit=library.circuit();self.addCleanup(circuit.close)
        _populate(circuit,parse_netlist(build(spec)['source']+wiring+'\n.op\n',native_extensions=True))
        return circuit

    def test_four_quadrant_current_kcl_and_negative_differential_resistance(self):
        spec=specification();spec['branches'][0].pop('charge_c')
        for voltage in [-2,-.5,.5,2]:
            circuit=self.circuit(spec,f'X1 p n FUTURE\nVP p 0 {voltage}\nVN n 0 0')
            with circuit.solve_operating_point() as result:
                self.assertEqual(result.status,'converged')
                expected=.001*voltage+.0001*voltage**3
                self.assertAlmostEqual(-result.element_current('VP'),expected,delta=1e-11)
                self.assertAlmostEqual(result.element_current('VP')+result.element_current('VN'),0,delta=1e-12)
        spec['branches'][0]['current_a']='-g*V(P,N)'
        circuit=self.circuit(spec,'X1 p 0 FUTURE\nVP p 0 1')
        with circuit.solve_operating_point() as result:
            self.assertEqual(result.status,'converged')
            self.assertAlmostEqual(result.element_current('VP'),.001,delta=1e-12)

    def test_nonlinear_charge_ramp_native_be_and_bdf2(self):
        spec=specification();spec['branches'][0].pop('current_a')
        step=1e-6
        for method in ['backward_euler','bdf2']:
            circuit=self.circuit(spec,'X1 p 0 FUTURE\nVP p 0 PULSE(0 1 0 100u 100u 1m 3m)')
            with circuit.solve_transient(time_step_s=step,stop_time_s=1e-5,integration_method=method) as result:
                self.assertEqual(result.status,'converged',result.message)
                # Compare terminal current with the exact discrete derivative
                # of Q(v), not C(v)*dv/dt on a finite integration step.
                charge=lambda v:1e-9*(v+v**3/3)
                for index in range(3,result.point_count):
                    v=result.node_voltage(index,'p');previous=result.node_voltage(index-1,'p')
                    if method=='backward_euler':expected=(charge(v)-charge(previous))/step
                    else:
                        older=result.node_voltage(index-2,'p')
                        expected=(1.5*charge(v)-2*charge(previous)+.5*charge(older))/step
                    self.assertAlmostEqual(-result.element_current(index,'VP'),expected,delta=1e-10)


if __name__=='__main__':unittest.main()
