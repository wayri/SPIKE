# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import json
import unittest

from examples.si08_causality_policy.run_campaign import prepare_report
from tests.python.test_sparameter_sampling import request
from tests.python.test_sparameter_rational import request as rational_request


class CausalityPolicyCampaignTests(unittest.TestCase):
    def test_preparation_keeps_unknown_source_and_missing_model(self):
        req = request(); original = deepcopy(req)
        report = prepare_report(req)
        self.assertEqual(req, original)
        self.assertEqual(report['interpretation']['source_causality'], 'unknown_from_finite_samples')
        self.assertEqual(report['interpretation']['constructed_model_causality'], 'not_constructed')
        self.assertIsNone(report['constructed_fit'])
        self.assertEqual(report['prepared']['source']['network'], original['source'])
        self.assertEqual(json.loads(json.dumps(report)), report)

    def test_constructed_causal_model_is_separate_from_unknown_original(self):
        original = rational_request()
        req = {'contract': request()['contract'], 'source': original['source'],
               'target_frequencies_hz': original['source']['frequencies_hz'],
               'dc_policy': {'mode': 'require_source'}}
        before = deepcopy(req)
        report = prepare_report(req, {key: original[key] for key in ('pole_rates_rad_s', 'max_absolute_error')})
        self.assertEqual(req, before)
        self.assertEqual(report['interpretation']['source_causality'], 'unknown_from_finite_samples')
        self.assertEqual(report['interpretation']['constructed_model_causality'], 'proper_real_rational_by_construction')
        self.assertEqual(report['constructed_fit']['source']['network'], report['prepared']['derived_network'])
        self.assertFalse(report['interpretation']['physical_qualified'])
        self.assertFalse(report['interpretation']['production_qualified'])
        report['constructed_fit']['source']['network']['port_names'][0] = 'derived mutation'
        self.assertEqual(req, before)
        self.assertEqual(report['prepared']['derived_network']['port_names'][0], 'left')

    def test_explicit_controls_dc_support_and_bad_fit_are_not_bypassed(self):
        with self.assertRaises(ValueError):
            prepare_report(request(), {'auto_infer_dc': True})
        req = request(); req['target_frequencies_hz'] = [3000.]
        with self.assertRaises(ValueError):
            prepare_report(req)
        with self.assertRaises(ValueError):
            prepare_report(request(), {'pole_rates_rad_s': [-1.], 'max_absolute_error': 1e-12})


if __name__ == '__main__':
    unittest.main()
