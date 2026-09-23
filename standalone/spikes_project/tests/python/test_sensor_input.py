from pathlib import Path
import sys
import tempfile
import unittest
import wave
import struct
import os
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.sensor_input import load_recording,apply_recording
from spikes_studio.document import Document


class RecordedInputs(unittest.TestCase):
    def test_stereo_pcm_and_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.wav'
            with wave.open(str(path),'wb') as wav:
                wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(1000)
                wav.writeframes(struct.pack('<hhhhhh',0,-16384,100,0,200,16384))
            record=load_recording(path,channel=1,gain=2,offset=1)
            self.assertEqual(record['values'],[0,1,2]);self.assertEqual(record['time_s'],[0,.001,.002])
            source=apply_recording('Sensor\nV1 in 0 0\nR1 in 0 1k\n.tran 1m 2m uic\n.end\n','V1',record)
            self.assertIn('PWL(',source);Document.from_netlist(source)
            library=os.environ.get('SPIKES_TEST_NATIVE_LIBRARY')
            if library:
                from spikes_studio.run_control import native_batch
                result=native_batch(source,library)
                self.assertEqual(result['status'],'completed')
                self.assertAlmostEqual(result['data']['node_voltage_v']['in'][-1],2,places=7)
            with self.assertRaises(ValueError):load_recording(path,channel=2)

    def test_csv_scaling_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'acceleration.csv'
            path.write_text('time_s,ax,ay\n0,1,2\n.1,3,4\n')
            r=load_recording(path,channel=0,gain=.1,unit='m/s^2')
            self.assertAlmostEqual(r['values'][1],.3)
            self.assertEqual(len(r['provenance']['sha256']),64)
            for rows in ('0,1\n0,2','0,1\n.1,nan','1,1\n2,2'):
                path.write_text('time_s,ax\n'+rows+'\n')
                with self.assertRaises(ValueError):load_recording(path)

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Native DLL not configured')
    def test_native_monte_carlo_reproducible(self):
        from python.spikes.netlist import parse_netlist
        from python.spikes.sweeps import run_monte_carlo,RelativeVariation
        project=parse_netlist('MC\nV1 in 0 1\nR1 in out 1k\nR2 out 0 1k\n.op\n.end\n')
        kwargs=dict(samples=4,seed=42,native_library=os.environ['SPIKES_TEST_NATIVE_LIBRARY'])
        a=run_monte_carlo(project,[RelativeVariation('R1',.1)],**kwargs)
        b=run_monte_carlo(project,[RelativeVariation('R1',.1)],**kwargs)
        self.assertEqual(a['status'],'completed');self.assertEqual(a['provenance']['execution'],'independent_owned_cpp_cases')
        self.assertEqual([c['relative_deviations'] for c in a['cases']],[c['relative_deviations'] for c in b['cases']])
        for case in a['cases']:
            delta=case['relative_deviations']['R1']
            self.assertAlmostEqual(case['result']['data']['node_voltage_v']['out'],1/(2+delta),places=8)
