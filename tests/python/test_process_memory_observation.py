# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Tests for truthful, nullable process-memory observations."""
import unittest
from unittest.mock import patch

from python.spike_core import process_memory_observation as memory


class ProcessMemoryObservationTests(unittest.TestCase):
    def test_linux_parser_uses_bytes_and_keeps_private_commit_unknown(self):
        text = "VmRSS:\t123 kB\nVmHWM:\t456 kB\nVmData:\t789 kB\n"
        with patch.object(memory, "_linux_resource_peak_bytes", return_value=999 * 1024):
            result = memory._linux_observation(lambda: text)
        self.assertEqual(result["resident_current_bytes"], 123 * 1024)
        self.assertEqual(result["resident_peak_bytes"], 456 * 1024)
        self.assertEqual(result["resident_peak_resource_bytes"], 999 * 1024)
        self.assertIsNone(result["private_commit_current_bytes"])
        self.assertIsNone(result["private_commit_peak_bytes"])

    def test_linux_missing_values_are_unknown_not_zero(self):
        with patch.object(memory, "_linux_resource_peak_bytes", return_value=None):
            result = memory._linux_observation(lambda: "Name:\tpython\n")
        for key in ("resident_current_bytes", "resident_peak_bytes",
                    "resident_peak_resource_bytes", "private_commit_current_bytes",
                    "private_commit_peak_bytes"):
            self.assertIsNone(result[key])

    def test_public_observation_has_stable_schema(self):
        result = memory.observe_process_memory()
        self.assertEqual(set(result), {
            "platform", "source", "resident_current_bytes", "resident_peak_bytes",
            "resident_peak_resource_bytes", "private_commit_current_bytes",
            "private_commit_peak_bytes",
        })
        for key, value in result.items():
            if key.endswith("_bytes"):
                self.assertTrue(value is None or isinstance(value, int))
                self.assertNotEqual(value, 0)


if __name__ == "__main__":
    unittest.main()
