# SPDX-License-Identifier: Apache-2.0
"""Independent limiting, energy, and discrete-line convergence oracles."""
import cmath
import math
import unittest
import numpy as np
from numpy.polynomial.legendre import leggauss
from python.spike_core.solvers.power_integrity.peec.ac_power_integrity import analyze_ac_power_integrity, slab_field_loss, MU0


def request():
    return {"contract": "spike/ac-pi-request/v1", "frequencies_hz": [0, 1e6],
            "length_m": 10, "R_ohm_per_m": .1, "L_h_per_m": 250e-9,
            "G_s_per_m": 0, "C_f_per_m": 100e-12,
            "source_impedance_ohm": [50, 0], "load_impedance_ohm": [50, 0]}


class AcPowerIntegrityTests(unittest.TestCase):
    def test_dc_resistive_and_short_open_limits(self):
        p = request()
        s = analyze_ac_power_integrity(p)["samples"][0]
        self.assertAlmostEqual(s["input_impedance_ohm"][0], 51)
        self.assertAlmostEqual(s["load_voltage_v_rms"][0], 50/101)
        p["load_impedance_ohm"] = [0, 0]
        s = analyze_ac_power_integrity(p)["samples"][0]
        self.assertEqual(s["load_voltage_v_rms"], [0, 0])
        self.assertAlmostEqual(s["input_impedance_ohm"][0], 1)
        p["load_impedance_ohm"] = None
        s = analyze_ac_power_integrity(p)["samples"][0]
        self.assertEqual(s["input_impedance_state"], "open")
        self.assertEqual(s["load_voltage_v_rms"], [1, 0])

    def test_lossless_matched_line_and_ferranti(self):
        p = request()
        p.update(frequencies_hz=[1e6], R_ohm_per_m=0)
        s = analyze_ac_power_integrity(p)["samples"][0]
        beta_length = 2*math.pi*1e6*math.sqrt(250e-9*100e-12)*10
        expected = .5*cmath.exp(-1j*beta_length)
        self.assertAlmostEqual(abs(complex(*s["load_voltage_v_rms"])-expected), 0, places=13)
        p.update(source_impedance_ohm=[0, 0], load_impedance_ohm=None)
        s = analyze_ac_power_integrity(p)["samples"][0]
        self.assertAlmostEqual(s["load_to_sending_voltage_gain"], 1/math.cos(beta_length))
        self.assertTrue(s["voltage_rise_above_sending"])
        p["load_impedance_ohm"] = [5000, 0]
        self.assertGreater(analyze_ac_power_integrity(p)["samples"][0]["load_to_sending_voltage_gain"], 1)

    def test_quarter_wave_resonance_is_reported_not_fabricated(self):
        p = request()
        p.update(R_ohm_per_m=0, frequencies_hz=[5e6], length_m=10,
                 L_h_per_m=1e-6, C_f_per_m=250e-12,
                 load_impedance_ohm=None, source_impedance_ohm=[0, 0])
        # beta*l=pi/2; ideal open load and zero source R cannot have finite steady state.
        p["frequencies_hz"] = [1/(4*10*math.sqrt(1e-6*250e-12))]
        result = analyze_ac_power_integrity(p)["samples"][0]
        self.assertEqual(result["status"], "singular_source_load_resonance")
        self.assertNotIn("load_voltage_v_rms", result)

    def test_pi_ladder_converges_to_loaded_line(self):
        p = request()
        p["frequencies_hz"] = [20e6]
        exact = complex(*analyze_ac_power_integrity(p)["samples"][0]["load_voltage_v_rms"])
        errors = []
        for n in (20, 40, 80):
            z = (.1+1j*2*math.pi*20e6*250e-9)*10/n
            y = 1j*2*math.pi*20e6*100e-12*10/n
            # Independently compose shunt-series-shunt lumped KCL elements.
            shunt = np.array([[1, 0], [y/2, 1]], complex)
            section = shunt @ np.array([[1, z], [0, 1]], complex) @ shunt
            a = np.linalg.matrix_power(section, n)
            voltage = 50/(a[0,0]*50+a[0,1]+50*(a[1,0]*50+a[1,1]))
            errors.append(abs(voltage-exact))
        self.assertGreater(errors[0]/errors[1], 3.9)
        self.assertGreater(errors[1]/errors[2], 3.9)
        self.assertLess(errors[-1], 1e-3)

    def test_slab_dc_deep_skin_and_bias(self):
        w, t, sigma = .001, 35e-6, 5.8e7
        dc = 1/(w*t*sigma)
        for f in (0, 1e-9):
            s = slab_field_loss(f,w,t,sigma,-500+0j,500+0j)
            self.assertAlmostEqual(s["effective_resistance_ohm_per_m"],dc,places=12)
        f = 1e10
        isolated = slab_field_loss(f,w,t,sigma,-500+0j,500+0j)
        expected = 1/(2*sigma*w*math.sqrt(1/(math.pi*f*MU0*sigma)))
        self.assertAlmostEqual(isolated["effective_resistance_ohm_per_m"]/expected,1,places=10)
        biased = slab_field_loss(f,w,t,sigma,0j,1000+0j)
        self.assertAlmostEqual(biased["effective_resistance_ohm_per_m"]/expected,2,places=10)
        zero_net = slab_field_loss(1e6,w,t,sigma,1000+0j,1000+0j)
        self.assertIsNone(zero_net["effective_resistance_ohm_per_m"])
        self.assertGreater(zero_net["joule_loss_w_per_m"],0)

    def test_slab_joule_integral_independent_quadrature(self):
        w,t,sigma,f = .001, 35e-6, 5.8e7, 1e8
        left,right = 200+350j,1000-100j
        k = cmath.sqrt(1j*2*math.pi*f*MU0*sigma)
        avg,diff=(right+left)/2,(right-left)/2
        nodes,weights=leggauss(128)
        x=nodes*t/2
        j=k*(avg*np.sinh(k*x)/cmath.cosh(k*t/2)+diff*np.cosh(k*x)/cmath.sinh(k*t/2))
        integral=w*t/2/sigma*np.dot(weights,abs(j)**2)
        actual=slab_field_loss(f,w,t,sigma,left,right)["joule_loss_w_per_m"]
        self.assertAlmostEqual(actual/integral,1,places=12)

    def test_bad_inputs_and_worker_contract(self):
        from python.spike_core.service_simulation_handlers import handle_simulation_request
        p=request()
        value=handle_simulation_request('analyze_ac_power_integrity',{'request':p},assembly_scope={},solver_registry=None)
        self.assertEqual(value['result']['model_status'],'experimental')
        for key,value in [('R_ohm_per_m',-1),('length_m',0),('frequencies_hz',[1,1]),
                          ('source_impedance_ohm',[-1,0]),('L_h_per_m',float('nan'))]:
            p=request();p[key]=value
            with self.assertRaises(ValueError):analyze_ac_power_integrity(p)

    def test_schema_and_explicit_skin_replaces_r(self):
        import json
        from pathlib import Path
        import jsonschema
        root=Path(__file__).resolve().parents[2]
        p=request()
        p['conductor']={'width_m':.001,'thickness_m':35e-6,'conductivity_s_m':5.8e7,
                        'field_bias_ratio':[1,0]}
        p['R_ohm_per_m']=100
        result=analyze_ac_power_integrity(p)
        self.assertAlmostEqual(result['samples'][0]['R_ohm_per_m'],1/(.001*35e-6*5.8e7))
        self.assertGreater(result['samples'][1]['slab']['imposed_field_proximity_loss_w_per_m'],0)
        for value,name in ((p,'request'),(result,'result')):
            schema=json.loads((root/'schemas'/f'ac-pi-{name}-v1.schema.json').read_text())
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_finite_high_impedance_and_small_voltage_are_not_open_or_null(self):
        p=request()
        p.update(frequencies_hz=[0],length_m=1,R_ohm_per_m=0,L_h_per_m=0,
                 G_s_per_m=1e-16,C_f_per_m=0,load_impedance_ohm=None,
                 source_impedance_ohm=[0,0])
        sample=analyze_ac_power_integrity(p)['samples'][0]
        self.assertEqual(sample['input_impedance_state'],'finite')
        self.assertEqual(sample['input_impedance_ohm'],[1e16,0])
        p.update(G_s_per_m=0,load_impedance_ohm=[1,0],source_impedance_ohm=[1e20,0])
        sample=analyze_ac_power_integrity(p)['samples'][0]
        self.assertAlmostEqual(sample['sending_voltage_v_rms'][0]/1e-20,1)
        self.assertEqual(sample['load_to_sending_voltage_gain'],1)

    def test_impedance_scale_preserves_voltage_response(self):
        p=request()
        p.update(frequencies_hz=[0],length_m=1,R_ohm_per_m=2,L_h_per_m=0,
                 G_s_per_m=.01,C_f_per_m=0,load_impedance_ohm=[3,0],
                 source_impedance_ohm=[5,0])
        baseline=analyze_ac_power_integrity(p)['samples'][0]
        factor=1e16
        p['R_ohm_per_m']*=factor
        p['G_s_per_m']/=factor
        p['load_impedance_ohm'][0]*=factor
        p['source_impedance_ohm'][0]*=factor
        scaled=analyze_ac_power_integrity(p)['samples'][0]
        self.assertEqual(scaled['input_impedance_state'],'finite')
        for key in ('load_to_source_voltage_gain','load_to_sending_voltage_gain'):
            self.assertAlmostEqual(baseline[key],scaled[key],places=14)
        self.assertAlmostEqual(scaled['input_impedance_ohm'][0]/factor,
                               baseline['input_impedance_ohm'][0],places=14)


if __name__ == '__main__':
    unittest.main()
