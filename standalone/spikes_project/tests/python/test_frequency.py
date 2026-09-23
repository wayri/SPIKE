from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
if (ROOT/'.tmp/studio-deps').exists():sys.path.insert(0,str(ROOT/'.tmp/studio-deps'))
from spikes_studio.document import RC_DECK
from spikes_studio.frequency import analyze,validate_result,complex_values,reflection,render,VIEWS,series,save_frequency,load_frequency
from spikes_studio.signal_math import ONE,VOLT,AMP


class FrequencyTests(unittest.TestCase):
    def test_frequency_input_suffixes(self):
        from spikes_studio.frequency import parse_hz
        for text,expected in [('1Meg',1e6),('1MHz',1e6),('2 kHz',2000),('1mHz',.001),('1m',.001),('10Hz',10)]:
            with self.subTest(text=text):self.assertEqual(parse_hz(text),expected)
    @classmethod
    def setUpClass(cls):
        cls.settings={'source':'V1','output':'V(out)','start_hz':1.,'stop_hz':1e5,'points':101,'scale':'log','pole_zero':True}
        cls.result=analyze(RC_DECK,cls.settings)

    def test_rc_phasor_and_descriptor_pole_match_analytical_result(self):
        engine=validate_result(self.result);actual,unit=series(engine,'V(out)/V(in)')
        np.testing.assert_allclose(actual,1/(1+2j*np.pi*engine.time*.001),rtol=1e-10,atol=1e-12)
        self.assertEqual(unit,ONE)
        np.testing.assert_allclose(complex_values(self.result['pole_zero']['data']['poles_rad_s']),[-1000],rtol=1e-12)
        self.assertEqual(self.result['pole_zero']['data']['zero_count'],0)
        self.assertFalse(self.result['provenance']['ac_engine']['owned_cpp_ac'])

    def test_highpass_zero_at_origin(self):
        source='Highpass\nV1 in 0 1\nC1 in out 1u\nR1 out 0 1k\n.op\n.end\n'
        result=analyze(source,self.settings)
        np.testing.assert_allclose(complex_values(result['pole_zero']['data']['zeros_rad_s']),[0],atol=1e-9)
        np.testing.assert_allclose(complex_values(result['pole_zero']['data']['poles_rad_s']),[-1000],rtol=1e-10)

    def test_frequency_expression_units_and_time_reductions(self):
        engine=validate_result(self.result)
        values,unit=series(engine,'exp(-j*2*pi*f*1e-3*s)')
        np.testing.assert_allclose(abs(values),1);self.assertEqual(unit,ONE)
        for expression in ('t','integral(V(out))','derivative(V(out))','mean(V(out))','rms(V(out))'):
            with self.subTest(expression=expression),self.assertRaises(ValueError):engine.evaluate(expression)

    def test_rf_mapping_admittance_active_load_and_singularity(self):
        ohm=VOLT.mul(AMP.pow(-1));z=np.array([50,0,50+50j,-25],dtype=complex)
        gamma=reflection(z,ohm,'Impedance',50)
        np.testing.assert_allclose(gamma,[0,-1,.2+.4j,-3])
        np.testing.assert_allclose(reflection(np.array([.02,0,.01j]),ohm.pow(-1),'Admittance',50),[0,1,.6-.8j])
        with self.assertRaises(ValueError):reflection(np.array([-50]),ohm,'Impedance',50)
        with self.assertRaises(ValueError):reflection(z,VOLT,'Impedance',50)
        with self.assertRaises(ValueError):reflection(z,ohm,'Impedance',0)

    def test_all_plot_types_render_from_real_calculation(self):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        for view in VIEWS:
            with self.subTest(view=view):
                figure=Figure(figsize=(7,5));canvas=FigureCanvasAgg(figure)
                expr='V(in)/(-I(V1))' if view.startswith('Smith') or view in ('Return loss','VSWR') else 'V(out)/V(in)'
                render(figure,self.result,expr,view);canvas.draw()
                self.assertGreater(len(figure.axes),0)

    def test_group_delay_matches_rc_at_dense_interior_samples(self):
        from matplotlib.figure import Figure
        result=analyze(RC_DECK,dict(self.settings,points=1001,pole_zero=False))
        plots=render(Figure(),result,'V(out)/V(in)','Group delay');_,f,delay,_=plots[0]
        np.testing.assert_allclose(delay[2:-2],.001/(1+(2*np.pi*f[2:-2]*.001)**2),rtol=.0003,atol=1e-10)

    def test_non_linear_and_unknown_probe_rejected(self):
        diode='Diode\nV1 in 0 1\nD1 in 0 rect\n.model rect D(IS=1p)\n.op\n.end\n'
        with self.assertRaises(ValueError):analyze(diode,self.settings)
        with self.assertRaises(ValueError):analyze(RC_DECK,dict(self.settings,output='V(missing)'))
        with self.assertRaises(ValueError):analyze(RC_DECK,dict(self.settings,points=1))

    def test_archive_preserves_complex_samples_and_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'rc.spkfreq';save_frequency(path,self.result)
            loaded=load_frequency(path);self.assertEqual(loaded,self.result)
            with self.assertRaises(FileExistsError):save_frequency(path,self.result)
        bad=deepcopy(self.result);bad['data']['frequency_hz'][1]=bad['data']['frequency_hz'][0]
        with self.assertRaises(ValueError):validate_result(bad)


if __name__=='__main__':unittest.main()
