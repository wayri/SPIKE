# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from python.spike_core.parallel_pool import (
    ALLOWED_METHODS,
    configure_worker_prefix,
    pool_catalog,
    run_parallel_batch,
    validate_batch,
)
from python.spike_core.cluster_protocol import encode as encode_cluster_message
from tests.python.test_harness_pi import fixture as harness_pi_fixture
from tests.python.test_internal_airflow import request as airflow_request


def batch(jobs, *, concurrency=1, threads_per_job=1, timeout_s=30):
    return {
        "contract": "spike/parallel-batch/v1",
        "jobs": jobs,
        "concurrency": concurrency,
        "threads_per_job": threads_per_job,
        "timeout_s": timeout_s,
    }


class ParallelPoolTests(unittest.TestCase):
    def tearDown(self):
        configure_worker_prefix(None)

    def test_two_real_analyses_use_concurrent_fresh_processes_in_input_order(self):
        request = batch([
            {"id": "harness", "method": "run_harness_pi",
             "params": {"request": harness_pi_fixture()}},
            {"id": "airflow", "method": "run_internal_airflow",
             "params": {"request": airflow_request(nx=120, ny=24)}},
        ], concurrency=2)
        with patch("python.spike_core.parallel_pool.cpu_thread_budget", return_value=4):
            result = run_parallel_batch(request)

        self.assertEqual(result["status"], "completed", result)
        self.assertEqual([item["id"] for item in result["outcomes"]], ["harness", "airflow"])
        self.assertEqual(result["provenance"]["peak_concurrency_observed"], 2)
        pids = {item["provenance"]["worker_pid"] for item in result["outcomes"]}
        self.assertEqual(len(pids), 2)
        self.assertTrue(all(item["ok"] for item in result["outcomes"]))
        self.assertEqual(result["outcomes"][0]["result"]["status"], "completed")
        self.assertEqual(result["outcomes"][1]["result"]["contract"],
                         "spike/internal-channel-airflow-result/v1")
        self.assertRegex(result["provenance"]["request_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(all(item["provenance"]["response_sha256"] for item in result["outcomes"]))

    def test_catalog_and_validation_expose_bounded_safe_contract(self):
        catalog = pool_catalog()
        self.assertEqual(catalog["contract"], "spike/parallel-pool-catalog/v1")
        self.assertEqual(set(catalog["allowed_methods"]), set(ALLOWED_METHODS))
        self.assertEqual(catalog["limits"]["max_timeout_s"], 180)
        self.assertEqual(catalog["limits"]["max_batch_timeout_s"], 900)
        self.assertEqual(catalog["limits"]["memory_limit"],
                         "unsupported_by_portable_process_pool")
        self.assertEqual(catalog["acceleration"]["contract"],
                         "spike/acceleration-catalog/v1")
        original = batch([{"id": "one", "method": "run_internal_airflow",
                           "params": {"request": airflow_request()}}])
        validated = validate_batch(original)
        self.assertEqual(validated, original)
        self.assertIsNot(validated, original)
        self.assertIsNot(validated["jobs"], original["jobs"])

    def test_rejects_unsafe_ambiguous_nonfinite_and_oversubscribed_requests(self):
        valid_job = {"id": "safe", "method": "run_internal_airflow",
                     "params": {"request": airflow_request()}}
        cases = []
        unsafe = batch([{**valid_job, "method": "run_python_script"}])
        cases.append((unsafe, "not allowed"))
        executable = batch([valid_job])
        executable["executable"] = ["python", "payload.py"]
        cases.append((executable, "exactly"))
        duplicate = batch([valid_job, dict(valid_job)], concurrency=1)
        cases.append((duplicate, "Duplicate"))
        nonfinite = batch([{"id": "bad-number", "method": "analyze_ac_power_integrity",
                            "params": {"request": {"frequency_hz": math.nan}}}])
        cases.append((nonfinite, "finite"))
        for value, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                validate_batch(value)
        with patch("python.spike_core.parallel_pool.cpu_thread_budget", return_value=3):
            with self.assertRaisesRegex(ValueError, "CPU threads"):
                validate_batch(batch([valid_job, {**valid_job, "id": "second"}],
                                     concurrency=2, threads_per_job=2))

    def test_timeout_kills_child_and_returns_per_job_error(self):
        request = batch([{"id": "slow", "method": "run_internal_airflow",
                          "params": {"request": airflow_request(nx=1000, ny=100)}}],
                        timeout_s=0.01)
        result = run_parallel_batch(request)
        outcome = result["outcomes"][0]
        self.assertFalse(outcome["ok"])
        self.assertEqual(outcome["status"], "timed_out")
        self.assertEqual(outcome["error"]["code"], "PARALLEL_JOB_TIMEOUT")
        self.assertIsInstance(outcome["provenance"]["worker_pid"], int)

    def test_timeout_and_cancel_do_not_block_when_child_never_reads_stdin(self):
        hung = [sys.executable, "-c", "import time; time.sleep(2)"]
        request_body = airflow_request()
        request_body["padding"] = "x" * 100_000
        request = batch([{
            "id": "blocked-input", "method": "run_internal_airflow",
            "params": {"request": request_body},
        }], timeout_s=0.05)

        configure_worker_prefix(hung)
        started = time.monotonic()
        timed_out = run_parallel_batch(request)
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual(timed_out["outcomes"][0]["error"]["code"],
                         "PARALLEL_JOB_TIMEOUT")

        request["timeout_s"] = 30
        started = time.monotonic()
        cancelled = run_parallel_batch(
            request, cancel_check=lambda: time.monotonic() - started > 0.05,
        )
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual(cancelled["outcomes"][0]["error"]["code"],
                         "PARALLEL_JOB_CANCELLED")

    def test_cancellation_kills_running_children_and_marks_queued_jobs(self):
        jobs = [
            {"id": f"air-{index}", "method": "run_internal_airflow",
             "params": {"request": airflow_request(nx=1000, ny=100)}}
            for index in range(3)
        ]
        started = time.monotonic()
        with patch("python.spike_core.parallel_pool.cpu_thread_budget", return_value=4):
            result = run_parallel_batch(
                batch(jobs, concurrency=2, timeout_s=30),
                cancel_check=lambda: time.monotonic() - started > 0.1,
            )
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual([item["id"] for item in result["outcomes"]], ["air-0", "air-1", "air-2"])
        self.assertTrue(all(item["status"] == "cancelled" for item in result["outcomes"]), result)
        self.assertTrue(any(item["provenance"]["worker_pid"] is not None
                            for item in result["outcomes"]))

    def test_child_rejects_duplicate_keys_and_nonfinite_json(self):
        for raw in (
            b'{"id":"a","id":"b","method":"run_internal_airflow","params":{}}',
            b'{"id":"a","method":"run_internal_airflow","params":{"request":NaN}}',
        ):
            with self.subTest(raw=raw):
                process = subprocess.run(
                    [sys.executable, "-m", "python.spike_core.parallel_child"],
                    input=raw, capture_output=True, timeout=10, check=False,
                )
                self.assertEqual(process.returncode, 0, process.stderr)
                response = json.loads(process.stdout)
                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["code"], "PARALLEL_CHILD_REJECTED")

    def test_protocol_mismatch_from_trusted_custom_prefix_is_contained(self):
        script = (
            "import json,sys; r=json.load(sys.stdin); "
            "print(json.dumps({'id':'wrong','ok':True,'result':{},"
            "'meta':{'method':r['method']}}))"
        )
        configure_worker_prefix([sys.executable, "-c", script])
        result = run_parallel_batch(batch([{
            "id": "expected", "method": "run_internal_airflow",
            "params": {"request": airflow_request()},
        }]))
        outcome = result["outcomes"][0]
        self.assertFalse(outcome["ok"])
        self.assertEqual(outcome["error"]["code"], "PARALLEL_JOB_PROTOCOL")

    def test_aggregate_structural_limit_replaces_excess_outcome(self):
        script = (
            "import json,sys; r=json.load(sys.stdin); "
            "print(json.dumps({'id':r['id'],'ok':True,'result':[None]*60000,"
            "'meta':{'method':r['method']}}))"
        )
        configure_worker_prefix([sys.executable, "-c", script])
        jobs = [{
            "id": f"large-{index}", "method": "run_internal_airflow",
            "params": {"request": airflow_request()},
        } for index in range(2)]
        with patch("python.spike_core.parallel_pool.cpu_thread_budget", return_value=2):
            result = run_parallel_batch(batch(jobs, concurrency=2))

        self.assertEqual([item["id"] for item in result["outcomes"]],
                         ["large-0", "large-1"])
        retained = [item for item in result["outcomes"] if item["ok"]]
        rejected = [item for item in result["outcomes"] if not item["ok"]]
        self.assertEqual(len(retained), 1)
        self.assertEqual(len(retained[0]["result"]), 60000)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["error"]["code"],
                         "PARALLEL_JOB_STRUCTURE_LIMIT")
        self.assertLessEqual(result["provenance"]["retained_child_output_bytes"],
                             6 * 1024 * 1024)
        encode_cluster_message(result)

    def test_child_output_flood_is_killed_before_timeout(self):
        script = ("import sys,time; sys.stdin.buffer.read(); "
                  "sys.stdout.buffer.write(b'x'*(8*1024*1024)); "
                  "sys.stdout.buffer.flush(); time.sleep(5)")
        configure_worker_prefix([sys.executable, "-c", script])
        started = time.monotonic()
        result = run_parallel_batch(batch([{
            "id": "flood", "method": "run_internal_airflow",
            "params": {"request": airflow_request()},
        }], timeout_s=10))
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(result["outcomes"][0]["error"]["code"], "PARALLEL_JOB_OUTPUT_LIMIT")


if __name__ == "__main__":
    unittest.main()
