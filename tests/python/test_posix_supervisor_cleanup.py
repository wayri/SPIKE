# SPDX-License-Identifier: Apache-2.0
"""Process-group lifecycle checks; native fixtures execute no solver workload."""
import json
import errno
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from python.spike_core import circuit_worker_supervisor as supervisor
from python.spike_core import circuit_worker_resources as resources


class PosixCleanupControlTests(unittest.TestCase):
    def test_unreaped_exited_leader_is_retained_until_last_group_signal(self):
        process = Mock(pid=4321, returncode=None)
        events = []
        process.poll.side_effect = AssertionError("poll must not reap the leader")
        def signal_group(pid, sig):
            self.assertIsNone(process.returncode, "group signal after reaping is unsafe")
            events.append(sig)
        def reap():
            events.append("wait")
            process.returncode = 0
            return 0
        process.wait.side_effect = reap
        with patch.object(supervisor.os, "killpg", side_effect=signal_group, create=True) as killpg, \
                patch.object(supervisor.signal, "SIGKILL", 9, create=True), \
                patch.object(supervisor.time, "monotonic", side_effect=[0, 0.6]):
            supervisor._terminate_posix_group(process)
        self.assertEqual(killpg.call_args_list,
                         [((4321, signal.SIGTERM),), ((4321, 0),), ((4321, 9),)])
        self.assertEqual(events, [signal.SIGTERM, 0, 9, "wait"])
        process.poll.assert_not_called()
        process.wait.assert_called_once_with()

    def test_disappeared_group_is_reaped_without_escalation(self):
        process = Mock(pid=4321)
        with patch.object(supervisor.os, "killpg", create=True,
                          side_effect=ProcessLookupError) as killpg:
            supervisor._terminate_posix_group(process)
        killpg.assert_called_once_with(4321, signal.SIGTERM)
        process.wait.assert_called_once_with()

    def test_owner_cleans_only_while_leader_is_unreaped_and_preserves_limits(self):
        resource = SimpleNamespace(RLIMIT_AS=1, RLIMIT_CORE=2, setrlimit=Mock())
        for reason in ("timeout", "cancelled", "completed", "callback_error", "poll_error"):
            with self.subTest(reason=reason):
                process = Mock(pid=4321)
                process.poll.return_value = 0 if reason == "completed" else None
                if reason == "poll_error":
                    process.poll.side_effect = RuntimeError("poll failed")
                process.wait.return_value = 0
                callback = Mock(return_value=reason == "cancelled")
                if reason == "callback_error":
                    callback.side_effect = RuntimeError("callback failed")
                resource.setrlimit.reset_mock()
                def launch(*args, **kwargs):
                    self.assertTrue(kwargs["start_new_session"])
                    self.assertFalse(kwargs["shell"])
                    kwargs["preexec_fn"]()
                    return process
                with patch.dict(sys.modules, {"resource": resource}), \
                        patch.object(supervisor.subprocess, "Popen", side_effect=launch), \
                        patch.object(supervisor, "_terminate_posix_group") as cleanup, \
                        patch.object(supervisor.time, "monotonic", side_effect=[0, 2]):
                    arguments = (Path(sys.executable), [], Path.cwd(), 1, 256, callback)
                    if reason == "callback_error":
                        with self.assertRaisesRegex(RuntimeError, "callback failed"):
                            supervisor._supervise_posix(*arguments)
                    elif reason == "poll_error":
                        with self.assertRaisesRegex(RuntimeError, "poll failed"):
                            supervisor._supervise_posix(*arguments)
                    else:
                        status, returncode = supervisor._supervise_posix(*arguments)
                        self.assertEqual((status, returncode), (reason, 0))
                    if reason in {"completed", "poll_error"}:
                        cleanup.assert_not_called()
                    else:
                        cleanup.assert_called_once_with(process)
                self.assertEqual(resource.setrlimit.call_args_list,
                                 [((1, (268435456, 268435456)),), ((2, (0, 0)),)])


class DarwinZombieGroupTests(unittest.TestCase):
    def test_eperm_requires_positive_zombie_evidence_before_reaping_at_each_signal(self):
        for failed_call in range(3):
            with self.subTest(failed_call=failed_call):
                original = PermissionError(errno.EPERM, "denied")
                process = Mock(pid=4321, returncode=None)
                process.poll.side_effect = AssertionError("must retain the leader")
                events = []
                def signal_group(pid, sig):
                    self.assertIsNone(process.returncode)
                    events.append("signal")
                    if len(events) == failed_call + 1:
                        raise original
                def observe(*args):
                    self.assertIsNone(process.returncode)
                    events.append("observe")
                    return b"4321 4321 Zs\n4322 4321 Z\n"
                def reap():
                    self.assertEqual(events[-1], "observe")
                    events.append("reap")
                    process.returncode = 0
                process.wait.side_effect = reap
                with patch.object(resources.sys, "platform", "darwin"), \
                        patch.object(resources.os, "killpg", create=True, side_effect=signal_group) as killpg, \
                        patch.object(resources, "_read_ps_group", side_effect=observe) as observation, \
                        patch.object(supervisor.signal, "SIGKILL", 9, create=True), \
                        patch.object(supervisor.time, "monotonic", side_effect=[0, .6]):
                    supervisor._terminate_posix_group(process)
                self.assertEqual(killpg.call_count, failed_call + 1)
                observation.assert_called_once_with(4321, "pid=,pgid=,stat=", .5)
                process.poll.assert_not_called()
                process.wait.assert_called_once_with()

    def test_live_missing_or_invalid_observation_never_suppresses_eperm(self):
        for output in (b"4321 4321 S\n", b"4321 4321 Z\n4322 4321 R\n", b"", b"garbage",
                       b"4322 4321 Z\n", b"4321 9999 Z\n", b"4321 4321 Z\n4321 4321 Z\n",
                       b"4321 4321 Zmalformed\n", b"4321 4321 Z\n\n",
                       resources.ResourceObservationError("observer timeout/nonzero/failure")):
            with self.subTest(output=output):
                original = PermissionError(errno.EPERM, "denied")
                process = Mock(pid=4321)
                with patch.object(resources.sys, "platform", "darwin"), \
                        patch.object(resources.os, "killpg", create=True, side_effect=original), \
                        patch.object(resources, "_read_ps_group",
                            return_value=output if isinstance(output, bytes) else None,
                            side_effect=output if isinstance(output, Exception) else None):
                    with self.assertRaises(PermissionError) as caught:
                        supervisor._terminate_posix_group(process)
                self.assertIs(caught.exception, original)
                process.wait.assert_not_called()
                process.poll.assert_not_called()

    def test_other_platforms_and_other_permission_errors_are_not_suppressed(self):
        for platform, error_number in (("linux", errno.EPERM), ("darwin", errno.EACCES)):
            original = PermissionError(error_number, "denied")
            with self.subTest(platform=platform, errno=error_number), \
                    patch.object(resources.sys, "platform", platform), \
                    patch.object(resources.os, "killpg", create=True, side_effect=original), \
                    patch.object(resources, "_read_ps_group") as observe:
                with self.assertRaises(PermissionError) as caught:
                    resources._signal_owned_group(4321, signal.SIGTERM)
                self.assertIs(caught.exception, original)
                observe.assert_not_called()

    @unittest.skipUnless(sys.platform == "darwin", "requires native Darwin zombie-group semantics")
    def test_native_zombie_leader_is_observed_before_cleanup_reaps_it(self):
        process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 3
            while not resources._group_has_only_zombies(process.pid):
                self.assertLess(time.monotonic(), deadline, "leader must become a visible zombie")
                time.sleep(.01)
            self.assertIsNone(process.returncode, "native fixture must remain unreaped")
            with patch.object(process, "poll", side_effect=AssertionError("poll would reap the leader")):
                supervisor._terminate_posix_group(process)
            self.assertEqual(process.returncode, 0)
        finally:
            if process.returncode is None:
                process.kill()
            process.wait(timeout=3)


_TREE = r'''
import json, os, pathlib, signal, sys, time
root = pathlib.Path(sys.argv[1])
def leave(signum, frame):
    (root / "leader-terminated").write_text("yes")
    raise SystemExit(0)
signal.signal(signal.SIGTERM, leave)
pid = os.fork()
if pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    (root / "child.json").write_text(json.dumps({"pid": os.getpid(), "group": os.getpgrp()}))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        time.sleep(0.02)
    raise SystemExit(0)
while not (root / "child.json").is_file():
    time.sleep(0.01)
while True:
    time.sleep(0.02)
'''


@unittest.skipUnless(os.name == "posix", "native POSIX process groups unavailable on Windows")
class NativePosixCleanupTests(unittest.TestCase):
    @staticmethod
    def _live(pid):
        # Orphaned zombies are already dead; only the OS's adopting parent can reap them.
        result = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                                capture_output=True, text=True, timeout=2)
        if result.returncode == 1 and not result.stdout.strip():
            return False
        if result.returncode != 0 or not result.stdout.strip():
            raise AssertionError("could not observe descendant process state")
        return not result.stdout.strip().startswith("Z")

    def test_leader_exits_on_sigterm_but_stubborn_child_is_killed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = subprocess.Popen([sys.executable, "-c", _TREE, directory],
                                       start_new_session=True, close_fds=True)
            child = None
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    try:
                        child = json.loads((root / "child.json").read_text())
                        break
                    except (FileNotFoundError, json.JSONDecodeError):
                        time.sleep(0.01)
                self.assertIsNotNone(child, "child must start before cleanup is tested")
                self.assertEqual(child["group"], process.pid)
                self.assertTrue(self._live(child["pid"]))
                supervisor._terminate_posix_group(process)
                self.assertEqual(process.returncode, 0, "leader must exit before forced group kill")
                self.assertEqual((root / "leader-terminated").read_text(), "yes")
                deadline = time.monotonic() + 3
                while self._live(child["pid"]) and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertFalse(self._live(child["pid"]), "SIGTERM-ignoring child survived")
            finally:
                if process.returncode is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
