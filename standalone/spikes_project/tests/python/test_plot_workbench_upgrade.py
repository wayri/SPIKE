# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'.tmp/studio-deps'))

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from spikes_studio.plot_interactions import PlotInteractions,CURSOR_COLORS
from spikes_studio.plot_workspace import (
    MAX_BROWSER_ROWS,
    PlotBrowserModel,
    cursor_table_text,
    run_browser_rows,
    signal_browser_rows,
)
from spikes_studio.plotting import add_waveform
from spikes_studio.signal_math import AMP,Quantity,SignalMath,VOLT


class Toggle:
    def __init__(self,value=False):self.value=value
    def GetValue(self):return self.value
    def SetValue(self,value):self.value=bool(value)


class PlotWorkbenchUpgradeTests(unittest.TestCase):
    def owner(self):
        engine=SignalMath([0,1,2],{
            'v(out)':Quantity([0,1,2],VOLT),
            'v(in)':Quantity([1,1,1],VOLT),
            'i(r1)':Quantity([0,.001,.002],AMP),
        })
        results=[
            {'data':{'time_s':[0,1,2]},'provenance':{'step_parameters':{'r':1000}}},
            {'data':{'time_s':[0,.5,1,1.5,2]},'provenance':{'step_parameters':{'r':2000}}},
        ]
        owner=SimpleNamespace(
            math=engine,traces=[('v(out)',engine.signals['v(out)'].values,'V')],hidden_traces=set(),
            run_results=results,run_engines=[engine,engine],visible_runs=None,overlay_runs=Toggle(),selected_run=0,
            cursors=[.5],cursor_bindings=[{'run':1,'expression':'v(out)'}],calls=[],
        )
        owner.add_trace=lambda expression:owner.calls.append(('add',expression))
        owner.draw_plot=lambda **kwargs:owner.calls.append(('draw',kwargs))
        owner.select_run=lambda index:owner.calls.append(('run',index))
        owner.cursor_descriptor=lambda index:dict(owner.cursor_bindings[index],time=owner.cursors[index])
        return owner

    def test_browser_rows_are_bounded_searchable_and_source_backed(self):
        owner=self.owner()
        self.assertEqual(signal_browser_rows(owner,'volt'),[])
        self.assertEqual(signal_browser_rows(owner,'v('),[('v(in)','V'),('v(out)','V')])
        self.assertEqual(signal_browser_rows(owner,' a'),[('i(r1)','A')])
        self.assertEqual(run_browser_rows(owner,'2,000'),[])
        self.assertEqual(run_browser_rows(owner,'r=2000'),[(1,'Run 2 · r=2000',5)])
        with self.assertRaises(ValueError):signal_browser_rows(owner,limit=MAX_BROWSER_ROWS+1)

    def test_browser_actions_route_to_existing_owner_contracts(self):
        owner=self.owner();model=PlotBrowserModel(owner)
        model.add_signal('v(in)')
        model.set_trace_visible('v(out)',False)
        model.activate_run(1)
        model.set_overlay_runs({1})
        self.assertEqual(owner.calls,[
            ('add','v(in)'),('draw',{'preserve_view':True}),('run',1),('draw',{'preserve_view':True}),
        ])
        self.assertEqual(owner.hidden_traces,{'v(out)'})
        self.assertEqual(owner.visible_runs,{1});self.assertTrue(owner.overlay_runs.GetValue())
        with self.assertRaises(ValueError):model.add_signal('v(fake)')
        with self.assertRaises(ValueError):model.set_overlay_runs({99})

    def test_cursor_copy_keeps_bound_run_expression_and_interpolated_value(self):
        owner=self.owner();text=cursor_table_text(owner)
        self.assertIn('Cursor\tRun\tSignal / expression\tCoordinate [s]\tValue',text)
        self.assertIn('A\t2\tv(out)\t0.5\t500.0000 mV',text)

    def test_linked_crosshair_and_cursor_styling_do_not_change_waveform_samples(self):
        figure=Figure(figsize=(7,4));canvas=FigureCanvasAgg(figure)
        top=figure.add_subplot(211);bottom=figure.add_subplot(212,sharex=top)
        source_time=np.array([0.,1.,2.]);source_value=np.array([0.,2.,4.])
        line=add_waveform(top,source_time,source_value,label='v(out)')
        add_waveform(bottom,source_time,source_value/1000,label='i(r1)')
        top.axvline(.5,linestyle='--');top.text(.5,.98,'A',transform=top.get_xaxis_transform())
        bottom.axvline(.5,linestyle='--');bottom.text(.5,.98,'A',transform=bottom.get_xaxis_transform())
        owner=SimpleNamespace(
            axes=[top,bottom],plot=canvas,palette={'accent':'#00ffff'},cursors=[.5],cursor_bindings=[{'run':0,'expression':'v(out)'}],
            run_engines=[SignalMath(source_time,{'v(out)':Quantity(source_value,VOLT)})],
        )
        owner.cursor_descriptor=lambda index:dict(owner.cursor_bindings[index],time=owner.cursors[index])
        controller=PlotInteractions(owner);controller.after_draw();canvas.draw()
        x,y=top.transData.transform((1.25,3.))
        controller.update_crosshair(SimpleNamespace(inaxes=top,xdata=1.25,ydata=3.,x=x,y=y))
        self.assertEqual(len(controller.crosshair),2)
        for vertical,_horizontal,_label in controller.crosshair:self.assertEqual(vertical.get_xdata()[0],1.25)
        self.assertTrue(controller.crosshair[0][1].get_visible());self.assertFalse(controller.crosshair[1][1].get_visible())
        self.assertIn('t=1.2500 s',controller.crosshair[0][2].get_text())
        cursor=[artist for artist in top.lines if getattr(artist,'_spikes_cursor',None)==0][0]
        self.assertEqual(cursor.get_color(),CURSOR_COLORS[0])
        np.testing.assert_array_equal(line._spikes_samples[0],source_time)
        np.testing.assert_array_equal(line._spikes_samples[1],source_value)


if __name__=='__main__':unittest.main()
