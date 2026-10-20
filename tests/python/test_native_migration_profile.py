# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Profiling must not turn varying or failed numerical output into evidence."""
import unittest
from scripts.profile_cfd_native_candidates import measure


class NativeProfileTests(unittest.TestCase):
    def test_five_samples_and_separate_instrumented_pass(self):
        calls = []
        def kernel():
            calls.append(1)
            return {"status": "completed", "fields": {"temperature_k": [300.]}}
        result = measure(kernel)
        self.assertEqual(len(calls), 7)
        self.assertEqual(len(result["wall_seconds"]), 5)
        self.assertEqual(len(result["cpu_seconds"]), 5)
        self.assertTrue(result["instrumented_top_cumulative"])

    def test_bad_counts_varying_fields_and_failed_kernel_reject(self):
        for count in (True, 0, 4, 21):
            with self.assertRaises(ValueError):
                measure(lambda: None, count)
        with self.assertRaisesRegex(ValueError, "did not complete"):
            measure(lambda: {"status": "blocked", "issues": []})
        state = [0]
        def variable():
            state[0] += 1
            return {"status": "completed", "fields": {"x": state[0]}}
        with self.assertRaisesRegex(ValueError, "changed"):
            measure(variable)


if __name__ == "__main__":
    unittest.main()
