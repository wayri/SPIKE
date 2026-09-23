from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'.tmp/studio-deps'))
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backend_bases import MouseEvent
from spikes_studio.plotting import viewport_indices,add_waveform,fit_visible_y,install_navigation


class NavigationTests(unittest.TestCase):
    def test_zoom_recovers_original_samples(self):
        time=np.arange(100000,dtype=float);signal=np.sin(time)
        selected=viewport_indices(time,signal,(50000,50010),budget=20)
        np.testing.assert_array_equal(selected,np.arange(49999,50012))
        self.assertLessEqual(len(viewport_indices(time,signal,(100,90000),budget=400)),400)
        self.assertEqual(signal[50000],np.sin(50000))

    def test_render_changes_not_source_and_links_axes(self):
        figure=Figure();canvas=FigureCanvasAgg(figure)
        top=figure.add_subplot(211);bottom=figure.add_subplot(212,sharex=top)
        time=np.arange(100000,dtype=float);signal=np.sin(time)
        a=add_waveform(top,time,signal);b=add_waveform(bottom,time,signal*2)
        install_navigation(canvas,[top,bottom]);top.set_xlim(50000,50010)
        np.testing.assert_array_equal(a.get_xdata(),np.arange(49999,50012))
        np.testing.assert_array_equal(b.get_xdata(),a.get_xdata())
        self.assertEqual(len(a._spikes_samples[0]),100000)

    def test_fit_excludes_hidden_and_cursor_lines(self):
        figure=Figure();axis=figure.add_subplot()
        add_waveform(axis,[0,1,2],[0,1,2]);add_waveform(axis,[0,1,2],[0,100,200],visible=False)
        axis.axvline(1);axis.set_xlim(.5,1.5);fit_visible_y([axis])
        np.testing.assert_allclose(axis.get_ylim(),[.45,1.55])

    def test_scroll_zoom_center_and_reinstall(self):
        figure=Figure();canvas=FigureCanvasAgg(figure);axis=figure.add_subplot()
        add_waveform(axis,[0,1,2],[0,1,2]);axis.set_xlim(0,2);canvas.draw()
        install_navigation(canvas,[axis]);install_navigation(canvas,[axis])
        x,y=axis.transData.transform((1,1))
        event=MouseEvent('scroll_event',canvas,x,y,step=1)
        canvas.callbacks.process('scroll_event',event)
        np.testing.assert_allclose(axis.get_xlim(),[.2,1.8],atol=.005)


if __name__=='__main__':unittest.main()
