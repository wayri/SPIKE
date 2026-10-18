# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio' / 'python'))

from spikes_studio.dashboard import (
    INSTRUMENT_ACTIONS,
    KINDS,
    meter_fraction,
    reconcile_control,
    run_provenance,
    scope_view,
    starter_dashboard,
    update_widget,
    validate_dashboard,
)
from spikes_studio.signal_math import AMP, VOLT, Quantity, SignalMath


def recorded_engine():
    time = np.array([0., .05, .2, 1.])
    return SignalMath(time, {
        'v(out)': Quantity(np.array([0., .4, .9, 1.]), VOLT),
        'i(r1)': Quantity(np.array([.001, .0006, .0001, 0.]), AMP),
    })


class DashboardWorkbenchUpgradeTests(unittest.TestCase):
    def test_kinds_and_named_palette_contract_remain_stable(self):
        self.assertEqual(KINDS, ('Meter', 'Scope', 'Indicator', 'Source control', 'Diagram block', 'Note'))
        self.assertEqual([row[0] for row in INSTRUMENT_ACTIONS], list(KINDS))
        for kind, label, tooltip in INSTRUMENT_ACTIONS:
            self.assertTrue(label, kind)
            self.assertIn('Add', tooltip)

    def test_starters_bind_only_real_available_signals_and_ranges(self):
        data = starter_dashboard(recorded_engine(), 1100)
        validate_dashboard(data)
        scope, meter = data['widgets']
        self.assertEqual((scope['kind'], scope['expression']), ('Scope', 'v(out)'))
        self.assertEqual((meter['kind'], meter['expression']), ('Meter', 'i(r1)'))
        self.assertLess(scope['minimum'], 0.)
        self.assertGreater(scope['maximum'], 1.)
        self.assertGreater(meter['x'], scope['x'] + scope['width'])

        narrow = starter_dashboard(recorded_engine(), 520)
        self.assertGreater(narrow['widgets'][1]['y'], narrow['widgets'][0]['y'])
        complex_first = SignalMath([0., 1.], {
            'z(raw)': Quantity(np.array([1j, 2j]), VOLT),
            'v(real)': Quantity(np.array([0., 1.]), VOLT),
        })
        self.assertEqual(starter_dashboard(complex_first)['widgets'][0]['expression'], 'v(real)')
        with self.assertRaisesRegex(ValueError, 'Acquire'):
            starter_dashboard(None)

    def test_scope_summary_preserves_real_peak_and_irregular_time_extent(self):
        view = scope_view([0., .01, .02, 9., 10.], [0., 1., 8., -2., 3.], 4)
        self.assertEqual(view['time_start'], 0.)
        self.assertEqual(view['time_end'], 10.)
        self.assertEqual(view['minimum'], -2.)
        self.assertEqual(view['maximum'], 8.)
        self.assertTrue(any(low <= -2. and high >= 3. for _, low, high in view['bins']))

    def test_meter_fraction_clamps_without_changing_displayed_value(self):
        self.assertEqual(meter_fraction(-1, 0, 5), 0.)
        self.assertEqual(meter_fraction(2.5, 0, 5), .5)
        self.assertEqual(meter_fraction(8, 0, 5), 1.)
        with self.assertRaises(ValueError):
            meter_fraction(1, 5, 5)

    def test_source_value_is_acknowledged_only_by_a_later_native_event(self):
        events = [
            {'time_s': .1, 'source': 'V1', 'value': 2.},
            {'time_s': .2, 'source': 'V1', 'value': 2., 'origin': 'compiled_controller'},
            {'time_s': .3, 'source': 'V2', 'value': 2.},
        ]
        pending = {'source': 'V1', 'value': 2., 'event_index': len(events),
                   'event_cursor': (.3, 'V2', 2., None)}
        self.assertIsNone(reconcile_control(pending, events))
        events.append({'time_s': .4, 'source': 'V1', 'value': 2.})
        self.assertEqual(reconcile_control(pending, events)['time_s'], .4)
        self.assertIsNone(reconcile_control(pending | {'event_cursor': (.01, 'missing', 0., None)}, events))

    def test_provenance_always_exposes_simulation_only_disconnection(self):
        disconnected = run_provenance()
        self.assertIn('Data source: disconnected', disconnected)
        self.assertIn('Hardware I/O: disconnected', disconnected)
        result = {'data': {'time_s': [0., 1.]}, 'provenance': {
            'solver': 'SPIKES owned C++ persistent session',
            'integration': 'bdf2',
            'source_sha256': '1234567890abcdef',
        }}
        summary = run_provenance(active_snapshot=result, session_state='paused')
        self.assertIn('continuous simulation', summary)
        self.assertIn('Session: paused', summary)
        self.assertIn('Source: 1234567890ab', summary)
        self.assertNotIn('HIL connected', summary)

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_WX') == '1', 'Opt-in native wx dashboard test')
    def test_native_panel_palette_canvas_controls_and_narrow_layout(self):
        import wx
        from spikes_studio.dashboard import empty_dashboard
        from spikes_studio.dashboard_panel import DashboardPanel
        from spikes_studio.themes import PALETTES

        class Doc:
            def __init__(self):
                self.data = {'dashboard': empty_dashboard()}

            def commit(self, change):
                candidate = deepcopy(self.data)
                change(candidate)
                validate_dashboard(candidate['dashboard'])
                self.data = candidate

        app = wx.App.Get() or wx.App(False)
        frame = wx.Frame(None, size=(900, 700))
        book = wx.Notebook(frame)
        owner = SimpleNamespace(
            book=book, doc=Doc(), palette=PALETTES['Dark'], math=recorded_engine(),
            result=None, active_run=None, update_title=lambda: None,
            guarded=lambda action: action(), pause_run=lambda: None, stop_run=lambda: None,
            execute_command=lambda command: None, start_interactive=lambda: None,
        )
        try:
            panel = DashboardPanel(owner, book)
            book.AddPage(panel, 'Dashboard')
            frame.Show();wx.Yield()
            self.assertEqual(set(panel.palette_buttons), set(KINDS))
            for kind, button in panel.palette_buttons.items():
                self.assertTrue(button.GetLabel(), kind)
                self.assertTrue(button.GetToolTipText(), kind)
            panel.create_starters()
            self.assertEqual(len(owner.doc.data['dashboard']['widgets']), 2)
            panel.canvas.Refresh();panel.canvas.Update();wx.Yield()
            panel._set_narrow(True)
            self.assertEqual(panel.body.GetOrientation(), wx.VERTICAL)
            frame.SetSize((600, 700));wx.Yield()
            panel._set_narrow(False)
            self.assertEqual(panel.body.GetOrientation(), wx.HORIZONTAL)
            frame.SetSize((900, 700));wx.Yield()
            panel.add('Source control')
            source = panel.selected_row()
            panel.commit(update_widget(owner.doc.data['dashboard'], source['id'], width=180, height=120))
            panel.mode_choice.SetStringSelection('Run')
            panel.change_mode()
            self.assertTrue(panel.canvas_control.IsShown())
            self.assertFalse(panel.canvas_send.IsEnabled())
            source_rect = wx.Rect(source['x'], source['y'], 180, 120)
            self.assertTrue(source_rect.Contains(panel.canvas_control.GetRect().GetBottomRight()))
            self.assertTrue(source_rect.Contains(panel.canvas_send.GetRect().GetBottomRight()))
            panel.canvas.Refresh();panel.canvas.Update();wx.Yield()
        finally:
            frame.Destroy()
            wx.Yield()


if __name__ == '__main__':
    unittest.main()
