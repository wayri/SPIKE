# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.analysis_plots import derive, render, VIEWS
from spikes_studio.signal_math import SignalMath, Quantity, VOLT, AMP


class AnalysisPlotTests(unittest.TestCase):
    def engine(self):
        t=np.arange(4096)/4096
        return SignalMath(t,{'v(out)':Quantity(2*np.sin(2*np.pi*32*t),VOLT),
                             'i(load)':Quantity(np.full(len(t),3.),AMP)})

    def test_fft_coherent_amplitude_dc_and_nyquist(self):
        engine=self.engine();result=derive(engine,'v(out)','FFT peak amplitude',window='Rectangular')
        f,a=result['curves'][0];self.assertAlmostEqual(a[np.argmax(a)],2,places=10);self.assertEqual(f[np.argmax(a)],32)
        result=derive(engine,'i(load)','FFT peak amplitude',window='Rectangular');self.assertAlmostEqual(result['curves'][0][1][0],3)
        n=SignalMath(np.arange(64)*1e-3,{'v(x)':Quantity((-1.)**np.arange(64),VOLT)})
        self.assertAlmostEqual(derive(n,'v(x)','FFT peak amplitude',window='Rectangular')['curves'][0][1][-1],1)

    def test_psd_parseval_hann_and_histogram(self):
        result=derive(self.engine(),'v(out)','Power spectral density',window='Rectangular')
        f,p=result['curves'][0];self.assertAlmostEqual(float(sum(p)*(f[1]-f[0])),2,places=9)
        hann=derive(self.engine(),'v(out)','FFT peak amplitude');self.assertAlmostEqual(max(hann['curves'][0][1]),2,delta=.001)
        hist=derive(self.engine(),'v(out)','Histogram');self.assertEqual(hist['report']['histogram_total'],4096)

    def test_integral_xy_and_eye_are_bounded(self):
        engine=self.engine();before=engine.signals['v(out)'].values.copy()
        energy=derive(engine,'v(out)*i(load)','Cumulative integral')
        self.assertIn('J',energy['y_label']);self.assertLess(abs(energy['report']['final_integral']),.001)
        xy=derive(engine,'v(out)','XY / phase portrait',x_expression='i(load)')
        self.assertTrue(np.all(xy['curves'][0][0]==3))
        eye=derive(engine,'v(out)','Eye diagram',period_s=1/32)
        self.assertLessEqual(len(eye['curves']),256);self.assertTrue(all(len(y)==256 for x,y in eye['curves']))
        np.testing.assert_array_equal(engine.signals['v(out)'].values,before)

    def test_nonuniform_fft_rejected_integral_is_time_weighted(self):
        engine=SignalMath([0,.1,.4,1],{'v(x)':Quantity([2,2,2,2],VOLT)})
        with self.assertRaisesRegex(ValueError,'uniform'):derive(engine,'v(x)','FFT peak amplitude')
        integral=derive(engine,'v(x)','Cumulative integral');self.assertEqual(integral['report']['final_integral'],2)
        self.assertEqual(integral['report']['mean'],2)

    def test_invalid_ranges_and_eye_sampling_rejected(self):
        for kwargs in ({'start_s':-.1},{'stop_s':2},{'start_s':.99,'stop_s':.9901}):
            with self.assertRaises(ValueError):derive(self.engine(),'v(out)','Histogram',**kwargs)
        with self.assertRaises(ValueError):derive(self.engine(),'v(out)','Eye diagram',period_s=1e-9)
        with self.assertRaises(ValueError):derive(self.engine(),'v(out)','Histogram',bins=500)

    def test_every_view_renders(self):
        from matplotlib.figure import Figure
        for view in VIEWS:
            result=derive(self.engine(),'v(out)',view,period_s=1/32)
            figure=Figure();axis=render(figure,result);self.assertTrue(axis.lines)


if __name__=='__main__':unittest.main()
