# SPDX-License-Identifier: Apache-2.0
"""Experimental RSS supervision policy and native Darwin lifecycle checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from python.spike_core import circuit_worker_supervisor as supervisor


class DarwinSampledRssTests(unittest.TestCase):
    def test_group_rss_sum_and_strict_observation_parser(self):
        self.assertEqual(supervisor._parse_group_rss(b"10 10 12\n11 10 8\n", 10), 20 * 1024)
        self.assertEqual(supervisor._parse_group_rss(b"10 10 0\n", 10), 0)
        for output in (b"", b"\n", b"10 10 -1\n", b"10 11 1\n", b"10 10 1\n10 10 2\n",
                       b"10 10 nan\n", b"10 10 1 extra\n", b"0 10 1\n", b"10 10 1\n\n",
                       b"10 10 " + b"9" * 100, b"x" * (supervisor.RSS_OBSERVER_MAX_BYTES + 1)):
            with self.subTest(output=output[:50]), self.assertRaises(supervisor.ResourceObservationError):
                supervisor._parse_group_rss(output, 10)

    def test_observer_command_bounds_and_failures(self):
        for failure in (None, "exit", "timeout", "output", "malformed", "launch"):
            with self.subTest(failure=failure):
                observer = Mock()
                observer.stdout.fileno.return_value = 7
                observer.poll.return_value = None
                observer.wait.return_value = 1 if failure == "exit" else 0
                chunks = [b"10 10 12\n", b""]
                if failure == "output":
                    chunks = [b"x" * (supervisor.RSS_OBSERVER_MAX_BYTES + 1)]
                elif failure == "malformed":
                    chunks = [b"garbage\n", b""]
                with patch.object(supervisor.subprocess, "Popen", return_value=observer,
                                  side_effect=OSError("private path") if failure == "launch" else None) as launch, \
                        patch("select.select", return_value=([] if failure == "timeout" else [observer.stdout], [], [])), \
                        patch.object(supervisor.os, "read", side_effect=chunks):
                    if failure:
                        with self.assertRaises(supervisor.ResourceObservationError):
                            supervisor._sample_group_rss_bytes(10, 0.2)
                    else:
                        self.assertEqual(supervisor._sample_group_rss_bytes(10, 0.2), 12 * 1024)
                self.assertEqual(launch.call_args.args[0],
                                 ["/bin/ps", "-x", "-g", "10", "-o", "pid=,pgid=,rss="])
                self.assertEqual(launch.call_args.kwargs["env"], {"LC_ALL": "C", "COMMAND_MODE": "unix2003"})
                self.assertFalse(launch.call_args.kwargs["shell"])
                if failure != "launch":
                    observer.kill.assert_called_once()
                    self.assertLessEqual(observer.wait.call_args.kwargs["timeout"], 0.5)
                    observer.stdout.close.assert_called_once()

    def test_policy_admission_precedes_execution_and_strict_remains_default(self):
        for platform, policy in (("linux", "darwin_sampled_rss"), ("win32", "darwin_sampled_rss"),
                                 ("darwin", "unknown"), ("darwin", None)):
            with self.subTest(platform=platform, policy=policy), \
                    patch.object(supervisor.sys, "platform", platform), \
                    patch.object(supervisor.subprocess, "Popen") as launch:
                with self.assertRaises(ValueError):
                    supervisor.supervise_process(Path(sys.executable), [], cwd=Path.cwd(),
                        timeout_seconds=1, memory_limit_mib=256, resource_policy=policy)
                launch.assert_not_called()
        with patch.object(supervisor, "os", SimpleNamespace(name="posix")), \
                patch.object(supervisor, "_supervise_posix", return_value=("completed", 0)) as run:
            result = supervisor.supervise_process(Path(sys.executable).resolve(), [],
                        cwd=Path.cwd().resolve(), timeout_seconds=1, memory_limit_mib=256)
        self.assertEqual(run.call_args.kwargs["resource_policy"], "strict_address_space")
        self.assertEqual(result.os_enforcement, "posix_process_group_rlimit")

    def test_sampled_policy_retains_core_limit_and_owned_cleanup(self):
        for reason in ("completed", "memory_exceeded", "observer_failed", "cancelled", "timeout_after_sample"):
            with self.subTest(reason=reason):
                resource = SimpleNamespace(RLIMIT_AS=1, RLIMIT_CORE=2, setrlimit=Mock())
                process = Mock(pid=10)
                process.poll.return_value = 0
                process.wait.return_value = 0
                def launch(*args, **kwargs):
                    self.assertTrue(kwargs["start_new_session"])
                    kwargs["preexec_fn"]()
                    return process
                def cleanup(owned):
                    self.assertIs(owned, process)
                    process.poll.assert_not_called()
                    process.wait.assert_not_called()
                observation = supervisor.ResourceObservationError("failed")
                with patch.dict(sys.modules, {"resource": resource}), \
                        patch.object(supervisor.subprocess, "Popen", side_effect=launch), \
                        patch.object(supervisor, "_sample_group_rss_bytes",
                            return_value=300 * 1024 * 1024 if reason == "memory_exceeded" else 10,
                            side_effect=observation if reason == "observer_failed" else None) as sample, \
                        patch.object(supervisor, "_terminate_posix_group", side_effect=cleanup) as terminate, \
                        patch.object(supervisor.time, "sleep"), \
                        patch.object(supervisor.time, "monotonic", side_effect=[0, 0, 0, 2] if reason == "timeout_after_sample" else [0] * 8):
                    args = (Path(sys.executable), [], Path.cwd(), 1, 256, lambda: reason == "cancelled")
                    if reason == "observer_failed":
                        with self.assertRaises(supervisor.ResourceObservationError) as caught:
                            supervisor._supervise_posix(*args, resource_policy="darwin_sampled_rss")
                        self.assertIs(caught.exception, observation)
                    else:
                        status, _ = supervisor._supervise_posix(*args, resource_policy="darwin_sampled_rss")
                        self.assertEqual(status, "timeout" if reason == "timeout_after_sample" else reason)
                    if reason == "completed":
                        terminate.assert_not_called()
                        sample.assert_called_once()
                    else:
                        terminate.assert_called_once_with(process)
                resource.setrlimit.assert_called_once_with(2, (0, 0))

    def test_memory_and_observer_failures_publish_experimental_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            worker, library = root / "spike-circuit-worker", root / "libspikes_c_api.dylib"
            worker.write_bytes(b"worker")
            library.write_bytes(b"library")
            (root / "job").mkdir()
            (root / "job/request.json").write_text("{}")
            for observer_failure in (False, True):
                with self.subTest(observer_failure=observer_failure), \
                        patch.object(supervisor, "os", SimpleNamespace(name="posix")), \
                        patch.object(supervisor.sys, "platform", "darwin"), \
                        patch.object(supervisor, "supervise_process",
                            side_effect=supervisor.ResourceObservationError("private diagnostic") if observer_failure else None,
                            return_value=supervisor.SupervisionResult("memory_exceeded", -9, 1, supervisor.DARWIN_RSS_ENFORCEMENT)) as run:
                    args = dict(worker_executable=worker, worker_sha256=supervisor.sha256_file(worker),
                                library_path=library, library_sha256=supervisor.sha256_file(library), job_root=root,
                                request="job/request.json", result="job/result.json", resource_policy="darwin_sampled_rss")
                    if observer_failure:
                        with self.assertRaises(supervisor.ResourceObservationError):
                            supervisor.run_circuit_worker(**args)
                    else:
                        supervisor.run_circuit_worker(**args)
                    run.assert_called_once()
                    self.assertEqual(run.call_args.kwargs["resource_policy"], "darwin_sampled_rss")
                result = json.loads((root / "job/result.json").read_text())
                self.assertEqual(result["status"], "failed")
                self.assertIsNone(result["circuit"])
                self.assertEqual(result["issues"][0]["code"], "SPIKE-BE-SPICE-E-0059" if observer_failure else "SPIKE-BE-SPICE-E-0058")
                self.assertFalse(result["provenance"]["hard_memory_cap"])
                self.assertTrue(result["provenance"]["overshoot_between_observations_possible"])

    def test_other_sampled_terminal_results_identify_the_policy_truthfully(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            worker, library = root / "spike-circuit-worker", root / "libspikes_c_api.dylib"
            worker.write_bytes(b"worker")
            library.write_bytes(b"library")
            (root / "job").mkdir()
            (root / "job/request.json").write_text("{}")
            result_path = root / "job/result.json"
            for status in ("completed", "timeout", "cancelled", "initialization_failed"):
                original = {"contract": supervisor.PROCESS_RESULT_CONTRACT, "status": "completed",
                            "validation_state": "experimental", "circuit": {"preserved": [1, 2]},
                            "provenance": {"process": "owned worker", "atomic_result_publication": True}}
                result_path.write_text(json.dumps(original))
                with self.subTest(status=status), \
                        patch.object(supervisor, "os", SimpleNamespace(name="posix")), \
                        patch.object(supervisor.sys, "platform", "darwin"), \
                        patch.object(supervisor, "supervise_process",
                            return_value=supervisor.SupervisionResult(status, 0, 1, supervisor.DARWIN_RSS_ENFORCEMENT),
                            side_effect=supervisor.SupervisorInitializationError("darwin", 300, 4096)
                            if status == "initialization_failed" else None):
                    args = dict(worker_executable=worker, worker_sha256=supervisor.sha256_file(worker),
                                library_path=library, library_sha256=supervisor.sha256_file(library), job_root=root,
                                request="job/request.json", result="job/result.json", resource_policy="darwin_sampled_rss")
                    if status == "initialization_failed":
                        with self.assertRaises(supervisor.SupervisorInitializationError):
                            supervisor.run_circuit_worker(**args)
                    else:
                        supervisor.run_circuit_worker(**args)
                result = json.loads(result_path.read_text())
                provenance = result["provenance"]
                self.assertEqual(provenance["resource_policy"], "darwin_sampled_rss")
                self.assertFalse(provenance["hard_memory_cap"])
                self.assertFalse(provenance["normal_leader_exit_descendants_covered"])
                self.assertEqual(provenance["complete_process_tree_termination_requested"],
                                 status in ("timeout", "cancelled"))
                if status == "completed":
                    self.assertEqual(result["circuit"], original["circuit"])
                    self.assertEqual(provenance["process"], "owned worker")
                if status == "initialization_failed":
                    self.assertFalse(provenance["enforcement_established"])

    def test_result_annotation_rejects_invalid_data_and_preserves_bytes_on_write_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root / "result.json"
            for payload in (b"not json", b'{"contract":"wrong"}', b'{"contract":1,"contract":2}',
                            b'{"invalid":NaN}', json.dumps({"contract": supervisor.PROCESS_RESULT_CONTRACT,
                                                           "provenance": []}).encode()):
                path.write_bytes(payload)
                with self.assertRaises(ValueError):
                    supervisor._attach_rss_provenance(root, Path("result.json"), 30, 256)
                self.assertEqual(path.read_bytes(), payload)
            valid = json.dumps({"contract": supervisor.PROCESS_RESULT_CONTRACT, "status": "completed", "circuit": {}}).encode()
            path.write_bytes(valid)
            with patch("python.spike_core.owned_spice_process.os.replace", side_effect=OSError("injected publication failure")):
                with self.assertRaisesRegex(OSError, "publication failure"):
                    supervisor._attach_rss_provenance(root, Path("result.json"), 30, 256)
            self.assertEqual(path.read_bytes(), valid)
            self.assertEqual(list(root.glob(".*.tmp")), [])


@unittest.skipUnless(sys.platform == "darwin", "requires native Darwin RSS observations")
class NativeDarwinSampledRssTests(unittest.TestCase):
    def _run(self, root, program, budget=256, cancelled=lambda: False):
        executable = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
        return supervisor.supervise_process(executable, ["-c", program], cwd=root,
            timeout_seconds=10, memory_limit_mib=budget, cancelled=cancelled,
            resource_policy="darwin_sampled_rss")

    @staticmethod
    def _no_live_members(group):
        result = subprocess.run(["/bin/ps", "-x", "-g", str(group), "-o", "stat="],
            capture_output=True, text=True, timeout=1,
            env={"LC_ALL": "C", "COMMAND_MODE": "unix2003"})
        if result.returncode not in (0, 1):
            raise AssertionError("could not inspect remaining process-group members")
        return all(line.strip().startswith("Z") for line in result.stdout.splitlines() if line.strip())

    def test_native_below_budget_preserves_core_and_does_not_change_as(self):
        import resource
        before = resource.getrlimit(resource.RLIMIT_AS)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            outcome = self._run(root, "import json,pathlib,resource,time; x=bytearray(16*1024*1024); pathlib.Path('started').write_text(json.dumps([resource.getrlimit(resource.RLIMIT_AS),resource.getrlimit(resource.RLIMIT_CORE)])); time.sleep(.3)")
            self.assertEqual((outcome.status, outcome.returncode), ("completed", 0))
            self.assertEqual(outcome.os_enforcement, supervisor.DARWIN_RSS_ENFORCEMENT)
            self.assertEqual(json.loads((root / "started").read_text()), [list(before), [0, 0]])
        self.assertEqual(resource.getrlimit(resource.RLIMIT_AS), before)

    def test_native_child_over_group_budget_is_terminated(self):
        program = """
import json,os,pathlib,time
pathlib.Path('started').write_text(str(os.getpid()))
if os.fork() == 0:
    pathlib.Path('child-started').write_text(str(os.getpid()))
    allocation = bytearray(128*1024*1024)
    for offset in range(0,len(allocation),4096): allocation[offset]=1
deadline=time.monotonic()+20
while time.monotonic()<deadline: time.sleep(.02)
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            outcome = self._run(root, program, budget=128)
            self.assertEqual(outcome.status, "memory_exceeded")
            self.assertTrue((root / "child-started").is_file(), "descendant must start before quota triggers")
            group = int((root / "started").read_text())
            deadline = time.monotonic() + 2
            while not self._no_live_members(group) and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(self._no_live_members(group))

    def test_native_cancellation_and_observer_failure_stop_started_worker(self):
        for failure in (False, True):
            with self.subTest(observer_failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                marker = root / "started"
                original = supervisor._sample_group_rss_bytes
                def observe(group, timeout):
                    if failure and marker.exists():
                        raise supervisor.ResourceObservationError("injected observer failure")
                    return original(group, timeout)
                with patch.object(supervisor, "_sample_group_rss_bytes", side_effect=observe):
                    program = "import os,pathlib,time; pathlib.Path('started').write_text(str(os.getpid())); time.sleep(20)"
                    if failure:
                        with self.assertRaises(supervisor.ResourceObservationError):
                            self._run(root, program)
                    else:
                        self.assertEqual(self._run(root, program, cancelled=marker.exists).status, "cancelled")
                self.assertTrue(marker.exists(), "worker must start before the failure/cancellation")
                self.assertTrue(self._no_live_members(int(marker.read_text())))


if __name__ == "__main__":
    unittest.main()
