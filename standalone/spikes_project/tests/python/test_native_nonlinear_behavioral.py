import os,unittest,math
from python.spikes.netlist import parse_netlist
from python.spikes.native_runner import run_native_project


@unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Updated native behavioral engine required')
class NativeBehavioral(unittest.TestCase):
    def test_time_source(self):
        deck='.title time\nB1 out 0 V={sin(2*pi*1000*time)}\nR1 out 0 1000\n.tran 10u 250u uic\n.end'
        d=self.run_deck(deck)
        self.assertAlmostEqual(d['node_voltage_v']['out'][-1],1,places=7)

    def run_deck(self,source,method='backward_euler'):
        result=run_native_project(parse_netlist(source,native_extensions=True),os.environ['SPIKES_TEST_NATIVE_LIBRARY'],integration_method=method).to_dict()
        self.assertEqual(result['status'],'completed',result)
        return result['data']

    def test_nonlinear_feedback(self):
        for analysis in ('.op','.tran 10u 100u uic'):
            data=self.run_deck(f'.title feedback\nV1 in 0 2\nR1 in out 1000\nB1 out 0 I={{.001*V(out)^3}}\n{analysis}\n.end')
            value=data['node_voltage_v']['out'];self.assertAlmostEqual(value[-1] if isinstance(value,list) else value,1,places=6)

    def test_functions_and_multiple_signals(self):
        for expression,expected in [('sin(V(a))+V(b)^2+1000*I(V1)',math.sin(2)+9-2),
                                    ('if(V(a)>0,log(V(a)),0)',math.log(2)),
                                    ('table(V(a),0,0,1,2,3,6)',4),
                                    ('limit(V(a)^2,0,3)',3),
                                    ('atan2(V(a)+1,V(b)+1)',math.atan2(3,4)),
                                    ('sqrt(V(a)+4)',math.sqrt(6))]:
            with self.subTest(expression=expression):
                data=self.run_deck(f'.title functions\nV1 a 0 2\nV2 b 0 3\nR1 a 0 1000\nB1 out 0 V={{{expression}}}\nR2 out 0 1000\n.op\n.end')
                self.assertAlmostEqual(data['node_voltage_v']['out'],expected,places=7)

    def test_dynamic_saturated_amplifier(self):
        deck='.title dynamic\nV1 in 0 PULSE(0 2 10u 10u 10u 1m 2m)\nB1 drive 0 V={tanh(V(in))}\nR1 drive out 1000\nC1 out 0 1n\n.tran 1u 100u uic\n.end'
        for method in ('backward_euler','bdf2','hybrid_trapezoidal'):
            d=self.run_deck(deck,method);self.assertAlmostEqual(d['node_voltage_v']['out'][-1],math.tanh(2),delta=5e-6)
