import contextlib
import json
import subprocess
import sys
import unittest
from io import StringIO
from unittest.mock import patch

from python.spikes.benchmark import (
    OBSERVATION_CONTRACT,
    BenchmarkCase,
    BenchmarkObservation,
    ExternalJsonCommandAdapter,
    NativeDcAdapter,
    analytical_dc_cases,
    run_benchmark_case,
    run_benchmark_suite,
)
from python.spikes.benchmark_cli import EXIT_OK, main


class _WrongAdapter:
    engine_id = "test.inaccurate"
    timing_scope = "test"

    def __init__(self):
        self.calls = 0

    def observe(self, case):
        self.calls += 1
        return BenchmarkObservation(case.expected + 1.0)


class SpikesBenchmarkTests(unittest.TestCase):
    def test_native_analytical_dc_corpus_is_accuracy_qualified(self):
        report = run_benchmark_suite(NativeDcAdapter(), warmups=1, repetitions=3)
        self.assertEqual(report["contract"], "spikes/benchmark-report/v1")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"]["total"], 3)
        self.assertEqual(report["summary"]["accuracy_passed"], 3)
        self.assertEqual(report["summary"]["speed_scored"], 3)
        self.assertEqual(report["claims"], [])
        for result in report["results"]:
            self.assertEqual(len(result["case"]["netlist_sha256"]), 64)
            self.assertEqual(len(result["timing_ns"]), 3)
            self.assertGreater(result["median_elapsed_ns"], 0)
            self.assertGreater(result["speed_score_runs_per_s"], 0.0)

    def test_accuracy_failure_blocks_speed_scoring_after_warmup_and_repeats(self):
        case = analytical_dc_cases(warmups=2, repetitions=4)[0]
        adapter = _WrongAdapter()
        result = run_benchmark_case(case, adapter)
        self.assertEqual(adapter.calls, 6)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["accuracy_passed"])
        self.assertFalse(result["speed_eligible"])
        self.assertIsNone(result["speed_score_runs_per_s"])
        self.assertEqual(result["issues"][0]["code"], "SPIKES_BENCHMARK_ACCURACY_GATE_FAILED")

    def test_case_contract_rejects_unbounded_timing_counts(self):
        common = dict(
            case_id="bounded", title="Bounded", netlist="R1 out 0 1k\n.op\n",
            probe="V(out)", expected=0.0, unit="V",
        )
        with self.assertRaises(ValueError):
            BenchmarkCase(**common, repetitions=101)
        with self.assertRaises(ValueError):
            BenchmarkCase(**common, warmups=21)

    def test_external_adapter_uses_explicit_argv_without_shell(self):
        case = analytical_dc_cases(warmups=0, repetitions=1)[0]
        completed = subprocess.CompletedProcess(
            args=["wrapper"], returncode=0,
            stdout=json.dumps({
                "contract": OBSERVATION_CONTRACT,
                "case_id": case.case_id,
                "value": case.expected,
                "diagnostics": {},
            }),
            stderr="",
        )
        with patch("python.spikes.benchmark.subprocess.run", return_value=completed) as launched:
            observation = ExternalJsonCommandAdapter("test.wrapper", ("wrapper", "--json")).observe(case)
        self.assertEqual(observation.value, case.expected)
        positional, keyword = launched.call_args
        self.assertEqual(positional[0], ["wrapper", "--json"])
        self.assertIs(keyword["shell"], False)
        request = json.loads(keyword["input"])
        self.assertEqual(request["contract"], "spikes/benchmark-request/v1")
        self.assertNotIn("expected", request)

    def test_external_timeout_is_reported_and_not_scored(self):
        case = analytical_dc_cases(warmups=0, repetitions=1)[0]
        adapter = ExternalJsonCommandAdapter(
            "test.timeout",
            (sys.executable, "-c", "import time; time.sleep(2)"),
            timeout_s=0.05,
        )
        result = run_benchmark_case(case, adapter)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["speed_eligible"])
        self.assertIn("timeout", result["issues"][0]["message"])

    def test_isolated_cli_emits_versioned_report(self):
        stream = StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(("--warmups", "0", "--repetitions", "1"))
        report = json.loads(stream.getvalue())
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(report["contract"], "spikes/benchmark-report/v1")


if __name__ == "__main__":
    unittest.main()
