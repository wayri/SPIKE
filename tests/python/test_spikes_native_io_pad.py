# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import unittest
from dataclasses import replace
from python.spikes.native_abi import load_native_library,NativeABIError
from python.spikes.native_io_pad import PadProfile,PadState,add_pad,set_pad,receive,observe_pad

ROOT=Path(__file__).resolve().parents[2]
DLL=os.environ.get('SPIKES_TEST_NATIVE_LIBRARY',str(ROOT/'build-spikes-io-pad-20261019/Release/spikes_c_api.dll'))


class NativePadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.lib=load_native_library(DLL)

    def test_pull_divider_and_observable_branches(self):
        with self.lib.circuit() as c:
            c.add_voltage_source('supply','vdd','0',3.3)
            c.add_resistor('load','pin','0',50000)
            ids=add_pad(c,'U1.P1','pin','vdd','0',initial=PadState(pull='up'))
            with c.transient_session(initialize_from_operating_point=True) as s:
                self.assertTrue(s.step(1e-6),s.message)
                self.assertAlmostEqual(s.node_voltage('pin'),1.65,delta=1e-7)
                self.assertEqual(len(ids),4)
                for name in ids:self.assertTrue(abs(s.element_current(name))<1)
                o=observe_pad(s,'U1.P1')
                self.assertAlmostEqual(o['pad_current_a'],-1.65/50000,delta=1e-12)
                self.assertAlmostEqual(sum(o[n] for n in ('pad_current_a','vdd_current_a','vss_current_a')),0,delta=1e-12)

    def test_open_drain_and_checkpoint_restores_state_cache(self):
        with self.lib.circuit() as c:
            c.add_voltage_source('supply','vdd','0',3.3)
            add_pad(c,'U','pin','vdd','0',initial=PadState('open_drain','low',pull='up'))
            with c.transient_session(initialize_from_operating_point=True) as s:
                s.step(1e-6);low=s.node_voltage('pin')
                with s.checkpoint() as cp:
                    set_pad(s,'U',PadState('open_drain','released',pull='up'))
                    s.step(1e-6);self.assertGreater(s.node_voltage('pin'),3.29)
                    s.restore(cp)
                    # Same state as before restore must actually update again.
                    set_pad(s,'U',PadState('open_drain','released',pull='up'))
                    s.step(1e-6);self.assertGreater(s.node_voltage('pin'),3.29)
                self.assertLess(low,.004)

    def test_snapshot_does_not_gain_pads_added_later(self):
        with self.lib.circuit() as c:
            c.add_voltage_source('supply','vdd','0',3.3)
            c.add_resistor('load','pin','0',1000)
            with c.transient_session() as s:
                add_pad(c,'later','pin','vdd','0')
                with self.assertRaises(NativeABIError):set_pad(s,'later',PadState())

    def test_duplicate_atomic_rejection_and_invalid_state(self):
        with self.lib.circuit() as c:
            c.add_voltage_source('supply','vdd','0',3.3)
            with self.assertRaises(NativeABIError):
                add_pad(c,'U','pin','vdd','0',replace(PadProfile(),package_inductance_h=-1))
            add_pad(c,'U','pin','vdd','0')
            with self.assertRaises(NativeABIError):add_pad(c,'U','pin','vdd','0')
            with c.transient_session() as s:
                with self.assertRaises(NativeABIError):set_pad(s,'U',PadState('push_pull','released'))
                with self.assertRaises(NativeABIError):s.set_resistance('U.io_pad.drive_high',100)

    def test_receiver_unknown_hysteresis_and_actual_rails(self):
        with self.lib.circuit() as c:
            c.add_voltage_source('V','x','0',1)
            with c.transient_session() as s:
                self.assertEqual(receive(s,1.5,3,0),'unknown')
                self.assertEqual(receive(s,1.5,3,0,previous='high'),'high')
                self.assertEqual(receive(s,1.5,3,0,previous='low'),'low')
                self.assertEqual(receive(s,2,2,1),'high')
                self.assertEqual(receive(s,1,2,1),'low')
                self.assertEqual(receive(s,1,0,0,previous='high'),'unknown')
                with self.assertRaises(NativeABIError):receive(s,1,3,0,vil_ratio=.8,vih_ratio=.3)

    def test_two_output_contention_is_finite(self):
        with self.lib.circuit() as c:
            c.add_voltage_source('supply','vdd','0',3.3)
            add_pad(c,'hi','pin','vdd','0',initial=PadState('push_pull','high'))
            add_pad(c,'lo','pin','vdd','0',initial=PadState('push_pull','low'))
            with c.transient_session(initialize_from_operating_point=True) as s:
                self.assertTrue(s.step(1e-6),s.message)
                self.assertAlmostEqual(s.node_voltage('pin'),1.65,delta=1e-9)
                self.assertAlmostEqual(s.element_current('supply'),-.033,delta=1e-9)

    def test_optional_element_ids_match_native(self):
        with self.lib.circuit() as c:
            c.add_voltage_source('supply','vdd','0',3.3)
            profile=replace(PadProfile(),package_resistance_ohm=1,package_inductance_h=1e-9,
                            capacitance_to_vss_f=1e-12,capacitance_to_vdd_f=1e-12,
                            enable_clamp_to_vdd=True,enable_clamp_to_vss=True)
            ids=add_pad(c,'U','pin','vdd','0',profile,PadState(pull='up'))
            with c.transient_session(initialize_from_operating_point=True) as s:
                self.assertTrue(s.step(1e-9),s.message)
                self.assertEqual(len(ids),10)
                for name in ids:s.element_current(name)


if __name__=='__main__':unittest.main()
