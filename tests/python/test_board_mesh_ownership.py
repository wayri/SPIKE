from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

from python.spike_core.board_mesh_ownership import (
    ERROR_CODE,
    BoardMeshOwnershipError,
    build_board_mesh_ownership_overlay,
    validate_board_mesh_ownership_overlay,
)
from python.spike_core.contracts import AnalysisSpec
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.meshing import VOLUME_3D, build_mesh
from tests.python.test_mesh_ownership import _volume_fixture


class BoardMeshOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.schema = json.loads((
            root / "schemas/pcb-board-mesh-ownership-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)

    @staticmethod
    def _fixture() -> tuple[object, dict]:
        design, cells = _volume_fixture()
        return design, {
            "contract": "spike/mesh/v3",
            "cells": cells,
            "truncated": False,
        }

    def test_all_supplied_copper_can_be_owned_without_board_or_physics_promotion(self) -> None:
        design, mesh = self._fixture()
        report = build_board_mesh_ownership_overlay(mesh, source_geometry=design)

        Draft202012Validator(self.schema).validate(report)
        self.assertEqual(report, validate_board_mesh_ownership_overlay(
            report, mesh=mesh, source_geometry=design,
        ))
        self.assertEqual(ERROR_CODE, "SPIKE-BE-MESH-E-0017")
        self.assertEqual(report["source"]["mesh_contract"], "spike/mesh/v3")
        self.assertEqual(report["source"]["geometry_contract"], "spike/v1")
        self.assertEqual(report["source"]["scope"], {
            "all_nets": True,
            "requested_nets": [],
        })
        self.assertEqual({record["status"] for record in report["source_records"]}, {"owned"})
        self.assertEqual({record["reason_code"] for record in report["source_records"]}, {
            "owned_by_exact_volume_containment",
        })
        self.assertEqual(
            report["accounting"]["owned_mesh_cell_count"], len(mesh["cells"]),
        )
        self.assertEqual(report["accounting"]["supplied_geometry_audit"]["status"], "passed")
        self.assertEqual(
            report["accounting"]["supplied_geometry_audit"]["checked_volumes"],
            len(mesh["cells"]),
        )
        self.assertEqual(report["resources"]["actual_mesh_cells"], len(mesh["cells"]))
        self.assertTrue(report["qualification"]["all_supplied_geometry_owned"])
        for field in (
            "complete_board_copper_coverage",
            "native_geometric_overlay_verified",
            "field_convergence_performed",
            "physics_ready",
            "solver_ready",
        ):
            with self.subTest(field=field):
                self.assertFalse(report["qualification"][field])

    def test_cancellation_and_ineligible_or_out_of_owner_meshes_fail_closed(self) -> None:
        design, mesh = self._fixture()
        with self.assertRaisesRegex(BoardMeshOwnershipError, "cancelled"):
            build_board_mesh_ownership_overlay(
                mesh, source_geometry=design, cancel_check=lambda: True,
            )

        truncated = copy.deepcopy(mesh)
        truncated["truncated"] = True
        with self.assertRaises(BoardMeshOwnershipError):
            build_board_mesh_ownership_overlay(truncated, source_geometry=design)

        escaped = copy.deepcopy(mesh)
        track = next(cell for cell in escaped["cells"]
                     if cell["source_kind"] == "track")
        track["vertices_mm"][0][1] += 10.0
        with self.assertRaises(BoardMeshOwnershipError):
            build_board_mesh_ownership_overlay(escaped, source_geometry=design)

    def test_absent_sources_are_explicitly_unsupported_or_intentionally_omitted(self) -> None:
        design, mesh = self._fixture()
        design.tracks.append({
            "id": "zero-track", "start": [1.0, 1.0], "end": [1.0, 1.0],
            "width": 0.2, "layer": "F.Cu", "net_name": "VCC",
        })
        design.pads.append({
            "id": "mounting-hole", "at": [20.0, 0.0], "size": [1.0, 1.0],
            "shape": "circle", "drill_size": [1.0, 1.0], "drill_shape": "circle",
            "plated": False, "layers": ["F.Cu", "B.Cu"], "net_name": "",
        })

        report = build_board_mesh_ownership_overlay(mesh, source_geometry=design)
        records = {item["source_id"]: item for item in report["source_records"]}
        self.assertEqual(records["zero-track"]["status"], "unsupported")
        self.assertEqual(records["zero-track"]["reason_code"], "unsupported_geometry")
        self.assertEqual(records["mounting-hole"]["status"], "intentionally_omitted")
        self.assertEqual(
            records["mounting-hole"]["reason_code"], "non_electrical_unplated_hole",
        )

    def test_schema_and_regeneration_reject_tampering_and_readiness_promotion(self) -> None:
        design, mesh = self._fixture()
        report = build_board_mesh_ownership_overlay(mesh, source_geometry=design)
        validator = Draft202012Validator(self.schema)

        invalid_scope = copy.deepcopy(report)
        invalid_scope["source"]["scope"]["requested_nets"] = ["VCC"]
        with self.assertRaises(ValidationError):
            validator.validate(invalid_scope)

        invalid_reason = copy.deepcopy(report)
        invalid_reason["source_records"][0]["reason_code"] = "unsupported_geometry"
        with self.assertRaises(ValidationError):
            validator.validate(invalid_reason)

        digest_tamper = copy.deepcopy(report)
        digest_tamper["source"]["mesh_sha256"] = "0" * 64
        validator.validate(digest_tamper)
        with self.assertRaises(BoardMeshOwnershipError):
            validate_board_mesh_ownership_overlay(
                digest_tamper, mesh=mesh, source_geometry=design,
            )

        for field in (
            "complete_board_copper_coverage",
            "native_geometric_overlay_verified",
            "field_convergence_performed",
            "physics_ready",
            "solver_ready",
        ):
            promoted = copy.deepcopy(report)
            promoted["qualification"][field] = True
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validator.validate(promoted)
            with self.assertRaises(BoardMeshOwnershipError):
                validate_board_mesh_ownership_overlay(
                    promoted, mesh=mesh, source_geometry=design,
                )

    def test_bundled_boards_have_resource_admitted_selected_net_accounting(self) -> None:
        root = Path(__file__).resolve().parents[2] / "app" / "public" / "demo"
        cases = (
            ("MODULAR-BUS-NIB.kicad_pcb", "/12Vout"),
            ("ebrake1.kicad_pcb", "3Vin"),
        )
        for filename, net in cases:
            with self.subTest(board=filename, net=net):
                design = import_kicad_design(str(root / filename))
                mesh = build_mesh(design, AnalysisSpec(
                    mode="dc", net_names=[net],
                    mesh={
                        "dimension": VOLUME_3D, "target_size_mm": 0.75,
                        "max_preview_cells": 50_000, "memory_budget_mb": 256,
                    },
                ))
                self.assertFalse(mesh["truncated"])
                report = build_board_mesh_ownership_overlay(
                    mesh, source_geometry=design,
                )
                Draft202012Validator(self.schema).validate(report)
                self.assertEqual(report["source"]["scope"], {
                    "all_nets": False, "requested_nets": [net],
                })
                selected_sources = sum(
                    str(item.get("net_name") or item.get("net") or "") == net
                    for records in (design.tracks, design.zones, design.pads, design.vias)
                    for item in records
                )
                self.assertEqual(
                    report["accounting"]["owned_source_count"], selected_sources,
                )
                self.assertEqual(report["accounting"]["unsupported_source_count"], 0)
                self.assertEqual(
                    report["accounting"]["owned_mesh_cell_count"], len(mesh["cells"]),
                )
                self.assertLessEqual(
                    report["resources"]["actual_serialized_bytes"],
                    report["resources"]["maximum_serialized_bytes"],
                )


if __name__ == "__main__":
    unittest.main()
