import os,unittest,math
from python.spikes.netlist import parse_netlist
from python.spikes.native_runner import run_native_project


@unittest.skipUnless(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY'),'Updated native charge library required')
class CompactCharge(unittest.TestCase):
    def test_wbg_binding(self):
        for model in ('SPK_GAN','SPK_SIC'):
            deck=f'.title WBG\nVd d 0 10\nVg g 0 PULSE(0 4 100n 100n 100n 10u 20u)\nZ1 d g 0 0 tj wm\n.model wm {model}(GATE_SOURCE_CAPACITANCE_F=1n THERMAL_CAPACITANCE_J_PER_K=.01)\n.tran 10n 2u\n.end'
            data=self.run_deck(deck)
            self.assertGreater(data['element_current_a']['Z1'][-1],0)
            self.assertGreater(data['node_voltage_v']['tj'][-1],0)

    def run_deck(self,source,method='backward_euler'):
        result=run_native_project(parse_netlist(source,native_extensions=True),os.environ['SPIKES_TEST_NATIVE_LIBRARY'],integration_method=method).to_dict()
        self.assertEqual(result['status'],'completed',result)
        return result['data']

    def test_mos_charge_and_kcl(self):
        deck='.title MOS charge\nVd d 0 1\nVg g 0 PULSE(0 3 100n 100n 100n 10u 20u)\nM1 d g 0 0 mm\n.model mm NMOS(LEVEL=1 KP=1m CGS=1n CGD=2n CDS=3n)\n.tran 10n 2u\n.end'
        for method in ('backward_euler','bdf2'):
            d=self.run_deck(deck,method);currents=d['element_current_a']
            # Gate draws charge, while MOS drain current includes Cgd displacement.
            self.assertGreater(max(-i for i in currents['VG']),.01)
            for a,b in zip(currents['VD'],currents['M1']):self.assertAlmostEqual(a+b,0,delta=1e-8)
            if method=='backward_euler':
                charge=sum(-currents['VG'][i]*(d['time_s'][i]-d['time_s'][i-1]) for i in range(1,len(d['time_s'])))
                self.assertAlmostEqual(charge,9e-9,delta=1e-12)

    def test_bjt_diffusion_charge(self):
        deck='.title BJT charge\nVc c 0 1\nVb b 0 PULSE(0 .6 100n 100n 100n 10u 20u)\nQ1 c b 0 qm\n.model qm NPN(IS=1f BF=99 {charge})\n.tran 10n 2u\n.end'
        baseline=self.run_deck(deck.replace('{charge}',''))
        charged=self.run_deck(deck.replace('{charge}','CBE=1n CBC=2n TF=1u TR=2u'))
        self.assertEqual(baseline['time_s'],charged['time_s'])
        t=charged['time_s'];b=baseline['element_current_a']['VB'];c=charged['element_current_a']['VB']
        integral=sum((b[i]-c[i])*(t[i]-t[i-1]) for i in range(1,len(t)))
        vt=8.617333262145e-5*300.15
        expected=3e-9*.6+1e-6*1e-15*math.expm1(.6/vt)+2e-6*1e-15*(math.exp(-.4/vt)-math.exp(-1/vt))
        self.assertAlmostEqual(integral,expected,delta=2e-12)
