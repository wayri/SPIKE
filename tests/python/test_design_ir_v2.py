import unittest
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import AssemblyIRV1, BoardInstance, CoordinateFrame, DesignIRV2, canonical_uuid


class DesignIRV2Tests(unittest.TestCase):
    @staticmethod
    def retained_nonregular_padstack_geometry():
        return {
            "contract": "spike/retained-padstack-geometry/v1",
            "user_primitives": [{
                "id": "USER-SPECIAL-1", "kind": "user_special", "source_index": 5,
                "source_units": "mm", "contours": [{"boundary_rings": [{
                    "role": "outer", "fill_style_id": "SOLID_FILL", "start_mm": [0, 0],
                    "segments": [
                        {"kind": "line", "end_mm": [2, 0]},
                        {"kind": "line", "end_mm": [2, 2]},
                        {"kind": "line", "end_mm": [0, 2]},
                        {"kind": "line", "end_mm": [0, 0]},
                    ],
                }]}],
            }],
            "occurrences": [{
                "source_index": 17, "source_id": "PADSTACK-17",
                "kind": "retained_padstack_nonregular_occurrence", "status": "retained_unresolved",
                "reason": "negative_plane_user_primitive_semantics_pending", "padstack_ref": "PTH-1",
                "layer_id": "F.Cu", "layer_polarity": "negative", "raw_net_ref": "VCC",
                "resolved_net_id": "VCC", "occurrence_pad_usage": "via", "matched_profile_use": "thermal",
                "at_mm": [3, 4], "xform": {"rotation_deg": 90, "mirror": False},
                "primitive_ref": "USER-SPECIAL-1",
            }],
        }

    @staticmethod
    def retained_standard_contour_land_geometry():
        return {
            "contract": "spike/retained-standard-contour-land-geometry/v2",
            # Empirical source facts only; they do not assert IPC conformance.
            "semantic_state": "unapplied_normative_semantics_missing", "projection": "forbidden",
            "definitions": [{
                "id": "LAND-1", "kind": "standard_contour_land_definition", "status": "retained_unresolved",
                "reason": "contour_land_layer_transform_semantics_pending", "source_index": 4, "source_units": "inch",
                "raw_entry_attributes": {"id": "LAND-1"},
                "contour": {"kind": "closed_line_ring", "points_mm": [[0, 0], [1, 0], [1, 1], [0, 0]],
                            "fill_style_ref": "SOLID", "raw_poly_begin_attributes": {"x": "0", "y": "0"},
                            "raw_poly_step_attributes": [{"x": "1", "y": "0"}, {"x": "1", "y": "1"}, {"x": "0", "y": "0"}],
                            "raw_fill_ref_attributes": {"id": "SOLID"}},
                "fill_descriptor": {"id": "SOLID", "source_units": "inch", "declared_fill_property": "FILL", "raw_attributes": {"fillproperty": "FILL"}},
            }],
            "padstacks": [{
                "name": "PS-1", "source_index": 5, "raw_attributes": {"name": "PS-1"}, "declared_regular_layer_id": "F.Cu",
                "raw_declared_regular_layer_ref": "F.Cu", "raw_profile_attributes": {"layerref": "F.Cu", "paduse": "REGULAR"},
                "profile_location": {"at_mm": [0, 0], "raw_attributes": {"x": "0", "y": "0"}},
                "profile_xform": {"rotation_deg": 90, "mirror": False, "raw_attributes": {"rotation": "90", "mirror": "false"}},
                "primitive_ref": "LAND-1", "raw_primitive_ref_attributes": {"id": "LAND-1"},
            }],
            "occurrences": [{
                "source_index": 6, "source_id": "PAD-6", "kind": "standard_contour_land_occurrence", "status": "retained_unresolved",
                "reason": "contour_land_layer_transform_semantics_pending", "padstack_ref": "PS-1", "primitive_ref": "LAND-1",
                "declared_regular_layer_id": "F.Cu", "observed_layer_id": "B.Cu", "declared_layer_matches_observed": False,
                "raw_observed_layer_ref": "B.Cu", "observed_layer_polarity": "positive", "raw_net_ref": "VCC", "resolved_net_id": "VCC",
                "pin_provenance": {"raw_component_ref": "U1", "resolved_component_id": "U1", "component_layer_id": "F.Cu", "pin": "1", "raw_attributes": {"componentref": "U1", "pin": "1"}},
                "at_mm": [3, 4], "xform": {"rotation_deg": 360, "mirror": True, "raw_attributes": {"rotation": "360", "mirror": "true"}},
                "raw_primitive_ref_attributes": {"id": "LAND-1"}, "raw_pad_attributes": {"padstackdefref": "PS-1"},
                "raw_set_attributes": {"net": "VCC"}, "raw_layer_feature_attributes": {"layerref": "B.Cu"},
            }],
        }

    def fixture(self):
        return DesignIR(
            design_id="native-board-id",
            name="fixture",
            source_format="kicad",
            layers=[{"id": 0, "name": "F.Cu", "type": "signal"}, {"id": 2, "name": "B.Cu", "type": "signal"}],
            nets=[{"id": 1, "name": "VCC"}],
            tracks=[{"id": "t1", "net_name": "VCC", "layer": "F.Cu", "start": [0, 0], "end": [10, 0], "width": 1}],
            pads=[{"id": "p1", "type": "through_hole", "net_name": "VCC", "layers": ["F.Cu", "B.Cu"], "at": [0, 0], "size": [2, 1.5], "drill": 0.6, "drill_size": [0.6, 1.0], "drill_shape": "oval"}],
            vias=[{"id": "v1", "net_name": "VCC", "at": [10, 0], "diameter": 0.8, "drill": 0.4, "layers": ["F.Cu", "B.Cu"]}],
            metadata={"source_sha256": "a" * 64},
        )

    def test_conversion_is_deterministic_and_round_trips_legacy_geometry(self):
        first = DesignIRV2.from_v1(self.fixture())
        second = DesignIRV2.from_v1(self.fixture())
        self.assertEqual(first.design_id, second.design_id)
        self.assertEqual(first.tracks[0].id, second.tracks[0].id)
        self.assertEqual(first.source.source_digest, "a" * 64)
        legacy = first.to_v1()
        self.assertEqual(legacy.tracks[0]["id"], "t1")
        self.assertEqual(legacy.vias[0]["layers"], ["F.Cu", "B.Cu"])
        self.assertEqual(first.pads[0].drill_size_mm, (0.6, 1.0))
        self.assertEqual(first.pads[0].drill_shape, "oval")
        self.assertTrue(first.pads[0].plated)
        self.assertEqual(legacy.pads[0]["drill_size"], [0.6, 1.0])
        self.assertEqual(legacy.pads[0]["drill_shape"], "oval")

    def test_custom_pad_contract_rejects_degenerate_and_admits_bounded_plated_drills(self):
        design = self.fixture()
        design.pads = [{
            "id": "custom-1", "type": "through_hole", "shape": "custom", "net_name": "VCC",
            "layers": ["F.Cu", "B.Cu"], "at": [0, 0], "size": [2, 2], "drill_size": [0, 0],
            "drill_shape": "none", "custom_geometry": {
                "status": "supported", "coordinate_space": "pad_local_mm", "mirror_x": False,
                "positive_filled_polygon": [[-1, -1], [1, -1], [1, 1], [-1, 1]],
            },
        }]
        typed = DesignIRV2.from_v1(design)
        self.assertEqual(typed.pads[0].custom_geometry["status"], "supported")

        degenerate = typed.to_dict()
        degenerate["pads"][0]["custom_geometry"]["positive_filled_polygon"] = [
            [-1, -1], [-1, -1], [1, 1], [-1, 1],
        ]
        with self.assertRaisesRegex(ValueError, "simple"):
            DesignIRV2.from_dict(degenerate)

        drilled = typed.to_dict()
        drilled["pads"][0]["drill_size_mm"] = [0.2, 0.2]
        drilled["pads"][0]["drill_shape"] = "circle"
        drilled["pads"][0]["plated"] = True
        self.assertEqual(DesignIRV2.from_dict(drilled).pads[0].drill_size_mm, [0.2, 0.2])

    def test_canonical_uuid_changes_with_source_digest(self):
        self.assertNotEqual(
            canonical_uuid("kicad", "a" * 64, "track", "1"),
            canonical_uuid("kicad", "b" * 64, "track", "1"),
        )

    def test_typed_serialization_rehydrates_the_public_schema(self):
        design = DesignIRV2.from_v1(self.fixture())
        restored = DesignIRV2.from_dict(design.to_dict())

        self.assertEqual(json.loads(json.dumps(restored.to_dict())), json.loads(json.dumps(design.to_dict())))
        self.assertEqual(restored.to_v1().to_dict(), design.to_v1().to_dict())

        schema_path = Path(__file__).parents[2] / "schemas" / "design-ir-v2.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(json.loads(json.dumps(design.to_dict())))

    def test_exact_per_layer_land_profiles_round_trip_and_validate(self):
        fixture = self.fixture()
        fixture.pads[0]["land_profiles"] = [
            {"layer_id": "F.Cu", "use": "regular", "shape": "rect", "size_mm": [2.0, 1.5],
             "offset_mm": [0.0, 0.0], "source_primitive_id": "RECT-TOP"},
            {"layer_id": "B.Cu", "use": "regular", "shape": "circle", "size_mm": [1.6, 1.6],
             "offset_mm": [0.0, 0.0], "source_primitive_id": "CIRCLE-BOT"},
        ]
        fixture.vias[0]["land_profiles"] = [
            {"layer_id": "F.Cu", "use": "regular", "shape": "circle", "size_mm": [0.8, 0.8],
             "offset_mm": [0.0, 0.0], "source_primitive_id": "VIA-TOP"},
            {"layer_id": "B.Cu", "use": "regular", "shape": "circle", "size_mm": [0.6, 0.6],
             "offset_mm": [0.0, 0.0], "source_primitive_id": "VIA-BOT"},
        ]

        design = DesignIRV2.from_v1(fixture)
        restored = DesignIRV2.from_dict(json.loads(json.dumps(design.to_dict())))
        self.assertEqual(json.loads(json.dumps(restored.to_dict())), json.loads(json.dumps(design.to_dict())))
        self.assertEqual(restored.pads[0].land_profiles[1].source_primitive_id, "CIRCLE-BOT")
        self.assertEqual(restored.to_v1().vias[0]["land_profiles"][1]["size_mm"], [0.6, 0.6])

        schema = json.loads((Path(__file__).parents[2] / "schemas" / "design-ir-v2.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(json.loads(json.dumps(design.to_dict())))
        broken = design.to_dict()
        broken["pads"][0]["land_profiles"][1]["layer_id"] = broken["pads"][0]["land_profiles"][0]["layer_id"]
        with self.assertRaisesRegex(ValueError, "unique canonical"):
            DesignIRV2.from_dict(broken)

    def test_typed_round_path_round_trips_and_rejects_broken_groups(self):
        fixture = self.fixture()
        fixture.tracks = [
            {"id": "path:segment:2", "net_name": "VCC", "layer": "F.Cu", "start": [5, 0], "end": [10, 2], "width": 1,
             "path_id": "path", "path_step_index": 1, "path_step_count": 2, "path_end_cap": "round", "path_join_style": "round"},
            {"id": "path:segment:1", "net_name": "VCC", "layer": "F.Cu", "start": [0, 0], "end": [5, 0], "width": 1,
             "path_id": "path", "path_step_index": 0, "path_step_count": 2, "path_end_cap": "round", "path_join_style": "round"},
        ]

        design = DesignIRV2.from_v1(fixture)
        restored = DesignIRV2.from_dict(design.to_dict())
        self.assertEqual(restored.to_dict(), design.to_dict())
        self.assertEqual(
            [(item["path_id"], item["path_step_index"], item["path_step_count"]) for item in restored.to_v1().tracks],
            [("path", 1, 2), ("path", 0, 2)],
        )

        broken = design.to_dict()
        broken["tracks"][0]["start_mm"] = [6, 0]
        with self.assertRaisesRegex(ValueError, "contiguous"):
            DesignIRV2.from_dict(broken)

        unsupported = design.to_dict()
        unsupported["tracks"][0]["path"]["end_cap"] = "square"
        with self.assertRaisesRegex(ValueError, "Only round-ended"):
            DesignIRV2.from_dict(unsupported)

    def test_legacy_sequence_drill_and_string_plating_are_normalized(self):
        fixture = self.fixture()
        fixture.pads[0].pop("drill_size")
        fixture.pads[0].pop("drill_shape")
        fixture.pads[0]["drill"] = [0.45, 0.9]
        fixture.pads[0]["plated"] = "false"

        design = DesignIRV2.from_v1(fixture)

        self.assertEqual(design.pads[0].drill_size_mm, (0.45, 0.9))
        self.assertEqual(design.pads[0].drill_shape, "oval")
        self.assertFalse(design.pads[0].plated)

    def test_manufacturing_drill_round_trips_with_typed_owner_identity(self):
        fixture = self.fixture()
        fixture.metadata["manufacturing_drills"] = [{
            "id": "H1", "name": "H1", "source_layer_id": "F.Cu", "at": [10, 0],
            "shape": "circle", "diameter_mm": 0.4, "size_mm": None, "rotation_deg": None,
            "plating_status": "via", "plated": True,
            "plus_tolerance_mm": 0.01, "minus_tolerance_mm": 0.0,
            "net_id": "VCC", "component_id": "", "geometry_ref": "VIA",
            "span_layer_ids": ["F.Cu", "B.Cu"], "span_provenance": "matched_owner",
            "owner_kind": "via", "owner_id": "v1", "owner_match": "exact_source",
        }]

        design = DesignIRV2.from_v1(fixture)
        self.assertEqual(len(design.drills), 1)
        self.assertEqual(design.drills[0].owner_id, design.vias[0].id)
        restored = DesignIRV2.from_dict(json.loads(json.dumps(design.to_dict())))
        self.assertEqual(
            json.loads(json.dumps(restored.to_dict())),
            json.loads(json.dumps(design.to_dict())),
        )
        projected = restored.to_v1().metadata["manufacturing_drills"][0]
        self.assertEqual((projected["owner_kind"], projected["owner_id"]), ("via", "v1"))

    def test_drill_references_must_resolve_to_typed_entities(self):
        fixture = self.fixture()
        fixture.metadata["manufacturing_drills"] = [{
            "id": "H1", "source_layer_id": "F.Cu", "at": [10, 0], "shape": "circle",
            "diameter_mm": 0.4, "net_id": "VCC", "component_id": "",
            "span_layer_ids": ["F.Cu", "B.Cu"], "span_provenance": "matched_owner",
            "owner_kind": "via", "owner_id": "v1", "owner_match": "exact_source",
        }]
        raw = DesignIRV2.from_v1(fixture).to_dict()

        invalid_references = {
            "owner_id": "unknown-via",
            "net_id": "unknown-net",
            "source_layer_id": "unknown-layer",
            "component_id": "unknown-component",
        }
        for field_name, invalid_id in invalid_references.items():
            broken = DesignIRV2.from_dict(raw).to_dict()
            broken["drills"][0][field_name] = invalid_id
            with self.subTest(field_name=field_name), self.assertRaisesRegex(ValueError, "references unknown"):
                DesignIRV2.from_dict(broken)

        broken = DesignIRV2.from_dict(raw).to_dict()
        broken["drills"][0]["span_layer_ids"] = ["unknown-layer"]
        with self.assertRaisesRegex(ValueError, "span_layer_ids references unknown layer"):
            DesignIRV2.from_dict(broken)

    def test_unresolved_manufacturing_drill_without_owner_is_valid(self):
        fixture = self.fixture()
        fixture.metadata["manufacturing_drills"] = [{
            "id": "M1", "at": [4, 5], "shape": "circle", "diameter_mm": 1.0,
            "plating_status": "unplated", "span_provenance": "unresolved",
            "owner_kind": "unresolved", "owner_id": "", "owner_match": "none",
        }]

        design = DesignIRV2.from_v1(fixture)
        self.assertEqual((design.drills[0].owner_kind, design.drills[0].owner_id), ("unresolved", ""))
        self.assertEqual(DesignIRV2.from_dict(design.to_dict()).to_dict(), design.to_dict())

    def test_retained_incomplete_padstack_groups_round_trip_but_never_become_copper(self):
        fixture = self.fixture()
        fixture.metadata["ipc2581_incomplete_pad_occurrence_groups"] = [{
            "id": "P-INCOMPLETE", "kind": "incomplete_padstack_occurrence_group",
            "status": "retained_unresolved", "reason": "missing_required_regular_layers",
            "padstack_ref": "PTH", "net_id": "VCC", "at_mm": [2, 3],
            "expected_regular_layer_ids": ["F.Cu", "B.Cu"], "observed_layer_ids": ["F.Cu"],
            "occurrence_count": 1, "occurrences": [{
                "source_index": 17, "source_id": "P-INCOMPLETE", "layer_id": "F.Cu",
                "pad_usage": "", "at_mm": [2, 3],
                "shape": {"kind": "circle", "size_mm": [1.4, 1.4], "source_primitive_id": "CIRCLE-14"},
                "pin": None,
            }],
        }]

        design = DesignIRV2.from_v1(fixture)
        payload = json.loads(json.dumps(design.to_dict()))
        restored = DesignIRV2.from_dict(payload)
        self.assertEqual(json.loads(json.dumps(restored.to_dict())), payload)
        self.assertEqual(len(restored.retained_padstack_occurrence_groups), 1)
        self.assertNotIn("ipc2581_incomplete_pad_occurrence_groups", restored.metadata)
        self.assertEqual(len(restored.pads), 1)
        self.assertEqual(restored.to_v1().metadata["ipc2581_incomplete_pad_occurrence_groups"][0]["occurrence_count"], 1)
        schema = json.loads((Path(__file__).parents[2] / "schemas" / "design-ir-v2.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(payload)

        broken = json.loads(json.dumps(payload))
        broken["retained_padstack_occurrence_groups"][0]["net_id"] = "unknown-net"
        with self.assertRaisesRegex(ValueError, "canonical net and layer"):
            DesignIRV2.from_dict(broken)

    def test_retained_nonregular_padstack_geometry_is_typed_and_round_trips_v1_v2_v1(self):
        fixture = self.fixture()
        fixture.metadata["ipc2581_retained_nonregular_padstack_geometry"] = self.retained_nonregular_padstack_geometry()

        design = DesignIRV2.from_v1(fixture)
        payload = json.loads(json.dumps(design.to_dict()))
        restored = DesignIRV2.from_dict(payload)

        self.assertEqual(len(restored.retained_nonregular_padstack_geometry.user_primitives), 1)
        self.assertEqual(restored.retained_nonregular_padstack_geometry.occurrences[0].layer_id, design.layers[0].id)
        self.assertEqual(restored.retained_nonregular_padstack_geometry.occurrences[0].resolved_net_id, design.nets[0].id)
        self.assertNotIn("ipc2581_retained_nonregular_padstack_geometry", restored.metadata)
        self.assertEqual(
            json.loads(json.dumps(restored.to_v1().metadata["ipc2581_retained_nonregular_padstack_geometry"])),
            self.retained_nonregular_padstack_geometry(),
        )

    def test_retained_nonregular_padstack_geometry_is_omitted_when_absent(self):
        payload = DesignIRV2.from_v1(self.fixture()).to_dict()
        self.assertNotIn("retained_nonregular_padstack_geometry", payload)

    def test_standard_contour_land_geometry_is_typed_source_only_and_lossless(self):
        fixture = self.fixture()
        fixture.components = [{"id": "U1", "reference": "U1", "at": [0, 0], "layer": "F.Cu"}]
        retained = self.retained_standard_contour_land_geometry()
        fixture.metadata["ipc2581_retained_standard_contour_land_geometry"] = retained

        design = DesignIRV2.from_v1(fixture)
        payload = json.loads(json.dumps(design.to_dict()))
        restored = DesignIRV2.from_dict(payload)
        geometry = restored.retained_standard_contour_land_geometry
        self.assertEqual((geometry.semantic_state, geometry.projection), ("unapplied_normative_semantics_missing", "forbidden"))
        self.assertEqual((geometry.padstacks[0].profile_xform.rotation_deg, geometry.padstacks[0].profile_xform.mirror), (90.0, False))
        self.assertEqual((geometry.occurrences[0].xform.rotation_deg, geometry.occurrences[0].xform.mirror), (360.0, True))
        self.assertEqual((len(restored.pads), len(restored.vias)), (1, 1))
        self.assertNotIn("ipc2581_retained_standard_contour_land_geometry", restored.metadata)
        self.assertEqual(
            json.loads(json.dumps(restored.to_v1().metadata["ipc2581_retained_standard_contour_land_geometry"])), retained,
        )
        schema = json.loads((Path(__file__).parents[2] / "schemas" / "design-ir-v2.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(payload)

    def test_standard_contour_land_geometry_rejects_projection_xform_and_reference_changes(self):
        fixture = self.fixture()
        fixture.components = [{"id": "U1", "reference": "U1", "at": [0, 0], "layer": "F.Cu"}]
        fixture.metadata["ipc2581_retained_standard_contour_land_geometry"] = self.retained_standard_contour_land_geometry()
        payload = DesignIRV2.from_v1(fixture).to_dict()
        for path, value in ((["projection"], "allowed"), (["occurrences", 0, "observed_layer_id"], "unknown-layer"), (["occurrences", 0, "xform", "rotation_deg"], float("nan"))):
            broken = json.loads(json.dumps(payload))
            target = broken["retained_standard_contour_land_geometry"]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ValueError):
                DesignIRV2.from_dict(broken)

    def test_source_only_negative_contours_round_trip_without_typed_copper(self):
        fixture = self.fixture()
        retained = {
            "contract": "spike/retained-negative-contours/v1",
            "records": [{
                "status": "retained_unresolved",
                "reason": "negative_layer_contour_semantics_pending",
                "source_id": "NEG-1", "source_index": 19,
                "layer_ref": "F.Cu", "resolved_layer_id": "F.Cu",
                "layer_polarity": "NEGATIVE", "raw_net_ref": "UNKNOWN",
                "resolved_net_id": "", "raw_fill_ref": "SOLID",
                "boundary_rings": [{
                    "role": "outer", "start_mm": [0, 0], "fill_style_id": "SOLID",
                    "segments": [
                        {"kind": "line", "end_mm": [1, 0]},
                        {"kind": "line", "end_mm": [1, 1]},
                        {"kind": "line", "end_mm": [0, 0]},
                    ],
                }],
            }],
        }
        fixture.metadata["ipc2581_retained_negative_contours"] = retained
        design = DesignIRV2.from_v1(fixture)
        restored = DesignIRV2.from_dict(json.loads(json.dumps(design.to_dict())))
        self.assertEqual(restored.to_v1().metadata["ipc2581_retained_negative_contours"], retained)
        self.assertEqual((len(restored.pads), len(restored.vias), len(restored.zones)), (1, 1, 0))

    def test_source_only_unnetted_padstack_groups_round_trip_without_connectivity(self):
        fixture = self.fixture()
        retained = {
            "contract": "spike/retained-unnetted-padstack-groups/v1",
            "groups": [{
                "id": "UNNETTED-1", "kind": "retained_unnetted_padstack_occurrence_group",
                "status": "retained_unresolved", "reason": "native_net_identity_absent",
                "padstack_ref": "MOUNT", "raw_net_ref": "", "at_mm": [4, 5],
                "expected_regular_layer_ids": ["F.Cu"], "occurrence_count": 1,
                "occurrences": [{"source_index": 12, "source_id": "pad:12", "layer_id": "F.Cu"}],
            }],
        }
        fixture.metadata["ipc2581_retained_unnetted_padstack_occurrence_groups"] = retained
        design = DesignIRV2.from_v1(fixture)
        restored = DesignIRV2.from_dict(json.loads(json.dumps(design.to_dict())))
        self.assertEqual(
            restored.to_v1().metadata["ipc2581_retained_unnetted_padstack_occurrence_groups"], retained,
        )
        self.assertEqual((len(restored.pads), len(restored.vias)), (1, 1))

    def test_retained_nonregular_padstack_geometry_rejects_unknown_references_and_malformed_transform(self):
        fixture = self.fixture()
        fixture.metadata["ipc2581_retained_nonregular_padstack_geometry"] = self.retained_nonregular_padstack_geometry()
        payload = DesignIRV2.from_v1(fixture).to_dict()

        for field_name, invalid_value in (("layer_id", "unknown-layer"), ("resolved_net_id", "unknown-net"),
                                          ("primitive_ref", "unknown-primitive")):
            broken = json.loads(json.dumps(payload))
            broken["retained_nonregular_padstack_geometry"]["occurrences"][0][field_name] = invalid_value
            with self.subTest(field_name=field_name), self.assertRaisesRegex(ValueError, "reference"):
                DesignIRV2.from_dict(broken)

        broken = json.loads(json.dumps(payload))
        broken["retained_nonregular_padstack_geometry"]["occurrences"][0]["xform"]["mirror"] = "false"
        with self.assertRaisesRegex(ValueError, "transform"):
            DesignIRV2.from_dict(broken)

    def test_exact_curved_zone_boundaries_round_trip_without_sampling(self):
        fixture = self.fixture()
        fixture.zones = [{
            "id": "Z1", "net_name": "VCC", "layer": "F.Cu",
            "boundary_rings": [
                {
                    "role": "outer", "start_mm": [0, 0],
                    "segments": [
                        {"kind": "line", "end_mm": [4, 0]},
                        {"kind": "line", "end_mm": [4, 4]},
                        {"kind": "line", "end_mm": [0, 4]},
                        {"kind": "line", "end_mm": [0, 0]},
                    ],
                },
                {
                    "role": "cutout", "start_mm": [3, 2],
                    "segments": [
                        {"kind": "arc", "end_mm": [1, 2], "center_mm": [2, 2], "clockwise": True},
                        {"kind": "arc", "end_mm": [3, 2], "center_mm": [2, 2], "clockwise": True},
                    ],
                },
            ],
            "fill_style_id": "SOLID_FILL", "fill_property": "FILL",
        }]

        design = DesignIRV2.from_v1(fixture)
        payload = design.to_dict()
        restored = DesignIRV2.from_dict(json.loads(json.dumps(payload)))
        self.assertEqual(json.loads(json.dumps(restored.to_dict())), json.loads(json.dumps(payload)))
        self.assertEqual(restored.zones[0].outlines_mm, [])
        self.assertEqual(restored.zones[0].boundary_rings[1].segments[0].center_mm, (2.0, 2.0))
        self.assertEqual(restored.to_v1().zones[0]["boundary_rings"], fixture.zones[0]["boundary_rings"])

        schema_path = Path(__file__).parents[2] / "schemas" / "design-ir-v2.schema.json"
        Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(
            json.loads(json.dumps(payload))
        )
        broken = json.loads(json.dumps(payload))
        broken["zones"][0]["boundary_rings"][0]["segments"][-1]["end_mm"] = [0, 1]
        with self.assertRaisesRegex(ValueError, "close exactly"):
            DesignIRV2.from_dict(broken)

    def test_assembly_admits_thirty_boards_and_rejects_thirty_one(self):
        boards = [BoardInstance(id=str(index), design_id=str(index), frame=CoordinateFrame(frame_id=f"frame-{index}")) for index in range(30)]
        assembly = AssemblyIRV1(assembly_id="assembly", name="at-limit", boards=boards)
        self.assertEqual(len(assembly.boards), 30)
        over_limit = [BoardInstance(id=str(index), design_id=str(index), frame=CoordinateFrame(frame_id=f"frame-{index}")) for index in range(31)]
        with self.assertRaisesRegex(ValueError, "at most 30"):
            AssemblyIRV1(assembly_id="assembly", name="too-large", boards=over_limit)

    def test_coordinate_frame_rejects_non_finite_transform_values(self):
        for invalid in (math.nan, math.inf, -math.inf):
            transform = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
            transform[3] = invalid
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "finite"):
                CoordinateFrame(frame_id="invalid", transform=tuple(transform))

    def test_fully_populated_assembly_round_trips_from_dict(self):
        raw = {
            "contract": "spike/assembly-ir/v1",
            "assembly_id": "assembly-two-board",
            "name": "Two board fixture",
            "frame": {"frame_id": "assembly"},
            "boards": [
                {
                    "id": "board-a",
                    "source_id": "cad-a",
                    "name": "Controller",
                    "design_id": "design-a",
                    "frame": {
                        "frame_id": "frame-board-a",
                        "parent_frame_id": "assembly",
                        "transform": [1, 0, 0, 10, 0, 1, 0, 20, 0, 0, 1, 0, 0, 0, 0, 1],
                    },
                },
                {
                    "id": "board-b",
                    "source_id": "cad-b",
                    "name": "Load",
                    "design_id": "design-b",
                    "frame": {
                        "frame_id": "frame-board-b",
                        "parent_frame_id": "assembly",
                        "transform": [0, -1, 0, 80, 1, 0, 0, 0, 0, 0, 1, 12, 0, 0, 0, 1],
                    },
                },
            ],
            "harnesses": [{
                "id": "harness-main",
                "source_id": "harness-native-1",
                "name": "Power harness",
                "endpoint_a": "board-a:J1",
                "endpoint_b": "board-b:J2",
                "length_mm": 250.0,
                "conductor_material_id": "copper",
                "gauge_awg": 18,
                "pin_map": {"1": "1", "2": "2"},
            }],
            "connector_mappings": [{
                "id": "connector-map-main",
                "source_id": "mapping-native-1",
                "name": "J1 to J2",
                "kind": "connector-pin-map",
                "data": {"endpoint_a": "board-a:J1", "endpoint_b": "board-b:J2", "pins": {"1": "1"}},
            }],
            "rigid_flex_links": [{
                "id": "flex-link-main",
                "name": "Board flex",
                "kind": "rigid-flex-link",
                "data": {"board_a_id": "board-a", "board_b_id": "board-b", "bend_radius_mm": 3.0},
            }],
            "parts": [{
                "id": "enclosure-main",
                "source_id": "step-body-1",
                "name": "Enclosure",
                "part_type": "enclosure",
                "model_id": "model-enclosure",
                "material_id": "aluminium-6061",
                "frame": {
                    "frame_id": "frame-enclosure",
                    "parent_frame_id": "assembly",
                    "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, -5, 0, 0, 0, 1],
                },
                "future_part_field": {"preserve": True},
            }],
            "materials": [{
                "id": "aluminium-6061", "name": "Aluminium 6061",
                "material_class": "metal", "thermal_conductivity_w_per_mk": 167.0,
            }],
            "thermal_contacts": [{
                "id": "case-to-board", "name": "Case interface",
                "endpoint_a": "enclosure-main:face:base", "endpoint_b": "board-a:region:mount",
                "contact_type": "thermal_pad", "material_id": "gap-pad",
                "contact_area_mm2": 64.0, "thermal_resistance_k_per_w": 0.35,
            }],
            "electrical_bonds": [{
                "id": "chassis-bond", "name": "Chassis bond",
                "endpoint_a": "enclosure-main:stud:1", "endpoint_b": "board-a:net:chassis",
                "bond_type": "braid", "electrical_material_id": "copper",
                "thermal_material_id": "copper", "contact_area_mm2": 8.0,
                "thickness_mm": 0.5, "electrical_resistance_ohm": 0.001,
            }],
            "extensions": {"vendor.fixture": {"revision": 7}},
            "metadata": {"purpose": "round-trip acceptance"},
            "future_top_level": ["must", "survive"],
        }

        assembly = AssemblyIRV1.from_dict(raw)
        restored = AssemblyIRV1.from_dict(assembly.to_dict())

        self.assertEqual(restored.to_dict(), assembly.to_dict())
        self.assertIsInstance(restored.boards[0].frame.transform, tuple)
        self.assertEqual(restored.harnesses[0].pin_map, {"1": "1", "2": "2"})
        self.assertEqual(restored.thermal_contacts[0].contact_area_mm2, 64.0)
        self.assertEqual(restored.electrical_bonds[0].electrical_resistance_ohm, 0.001)
        self.assertEqual(
            restored.parts[0].extensions["spike.assembly-ir.unknown-fields"]["future_part_field"],
            {"preserve": True},
        )
        self.assertEqual(
            restored.extensions["spike.assembly-ir.unknown-fields"]["future_top_level"],
            ["must", "survive"],
        )

    def test_assembly_rejects_invalid_references_and_limits(self):
        with self.assertRaisesRegex(ValueError, "reference a design_id"):
            AssemblyIRV1(
                assembly_id="assembly",
                name="missing design",
                boards=[BoardInstance(id="board-a", design_id="")],
            )
        with self.assertRaisesRegex(ValueError, "pin mappings"):
            AssemblyIRV1.from_dict({
                "assembly_id": "assembly",
                "name": "bad harness",
                "boards": [],
                "harnesses": [{
                    "id": "harness",
                    "endpoint_a": "board-a:J1",
                    "endpoint_b": "board-b:J2",
                    "length_mm": 1,
                    "pin_map": {"": "1"},
                }],
            })
        with self.assertRaisesRegex(ValueError, "thermal contact area"):
            AssemblyIRV1.from_dict({
                "assembly_id": "assembly", "name": "bad contact", "boards": [],
                "thermal_contacts": [{
                    "id": "contact", "endpoint_a": "a", "endpoint_b": "b",
                    "contact_area_mm2": 0,
                }],
            })
        with self.assertRaisesRegex(ValueError, "material thermal conductivity"):
            AssemblyIRV1.from_dict({
                "assembly_id": "assembly", "name": "bad material", "boards": [],
                "materials": [{"id": "bad", "thermal_conductivity_w_per_mk": -1}],
            })
        with self.assertRaisesRegex(ValueError, "unknown parent frame"):
            AssemblyIRV1.from_dict({
                "assembly_id": "assembly", "name": "orphan", "boards": [],
                "parts": [{
                    "id": "part", "model_id": "model", "frame": {
                        "frame_id": "part-frame", "parent_frame_id": "missing-frame",
                    },
                }],
            })
        with self.assertRaisesRegex(ValueError, "contains a cycle"):
            AssemblyIRV1.from_dict({
                "assembly_id": "assembly", "name": "cycle", "boards": [],
                "parts": [
                    {"id": "part-a", "model_id": "model-a", "frame": {"frame_id": "frame-a", "parent_frame_id": "frame-b"}},
                    {"id": "part-b", "model_id": "model-b", "frame": {"frame_id": "frame-b", "parent_frame_id": "frame-a"}},
                ],
            })


if __name__ == "__main__":
    unittest.main()
