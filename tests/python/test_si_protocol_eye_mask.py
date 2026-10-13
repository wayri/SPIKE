# SPDX-License-Identifier: Apache-2.0
import copy
import json
from pathlib import Path
import unittest
from tests.python import test_si_protocol_test_runner as runner_fixture
from tests.python import test_si_channel as channel_fixture
from python.spike_core.si_protocol_test_runner import run_si_protocol_test_suite, SiProtocolTestRunnerError
from python.spike_core.si_protocol_eye_mask import validate_lane_mask, run_lane_mask
from python.spike_core.si_eye_mask_profiles import standard_eye_mask
from python.spike_core.si_eye_mask import evaluate_eye_mask


def custom_mask(y):
    return {"schema":"spike/si-eye-mask/v1","id":"fixture.mask","name":"Test polygon", "protocol":"DDR", "revision":"fixture", "source":{"locator":"fixture://independent","clause":"test"},"voltage_unit":"normalized","polygons":[[[.2,y],[.8,y],[.8,y+.1],[.2,y+.1]]]}

class ProtocolEyeMaskTests(unittest.TestCase):
    def test_standard_numerical_coordinates_and_inner_opening_pass_fail(self):
        a=standard_eye_mask("usb2.hs.template1.inner")
        self.assertEqual(a["polygons"][0],[[.075,0],[.375,.3],[.625,.3],[.925,0],[.625,-.3],[.375,-.3]])
        b=standard_eye_mask("usb2.hs.template2.inner")
        self.assertEqual(b["polygons"][0][1],[.35,.175])
        trace=[[{"time_ui":0,"value":.4},{"time_ui":2,"value":.4}]]
        self.assertEqual(evaluate_eye_mask(a,trace,"V")["status"],"pass")
        trace=[[{"time_ui":.5,"value":.299}]]
        self.assertEqual(evaluate_eye_mask(a,trace,"V")["status"],"fail")
        self.assertEqual(evaluate_eye_mask(b,trace,"V")["status"],"pass")

    def test_real_runner_preserves_mask_outcome_without_protocol_pass(self):
        f=runner_fixture.SiProtocolTestRunnerTests();f.setUp()
        req=f.request();req["requested_tests"]=["eye"]
        req["lanes"][0]["eye_mask"]=custom_mask(10)
        result=run_si_protocol_test_suite(f.design,req)
        self.assertEqual(result["lanes"][0]["eye_mask_result"]["status"],"pass")
        self.assertEqual(result["summary"]["mask_pass_count"],1)
        self.assertFalse(result["summary"]["protocol_pass_claimed"])
        req["lanes"][0]["eye_mask"]["polygons"]=[[[0,-10],[2,-10],[2,10],[0,10]]]
        result=run_si_protocol_test_suite(f.design,req)
        self.assertEqual(result["lanes"][0]["eye_mask_result"]["status"],"fail")
        self.assertEqual(result["summary"]["mask_fail_count"],1)
        self.assertEqual(result["compliance_status"],"not_evaluated")

    def test_standard_binding_requires_correct_family_rate_and_voltage_mapping(self):
        lane={"eye_mask_id":"usb2.hs.template1.inner","channel_request":{"bit_rate_hz":480e6,"signaling":"differential"},"eye_voltage_mapping":{"scale_v":.8,"offset_v":-.4,"bit_rate_hz":480e6}}
        validate_lane_mask(lane,{"family":"USB"})
        for field,value in (("bit_rate_hz",1e9),("signaling","single_ended")):
            bad=copy.deepcopy(lane);bad["channel_request"][field]=value
            with self.assertRaises(ValueError):validate_lane_mask(bad,{"family":"USB"})
        with self.assertRaises(ValueError):validate_lane_mask(lane,{"family":"DDR"})
        bad=copy.deepcopy(lane);bad.pop("eye_voltage_mapping")
        with self.assertRaises(ValueError):validate_lane_mask(bad,{"family":"USB"})

    def test_mapping_and_missing_phase_evidence(self):
        lane={"eye_mask_id":"usb2.hs.template1.inner","channel_request":{"bit_rate_hz":480e6,"signaling":"differential"},"eye_voltage_mapping":{"scale_v":.8,"offset_v":-.4,"bit_rate_hz":480e6}}
        eye={"contract":"spike/si-nrz-eye/v1","bit_rate_hz":480e6,"traces":[{"phase_ui":[0,2],"values":[1,1]}]}
        result=run_lane_mask(lane,{"eye":eye})
        self.assertEqual(result["status"],"pass")
        self.assertEqual(result["evidence"]["voltage_mapping"],lane["eye_voltage_mapping"])
        eye["traces"][0].pop("phase_ui")
        self.assertEqual(run_lane_mask(lane,{"eye":eye})["status"],"blocked")

if __name__ == "__main__":unittest.main()
