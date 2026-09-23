# SPDX-License-Identifier: MIT
import copy
import unittest

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.spikes_layout_adapter import (
    SpikesLayoutAdapterError,
    design_ir_artifact_identity,
    preflight_layout_candidate,
)


class SpikesLayoutCandidatePreflightTests(unittest.TestCase):
    def setUp(self):
        legacy = DesignIR(
            design_id="board-native-id",
            name="Layout candidate",
            source_format="kicad",
            layers=[{"id": "layer-f-cu", "name": "F.Cu", "type": "signal"}],
            nets=[{"id": "net-vcc", "name": "VCC"}],
            tracks=[{
                "id": "track-vcc-1", "net_name": "VCC", "layer": "F.Cu",
                "start": [0.0, 0.0], "end": [10.0, 0.0], "width": 0.5,
            }],
            components=[{
                "id": "component-u1", "reference": "U1", "footprint": "QFN",
                "at": [2.0, 2.0], "rotation": 0.0,
            }],
            metadata={"source_sha256": "1" * 64},
        )
        self.parent = DesignIRV2.from_v1(legacy)
        candidate_raw = copy.deepcopy(self.parent.to_dict())
        candidate_raw["tracks"][0]["end_mm"] = [12.0, 0.0]
        self.candidate = DesignIRV2.from_dict(candidate_raw)
        self.track_id = self.candidate.tracks[0].id
        self.component_id = self.candidate.components[0].id
        self.request = self._request("autorouter", self.track_id)

    def _artifact(self, design):
        identity = design_ir_artifact_identity(design)
        return {
            "path": "candidates/design-ir-v2.json",
            "sha256": identity["sha256"],
            "bytes": identity["bytes"],
            "contract": identity["contract"],
        }

    def _request(self, consumer, scoped_id):
        candidate = self._artifact(self.candidate)
        parent = self._artifact(self.parent)
        return {
            "contract": "spike/layout-evaluation/v1",
            "record_type": "request",
            "evaluation_id": "layout.iteration-2",
            "consumer": {"kind": consumer, "implementation": "fixture-engine"},
            "candidate": candidate,
            "parent_candidate_sha256": parent["sha256"],
            "changed_entity_ids": [self.track_id],
            "requirements": [{
                "id": "layout.clearance",
                "evaluator": "custom",
                "kind": "hard_constraint",
                "metric_id": "pcb.minimum_clearance",
                "relation": "ge",
                "dimension": [1, 0, 0, 0, 0, 0, 0],
                "lower_si": 0.0002,
                "scope": {"frame": "board", "entity_ids": [scoped_id]},
            }],
            "physics_evaluations": [],
            "resources": {
                "max_memory_bytes": 16777216, "max_wall_time_s": 30,
                "ranks": 1, "threads": 1,
            },
            "deterministic": True,
        }

    def test_router_candidate_is_digest_bound_and_correlated_to_parent(self):
        result = preflight_layout_candidate(self.request, self.candidate, parent=self.parent)

        self.assertEqual(result["consumer_kind"], "autorouter")
        self.assertEqual(result["candidate_design_id"], self.parent.design_id)
        self.assertEqual(result["changed_entities"], [{"entity_id": self.track_id, "kind": "tracks"}])
        self.assertEqual(
            result["scope_bindings"]["layout.clearance"],
            [{"entity_id": self.track_id, "kind": "tracks"}],
        )
        self.assertEqual(result["parent_candidate_sha256"], self.request["parent_candidate_sha256"])

    def test_tampered_candidate_digest_fails_closed(self):
        request = copy.deepcopy(self.request)
        request["candidate"]["sha256"] = "0" * 64

        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            preflight_layout_candidate(request, self.candidate, parent=self.parent)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-PREFLIGHT-0004")

    def test_tampered_candidate_byte_count_fails_closed(self):
        request = copy.deepcopy(self.request)
        request["candidate"]["bytes"] += 1

        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            preflight_layout_candidate(request, self.candidate, parent=self.parent)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-PREFLIGHT-0004")

    def test_unknown_scope_and_wrong_frame_fail_before_evaluation(self):
        request = copy.deepcopy(self.request)
        request["requirements"][0]["scope"]["entity_ids"] = ["missing-entity"]
        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            preflight_layout_candidate(request, self.candidate, parent=self.parent)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-PREFLIGHT-0006")

        request = copy.deepcopy(self.request)
        request["requirements"][0]["scope"]["frame"] = "assembly"
        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            preflight_layout_candidate(request, self.candidate, parent=self.parent)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-PREFLIGHT-0006")

    def test_change_declaration_must_exactly_match_parent_diff(self):
        request = copy.deepcopy(self.request)
        request["changed_entity_ids"] = []

        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            preflight_layout_candidate(request, self.candidate, parent=self.parent)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-PREFLIGHT-0007")

    def test_autoplacer_cannot_claim_route_mutation_or_route_scope(self):
        request = self._request("autoplacer", self.track_id)

        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            preflight_layout_candidate(request, self.candidate, parent=self.parent)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-PREFLIGHT-0006")

    def test_invalid_net_or_layer_reference_fails_closed(self):
        broken_raw = copy.deepcopy(self.candidate.to_dict())
        broken_raw["tracks"][0]["net_id"] = "missing-net"
        broken = DesignIRV2.from_dict(broken_raw)
        request = copy.deepcopy(self.request)
        request["candidate"] = self._artifact(broken)

        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            preflight_layout_candidate(request, broken, parent=self.parent)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-PREFLIGHT-0003")

    def test_canonical_entity_identity_cannot_change_across_lineage(self):
        changed_raw = copy.deepcopy(self.candidate.to_dict())
        changed_raw["tracks"][0]["id"] = "substituted-track-id"
        substituted = DesignIRV2.from_dict(changed_raw)
        request = copy.deepcopy(self.request)
        request["candidate"] = self._artifact(substituted)
        request["changed_entity_ids"] = [self.track_id, "substituted-track-id"]
        request["requirements"][0]["scope"]["entity_ids"] = ["substituted-track-id"]

        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            preflight_layout_candidate(request, substituted, parent=self.parent)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-PREFLIGHT-0005")

    def test_source_identity_and_coordinate_frame_cannot_drift(self):
        source_drift_raw = copy.deepcopy(self.candidate.to_dict())
        source_drift_raw["source"]["source_digest"] = "2" * 64
        source_drift = DesignIRV2.from_dict(source_drift_raw)
        request = copy.deepcopy(self.request)
        request["candidate"] = self._artifact(source_drift)
        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            preflight_layout_candidate(request, source_drift, parent=self.parent)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-PREFLIGHT-0005")

        frame_drift_raw = copy.deepcopy(self.candidate.to_dict())
        frame_drift_raw["frame"]["frame_id"] = "shifted-board"
        frame_drift = DesignIRV2.from_dict(frame_drift_raw)
        request = copy.deepcopy(self.request)
        request["candidate"] = self._artifact(frame_drift)
        request["requirements"][0]["scope"]["frame"] = "shifted-board"
        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            preflight_layout_candidate(request, frame_drift, parent=self.parent)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-PREFLIGHT-0005")

    def test_baseline_binding_is_independent_of_parent_field(self):
        request = copy.deepcopy(self.request)
        request.pop("parent_candidate_sha256")
        request["baseline"] = self._artifact(self.parent)

        result = preflight_layout_candidate(request, self.candidate, baseline=self.parent)
        self.assertEqual(result["baseline_sha256"], request["baseline"]["sha256"])


if __name__ == "__main__":
    unittest.main()
