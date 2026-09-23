"""Focused conformance tests for the DC FEM conductor-volume exchange contract."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.solver_geometry import build_dc_fem_geometry


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "dc-fem-conductor-volumes-v1.schema.json"


def dc_fixture() -> tuple[DesignIR, AnalysisSpec]:
    design = DesignIR(
        design_id="dc-fem-schema-fixture",
        name="DC FEM schema copper bar",
        layers=[{"name": "F.Cu", "type": "copper"}],
        nets=[{"name": "VCC"}],
        tracks=[{
            "id": "bar", "start": [0.0, 0.0], "end": [20.0, 0.0],
            "width": 2.0, "layer": "F.Cu", "net_name": "VCC",
        }],
        stackup=[{
            "name": "F.Cu", "type": "copper", "thickness": 0.035,
            "conductivity_s_m": 5.8e7,
        }],
    )
    spec = AnalysisSpec(
        analysis_id="dc-fem-schema", mode="dc", net_names=["VCC"],
        sources=[{
            "id": "source", "position_mm": [0.0, 0.0], "layer": "F.Cu",
            "net": "VCC", "voltage_v": 1.0,
        }],
        loads=[{
            "id": "load", "position_mm": [20.0, 0.0], "layer": "F.Cu",
            "net": "VCC", "current_a": 1.0,
        }],
        mesh={"target_size_mm": 1.0, "max_preview_cells": 10000, "memory_budget_mb": 64},
    )
    return design, spec


class DcFemGeometrySchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def payload(self) -> dict:
        design, spec = dc_fixture()
        return build_dc_fem_geometry(design, spec)

    def assert_invalid(self, payload: dict, fragment: str) -> None:
        errors = sorted(self.validator.iter_errors(payload), key=lambda error: list(error.path))
        self.assertTrue(errors, "Expected schema validation to fail")
        self.assertTrue(
            any(fragment in error.message for error in errors),
            "\n".join(error.message for error in errors),
        )

    def test_schema_identity_and_public_boundary_are_strict(self) -> None:
        self.assertEqual(self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(
            self.schema["$id"],
            "https://spike.local/schemas/dc-fem-conductor-volumes-v1.schema.json",
        )
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(
            self.schema["properties"]["contract"]["const"],
            "spike/dc-fem-conductor-volumes/v1",
        )

    def test_actual_dc_geometry_payload_conforms(self) -> None:
        payload = self.payload()

        self.assertEqual(list(self.validator.iter_errors(payload)), [])
        self.assertEqual(payload["counts"]["volumes"], len(payload["volumes"]))
        self.assertEqual(payload["counts"]["material_regions"], len(payload["material_regions"]))
        self.assertEqual(payload["ownership_audit"]["status"], "passed")
        self.assertEqual(payload["ownership_audit"]["checked_volumes"], len(payload["volumes"]))
        self.assertEqual(
            payload["counts"]["terminal_boundary_faces"],
            len(payload["terminal_boundary_faces"]),
        )

    def test_schema_rejects_graph_like_cells_and_invalid_terminal_faces(self) -> None:
        graph_like = copy.deepcopy(self.payload())
        graph_like["volumes"][0]["kind"] = "surface"
        graph_like["volumes"][0]["vertices_mm"] = graph_like["volumes"][0]["vertices_mm"][:4]
        self.assert_invalid(graph_like, "'volume' was expected")

        missing_load = copy.deepcopy(self.payload())
        missing_load["terminal_boundary_faces"] = [
            face for face in missing_load["terminal_boundary_faces"] if face["role"] != "load"
        ]
        missing_load["counts"]["terminal_boundary_faces"] = 1
        self.assert_invalid(missing_load, "too short")

    def test_schema_rejects_wrong_source_contract_and_untracked_root_properties(self) -> None:
        wrong_contract = copy.deepcopy(self.payload())
        wrong_contract["source_mesh_contract"] = "spike/hybrid-conductor/v1"
        self.assert_invalid(wrong_contract, "'spike/mesh/v3' was expected")

        unknown_root = copy.deepcopy(self.payload())
        unknown_root["branches"] = []
        self.assert_invalid(unknown_root, "Additional properties are not allowed")

        missing_audit = copy.deepcopy(self.payload())
        del missing_audit["ownership_audit"]
        self.assert_invalid(missing_audit, "'ownership_audit' is a required property")


if __name__ == "__main__":
    unittest.main()
