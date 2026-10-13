# SPDX-License-Identifier: Apache-2.0
import contextlib
import io
import unittest
from python.spike_core.service import handle
from tests.python.test_spice_workspace import fixture_design, fixture_workspace
from tests.python.test_studio_board_coupling import request

class StudioIntegrationTests(unittest.TestCase):
    def test_composed_board_runs_through_registered_worker_with_progress(self):
        design=fixture_design().to_dict()
        workspace=fixture_workspace()
        workspace["models"][0]["value"]="DC 1"
        workspace["analysis"]={"mode":"operating_point"}
        context=handle({"method":"prepare_studio_board_context","params":{"design":design}})
        self.assertTrue(context["ok"],context)
        composed=handle({"method":"compose_spice_workspace","params":{"design":design,"workspace":workspace}})
        self.assertEqual(composed["result"]["status"],"ready",composed)
        supplied=request("steady_state")
        supplied["netlist"]=composed["result"]["netlist"]
        supplied["board_revision"]=context["result"]["board_revision"]
        supplied["bindings"][0].update(component_id="component-r1",element_id=composed["result"]["element_aliases"]["R1"])
        stderr=io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result=handle({"id":"studio-integration","method":"run_studio_board_cosimulation","params":{"design":design,"request":supplied}})
        self.assertTrue(result["ok"],result)
        self.assertEqual(result["result"]["status"],"completed",result)
        self.assertAlmostEqual(result["result"]["frames"][0]["temperature_k"]["body"],300.1,places=8)
        self.assertIn('"accepted_frame"',stderr.getvalue())
        self.assertIn('"operation_id":"studio-integration"',stderr.getvalue())
    def test_registered_worker_rejects_unapproved_scope_and_stale_revision(self):
        design=fixture_design().to_dict()
        supplied=request("steady_state")
        supplied["bindings"][0]["component_id"]="component-r1"
        stale=handle({"method":"validate_studio_board_cosimulation","params":{"design":design,"request":supplied}})
        self.assertTrue(stale["ok"],stale)
        self.assertEqual(stale["result"]["status"],"rejected")
        blocked=handle({"method":"run_studio_board_cosimulation","params":{"design":design,"request":supplied,"assembly_scope":{"mode":"invalid"}}})
        self.assertFalse(blocked["ok"],blocked)

if __name__=="__main__":unittest.main()
