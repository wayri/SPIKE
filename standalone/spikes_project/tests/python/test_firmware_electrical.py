# SPDX-License-Identifier: Apache-2.0
"""Owned native plant tests; mocked register transport and opt-in real firmware."""
from pathlib import Path
import os
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'standalone/spikes_project/studio/python'))
from spikes_studio import firmware_electrical as electrical
from spikes_studio.firmware_pad_state import decode_nrf
from spikes_studio.firmware_session import FirmwareSession
from python.spikes.native_abi import load_native_library
from python.spikes.native_runner import _populate
from python.spikes.netlist import parse_netlist

DLL=os.environ.get('SPIKES_TEST_NATIVE_LIBRARY',str(ROOT/'build-spikes-io-pad-20261019/Release/spikes_c_api.dll'))
NRF='nordic-nrf52840-dk-pca10056-r3-0-2'
SOURCE='Pad test\nVDD vdd 0 3.3\nVIN input 0 0\nRLOAD output 0 1k\n.tran 100u 10m\n.end\n'


class RegisterTransport:
    """Fixture only: not a firmware/peripheral emulator."""
    def __init__(self,*args,**kwargs):
        self.time_ns=0;self.cnf={2:0,3:1};self.out=0;self.levels={};self.closed=False
    def _gpio_device(self,*args):return 'fixture'
    def pad_configuration(self,port,pin):return decode_nrf(self.cnf[pin],self.out,pin)
    def set_gpio(self,port,pin,level):self.levels[pin]=level
    def run_for(self,seconds):
        self.time_ns+=round(seconds*1e9)
        self.out=8 if self.levels.get(2) else 0
    def uart_read(self):return b''
    def provenance(self):return {'test_transport':True}
    def close(self):self.closed=True


class ElectricalAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.lib=load_native_library(DLL)
    def bridge(self):
        with patch.object(electrical,'FirmwareSession',RegisterTransport):
            return electrical.ElectricalFirmwareController(None,None,NRF,[
                electrical.PadConnection('input','0',2,'input','vdd'),
                electrical.PadConnection('output','0',3,'output','vdd')])

    def test_late_start_clock_mismatch_is_rejected(self):
        b=self.bridge();p=parse_netlist(SOURCE);b.bind(p)
        with self.lib.circuit() as c:
            _populate(c,p);ids=b.configure_circuit(c,p)
            self.assertEqual(len(ids),8);self.assertEqual(b.outputs,())
            with c.transient_session(initialize_from_operating_point=True) as s:
                s.step(.0001);s.set_source_value('VIN',3.3);s.step(.0001)
                # Firmware clock starts at the first scheduled boundary.
                with self.assertRaisesRegex(RuntimeError,'clock mismatch'):b.advance(s)
        b.close()

    def test_native_feedback_and_runtime_mode(self):
        b=self.bridge();p=parse_netlist(SOURCE);b.bind(p)
        with self.lib.circuit() as c:
            _populate(c,p);b.configure_circuit(c,p)
            with c.transient_session(initialize_from_operating_point=True) as s:
                s.step(.0001);b.advance(s)
                s.set_source_value('VIN',3.3);s.step(.0001);b.advance(s);s.step(.0001)
                # nRF standard drive chooses the explicit 500-ohm generic profile.
                self.assertAlmostEqual(s.node_voltage('output'),2.2,delta=1e-7)
                b.session.cnf[3]=1|(6<<8)|(3<<2)  # open drain, pull up, OUT=1 => release
                b.advance(s);s.step(.0001)
                self.assertAlmostEqual(s.node_voltage('output'),3.3/51,delta=1e-7)
        self.assertTrue(b.provenance()['electrical_pin_physics']);b.close()

    def test_disconnected_receiver_forgets_history_and_unknown_stops(self):
        b=self.bridge();p=parse_netlist(SOURCE);b.bind(p)
        with self.lib.circuit() as c:
            _populate(c,p);b.configure_circuit(c,p)
            with c.transient_session(initialize_from_operating_point=True) as s:
                s.step(.0001);b.advance(s);self.assertEqual(b.previous['input'],'low')
                b.session.cnf[2]=2  # disable input buffer
                s.set_source_value('VIN',1.65);s.step(.0001);b.advance(s)
                self.assertEqual(b.previous['input'],'unknown')
                b.session.cnf[2]=0
                s.step(.0001)
                with self.assertRaisesRegex(RuntimeError,'Unresolved GPIO'):b.advance(s)
        b.close()

    def test_unimplemented_nrf_p1_pins_reject(self):
        s=object.__new__(FirmwareSession);s.target_id=NRF
        with self.assertRaises(ValueError):s._gpio_device('1',16)
        self.assertEqual(s._gpio_device('1',15),'gpio1')

    def test_clock_guard_accepts_long_run_roundoff_but_rejects_duplicate_tick(self):
        b=self.bridge();b.bind(parse_netlist(SOURCE))
        t=0.
        for _ in range(25705):t+=.0001
        b.session.time_ns=25704*100000
        plant=SimpleNamespace(step_index=25705,time_s=t,
            node_voltage=lambda node:3.3 if node=='vdd' else 0.)
        with patch.object(electrical,'set_pad'),patch.object(electrical,'receive',return_value='low'):
            b.advance(plant)
            with self.assertRaisesRegex(RuntimeError,'clock mismatch'):b.advance(plant)
        b.close()

    def test_bad_profile_mapping_and_clock_quantum(self):
        with patch.object(electrical,'FirmwareSession',RegisterTransport):
            for pads in ([],[electrical.PadConnection('X','0',2,'input','vdd',vil_ratio=.9,vih_ratio=.1)]):
                with self.assertRaises(ValueError):electrical.ElectricalFirmwareController(None,None,NRF,pads)
        b=self.bridge()
        with self.assertRaises(ValueError):b.bind(parse_netlist(SOURCE.replace('100u','70u')))
        b.close()

    def test_continuous_run_records_pad_branches_and_retains_pause_state(self):
        from spikes_studio.run_control import InteractiveRun
        b=self.bridge();run=InteractiveRun(SOURCE,DLL,controller=b,capacity=20)
        def wait(predicate):
            deadline=time.monotonic()+5
            while not predicate():
                if run.state=='failed':self.fail(run.error)
                if time.monotonic()>deadline:self.fail('Continuous native pad test timeout')
                time.sleep(.005)
        try:
            wait(lambda:run.total_samples>=3)
            run.pause();wait(lambda:run.state=='paused')
            count=run.total_samples
            self.assertIn('output.io_pad.drive_high',run.snapshot()['data']['element_current_a'])
            time.sleep(.02);self.assertEqual(run.total_samples,count)
            run.set_source('VIN',3.3);run.resume()
            wait(lambda:any(v>2 for v in run.snapshot()['data']['node_voltage_v']['output']))
            self.assertLessEqual(len(run.rows),20)
        finally:run.stop();run.thread.join(timeout=5)
        self.assertFalse(run.thread.is_alive());self.assertTrue(b.session.closed)

    def test_timestamped_capture_retains_hidden_pulse_points_not_only_grid(self):
        from spikes_studio import firmware_timestamped as timed
        class Transport:
            def __init__(self,session,pins):
                self.session=session;self.states={(port,pin):session.pad_configuration(port,pin) for port,pin in pins}
            def run_for_ns(self,ns):
                start=self.session.time_ns;self.session.time_ns+=ns
                if start:return []
                return [{'time_ns':23,'port':'0','pin':3,'config':decode_nrf(1,8,3)},
                        {'time_ns':67,'port':'0','pin':3,'config':decode_nrf(1,0,3)}]
        with patch.object(electrical,'FirmwareSession',RegisterTransport),patch.object(timed,'FirmwareEdgeTransport',Transport):
            b=timed.TimestampedFirmwareController(None,None,NRF,[electrical.PadConnection('OUT','0',3,'output','vdd')])
        p=parse_netlist(SOURCE.replace('RLOAD output','CLOAD output 0 1n\nRLOAD output'))
        b.bind(p)
        try:
            with self.lib.circuit() as c:
                _populate(c,p);b.configure_circuit(c,p)
                with c.transient_session(initialize_from_operating_point=True) as s:
                    rows=[];b.advance(s)
                    b.step_plant(s,.0001,lambda:rows.append((s.time_s,s.node_voltage('output'))))
                    self.assertEqual([round(t*1e9) for t,v in rows],[23,67,100000])
                    self.assertGreater(rows[1][1],.1)
                    self.assertLess(rows[-1][1],.01)
                    b.advance(s) # Native internal step count must not break outer clock alignment.
        finally:b.close()


@unittest.skipUnless(os.environ.get('SPIKES_TEST_FIRMWARE')=='1','opt-in real firmware engine')
class RealFirmwareElectricalTests(unittest.TestCase):
    def test_nrf_binary_and_native_pad_loading(self):
        from scripts.make_spikes_firmware_examples import gpio_echo
        from spikes_studio.renode_process import find_runtime
        lib=load_native_library(DLL);project=parse_netlist(SOURCE)
        with tempfile.TemporaryDirectory() as folder:
            image=Path(folder)/'echo.bin';image.write_bytes(gpio_echo())
            b=electrical.ElectricalFirmwareController(find_runtime(),image,NRF,[
                electrical.PadConnection('P02','0',2,'input','vdd'),
                electrical.PadConnection('P03','0',3,'output','vdd')],trusted=True)
            try:
                b.bind(project)
                with lib.circuit() as c:
                    _populate(c,project);b.configure_circuit(c,project)
                    with c.transient_session(initialize_from_operating_point=True) as s:
                        s.step(.0001);b.advance(s)
                        s.set_source_value('VIN',3.3);s.step(.0001);b.advance(s);s.step(.0001)
                        self.assertAlmostEqual(s.node_voltage('output'),2.2,delta=1e-7)
                        self.assertAlmostEqual(s.element_current('P03.io_pad.drive_high'),-.0022,delta=1e-9)
                        # Change GPIO register mode, not an ideal circuit source.
                        b.session.engine.command('sysbus WriteDoubleWord 0x5000070c 0x60d')
                        b.advance(s);s.step(.0001)
                        self.assertAlmostEqual(s.node_voltage('output'),3.3/51,delta=1e-7)
            finally:b.close()
            self.assertIsNotNone(b.session.engine.process.poll())


if __name__=='__main__':unittest.main()
