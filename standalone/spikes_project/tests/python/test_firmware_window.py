# SPDX-License-Identifier: Apache-2.0
"""Real-wx tests for the explicit, inert-on-open firmware manager."""
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "standalone/spikes_project/studio/python"))


@unittest.skipUnless(os.environ.get("SPIKES_TEST_WX") == "1", "requires real wx runtime")
class FirmwareWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx
        cls.wx = wx
        cls.app = wx.GetApp() or wx.App(False)

    def setUp(self):
        from spikes_studio import firmware_window
        self.module = firmware_window
        self.owner = self.wx.Frame(None)
        self.owner.job_running = False
        self.started = []

        started = self.started

        class FakeSession:
            def __init__(self, *args, **kwargs):
                started.append((args, kwargs))
                self.time_s = 0.0
                self.closed = False

            def close(self): self.closed = True
            def gpio_state(self, port): return {"input": 0, "output": 0, "direction": 0}
            def uart_read(self): return b""

        self.patches = [
            patch.object(firmware_window, "FirmwareSession", FakeSession),
            patch.object(firmware_window, "find_runtime", return_value=None),
            patch.object(firmware_window, "runtime_digest", return_value="a" * 64),
        ]
        for item in self.patches: item.start()
        self.window = firmware_window.FirmwareWindow(self.owner)

    def tearDown(self):
        if not self.window.closed:
            self.window.close()
        self.owner.Destroy()
        self.wx.Yield()
        for item in reversed(self.patches): item.stop()

    def pump_until(self, predicate, timeout=2):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:
            self.wx.Yield();time.sleep(.01)
        self.assertTrue(predicate())

    def test_constructs_three_exact_targets_without_executing(self):
        from spikes_studio.firmware_image import TARGETS
        self.assertEqual(self.window.target_ids, list(TARGETS))
        self.assertEqual(self.window.target.GetCount(), 3)
        self.assertEqual(self.started, [])
        self.assertIsNone(self.window.session)

    def test_gpio_inputs_editable_only_with_idle_session(self):
        self.window._reflect()
        self.assertTrue(self.window.gpio.IsReadOnly(0, 4))
        self.window.session = object()
        self.window._reflect()
        self.assertFalse(self.window.gpio.IsReadOnly(0, 4))
        self.window.busy = True
        self.window._reflect()
        self.assertTrue(self.window.gpio.IsReadOnly(0, 4))
        self.window.busy = False
        self.window.session = None

    def test_unsupported_selected_block_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "unsupported firmware target"):
            self.module._target_from_block({"board": {"id": "unsupported-board"}})

    def test_file_change_clears_hash_specific_trust(self):
        self.window.image.SetPath("old.bin")
        self.window.runtime.SetPath("Renode.exe")
        self.window.inspected = {"sha256": "1" * 64}
        self.window.trust.SetValue(True)
        self.window._trust_changed()
        self.assertTrue(self.window.attachment_context()["approved"])
        self.window.image.SetPath("new.bin")
        self.window._configuration_changed()
        self.assertFalse(self.window.trust.GetValue())
        self.assertIsNone(self.window.inspected)
        self.assertIsNone(self.window.approval)
        self.assertEqual(self.started, [])

    def test_selection_change_discards_inflight_startup_session(self):
        entered=threading.Event();release=threading.Event();instances=[]
        class SlowSession:
            def __init__(self,*args,**kwargs):
                self.closed=False;instances.append(self);entered.set();release.wait(2)
            def close(self):self.closed=True
        self.module.FirmwareSession=SlowSession
        self.window.image.SetPath("old.bin");self.window.runtime.SetPath("Renode.exe")
        self.window.inspected={"sha256":"1"*64}
        self.window.approval=(self.window.target_id,"old.bin","Renode.exe","1"*64)
        self.window.trust.SetValue(True);self.window.load()
        self.assertTrue(entered.wait(1));self.assertTrue(self.window.busy)
        self.window.image.SetPath("new.bin");self.window._configuration_changed();release.set()
        self.pump_until(lambda:not self.window.busy)
        self.assertEqual(len(instances),1);self.assertTrue(instances[0].closed)
        self.assertIsNone(self.window.session);self.assertFalse(self.window.trust.GetValue())

    def test_initial_snapshot_failure_closes_runtime_before_dropping_it(self):
        class BrokenSession:
            time_s=0.0
            def __init__(self):self.closed=False
            def gpio_state(self,port):raise RuntimeError("snapshot failed")
            def uart_read(self):return b""
            def close(self):self.closed=True
        session=BrokenSession();self.window.session=session;self.window._request_snapshot()
        self.pump_until(lambda:not self.window.busy)
        self.assertTrue(session.closed);self.assertIsNone(self.window.session)
        self.assertIn("snapshot failed",self.window.status.GetLabel())

    def test_close_after_completion_before_callafter_disposes_loaded_session(self):
        instances=[]
        class TrackingSession:
            def __init__(self,*args,**kwargs):self.closed=False;instances.append(self)
            def close(self):self.closed=True
        self.module.FirmwareSession=TrackingSession
        self.window.image.SetPath("firmware.bin");self.window.runtime.SetPath("Renode.exe")
        self.window.inspected={"sha256":"2"*64}
        self.window.approval=(self.window.target_id,"firmware.bin","Renode.exe","2"*64)
        self.window.trust.SetValue(True);self.window.load();future=self.window.pending
        deadline=time.monotonic()+1
        while not future.done() and time.monotonic()<deadline:time.sleep(.005)
        self.assertTrue(future.done());self.assertEqual(len(instances),1)
        self.window.close()
        self.pump_until(lambda:instances[0].closed)
        self.assertIsNone(self.window.session)

    def test_reload_clears_remembered_di_levels_and_checkboxes(self):
        class OldSession:
            def __init__(self):self.closed=False
            def close(self):self.closed=True
        self.window.session=OldSession();port,index=self.window.pin_rows[0][1:]
        self.window.inputs[(port,index)]=True;self.window.gpio.SetCellValue(0,4,"1")
        self.window.image.SetPath("firmware.bin");self.window.runtime.SetPath("Renode.exe")
        self.window.inspected={"sha256":"3"*64}
        self.window.approval=(self.window.target_id,"firmware.bin","Renode.exe","3"*64)
        self.window.trust.SetValue(True);self.window.load()
        self.assertEqual(self.window.inputs,{})
        self.assertTrue(all(not self.window.gpio.GetCellValue(row,4)
                            for row in range(self.window.gpio.GetNumberRows())))


if __name__ == "__main__":
    unittest.main()
