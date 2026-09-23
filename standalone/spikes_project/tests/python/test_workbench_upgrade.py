from copy import deepcopy
from pathlib import Path
import os
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.document import Document,RC_DECK
from spikes_studio.power_tree import empty_tree,new_stage,budgets,validate,model_from_text,compile_tree
from spikes_studio.analytics import statistics,spectrum,validate_extension,evaluate_extension,EXTENSION_CONTRACT
from spikes_studio.signal_math import SignalMath,Quantity,VOLT
from spikes_studio.plot_panes import groups,default_layout
from spikes_studio.themes import PALETTES

def example_tree():
    tree=empty_tree();source=new_stage();stage=new_stage('converter',source['id']);load=new_stage('load',stage['id'])
    stage.update(voltage_v=3.3,efficiency=.9,quiescent_a=.001);load.update(current_a=.2,max_current_a=.4)
    tree['stages']=[source,stage,load];return tree

class UpgradeTests(unittest.TestCase):
    def test_theme_readability_contrast(self):
        def luminance(color):
            rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)];linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
            return sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))
        for name,p in PALETTES.items():
            for text in ('fg','muted','accent'):
                for surface in ('panel','field','canvas'):
                    a,b=sorted((luminance(p[text]),luminance(p[surface])))
                    self.assertGreaterEqual((b+.05)/(a+.05),4.5,(name,text,surface))
        self.assertEqual(PALETTES['Dark']['canvas'],'#000000')

    def test_pane_groups_weights_and_unit_safety(self):
        traces=[('V(a)',[1,2],'V'),('V(b)',[2,3],'V'),('I(R)',[1,2],'A')]
        self.assertEqual(len(groups(traces,default_layout())),2)
        layout={'mode':'custom','panes':{'V(a)':1,'V(b)':2,'I(R)':3},'heights':{'1':2}}
        result=groups(traces,layout);self.assertEqual(len(result),3);self.assertEqual(result[0][2],2)
        layout['panes']['I(R)']=1
        with self.assertRaises(ValueError):groups(traces,layout)

    def test_power_tree_typical_maximum_losses_and_limits(self):
        tree=example_tree();result=budgets(tree)
        self.assertAlmostEqual(result['total_input_w'],.66/.9+.012)
        self.assertAlmostEqual(result['conversion_loss_w'],.66/.9+.012-.66)
        self.assertAlmostEqual(budgets(tree,True)['total_input_w'],1.32/.9+.012)
        tree['stages'][1]['limit_a']=.1
        self.assertTrue(budgets(tree)['stages'][tree['stages'][1]['id']]['over_limit'])
        with self.assertRaises(ValueError):compile_tree(tree)

    def test_real_subcircuit_compiles_with_explicit_pin_order(self):
        tree=example_tree();tree['stages'][1]['model']=model_from_text('.subckt series INPUT OUTPUT GND\nRloss INPUT OUTPUT 2\n.ends series\n')
        source=compile_tree(tree)
        self.assertIn('.subckt series',source);self.assertIn(' 0 series',source);self.assertIn('Rloss INPUT OUTPUT 2',source)
        from python.spikes.netlist import parse_netlist
        project=parse_netlist(source,native_extensions=True)
        self.assertEqual(len(project.elements),3)

    def test_model_file_and_tree_safety(self):
        self.assertEqual(model_from_text('.subckt buck VIN GND VOUT\n.ends buck')['bindings'],['{in}','{gnd}','{out}'])
        self.assertEqual(model_from_text('.subckt custom A B\n.ends custom')['bindings'],['',''])
        for text in ('.include model.lib\n.subckt x a b\n.ends', '.subckt x a b\n.ends\nVbad a 0 12', '.subckt x a b\n.ends\n.end'):
            with self.assertRaises(ValueError):model_from_text(text)
        tree=example_tree();tree['stages'][1]['parent']=tree['stages'][1]['id']
        with self.assertRaises(ValueError):validate(tree)
        tree=example_tree();tree['stages'][0]['efficiency']=0
        with self.assertRaises(ValueError):validate(tree)

    def test_new_metadata_persists_with_undo_and_source_changes(self):
        doc=Document.from_netlist(RC_DECK);tree=example_tree();doc.commit(lambda d:d.__setitem__('power_tree',tree))
        doc.undo();self.assertEqual(doc.data['power_tree']['stages'],[]);doc.redo()
        doc.apply_source(RC_DECK.replace('1k','2k'))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'project.spksch';doc.save(path);self.assertEqual(Document.load(path).data['power_tree'],tree)

    def test_time_weighted_stats_and_spectrum_scaling(self):
        time=np.arange(4096)/4096;y=np.sin(2*np.pi*128*time);engine=SignalMath(time,{'v(a)':Quantity(y,VOLT)})
        report=statistics(engine,'V(a)');self.assertAlmostEqual(report['peak_to_peak'],2)
        self.assertAlmostEqual(report['rms'],2**-.5,delta=.001)
        spec=spectrum(engine,'V(a)');index=int(np.argmax(spec['amplitude']))
        self.assertEqual(spec['frequency_hz'][index],128);self.assertAlmostEqual(spec['amplitude'][index],1,places=6)
        self.assertAlmostEqual(float(np.sum(spec['psd']))*(spec['frequency_hz'][1]-spec['frequency_hz'][0]),.5,places=6)

    def test_irregular_resampling_must_be_explicit(self):
        t=np.linspace(0,1,64)**1.1;engine=SignalMath(t,{'v(a)':Quantity(t,VOLT)})
        with self.assertRaises(ValueError):spectrum(engine,'V(a)')
        self.assertTrue(spectrum(engine,'V(a)',True)['resampled'])

    def test_expression_extensions_are_bounded_and_not_executable(self):
        extension={'contract':EXTENSION_CONTRACT,'id':'ripple','name':'Ripple','measurements':[{'name':'pp','expression':'pp(x)'}],'traces':[{'name':'AC','expression':'x-mean(x)'}]}
        engine=SignalMath([0,1,2],{'v(a)':Quantity([1,2,3],VOLT)});result=evaluate_extension(engine,'V(a)',extension)
        self.assertEqual(result['measurements']['pp'].values,2);np.testing.assert_allclose(result['traces']['AC'].values,[-1,0,1])
        bad=extension|{'entrypoint':'evil.py'}
        with self.assertRaises(ValueError):validate_extension(bad)
        extension['measurements'][0]['expression']='__import__("os")'
        with self.assertRaises(ValueError):evaluate_extension(engine,'V(a)',extension)

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_LIBRARY'),'Native library required')
    def test_native_power_tree_uses_real_model_not_budget_voltage(self):
        from python.spikes.netlist import parse_netlist
        from python.spikes.native_runner import run_native_project
        tree=example_tree();tree['stages'][1]['model']=model_from_text('.subckt series INPUT OUTPUT GND\nRloss INPUT OUTPUT 2\n.ends series\n')
        result=run_native_project(parse_netlist(compile_tree(tree),native_extensions=True),os.environ['SPIKES_TEST_LIBRARY']).to_dict()
        self.assertEqual(result['status'],'completed')
        self.assertAlmostEqual(result['data']['node_voltage_v']['rail_'+tree['stages'][1]['id']],11.6)
        self.assertEqual(tree['stages'][1]['voltage_v'],3.3)

if __name__=='__main__':unittest.main()
