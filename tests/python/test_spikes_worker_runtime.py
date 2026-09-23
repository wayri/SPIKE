import unittest

from python.spike_core.service import handle
from python.spike_core.spikes_runtime import close_all_sessions


RC_NETLIST = """* Interactive RC worker test
Vdrive in 0 0
R1 in out 1k
C1 out 0 1u
.tran 100u 2m
.end
"""


class SpikesWorkerRuntimeTests(unittest.TestCase):
    def tearDown(self):
        close_all_sessions()

    def test_owned_engine_is_available_with_persistent_sessions(self):
        response = handle({"method": "spikes_engine_status", "params": {}})
        self.assertTrue(response["ok"])
        status = response["result"]
        self.assertEqual(status["status"], "ready")
        self.assertTrue(status["features"]["persistent_sessions"])
        self.assertEqual(status["execution_class"], "soft_realtime")
        self.assertFalse(status["hard_realtime_qualified"])

    def test_interactive_source_step_and_checkpoint_restore(self):
        created = handle({
            "method": "spikes_session_create",
            "params": {
                "netlist": RC_NETLIST,
                "probes": ["V(out)"],
                "integration_method": "backward_euler",
            },
        })["result"]
        session_id = created["session_id"]
        stepped = handle({
            "method": "spikes_session_step",
            "params": {
                "session_id": session_id,
                "source_values": {"Vdrive": 1.0},
                "steps": 10,
            },
        })["result"]
        observed = stepped["samples"][-1]["values"]["V(out)"]
        expected = 1.0 - (1.0 / 1.1) ** 10
        self.assertAlmostEqual(observed, expected, places=12)

        checkpoint = handle({
            "method": "spikes_session_checkpoint",
            "params": {"session_id": session_id},
        })["result"]
        handle({
            "method": "spikes_session_step",
            "params": {
                "session_id": session_id,
                "source_values": {"Vdrive": -1.0},
                "steps": 3,
            },
        })
        restored = handle({
            "method": "spikes_session_restore",
            "params": {
                "session_id": session_id,
                "checkpoint_id": checkpoint["checkpoint_id"],
            },
        })["result"]
        self.assertEqual(restored["sample"]["values"]["V(out)"], observed)

        closed = handle({
            "method": "spikes_session_close",
            "params": {"session_id": session_id},
        })["result"]
        self.assertEqual(closed["status"], "closed")

    def test_owned_one_shot_transient_route(self):
        result = handle({
            "method": "spikes_run_netlist",
            "params": {
                "netlist": RC_NETLIST,
                "probes": ["V(out)"],
                "integration_method": "hybrid_trapezoidal",
            },
        })["result"]
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["provenance"]["owned_cpp_transient"])
        self.assertGreater(len(result["data"]["time_s"]), 10)


if __name__ == "__main__":
    unittest.main()
