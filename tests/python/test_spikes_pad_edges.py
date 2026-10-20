# SPDX-License-Identifier: Apache-2.0
"""Independent backward-Euler recurrence and non-grid event admission oracles."""
from dataclasses import replace
import os
import math
from pathlib import Path
import unittest
from python.spikes.native_abi import load_native_library,NativeABIError
from python.spikes.native_io_pad import PadProfile,PadState,add_pad,set_pad,schedule_pad_edge,pending_pad_edges
ROOT=Path(__file__).resolve().parents[2]
DLL=os.environ.get('SPIKES_TEST_NATIVE_LIBRARY',str(ROOT/'build-spikes-io-pad-20261019/Release/spikes_c_api.dll'))


class PadEdgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.lib=load_native_library(DLL)

    def circuit(self):
        c=self.lib.circuit();c.add_voltage_source('V','vdd','0',1)
        # Known initial charge zero; active path100ohm, three inactive paths.
        add_pad(c,'U','p','vdd','0',replace(PadProfile(),
            high_strong_resistance_ohm=100,low_strong_resistance_ohm=100,
            capacitance_to_vss_f=1e-9),PadState('push_pull','low'))
        return c

    def test_two_edges_inside_one_step_are_not_lost(self):
        with self.circuit() as c,c.transient_session() as s:
            schedule_pad_edge(s,'U',23,PadState('push_pull','high'))
            schedule_pad_edge(s,'U',67,PadState('push_pull','low'))
            self.assertEqual(pending_pad_edges(s),(2,23))
            self.assertTrue(s.step(100e-9),s.message)
            # BE: integrate23ns low,44ns high,33ns low. Retained leakage included.
            g=.01+3e-12;cap=1e-9;v=0.
            for h,high in ((23e-9,False),(44e-9,True),(33e-9,False)):
                source=(.01+1e-12) if high else 2e-12
                v=(cap*v+h*source)/(cap+h*g)
            self.assertAlmostEqual(s.node_voltage('p'),v,delta=1e-10)
            self.assertGreater(v,.2);self.assertEqual(pending_pad_edges(s),(0,None))
            self.assertAlmostEqual(s.time_s,100e-9,delta=1e-20)

    def test_checkpoints_restore_pending_and_consumed_events(self):
        with self.circuit() as c,c.transient_session() as s:
            schedule_pad_edge(s,'U',10,PadState('push_pull','high'))
            with s.checkpoint() as cp:
                self.assertTrue(s.step(100e-9),s.message);voltage=s.node_voltage('p')
                self.assertEqual(pending_pad_edges(s)[0],0)
                s.restore(cp);self.assertEqual(pending_pad_edges(s),(1,10))
                self.assertTrue(s.step(100e-9));self.assertAlmostEqual(s.node_voltage('p'),voltage,delta=1e-12)

    def test_ties_are_stable_and_zero_time_events_apply_before_integration(self):
        with self.circuit() as c,c.transient_session() as s:
            schedule_pad_edge(s,'U',0,PadState('push_pull','low'))
            schedule_pad_edge(s,'U',0,PadState('push_pull','high'))
            self.assertTrue(s.step(100e-9));self.assertAlmostEqual(s.node_voltage('p'),.5,delta=1e-9)

    def test_past_invalid_state_and_unknown_pad_reject_without_queueing(self):
        with self.circuit() as c,c.transient_session() as s:
            s.step(100e-9)
            for prefix,ns,state in [('U',1,PadState()),('missing',200,PadState()),
                                    ('U',200,PadState('push_pull','released'))]:
                with self.assertRaises(NativeABIError):schedule_pad_edge(s,prefix,ns,state)
            for ns in (-1,True,1.5,2**48+1):
                with self.assertRaises(ValueError):schedule_pad_edge(s,'U',ns,PadState())
            self.assertEqual(pending_pad_edges(s),(0,None))

    def test_event_at_endpoint_changes_next_interval_not_stored_charge(self):
        with self.circuit() as c,c.transient_session() as s:
            schedule_pad_edge(s,'U',100,PadState('push_pull','high'))
            s.step(100e-9);v=s.node_voltage('p')
            self.assertLess(v,1e-8)
            s.step(100e-9);self.assertAlmostEqual(s.node_voltage('p'),.5,delta=1e-9)

    def test_time_zero_op_startup_rejects_uninitialized_storage_change(self):
        with self.circuit() as c,c.transient_session(initialize_from_operating_point=True) as s:
            with self.assertRaisesRegex(NativeABIError,'time-zero'):
                schedule_pad_edge(s,'U',0,PadState('push_pull','high'))
            self.assertEqual(pending_pad_edges(s),(0,None))

    def test_later_segment_failure_restores_clock_storage_modes_and_queue(self):
        with self.circuit() as c:
            c.add_diode('D','p','0')
            with c.transient_session(max_newton_iterations=1) as s:
                self.assertTrue(s.step(1e-9),s.message)
                before=(s.time_s,s.node_voltage('p'),s.step_index)
                schedule_pad_edge(s,'U',30,PadState('push_pull','high'))
                with self.assertRaisesRegex(NativeABIError,'GPIO edge final segment failed'):
                    s.step(10e-6)
                self.assertEqual((s.time_s,s.node_voltage('p'),s.step_index),before)
                self.assertEqual(pending_pad_edges(s),(1,30))

    def test_large_time_future_edge_never_overshoots_requested_end(self):
        with self.circuit() as c,c.transient_session() as s:
            edge=2**48;end=edge/1e9-1e-10
            schedule_pad_edge(s,'U',edge,PadState('push_pull','high'))
            self.assertTrue(s.step(end),s.message)
            self.assertLess(s.time_s,edge/1e9)
            self.assertEqual(pending_pad_edges(s),(1,edge))

    def test_offgrid_pulse_refines_toward_continuous_rc_oracle(self):
        g=.01+3e-12;cap=1e-9;exact=0.
        for duration,source in ((23e-9,2e-12),(44e-9,.01+1e-12),(33e-9,2e-12)):
            equilibrium=source/g
            exact=equilibrium+(exact-equilibrium)*math.exp(-duration*g/cap)
        errors=[]
        for h in (1e-9,.5e-9,.25e-9):
            with self.circuit() as c,c.transient_session() as s:
                schedule_pad_edge(s,'U',23,PadState('push_pull','high'))
                schedule_pad_edge(s,'U',67,PadState('push_pull','low'))
                for _ in range(round(100e-9/h)):self.assertTrue(s.step(h),s.message)
                errors.append(abs(s.node_voltage('p')-exact))
        self.assertLess(errors[0],.005)
        for a,b in zip(errors,errors[1:]):self.assertTrue(1.8<a/b<2.2,(errors,exact))


if __name__=='__main__':unittest.main()
