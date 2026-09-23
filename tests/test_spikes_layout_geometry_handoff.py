# SPDX-License-Identifier: MIT
import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.design_ir_v2_schema import (
    Arc,
    Component,
    CoordinateFrame,
    Drill,
    Layer,
    Material,
    Net,
    Pad,
    Region,
    SourceIdentity,
    Track,
    Via,
    Zone,
)
from python.spike_core.spikes_layout_adapter import design_ir_artifact_identity
from python.spike_core.spikes_layout_contract import SpikesLayoutAdapterError
from python.spike_core.spikes_layout_geometry_handoff import (
    DESIGNIR_LAYOUT_HANDOFF_CONTRACT,
    build_designir_layout_handoff,
    canonical_designir_layout_handoff_json,
    validate_designir_layout_handoff_identity,
)


class SpikesLayoutGeometryHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema_path = Path(__file__).parents[1] / "schemas" / "designir-layout-handoff-v1.schema.json"
        cls.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def setUp(self):
        self.parent = self._design(track_end=(8.0, 1.0))
        self.candidate = self._design(track_end=(9.0, 1.0))
        self.request = self._request(self.candidate, parent=self.parent)

    @staticmethod
    def _design(*, track_end):
        copper = Material(
            id="material-copper", name="Copper", material_class="conductor",
            conductivity_s_per_m=5.8e7, relative_permittivity=1.0,
            loss_tangent=0.0,
        )
        dielectric = Material(
            id="material-fr4", name="FR-4", material_class="dielectric",
            relative_permittivity=4.1, loss_tangent=0.018,
        )
        layers = [
            Layer(id="layer-bottom", name="B.Cu", layer_type="copper", order=0,
                  z_mm=0.0, thickness_mm=0.035, material_id=copper.id),
            Layer(id="layer-core", name="Core", layer_type="dielectric", order=1,
                  z_mm=0.035, thickness_mm=0.93, material_id=dielectric.id),
            Layer(id="layer-top", name="F.Cu", layer_type="copper", order=2,
                  z_mm=0.965, thickness_mm=0.035, material_id=copper.id),
        ]
        signal = Net(id="net-signal", name="SIG")
        ground = Net(id="net-ground", name="GND")
        zone = Zone(
            id="zone-ground", name="Ground fill", net_id=ground.id,
            layer_ids=[layers[0].id],
            outlines_mm=[[(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]],
            filled_copper_state="source_filled", filled_copper_id="source-fill-component",
            source_fill_group_id="source-fill-group",
            source_fill_group_sha256="a" * 64,
            source_fill_component_ordinal=1, source_fill_component_count=1,
            source_fill_component_sha256="b" * 64,
            source_fill_representation="flat_polygon_path",
            source_fill_provenance_complete=True,
        )
        return DesignIRV2(
            design_id="board-1", name="Supported subset",
            source=SourceIdentity(source_format="kicad", source_digest="1" * 64),
            frame=CoordinateFrame(
                transform=(1.0, 0.0, 0.0, 2.0,
                           0.0, 1.0, 0.0, 3.0,
                           0.0, 0.0, 1.0, 4.0,
                           0.0, 0.0, 0.0, 1.0),
            ),
            materials=[dielectric, copper], layers=layers, nets=[signal, ground],
            tracks=[Track(id="track-signal", net_id=signal.id, layer_id=layers[2].id,
                          start_mm=(1.0, 1.0), end_mm=track_end, width_mm=0.2)],
            arcs=[Arc(id="arc-signal", net_id=signal.id, layer_id=layers[2].id,
                      start_mm=(1.0, 2.0), mid_mm=(2.0, 3.0), end_mm=(3.0, 2.0),
                      width_mm=0.2)],
            zones=[zone],
            pads=[Pad(id="pad-signal", net_id=signal.id, layer_ids=[layers[2].id],
                      center_mm=(1.0, 1.0), size_mm=(0.6, 0.6), shape="circle")],
            vias=[Via(id="via-signal", net_id=signal.id, center_mm=(5.0, 1.0),
                      diameter_mm=0.6, drill_mm=0.3,
                      start_layer_id=layers[0].id, end_layer_id=layers[2].id,
                      plating_mm=0.05, via_type="through")],
        )

    @staticmethod
    def _artifact(design):
        identity = design_ir_artifact_identity(design)
        return {"path": "candidates/design-ir-v2.json", **identity}

    def _request(self, candidate, *, parent=None, consumer="autorouter"):
        request = {
            "contract": "spike/layout-evaluation/v1", "record_type": "request",
            "evaluation_id": "layout.native-handoff", "consumer": {
                "kind": consumer, "implementation": "fixture-router", "version": "1",
            },
            "candidate": self._artifact(candidate),
            "changed_entity_ids": ["track-signal"] if parent is not None else [],
            "requirements": [{
                "id": "layout.clearance", "evaluator": "custom",
                "kind": "hard_constraint", "metric_id": "pcb.minimum_clearance",
                "relation": "ge", "dimension": [1, 0, 0, 0, 0, 0, 0],
                "lower_si": 0.0002,
                "scope": {"frame": "board", "entity_ids": ["track-signal"]},
            }],
            "physics_evaluations": [],
            "resources": {"max_memory_bytes": 16777216, "max_wall_time_s": 30,
                          "ranks": 1, "threads": 1},
            "deterministic": True,
        }
        if parent is not None:
            request["parent_candidate_sha256"] = self._artifact(parent)["sha256"]
        return request

    def _without_parent(self, design):
        return self._request(design)

    def test_supported_subset_is_schema_valid_digest_bound_and_non_product(self):
        handoff = build_designir_layout_handoff(
            self.request, self.candidate, parent=self.parent,
        )
        self.validator.validate(handoff)
        validate_designir_layout_handoff_identity(handoff)

        self.assertEqual(handoff["contract"], DESIGNIR_LAYOUT_HANDOFF_CONTRACT)
        self.assertEqual(handoff["lineage"]["source_sha256"], "1" * 64)
        self.assertEqual(
            handoff["lineage"]["candidate_sha256"],
            design_ir_artifact_identity(self.candidate)["sha256"],
        )
        self.assertEqual(
            handoff["lineage"]["parent_candidate_sha256"],
            design_ir_artifact_identity(self.parent)["sha256"],
        )
        self.assertEqual(handoff["frame"]["translation_mm"], [2.0, 3.0, 4.0])
        self.assertEqual([item["public_id"] for item in handoff["materials"]],
                         ["material-copper", "material-fr4"])
        self.assertEqual(handoff["changed_entity_ids"], ["track-signal"])
        self.assertFalse(handoff["claims"]["solid_boolean_meshing_performed"])
        self.assertFalse(handoff["claims"]["conforming_volume_mesh_generated"])
        self.assertFalse(handoff["claims"]["product_em_ready"])

        serialized = canonical_designir_layout_handoff_json(handoff)
        self.assertEqual(serialized, canonical_designir_layout_handoff_json(handoff))

    def test_identity_reconstruction_rejects_tampering(self):
        handoff = build_designir_layout_handoff(
            self.request, self.candidate, parent=self.parent,
        )
        handoff["tracks"][0]["width_mm"] = 0.25
        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            validate_designir_layout_handoff_identity(handoff)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-HANDOFF-0002")

    def test_non_affine_or_nested_frame_fails_closed(self):
        for change in ("perspective", "parent"):
            raw = copy.deepcopy(self.candidate.to_dict())
            if change == "perspective":
                raw["frame"]["transform"] = list(raw["frame"]["transform"])
                raw["frame"]["transform"][12] = 0.1
            else:
                raw["frame"]["parent_frame_id"] = "assembly"
            design = DesignIRV2.from_dict(raw)
            with self.subTest(change=change), self.assertRaises(SpikesLayoutAdapterError) as caught:
                build_designir_layout_handoff(self._without_parent(design), design)
            self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-HANDOFF-0003")

    def test_unsupported_consumer_and_entity_families_fail_closed(self):
        joint = self._request(self.candidate, parent=self.parent, consumer="joint")
        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            build_designir_layout_handoff(joint, self.candidate, parent=self.parent)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-HANDOFF-0004")

        additions = {
            "components": Component(id="component-u1", reference="U1"),
            "regions": Region(id="region-board", outlines_mm=[[(0.0, 0.0), (1.0, 0.0),
                                                                  (1.0, 1.0)]],
                              layer_ids=["layer-core"]),
            "drills": Drill(id="drill-1", center_mm=(2.0, 2.0), shape="circle",
                             diameter_mm=0.3, owner_kind="none"),
        }
        for collection, item in additions.items():
            design = DesignIRV2.from_dict(self.candidate.to_dict())
            getattr(design, collection).append(item)
            with self.subTest(collection=collection), self.assertRaises(SpikesLayoutAdapterError) as caught:
                build_designir_layout_handoff(self._without_parent(design), design)
            self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-HANDOFF-0004")

    def test_custom_pad_track_path_and_unresolved_zone_fail_closed(self):
        cases = []
        custom = copy.deepcopy(self.candidate.to_dict())
        custom["pads"][0]["shape"] = "oval"
        cases.append(("unsupported-pad-shape", custom))

        path = copy.deepcopy(self.candidate.to_dict())
        path["tracks"][0]["path"] = {
            "path_id": "path-1", "step_index": 0, "step_count": 1,
            "end_cap": "round", "join_style": "round",
        }
        cases.append(("track-path", path))

        zone = copy.deepcopy(self.candidate.to_dict())
        zone["zones"][0].update({
            "filled_copper_state": "unknown", "filled_copper_id": "",
            "source_fill_group_id": "", "source_fill_group_sha256": "",
            "source_fill_component_ordinal": 0, "source_fill_component_count": 0,
            "source_fill_component_sha256": "", "source_fill_representation": "none",
            "source_fill_provenance_complete": False,
        })
        cases.append(("unresolved-zone", zone))

        for label, raw in cases:
            design = DesignIRV2.from_dict(raw)
            with self.subTest(label=label), self.assertRaises(SpikesLayoutAdapterError) as caught:
                build_designir_layout_handoff(self._without_parent(design), design)
            self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-HANDOFF-0004")

    def test_stackup_gap_and_implicit_via_plating_fail_closed(self):
        gap = copy.deepcopy(self.candidate.to_dict())
        gap["layers"][1]["z_mm"] = 0.04
        design = DesignIRV2.from_dict(gap)
        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            build_designir_layout_handoff(self._without_parent(design), design)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-HANDOFF-0005")

        implicit = copy.deepcopy(self.candidate.to_dict())
        implicit["vias"][0]["plating_mm"] = None
        design = DesignIRV2.from_dict(implicit)
        with self.assertRaises(SpikesLayoutAdapterError) as caught:
            build_designir_layout_handoff(self._without_parent(design), design)
        self.assertEqual(caught.exception.code, "SPIKE-LAYOUT-HANDOFF-0006")


if __name__ == "__main__":
    unittest.main()
