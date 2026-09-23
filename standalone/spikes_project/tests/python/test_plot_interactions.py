from pathlib import Path
import sys
import os
import unittest
from types import SimpleNamespace
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'.tmp/studio-deps'))
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backend_bases import MouseEvent
from spikes_studio.plotting import install_navigation,zoom_limits,add_waveform
from spikes_studio.plot_interactions import PlotInteractions,nearest_cursor,cursor_rows
from spikes_studio.signal_math import SignalMath,Quantity,VOLT


class InteractionTests(unittest.TestCase):
    def figure(self):
        fig=Figure(figsize=(8,5));canvas=FigureCanvasAgg(fig);axis=fig.add_subplot()
        axis.set_xlim(0,10);axis.set_ylim(0,10);canvas.draw()
        return canvas,axis

    def test_gutter_wheel_targets_only_matching_dimension(self):
        canvas,axis=self.figure();install_navigation(canvas,[axis]);box=axis.bbox
        canvas.callbacks.process('scroll_event',MouseEvent('scroll_event',canvas,box.x0-20,(box.y0+box.y1)/2,step=1))
        self.assertEqual(axis.get_xlim(),(0,10));self.assertAlmostEqual(np.diff(axis.get_ylim())[0],8)
        canvas.callbacks.process('scroll_event',MouseEvent('scroll_event',canvas,(box.x0+box.x1)/2,box.y0-20,step=1))
        self.assertAlmostEqual(np.diff(axis.get_xlim())[0],8)

    def test_log_zoom_and_pixel_cursor_hit(self):
        low,high=zoom_limits((1,100),10,.5,'log')
        self.assertAlmostEqual(low,np.sqrt(10));self.assertAlmostEqual(high,10*np.sqrt(10))
        canvas,axis=self.figure();x=axis.transData.transform((3,5))[0]
        self.assertEqual(nearest_cursor(axis,[3,8],x+8),0)
        self.assertIsNone(nearest_cursor(axis,[3,8],x+20))

    def test_drag_keeps_original_run_and_expression(self):
        canvas,axis=self.figure()
        add_waveform(axis,np.array([0,5,10]),np.array([0,5,10]))
        line=axis.axvline(3,linestyle='--');axis.text(3,.98,'A',transform=axis.get_xaxis_transform())
        owner=SimpleNamespace(plot=canvas,axes=[axis],cursors=[3.],cursor_bindings=[{'run':1,'expression':'v(out)'}],run_engines=[None,SignalMath([0,5,10],{'v(out)':Quantity([0,10,20],VOLT)})])
        owner.cursor_descriptor=lambda i:dict(owner.cursor_bindings[i],time=owner.cursors[i])
        def put(t,run,expr,index):
            owner.cursors[index]=t;self.assertEqual((run,expr),(1,'v(out)'))
        owner.put_cursor=put
        controller=PlotInteractions(owner);controller.after_draw();controller.drag=(0,axis)
        x,y=axis.transData.transform((7,5));controller.motion(SimpleNamespace(x=x,y=y))
        self.assertAlmostEqual(owner.cursors[0],7);self.assertAlmostEqual(line.get_xdata()[0],7)
        self.assertEqual(cursor_rows(owner)[0][1],'2');self.assertIn('14',cursor_rows(owner)[0][4])
        x,y=axis.transData.transform((20,5));controller.motion(SimpleNamespace(x=x,y=y))
        self.assertEqual(owner.cursors[0],10)

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','Opt-in real wx cursor-window test')
    def test_native_cursor_window_live_readings(self):
        import wx
        from spikes_studio.themes import PALETTES
        app=wx.App.Get() or wx.App(False)
        frame=wx.Frame(None)
        try:
            frame.cursors=[.5,1.5];frame.cursor_bindings=[{'run':0,'expression':'v(out)'}]*2
            frame.run_engines=[SignalMath([0,1,2],{'v(out)':Quantity([0,2,4],VOLT)})]
            frame.cursor_descriptor=lambda i:dict(frame.cursor_bindings[i],time=frame.cursors[i])
            frame.palette=PALETTES['Dark'];frame.manage_cursors=lambda:None
            controller=PlotInteractions(frame);controller.show_cursors();wx.Yield()
            self.assertEqual(controller.table.GetItemCount(),2)
            self.assertIn('2.0000 V',controller.delta.GetLabel())
            frame.cursors[1]=2;controller.refresh_table()
            self.assertEqual(controller.table.GetItemText(1,3),'2')
            self.assertIn('3.0000 V',controller.delta.GetLabel())
            controller.window.Hide()
        finally:
            frame.Destroy();wx.Yield()


if __name__=='__main__':unittest.main()
