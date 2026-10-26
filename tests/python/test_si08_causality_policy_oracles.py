# SPDX-License-Identifier: Apache-2.0
"""Original finite-grid witnesses: constructed time support is not inferred."""
from copy import deepcopy
from fractions import Fraction
import math
import unittest

import numpy as np
from scipy.integrate import quad

from python.spike_core.solvers.signal_integrity.networks import sparameter_sampling as sampling
from python.spike_core.solvers.signal_integrity.networks import sparameter_rational as rational


ALPHA = 2 * math.pi * 40e6
BETA = 4 * ALPHA
GAIN = 0.2
DELAY = 0.6e-9


def resonance(frequency):
    s = 2j * math.pi * np.asarray(frequency)
    return GAIN * (ALPHA**2 + BETA**2) / ((s + ALPHA)**2 + BETA**2)


def impulse(time):
    if time < 0:
        return 0.0
    return GAIN * (ALPHA**2 + BETA**2) / BETA * math.exp(-ALPHA*time) * math.sin(BETA*time)


def request(frequencies, responses, targets=None):
    grid = [float(f) for f in frequencies]
    return {"contract": sampling.REQUEST_CONTRACT,
            "source": {"id": "original-i02-supplied-samples", "port_names": ["observed-port"],
                       "reference_impedance_ohm": 50.0, "frequencies_hz": grid,
                       "s_parameters": [[[{'real': float(complex(h).real), 'imag': float(complex(h).imag)}]]
                                        for h in responses]},
            "target_frequencies_hz": grid[:] if targets is None else [float(f) for f in targets],
            "dc_policy": {"mode": "require_source"}}


def output_values(result):
    return np.array([complex(m[0][0]['real'], m[0][0]['imag'])
                     for m in result['derived_network']['s_parameters']])


def refinement(kind):
    """Actual owner calls on explicitly refined supports; no inferred samples."""
    counts = (16, 32, 64, 128) if kind == "delay" else (64, 128, 256, 512)
    bandwidth = 4e9 if kind == "delay" else 2 * BETA / (2 * math.pi)
    response = (lambda f: 0.72 * np.exp(-2j * math.pi * np.asarray(f) * DELAY)) if kind == "delay" else resonance
    errors = []
    for count in counts:
        grid = np.linspace(0, bandwidth, count+1)
        targets = (grid[:-1] + grid[1:]) / 2
        result = sampling.resample_sparameter_network(request(grid, response(grid), targets))
        errors.append(float(np.max(abs(output_values(result) - response(targets)))))
    return counts, bandwidth, errors


class CausalityPolicyOracleTests(unittest.TestCase):
    def assert_unknown_source(self, result):
        self.assertEqual(result['model_status'], 'experimental')
        self.assertFalse(result['production_qualified'])
        limitations = ' '.join(result['limitations']).lower()
        self.assertIn('causality', limitations)
        self.assertNotIn('source_causality', result)

    def test_resonant_time_support_and_independent_fourier_quadrature(self):
        # Integration is in u=alpha*t. H uses exp(-j*omega*t), in Hz below.
        coefficient = GAIN * (ALPHA**2 + BETA**2) / (ALPHA * BETA)
        self.assertLess(coefficient * math.exp(-40), 4e-18)
        for frequency in (0.0, 64e6, 160e6, 272e6):
            q = 2 * math.pi * frequency / ALPHA
            real = quad(lambda u: coefficient * math.exp(-u) * math.sin(4*u) * math.cos(q*u),
                        0, 40, epsabs=2e-13, epsrel=2e-13, limit=250)[0]
            imag = quad(lambda u: -coefficient * math.exp(-u) * math.sin(4*u) * math.sin(q*u),
                        0, 40, epsabs=2e-13, epsrel=2e-13, limit=250)[0]
            self.assertAlmostEqual(abs(complex(real, imag) - resonance(frequency)), 0, delta=2e-12)
            # t -> -t reverses the Fourier sign, retaining magnitude.
            self.assertAlmostEqual(abs(complex(real, -imag) - resonance(frequency).conjugate()), 0, delta=2e-12)
        witness = math.pi / (2 * BETA)
        self.assertEqual(impulse(-witness), 0)
        self.assertGreater(impulse(witness), 0)
        self.assertGreater(impulse(-(-witness)), 0)  # reversed impulse is nonzero before zero

    def test_delayed_resonance_time_shift_and_advance_sign(self):
        coefficient = GAIN * (ALPHA**2 + BETA**2) / (ALPHA * BETA)
        for frequency in (35e6, 160e6, 310e6):
            omega = 2 * math.pi * frequency
            # Integrate h(t-tau) from tau onward; delay occurs inside the phase.
            real = quad(lambda u: coefficient * math.exp(-u) * math.sin(4*u)
                        * math.cos(omega * (u/ALPHA + DELAY)), 0, 40,
                        epsabs=2e-13, epsrel=2e-13, limit=250)[0]
            imag = quad(lambda u: -coefficient * math.exp(-u) * math.sin(4*u)
                        * math.sin(omega * (u/ALPHA + DELAY)), 0, 40,
                        epsabs=2e-13, epsrel=2e-13, limit=250)[0]
            expected = np.exp(-1j * omega * DELAY) * resonance(frequency)
            self.assertAlmostEqual(abs(complex(real, imag) - expected), 0, delta=2e-12)
        frequency = 1 / (4 * DELAY)
        self.assertAlmostEqual(abs(np.exp(-2j*math.pi*frequency*DELAY) + 1j), 0, delta=2e-15)
        self.assertAlmostEqual(abs(np.exp(2j*math.pi*frequency*DELAY) - 1j), 0, delta=2e-15)
        self.assertEqual(impulse(DELAY/2 - DELAY), 0)

    def test_actual_delayed_grid_refinement_matches_exact_error(self):
        counts, bandwidth, errors = refinement('delay')
        for count, error in zip(counts, errors):
            exact_error = 0.72 * (1 - math.cos(math.pi * bandwidth / count * DELAY))
            self.assertAlmostEqual(error, exact_error, delta=5e-15)
        self.assertTrue(all(3.9 < a/b < 4.01 for a, b in zip(errors, errors[1:])))
        self.assertLess(errors[-1], 0.0013)

    def test_actual_resonant_grid_refinement_and_curvature_bound(self):
        counts, bandwidth, errors = refinement('resonance')
        curvature_bound = 2 * GAIN * (ALPHA**2+BETA**2) * (2*math.pi)**2 / (BETA * ALPHA**3)
        for count, error in zip(counts, errors):
            self.assertLess(error, curvature_bound * (bandwidth/count)**2 / 8)
        self.assertTrue(all(3.8 < a/b < 4.1 for a, b in zip(errors, errors[1:])) )
        self.assertLess(errors[-1], 3e-5)

    def test_anti_causal_advance_and_reversed_resonance_are_not_classified(self):
        grid = np.linspace(0, 320e6, 65)
        for causal in (0.72*np.exp(-2j*math.pi*grid*DELAY), resonance(grid)):
            outputs = []
            for responses in (causal, causal.conjugate()):
                req = request(grid, responses, np.linspace(0, 320e6, 129))
                saved = deepcopy(req)
                out = sampling.resample_sparameter_network(req)
                self.assert_unknown_source(out)
                self.assertIn('not broadband passivity or causality qualification', ' '.join(out['limitations']))
                self.assertEqual(req, saved)
                self.assertEqual(out['source']['network'], saved['source'])
                self.assertTrue(all(row['smax'] < 1 for row in out['diagnostics']))
                outputs.append(output_values(out))
                out['derived_network']['s_parameters'][0][0][0]['real'] = 99
                self.assertEqual(req, saved)
                self.assertEqual(out['source']['network'], saved['source'])
            np.testing.assert_allclose(outputs[1], outputs[0].conjugate(), atol=2e-15, rtol=0)

    def test_finite_grid_exact_delay_advance_alias_and_offgrid_separation(self):
        spacing = 100e6
        grid = np.arange(17, dtype=float) * spacing
        delay, advance = 1/(4*spacing), 3/(4*spacing)
        # Exact quarter-cycle records avoid confusing floating exp noise with ambiguity.
        roots = np.array([1, -1j, -1, 1j]) * 0.7
        identical = roots[np.arange(len(grid)) % 4]
        delay_cycles = [Fraction(-k, 4) % 1 for k in range(len(grid))]
        advance_cycles = [Fraction(3*k, 4) % 1 for k in range(len(grid))]
        self.assertEqual(delay_cycles, advance_cycles)
        for cycles in (delay_cycles, advance_cycles):
            evaluated = 0.7*np.exp(2j*math.pi*np.array([float(c) for c in cycles]))
            np.testing.assert_allclose(evaluated, identical, atol=2e-15, rtol=0)
        targets = (grid[:-1] + grid[1:]) / 2
        causal_req = request(grid, identical, targets)
        advance_req = deepcopy(causal_req)
        advance_req['source']['id'] = 'same-samples-from-advance'
        causal_out = sampling.resample_sparameter_network(causal_req)
        advance_out = sampling.resample_sparameter_network(advance_req)
        self.assertEqual(causal_out['derived_network']['s_parameters'], advance_out['derived_network']['s_parameters'])
        self.assert_unknown_source(causal_out)
        self.assert_unknown_source(advance_out)
        # Their exact midpoint responses are opposite despite identical samples.
        difference = abs(0.7*np.exp(-2j*math.pi*targets*delay) - 0.7*np.exp(2j*math.pi*targets*advance))
        np.testing.assert_allclose(difference, 1.4, atol=5e-15, rtol=0)

    def test_dc_missing_supplied_and_source_are_distinct_policies(self):
        grid = [40e6, 160e6, 320e6]
        req = request(grid, resonance(grid))
        self.assertEqual(sampling.resample_sparameter_network(req)['diagnostics'][0]['kind'], 'source_sample')
        req['target_frequencies_hz'] = [0.0, 20e6, 40e6]
        with self.assertRaises(sampling.SParameterSamplingError) as caught:
            sampling.resample_sparameter_network(req)
        self.assertEqual(caught.exception.code, 'SPARAMETER_SAMPLING_OUTSIDE_SUPPORT')
        req['dc_policy'] = {'mode': 'supplied', 's_parameters': [[{'real': GAIN, 'imag': 0.0}]]}
        supplied = sampling.resample_sparameter_network(req)
        self.assert_unknown_source(supplied)
        self.assertEqual(supplied['diagnostics'][0]['kind'], 'supplied_dc')
        self.assertEqual(supplied['diagnostics'][1]['weight_upper'], 0.5)
        np.testing.assert_allclose(output_values(supplied), [GAIN, (GAIN+resonance(40e6))/2, resonance(40e6)], atol=1e-16, rtol=0)
        source_req = request([0.0]+grid, resonance([0.0]+grid), [0.0, 20e6, 40e6])
        self.assertEqual(sampling.resample_sparameter_network(source_req)['diagnostics'][0]['kind'], 'source_sample')
        source_req['dc_policy'] = req['dc_policy']
        with self.assertRaisesRegex(sampling.SParameterSamplingError, 'cannot override'):
            sampling.resample_sparameter_network(source_req)
        req['dc_policy']['s_parameters'][0][0]['imag'] = 1e-300
        with self.assertRaisesRegex(sampling.SParameterSamplingError, 'exactly real'):
            sampling.resample_sparameter_network(req)

    def test_rational_causal_model_and_source_uncertainty_remain_separate(self):
        grid = np.array([0, 1e6, 10e6, 100e6, 500e6])
        rate = 2*math.pi*20e6
        values = 0.1 + 0.4 * rate / (rate + 2j*math.pi*grid)
        req = {'contract': rational.REQUEST_CONTRACT, 'source': request(grid, values)['source'],
               'pole_rates_rad_s': [rate], 'max_absolute_error': 1e-12}
        out = rational.fit_sparameter_rational(req)
        self.assert_unknown_source(out)
        self.assertEqual(out['model']['causality'], 'proper_real_rational_by_construction')
        self.assertIn('do not establish source causality', ' '.join(out['limitations']))
        np.testing.assert_allclose(out['model']['direct'], [[0.1]], atol=2e-15, rtol=0)
        np.testing.assert_allclose(out['model']['residues'], [[[0.4]]], atol=2e-15, rtol=0)
        req['source']['s_parameters'] = request(grid, values.conjugate())['source']['s_parameters']
        with self.assertRaises(rational.SParameterRationalError) as caught:
            rational.fit_sparameter_rational(req)
        # A failed chosen fit is an error-limit failure, not a causality detector.
        self.assertEqual(caught.exception.code, 'SPARAMETER_RATIONAL_ERROR_LIMIT')

    def test_causal_rational_fit_can_match_anti_causal_aliased_source(self):
        spacing = 100e6
        grid = np.arange(9, dtype=float) * spacing
        advance = 1/spacing
        np.testing.assert_allclose(0.7*np.exp(2j*math.pi*grid*advance), 0.7, atol=3e-15, rtol=0)
        req = {'contract': rational.REQUEST_CONTRACT, 'source': request(grid, [0.7]*len(grid))['source'],
               'pole_rates_rad_s': [2*math.pi*spacing], 'max_absolute_error': 1e-12}
        out = rational.fit_sparameter_rational(req)
        self.assert_unknown_source(out)
        self.assertEqual(out['model']['causality'], 'proper_real_rational_by_construction')
        np.testing.assert_allclose(out['model']['direct'], [[0.7]], atol=2e-15, rtol=0)
        np.testing.assert_allclose(out['model']['residues'], [[[0.0]]], atol=2e-15, rtol=0)
        self.assertLess(out['diagnostics']['max_absolute_error'], 2e-15)
        self.assertAlmostEqual(abs(0.7*np.exp(2j*math.pi*(spacing/2)*advance) - 0.7), 1.4, delta=2e-15)


if __name__ == '__main__':
    unittest.main()
