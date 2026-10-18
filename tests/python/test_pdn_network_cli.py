# SPDX-License-Identifier: Apache-2.0
"""Actual CLI-to-worker PI workflow with independent RC frequency/time reference."""
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
REQUEST=ROOT/'examples/tutorial_pi_si/rc-pdn.request.json'


class PdnNetworkCliTests(unittest.TestCase):
    def run_cli(self,*args):
        return subprocess.run([sys.executable,'-m','python.spike_core.cli',*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=60)

    def test_actual_saved_result_matches_independent_rc_ac_and_ramp(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            output=Path(folder)/'result.json'
            completed=self.run_cli('--quiet','--output',output,'pdn-network',REQUEST)
            self.assertEqual(completed.returncode,0,completed.stderr)
            result=json.loads(output.read_text(encoding='utf-8'))
        self.assertEqual(result['contract'],'spike/pdn-network-result/v1')
        self.assertEqual(result['model_status'],'approximate');self.assertEqual(result['reference'],'GND')
        raw=json.loads(REQUEST.read_text(encoding='utf-8'))
        for sample,f in zip(result['ac'],raw['frequencies_hz']):
            actual=sample['impedance_ohm'][0][0];expected=1/(20+2j*math.pi*f*1e-4)
            self.assertAlmostEqual(actual['real'],expected.real,delta=1e-12)
            self.assertAlmostEqual(actual['imag'],expected.imag,delta=1e-12)
        tau=5e-6;rise=1e-6
        for point in result['load_transient']['points']:
            t=point['time_s']
            # tau*y'+y=R*I(t), with a finite linear current rise.
            expected=.05*(t/rise+tau/rise*math.expm1(-t/tau)) if t<=rise else .05*(1+tau/rise*math.expm1(-rise/tau)*math.exp(-(t-rise)/tau))
            self.assertAlmostEqual(-point['port_voltage_v']['load'],expected,delta=2e-7)
        self.assertLess(result['load_transient']['energy_balance_relative_error'],1e-8)

    def test_invalid_model_returns_error_and_no_completed_result(self):
        raw=json.loads(REQUEST.read_text(encoding='utf-8'));raw['elements'][0]['resistance_ohm']=-1
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            source=Path(folder)/'invalid.json';source.write_text(json.dumps(raw),encoding='utf-8');output=Path(folder)/'result.json'
            completed=self.run_cli('--quiet','--output',output,'pdn-network',source)
            self.assertNotEqual(completed.returncode,0)
            if output.exists():self.assertNotEqual(json.loads(output.read_text()).get('contract'),'spike/pdn-network-result/v1')


if __name__=='__main__':unittest.main()
