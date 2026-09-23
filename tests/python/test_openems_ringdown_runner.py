# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import unittest
from scripts.run_openems_cavity_ringdown import reference_checks


class ReferenceAdmissionTests(unittest.TestCase):
    def fixture(self):
        return [{k:v for k in ('frequency_hz','q_factor','amplitude_decay_per_s')} for v in (.0009,.0004,.0002)]

    def test_all_checks_required(self):
        r=reference_checks(self.fixture(),{'status':'numerically_stable_observed_mode'},True)
        self.assertEqual(r['status'],'qualified_reference_case')
        self.assertEqual(r['exit_code'],0)
        self.assertEqual(reference_checks(self.fixture(),{'status':'not_qualified'},True)['exit_code'],1)
        self.assertEqual(reference_checks(self.fixture(),{'status':'numerically_stable_observed_mode'},False)['exit_code'],1)

    def test_bad_error_and_nonmonotonic_rejected(self):
        for value in (None,float('nan'),.01):
            errors=self.fixture(); errors[-1]['amplitude_decay_per_s']=value
            self.assertEqual(reference_checks(errors,{'status':'numerically_stable_observed_mode'},True)['exit_code'],1)
        self.assertEqual(reference_checks([],{'status':'numerically_stable_observed_mode'},True)['exit_code'],1)
        errors=self.fixture(); errors[-1]['q_factor']=.0006
        self.assertEqual(reference_checks(errors,{'status':'numerically_stable_observed_mode'},True)['exit_code'],1)
        errors=self.fixture(); errors[-1]['q_factor']=.002
        self.assertEqual(reference_checks(errors,{'status':'numerically_stable_observed_mode'},True)['exit_code'],1)
        errors=self.fixture(); errors[-1]['amplitude_decay_per_s']=.0006
        self.assertEqual(reference_checks(errors,{'status':'numerically_stable_observed_mode'},True)['exit_code'],0)


if __name__=='__main__':
    unittest.main()
