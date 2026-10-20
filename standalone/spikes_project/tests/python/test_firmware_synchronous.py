# SPDX-License-Identifier: Apache-2.0
"""Causality/restart tests for the instruction-boundary plant master."""
from collections import deque
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'standalone/spikes_project/studio/python'))
sys.path.insert(0, str(ROOT))


class SynchronousMasterTests(unittest.TestCase):
    def setup_master(self):
        from spikes_studio.firmware_synchronous import SynchronousFirmwareController
        from spikes_studio.firmware_electrical import PadConnection
        from spikes_studio.firmware_pad_state import decode_stm32
        master = SynchronousFirmwareController.__new__(SynchronousFirmwareController)
        master.pads = (PadConnection('P','B',0,'pin','vdd'),)
        master.previous = {'P':'unknown'}
        master.initial_values = {'P':(0,3.3,0)}
        master._pins = {('B',0):master.pads[0]}
        master.edges = deque(maxlen=1000)
        master.edge_count = master.instruction_count = 0
        master.failed = False
        log = []
        plant = SimpleNamespace(time_s=0, message='plant failure', fail=False)
        def integrate(dt):
            log.append(('plant', dt))
            if plant.fail:return False
            plant.time_s += dt
            return True
        plant.step = integrate
        plant.node_voltage = lambda name: 0 if name=='0' else 3.3
        transport = SimpleNamespace(time_ns=0, step_ns=10,
            states={('B',0):decode_stm32(0,0,0,0,0,0)})
        transport.set_inputs = lambda values:log.append(('input',tuple(values)))
        def step():
            log.append(('cpu',transport.time_ns))
            begin = transport.time_ns; transport.time_ns += 10
            return {'start_ns':begin,'end_ns':transport.time_ns,'events':[]}
        transport.step = step
        master.transport = transport
        return master,plant,log

    def test_receiver_is_refreshed_before_each_next_instruction(self):
        master,plant,log = self.setup_master()
        with patch('spikes_studio.firmware_synchronous.receive',side_effect=['low','high']):
            master.step_plant(plant,20e-9,lambda:log.append(('record',plant.time_s)))
        self.assertEqual([item[0] for item in log],['input','cpu','plant','record']*2)
        self.assertFalse(log[0][1][0][2]); self.assertTrue(log[4][1][0][2])
        self.assertEqual(master.instruction_count,2)

    def test_native_failure_permanently_latches_combined_session(self):
        master,plant,log = self.setup_master(); plant.fail = True
        with patch('spikes_studio.firmware_synchronous.receive',return_value='low'):
            with self.assertRaisesRegex(RuntimeError,'plant failure'):
                master.step_plant(plant,10e-9,lambda:None)
        with self.assertRaisesRegex(RuntimeError,'restart'):
            master.advance(plant)
        self.assertEqual(master.transport.time_ns,10)

    def test_fractional_grid_and_oversize_steps_reject_before_cpu_execution(self):
        for dt in (11e-9,0,10010e-9):
            master,plant,log = self.setup_master()
            with self.assertRaises(ValueError):master.step_plant(plant,dt,lambda:None)
            self.assertEqual(log,[])

    def test_unknown_input_never_reaches_cpu(self):
        master,plant,log = self.setup_master()
        with patch('spikes_studio.firmware_synchronous.receive',return_value='unknown'):
            with self.assertRaisesRegex(RuntimeError,'Unresolved'):
                master.step_plant(plant,10e-9,lambda:None)
        self.assertEqual(log,[])

    def test_cooperative_stop_occurs_before_next_instruction(self):
        master,plant,log = self.setup_master()
        master.set_boundary_control(lambda:False)
        master.step_plant(plant,10e-9,lambda:None)
        self.assertEqual(log,[])
        self.assertFalse(master.failed)

    def test_absolute_instruction_endpoints_do_not_accumulate_clock_drift(self):
        master,plant,log = self.setup_master()
        with patch('spikes_studio.firmware_synchronous.receive',return_value='low'):
            for _ in range(31):
                master.step_plant(plant,10e-6,lambda:None)
                log.clear()
        self.assertEqual(master.instruction_count,31000)
        self.assertEqual(plant.time_s,310000/1e9)
        master.advance(plant)

    def test_source_edits_have_explicit_next_boundary_visibility(self):
        master,plant,log = self.setup_master()
        metadata=master.source_control_metadata(0)
        self.assertEqual(metadata['input_visibility'],'next accepted instruction boundary')
        self.assertEqual(metadata['earliest_input_observation_time_s'],10e-9)

    def test_native_source_edit_is_observed_at_next_accepted_boundary(self):
        # Synthetic CPU transport, actual C++ algebraic state: this specifically
        # tests the documented deferred manual-control semantics, not MCU code.
        from python.spikes.native_abi import load_native_library
        from python.spikes.native_io_pad import add_pad
        path=os.environ.get('SPIKES_TEST_NATIVE_LIBRARY',str(ROOT/'build-spikes-io-pad-20261019/Release/spikes_c_api.dll'))
        master,_,log = self.setup_master()
        with load_native_library(path).circuit() as c:
            c.add_voltage_source('VDD','vdd','0',3.3)
            c.add_voltage_source('VIN','pin','0',0)
            add_pad(c,'P','pin','vdd','0')
            with c.transient_session(initialize_from_operating_point=True) as plant:
                master.step_plant(plant,10e-9,lambda:None)
                plant.set_source_value('VIN',3.3)
                master.step_plant(plant,10e-9,lambda:None)
                master.step_plant(plant,10e-9,lambda:None)
        received=[entry[1][0][2] for entry in log if entry[0]=='input']
        self.assertEqual(received,[False,False,True])


@unittest.skipUnless(os.environ.get('SPIKES_TEST_FIRMWARE')=='1','opt-in native MCU plus native electrical plant')
class RealSynchronousMasterTests(unittest.TestCase):
    def test_nrf_gpio_echo_observes_change_without_old_held_quantum(self):
        from spikes_studio.firmware_synchronous import SynchronousFirmwareController
        from spikes_studio.firmware_electrical import PadConnection
        from spikes_studio.renode_process import find_runtime
        from scripts.make_spikes_firmware_examples import gpio_echo
        from python.spikes.native_abi import load_native_library
        from python.spikes.netlist import parse_netlist
        from python.spikes.native_runner import _populate
        library=os.environ.get('SPIKES_TEST_NATIVE_LIBRARY',str(ROOT/'build-spikes-io-pad-20261019/Release/spikes_c_api.dll'))
        project=parse_netlist('Closed loop\nVDD vdd 0 3.3\nVIN input 0 0\nRLOAD output 0 1k\n.tran 100n 2u\n.end\n')
        with tempfile.TemporaryDirectory() as directory:
            image=Path(directory)/'echo.bin'; image.write_bytes(gpio_echo(uart=False))
            master=SynchronousFirmwareController(find_runtime(),image,
                'nordic-nrf52840-dk-pca10056-r3-0-2',
                [PadConnection('IN','0',2,'input','vdd'),PadConnection('OUT','0',3,'output','vdd')],
                trusted=True,step_s=1e-6)
            try:
                master.bind(project)
                with load_native_library(library).circuit() as circuit:
                    _populate(circuit,project); master.configure_circuit(circuit,project)
                    with circuit.transient_session(initialize_from_operating_point=True) as plant:
                        for _ in range(10): master.step_plant(plant,100e-9,lambda:None)
                        self.assertLess(plant.node_voltage('output'),.01)
                        plant.set_source_value('VIN',3.3)
                        for _ in range(3): master.step_plant(plant,100e-9,lambda:None)
                        # Nordic S0S1 maps to the generic weak 500-ohm driver;
                        # loaded by 1k, the independently expected value is2.2V.
                        self.assertAlmostEqual(plant.node_voltage('output'),2.2,delta=1e-7)
                        plant.set_source_value('VIN',0)
                        for _ in range(3): master.step_plant(plant,100e-9,lambda:None)
                        self.assertLess(plant.node_voltage('output'),.01)
                        self.assertEqual(master.instruction_count,160)
                        self.assertEqual(master.transport.time_ns,1600)
            finally: master.close()


if __name__ == '__main__':unittest.main()
