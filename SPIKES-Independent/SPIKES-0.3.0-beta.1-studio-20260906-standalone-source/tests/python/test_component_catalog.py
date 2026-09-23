import os
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))
from spikes_studio.component_catalog import catalog,evaluate,native_recipe,validate_record,NATIVE
from spikes_studio.controller_block import Controller,default_config,validate
from spikes_studio.ide import find_tool


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.library=catalog();cls.records=cls.library['records']

    def test_counts_and_unique_parameter_sets(self):
        self.assertEqual(len(self.records),5000);self.assertEqual(self.library['archetype_count'],100)
        self.assertEqual(set(self.library['counts'].values()),{500})
        import json
        keys={(r['family'],json.dumps(r['parameters'],sort_keys=True)) for r in self.records}
        self.assertEqual(len(keys),5000)
        self.assertEqual(sum(r['status']=='native_subcircuit' for r in self.records),650)

    def test_every_preset_validates_and_evaluates(self):
        for record in self.records:
            validate_record(record)
            result=evaluate(record,{'x':.1,'voltage':.01,'current':.01,'frequency_hz':1000})
            self.assertTrue(result['outputs'],record['id']);self.assertTrue(result['not_circuit_coupled'])

    def test_native_recipes_all_parse(self):
        from python.spikes.netlist import parse_netlist
        for record in self.records:
            if record['family'] not in NATIVE:continue
            model=native_recipe(record);nodes=['in','0'] if len(model['pins'])==2 else ['in','out','0']
            source='Recipe qualification\nVTEST supply 0 0.1\nRTEST supply in 1000\nRLOAD out 0 10000\n'+model['source']+'XTEST '+' '.join(nodes)+' '+model['name']+'\n.op\n.end\n'
            project=parse_netlist(source,native_extensions=True)
            self.assertGreater(len(project.elements),3)

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_LIBRARY'),'Native library not configured')
    def test_all_650_recipes_solve_with_owned_cpp(self):
        from python.spikes.netlist import parse_netlist
        from python.spikes.native_runner import run_native_project
        for record in self.records:
            if record['family'] not in NATIVE:continue
            model=native_recipe(record);nodes=['in','0'] if len(model['pins'])==2 else ['in','out','0']
            source='Recipe smoke solve\nVTEST supply 0 0.1\nRTEST supply in 1000\nRLOAD out 0 10000\n'+model['source']+'XTEST '+' '.join(nodes)+' '+model['name']+'\n.op\n.end\n'
            result=run_native_project(parse_netlist(source,native_extensions=True),os.environ['SPIKES_TEST_LIBRARY'])
            self.assertEqual(result.status,'completed',(record['id'],result.to_dict()))

    def test_unknown_parameters_rejected_and_dropout_loss(self):
        record=next(r for r in self.records if r['family']=='linear_regulator')
        record['parameters']['voltage']=5
        result=evaluate(record,{'voltage':3,'current':1})
        self.assertAlmostEqual(result['outputs']['dissipation']['value'],.3)
        record['parameters']['invented_parameter']=12
        with self.assertRaises(ValueError):validate_record(record)

    def test_physics_and_failure_relations(self):
        pick=lambda name:next(r for r in self.records if r['family']==name)
        ntc=pick('ntc');cold=evaluate(ntc,{'temperature_k':298.15})['outputs']['resistance']['value'];hot=evaluate(ntc,{'temperature_k':350})['outputs']['resistance']['value'];self.assertLess(hot,cold)
        fuse=pick('fuse');self.assertTrue(evaluate(fuse,{'current':100})['alerts'])
        lut=pick('lookup_table');lut['parameters'].update(x=[-2,0,2],y=[3,0,-3]);self.assertEqual(evaluate(lut,{'x':1})['outputs']['output']['value'],-1.5)

    def test_logic_truth_tables_and_quantizer_endpoints(self):
        expected={'and':lambda a,b:a and b,'or':lambda a,b:a or b,'not':lambda a,b:not a,'nand':lambda a,b:not(a and b),'nor':lambda a,b:not(a or b),'xor':lambda a,b:a!=b,'xnor':lambda a,b:a==b}
        for family,logic in expected.items():
            record=next(r for r in self.records if r['family']==family);vdd=record['parameters']['vdd']
            for a in (0,1):
                for b in (0,1):self.assertEqual(evaluate(record,{'a':a*vdd,'b':b*vdd})['outputs']['output']['value'],float(logic(a,b))*vdd)
        for family in ('adc','dac'):
            record=next(r for r in self.records if r['family']==family);top=2**int(record['parameters']['bits'])-1
            output=evaluate(record,{'x':record['parameters']['vref'] if family=='adc' else top})['outputs']
            self.assertEqual(next(iter(output.values()))['value'],top if family=='adc' else record['parameters']['vref'])

    def test_battery_coulomb_count_and_filter_corner(self):
        import math
        battery=next(r for r in self.records if r['family']=='battery_liion');state={'soc':.8}
        result=evaluate(battery,{'current':1},state,dt=1)
        self.assertAlmostEqual(result['state']['soc'],.8-1/(3600*battery['parameters']['capacity_ah']))
        rc=next(r for r in self.records if r['family']=='rc_lowpass');result=evaluate(rc,{'frequency_hz':rc['parameters']['frequency']})
        self.assertAlmostEqual(result['outputs']['magnitude']['value'],1/math.sqrt(2));self.assertAlmostEqual(result['outputs']['phase']['value'],-45)

    def test_controller_trust_and_pin_validation(self):
        config=default_config()
        with self.assertRaisesRegex(ValueError,'consent'):Controller(config)
        config['pins'][1]['name']=config['pins'][0]['name']
        with self.assertRaises(ValueError):validate(config)

    def test_measured_alerts_no_thermal_invention(self):
        from spikes_studio.part_alerts import evaluate_limits
        snapshot={'components':[{'id':'r','ref':'R1','nodes':['a','0'],'limits':{'power_w':.25,'current_a':1.,'voltage_v':2.,'temperature_k':400}}]}
        result={'data':{'node_voltage_v':{'a':[1.,2.],'0':[0.,0.]},'element_current_a':{'R1':[.1,.9]},'element_power_w':{'R1':[.1,.3]}}}
        findings=evaluate_limits(snapshot,result)['r']['findings'];levels={f['limit']:f['severity'] for f in findings}
        self.assertEqual(levels,{'power_w':'exceeded','current_a':'warning','voltage_v':'exceeded','temperature_k':'unavailable'})

    def test_vendor_intake_never_approves_execution(self):
        from spikes_studio.vendor_intake import intake
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'local.lib';path.write_text('.model DLOCAL D(IS=1e-12)\n.include external.lib\n',encoding='utf-8')
            report=intake(path)
        self.assertEqual(report['execution'],'not_approved');self.assertEqual(report['models'][0]['name'],'DLOCAL');self.assertEqual(report['dependencies_not_loaded'],['external.lib'])

    @unittest.skipUnless(find_tool('cl') or find_tool('clang'),'Compiler not configured')
    def test_real_compiled_c_and_cpp_virtual_ticks(self):
        for language in ('C','C++'):
            config=default_config();config['language']=language
            config['source']=config['source'].replace('inputs[0]','inputs[IN_sense]').replace('outputs[0]','outputs[OUT_drive]')
            controller=Controller(config,trusted=True)
            try:
                self.assertEqual(controller.step({'sense':0},0,.001),{'V1':3.3})
                self.assertEqual(controller.step({'sense':2},.001,.001),{'V1':0})
                self.assertAlmostEqual(controller.state['state_0'],.002)
                self.assertEqual(controller.tick,2)
            finally:controller.close()

    @unittest.skipUnless(os.environ.get('SPIKES_TEST_LIBRARY') and (find_tool('cl') or find_tool('clang')),'Native library/compiler not configured')
    def test_native_closed_loop_controller(self):
        from python.spikes.netlist import parse_netlist
        from python.spikes.native_abi import load_native_library
        from python.spikes.native_runner import _populate
        project=parse_netlist('Control plant\nV1 in 0 0\nR1 in out 1000\nC1 out 0 1u\n.tran 100u 5m uic\n.end',native_extensions=True)
        controller=Controller(default_config(),trusted=True);controller.bind(project)
        try:
            with load_native_library(os.environ['SPIKES_TEST_LIBRARY']).circuit() as circuit:
                _populate(circuit,project)
                with circuit.transient_session(initialize_from_operating_point=False) as session:
                    for _ in range(30):controller.advance(session);self.assertTrue(session.step(.0001))
                    self.assertGreater(session.node_voltage('out'),.7);self.assertLess(session.node_voltage('out'),1.4)
        finally:controller.close()

if __name__=='__main__':unittest.main()
