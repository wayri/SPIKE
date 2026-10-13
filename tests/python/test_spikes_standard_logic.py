# SPDX-License-Identifier: Apache-2.0
import itertools
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from python.spikes.digital import DigitalKernel, LogicValue
from python.spikes.standard_logic import package, catalog, bind, spice_recipe


class StandardLogicTests(unittest.TestCase):
    def fixture(self, part, delay=3):
        kernel = DigitalKernel()
        descriptor = package(part)
        mapping = {p['number']: 'pin'+p['number'] for p in descriptor['pins']}
        for name in mapping.values(): kernel.add_signal(name)
        bind(kernel, part, 'U1', mapping, delay_ticks=delay)
        return kernel, descriptor, mapping

    def test_all_gates_truth_tables_and_delay(self):
        operations = {'nand': lambda bits: not all(bits), 'nor': lambda bits: not any(bits),
                      'not': lambda bits: not bits[0], 'and': all,
                      'or': any, 'xor': lambda bits: sum(bits)%2}
        for part in catalog():
            for bits in itertools.product((0,1), repeat=len(part['gates'][0]['inputs'])):
                kernel, descriptor, mapping = self.fixture(part['part'])
                for gate in descriptor['gates']:
                    for p,value in zip(gate['inputs'], bits):
                        kernel.drive(mapping[p], 'stimulus', str(value))
                kernel.run_until(2)
                for gate in descriptor['gates']: self.assertEqual(kernel.value(mapping[gate['output']]), LogicValue.Z)
                kernel.run_until(3)
                expected = '1' if operations[part['family']](bits) else '0'
                for gate in descriptor['gates']: self.assertEqual(kernel.value(mapping[gate['output']]).value, expected)

    def test_pinout_special_cases_and_isolated_copies(self):
        self.assertEqual(package('SN74HC02N')['gates'][0], {'inputs':['2','3'], 'output':'1'})
        self.assertEqual(package('SN54HC04J')['gates'][-1], {'inputs':['13'], 'output':'12'})
        first = package('SN74HC00N');first['pins'].clear()
        self.assertEqual(len(package('SN74HC00N')['pins']),14)
        self.assertEqual(len(catalog()),20)
        self.assertEqual(package('SN74HC10N')['gates'][0]['inputs'], ['1','2','13'])
        self.assertEqual([p['number'] for p in package('SN54HC21J')['pins']
                          if p['role']=='unconnected'], ['3','11'])

    def test_unknown_propagation_and_controlling_values(self):
        kernel, descriptor, mapping = self.fixture('SN74HC00N')
        kernel.drive(mapping['1'],'stimulus','0');kernel.drive(mapping['2'],'stimulus','X')
        kernel.run_until(3);self.assertEqual(kernel.value(mapping['3']),LogicValue.ONE)
        kernel.drive(mapping['1'],'stimulus','1');kernel.run_until(6)
        self.assertEqual(kernel.value(mapping['3']),LogicValue.X)

    def test_errors_do_not_partially_bind(self):
        kernel, descriptor, mapping = self.fixture('SN74HC08N')
        before=kernel.model()
        for bad in ({**mapping,'1':'missing'}, {k:v for k,v in mapping.items() if k!='14'}):
            with self.assertRaises(ValueError):bind(kernel,'SN74HC08N','U2',bad,delay_ticks=1)
            self.assertEqual(kernel.model(),before)
        with self.assertRaises(ValueError):bind(kernel,'SN74HC08N','U1',mapping,delay_ticks=1)
        for part in ('SN74LS00N','SN74HC00J','SN54HC00FK','STM32'):
            with self.assertRaises(ValueError):package(part)
        with self.assertRaises(ValueError):spice_recipe('SN74HC00N',output_resistance_ohm=0,input_capacitance_f=1e-12,transition_v=.1)

    def test_electrical_recipe_declares_approximation(self):
        recipe=spice_recipe('SN74HC02N',output_resistance_ohm=50,input_capacitance_f=5e-12,transition_v=.1)
        self.assertEqual(recipe['qualification'],'unqualified_generic')
        self.assertIn('P2',recipe['source']);self.assertIn('NO DELAY',recipe['source'])

    def test_ngspice_electrical_truth_tables(self):
        runtime = Path(os.environ.get('SPIKES_TEST_NGSPICE', 'runtime/external/Spice64/bin/ngspice_con.exe')).resolve()
        if not runtime.is_file(): self.skipTest('Explicit ngspice runtime is unavailable')
        operations = {'nand':lambda bits:not all(bits), 'nor':lambda bits:not any(bits),
                      'not':lambda bits:not bits[0], 'and':all,
                      'or':any, 'xor':lambda bits:sum(bits)%2}
        with tempfile.TemporaryDirectory() as directory:
            for descriptor in catalog():
                gate=descriptor['gates'][0];operation=operations[descriptor['family']]
                recipe=spice_recipe(descriptor['part'],output_resistance_ohm=50,input_capacitance_f=5e-12,transition_v=.05)
                for bits in itertools.product((0,1), repeat=len(gate['inputs'])):
                    nodes={str(i):'0' for i in range(1,15)};nodes['14']='supply'
                    for pin in gate['inputs']:nodes[pin]='in'+pin
                    # Every output is isolated, never short unused gates to ground.
                    for channel in descriptor['gates']:nodes[channel['output']]='out'+channel['output']
                    out=nodes[gate['output']]
                    stimulus=''.join(f'V{pin} in{pin} 0 {value*5}\n' for pin,value in zip(gate['inputs'],bits))
                    source='Standard functional electrical gate test\nVs supply 0 5\n'+stimulus+recipe['source']
                    source+='XU '+' '.join(nodes[str(i)] for i in range(1,15))+' '+recipe['name']+'\n'
                    source+=f'RL {out} 0 10000\n.op\n.control\nrun\nprint v({out})\nquit\n.endc\n.end\n'
                    path=Path(directory)/'gate.cir';path.write_text(source,encoding='ascii')
                    run=subprocess.run([str(runtime),'-b',str(path)],cwd=directory,capture_output=True,text=True,timeout=15)
                    self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                    values=re.findall(r'v\('+out+r'\)\s*=\s*([-+0-9.eE]+)',run.stdout)
                    self.assertTrue(values,run.stdout+run.stderr)
                    expected=5*10000/10050 if operation(bits) else 0
                    self.assertAlmostEqual(float(values[-1]),expected,delta=1e-5)


if __name__ == '__main__':unittest.main()
