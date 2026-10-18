# SPDX-License-Identifier: Apache-2.0
"""Hidden placeholders coalesce work but still render when selected."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class StartupRenderingTests(unittest.TestCase):
    def test_hidden_plots_render_on_show_with_latest_theme(self):
        import wx
        from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
        from spikes_studio.desktop import Studio
        app=wx.GetApp() or wx.App(False);app.SetExitOnFrameDelete(False)
        draws=[];original=FigureCanvasWxAgg.draw
        def draw(canvas,*args,**kwargs):
            draws.append(canvas);return original(canvas,*args,**kwargs)
        with patch.object(FigureCanvasWxAgg,'draw',draw):
            frame=Studio()
            try:
                canvases=[frame.plot,frame.frequency.plot,frame.analytics.plot]
                self.assertFalse(any(canvas in draws for canvas in canvases))
                frame.set_theme('Midnight',save=False)
                frame.Show();wx.Yield()
                for canvas in canvases:
                    page=canvas.GetParent()
                    pages=[frame.book.GetPage(i) for i in range(frame.book.GetPageCount())]
                    while page not in pages and page is not None:page=page.GetParent()
                    self.assertIsNotNone(page)
                    index=pages.index(page)
                    frame.book.SetSelection(index);wx.Yield();canvas.Update();wx.Yield()
                    self.assertIn(canvas,draws)
                    self.assertTrue(canvas.figure.axes[0].get_title())
                    self.assertGreater(canvas.GetSize().width,0)
                frame.set_theme('Light',save=False);wx.Yield()
            finally:
                frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()
