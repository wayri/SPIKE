from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.offline_report import snapshot,render,script_json,MAX_POINTS
from spikes_studio.signal_math import SignalMath,Quantity,VOLT


class OfflineReportTests(unittest.TestCase):
    def test_bounded_display_exact_measurement_and_offline_html(self):
        time=np.linspace(0,1,10001);values=np.zeros_like(time);values[4567]=123.5
        engine=SignalMath(time,{'v(out)':Quantity(values,VOLT)})
        report=snapshot(engine,['v(out)'],title='Actual acquisition',provenance={'solver':'test fixture'})
        self.assertLessEqual(len(report['traces'][0]['x']),MAX_POINTS)
        self.assertEqual(report['measurements'][0]['maximum'],123.5)
        self.assertEqual(report['measurements'][0]['count'],10001)
        self.assertFalse(report['capture']['live'])
        html=render(report)
        self.assertIn("connect-src 'none'",html)
        self.assertNotIn('<script src=',html)
        self.assertIn('Plotly.newPlot',html)
        self.assertEqual(engine.signals['v(out)'].values[4567],123.5)

    def test_untrusted_project_text_cannot_end_script(self):
        title='</script><img src=https://example.test/leak>'
        self.assertNotIn('<',script_json({'title':title}))
        engine=SignalMath([0,1],{'v(out)':Quantity([0,1],VOLT)})
        html=render(snapshot(engine,['v(out)'],title=title))
        self.assertNotIn('<img src=https://example.test/leak>',html)
        with self.assertRaises(ValueError):snapshot(engine,['v(out)'],palette={'canvas':'red; background:url(x)','fg':'#000000','grid':'#000000'})
        with self.assertRaises(ValueError):snapshot(engine,[])
