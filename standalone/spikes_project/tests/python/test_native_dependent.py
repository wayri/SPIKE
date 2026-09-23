from pathlib import Path
import sys,os,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.run_control import native_batch


@unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Updated native library required')
class DependentSources(unittest.TestCase):
    def test_interactive_control(self):
        import time
        from spikes_studio.run_control import InteractiveRun
        deck='.title live dependent\nV1 in 0 2\nE1 out 0 in 0 3\nR1 out 0 1000\n.tran 100u 10m uic\n.end'
        session=InteractiveRun(deck,os.environ['SPIKES_TEST_NATIVE_LIBRARY'],speed_ratio=1)
        try:
            session.set_source('V1',3)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                if session.state=='failed':self.fail(session.error)
                sample=session.snapshot()
                if sample and abs(sample['data']['node_voltage_v']['out'][-1]-9)<1e-8:break
                time.sleep(.01)
            else:self.fail('Dependent output did not follow interactive source update')
        finally:session.stop();session.thread.join(5)

    def test_dc_and_transient(self):
        for record,expected in [('E1 out 0 in 0 3',6),('G1 0 out in 0 .003',6),
                                ('F1 0 out V1 -3',6),('H1 out 0 V1 -3000',6),
                                ('B1 out 0 V={3*V(in)}',6),('B1 0 out I={.003*V(in)}',6),
                                ('E1 out 0 in 0 -3',-6)]:
            for analysis in ('.op','.tran 10u 100u uic'):
                with self.subTest(record=record,analysis=analysis):
                    # Place control source after the controlled source: forward reference.
                    deck=f'.title dependent\n{record}\nRload out 0 1000\nV1 in 0 2\nRin in 0 1000\n{analysis}\n.end'
                    result=native_batch(deck,os.environ['SPIKES_TEST_NATIVE_LIBRARY'])
                    value=result['data']['node_voltage_v']['out']
                    self.assertAlmostEqual(value[-1] if isinstance(value,list) else value,expected,places=7)
