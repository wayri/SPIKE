# SPDX-License-Identifier: Apache-2.0
import copy
import json
from pathlib import Path
import unittest

from python.spike_core.service_si_spatial import inspect_si_spatial_context, run_si_spatial_pair
from python.spike_core.service_si_models import handle_si_model_request


class SpatialContextTests(unittest.TestCase):
    def params(self):
        return {"design": {"contract": "spike/design-ir/v2", "design_id": "pair", "name": "Original pair",
                "source": {"source_format": "fixture", "source_digest": "a" * 64},
                "layers": [{"id": "top", "layer_type": "copper", "z_mm": 0.}],
                "nets": [{"id": "A"}, {"id": "V"}],
                "tracks": [{"id": "aggressor", "net_id": "A", "layer_id": "top", "start_mm": [0., 0.], "end_mm": [80., 0.], "width_mm": .2},
                           {"id": "victim", "net_id": "V", "layer_id": "top", "start_mm": [0., 1.], "end_mm": [80., 1.], "width_mm": .2}]},
                "occurrence_id": "board1", "aggressor_net_id": "A", "victim_net_id": "V", "request_id": "run1"}

    def pair(self):
        params = self.params()
        raw = json.loads((Path(__file__).resolve().parents[2] / "examples/rlgc_coupled_pair/symmetric-pair.request.json").read_text())
        raw["conductor_ids"] = ["A", "V"]
        for excitation in raw["excitations"]:
            excitation["incident_waves"] = [{"real": 1., "imag": 0.}, {"real": 0., "imag": 0.}, {"real": 0., "imag": 0.}, {"real": 0., "imag": 0.}]
        params.update(pair_request=raw, aggressor_segment_id="aggressor", victim_segment_id="victim")
        return params

    def test_current_coordinates_and_revision_digest(self):
        params = self.params()
        before = inspect_si_spatial_context(params)
        self.assertEqual(before["traceSegments"][0]["endMm"], [80., 1., 0.])
        params["design"]["tracks"][1]["end_mm"][0] = 81.
        self.assertNotEqual(before["designDigest"], inspect_si_spatial_context(params)["designDigest"])

    def test_fail_closed_net_nonfinite_and_nonidentity_frame(self):
        for mutation in (lambda p: p.update(victim_net_id="missing"),
                         lambda p: p["design"]["tracks"][1]["start_mm"].__setitem__(0, float("nan")),
                         lambda p: p["design"].update(frame={"parent_frame_id": "assembly"})):
            params = self.params(); mutation(params)
            with self.assertRaises(ValueError): inspect_si_spatial_context(params)

    def test_actual_phasors_and_scope_preserved(self):
        output = run_si_spatial_pair(self.pair())
        self.assertFalse(output["data"]["sourceResult"]["modelScope"]["extracted"])
        self.assertNotIn("fieldSamples", output["data"])
        for probe_index, sample in enumerate(output["data"]["traceSamples"]):
            for frequency_index, voltage in enumerate(sample["inducedVoltageV"]):
                raw = output["sourceResult"]["points"][frequency_index]["probe_values"][probe_index]["conductors"][1]["voltage_v"]
                self.assertEqual(voltage, [raw["real"], raw["imag"]])

    def test_driven_victim_and_wrong_geometry_rejected(self):
        for mutation in (lambda p: p["pair_request"]["excitations"][0]["incident_waves"][1].update(real=.1),
                         lambda p: p["design"]["tracks"][1]["end_mm"].__setitem__(0, 81.)):
            params = self.pair(); mutation(params)
            with self.assertRaises(ValueError): run_si_spatial_pair(params)

    def test_worker_dispatch(self):
        self.assertTrue(handle_si_model_request("inspect_si_spatial_context", self.params())["ok"])
        self.assertFalse(handle_si_model_request("inspect_si_spatial_context", {})["ok"])


if __name__ == "__main__": unittest.main()
