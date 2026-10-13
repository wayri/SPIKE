# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from python.spike_core.contracts import SpiDeR, ValidationIssue
from python.spike_core.hybrid_mesh import HybridMesh


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/profile_retained_board_mesher.py"
SPEC = importlib.util.spec_from_file_location("profile_retained_board_mesher", SCRIPT)
assert SPEC and SPEC.loader
PROFILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROFILE)


class RetainedBoardProfilerTests(unittest.TestCase):
    def test_sidecars_are_derived_beside_explicit_result(self) -> None:
        output = ROOT / "output/example/profile.json"
        marker, stacks, zones = PROFILE._evidence_sidecars(output)
        self.assertEqual(marker, output.with_name("profile.phase.json"))
        self.assertEqual(stacks, output.with_name("profile.mesh-wall-stacks.log"))
        self.assertEqual(zones, output.with_name("profile.selected-zone-polygons.json"))
        self.assertEqual(
            PROFILE._memory_heartbeat_path(output),
            output.with_name("profile.mesh-memory-heartbeat.json"),
        )

    def test_new_evidence_refuses_replacement(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "evidence.json"
            PROFILE._write_new_text(path, "first")
            with self.assertRaises(FileExistsError):
                PROFILE._write_new_text(path, "second")
            self.assertEqual(path.read_text(encoding="utf-8"), "first")

    def test_output_must_resolve_under_repository(self) -> None:
        with self.assertRaisesRegex(ValueError, "under the repository root"):
            PROFILE._require_repo_output(ROOT.parent / "outside-profile.json")

    def test_worker_retains_full_warnings_and_selected_zone_coordinates(self) -> None:
        design = SpiDeR(
            zones=[{
                "id": "zone-missing:F.Cu:1",
                "net_name": "+1V0",
                "layer": "F.Cu",
                "points": [[0.0, 0.0], [2.0, 0.0], [0.0, 2.0]],
            }],
        )
        warning = ValidationIssue(
            "SPIKE-BE-MESH-W-0002",
            "warning",
            "zone-missing:F.Cu:1 has no usable simple filled copper polygon.",
            path="design.zones[zone-missing:F.Cu:1]",
            suggestion="Repair the imported zone outline.",
            status="approximate",
        )
        connection_report = {
            "contract": "spike/zone-pad-connection-evidence/v1",
            "source": {"design_id": "profile-fixture"},
            "records": [
                {"record_id": "record-2", "observation": "no_source_filled_copper_contact"},
                {"record_id": "record-1", "observation": "source_filled_copper_contact"},
            ],
            "accounting": {
                "status": "complete", "candidate_record_count": 2,
            },
            "resources": {"actual_records": 2, "actual_work_steps": 7},
            "qualification": {"physics_ready": False, "solver_ready": False},
        }
        mesh = HybridMesh(
            issues=[warning], zone_pad_connection_evidence=connection_report,
        )
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            temporary = Path(directory)
            board = temporary / "Marble.kicad_pcb"
            board.write_bytes(b"bounded fixture")
            marker = temporary / "profile.phase.json"
            stacks = temporary / "profile.mesh-wall-stacks.log"
            zones = temporary / "profile.selected-zone-polygons.json"
            payload = {
                "board": str(board),
                "expected_board_sha256": PROFILE._sha_file(board),
                "source_board_display": "retained/Marble.kicad_pcb",
                "net": "+1V0",
                "target_size_mm": 2.0,
                "zone_cell_mm": 2.0,
                "max_zone_cells": 50_000,
                "max_pad_cells": 10_000,
                "max_conductors": 300_000,
                "solver_memory_limit_gb": 2.0,
                "phase_marker": str(marker),
                "stack_log": str(stacks),
                "selected_zone_polygons": str(zones),
                "memory_heartbeat": str(temporary / "profile.mesh-memory-heartbeat.json"),
                "faulthandler_enabled": False,
            }
            with (
                patch(
                    "python.spike_core.kicad_importer.import_kicad_design",
                    return_value=design,
                ),
                patch(
                    "python.spike_core.hybrid_mesh.build_hybrid_mesh",
                    return_value=mesh,
                ),
            ):
                result = PROFILE._worker(payload)

            self.assertEqual(result["mesh"]["issues"], [warning.__dict__])
            expected_sources = {
                "python/spike_core/hybrid_mesh.py",
                "python/spike_core/filled_copper_path.py",
                "python/spike_core/boundary_spatial_index.py",
                "python/spike_core/hybrid_owned_copper.py",
                "python/spike_core/planar_polygon_topology.py",
                "python/spike_core/source_filled_boundary.py",
                "python/spike_core/kicad_importer.py",
                "python/spike_core/zone_pad_connection_evidence.py",
                "python/core/board_parser.py",
            }
            self.assertEqual(
                set(result["runtime_sources_before_sha256"]), expected_sources,
            )
            self.assertEqual(
                result["runtime_sources_before_sha256"],
                result["runtime_sources_after_sha256"],
            )
            self.assertEqual(
                result["worker_python_runtime"]["executable"],
                str(Path(PROFILE.sys.executable).resolve(strict=False)),
            )
            self.assertEqual(
                result["worker_python_runtime"]["implementation"],
                PROFILE.sys.implementation.name,
            )
            self.assertEqual(
                result["worker_python_runtime"]["version_info"],
                list(PROFILE.sys.version_info[:5]),
            )
            self.assertEqual(
                result["selection"]["missing_requested_source_issue_matches"]
                ["zone"]["zone-missing:F.Cu:1"],
                [warning.__dict__],
            )
            connection_summary = result["mesh"]["zone_pad_connection_evidence"]
            self.assertNotIn("records", connection_summary)
            self.assertEqual(connection_summary["record_count"], 2)
            self.assertEqual(
                connection_summary["records_sha256"],
                PROFILE._sha_bytes(PROFILE._canonical(connection_report["records"])),
            )
            self.assertEqual(
                connection_summary["full_report_sha256"],
                PROFILE._sha_bytes(PROFILE._canonical(connection_report)),
            )
            self.assertEqual(connection_summary["accounting"]["status"], "complete")
            self.assertFalse(connection_summary["qualification"]["physics_ready"])
            saved = json.loads(zones.read_text(encoding="utf-8"))
            self.assertEqual(saved["fixture"]["source_sha256"], PROFILE._sha_file(board))
            self.assertEqual(saved["selection"]["zone_count"], 1)
            self.assertEqual(
                saved["selection"]["zones"][0]
                ["importer_normalized_filled_polygon_points_mm"],
                [[0.0, 0.0], [2.0, 0.0], [0.0, 2.0]],
            )
            self.assertTrue(stacks.is_file())
            heartbeat = json.loads(
                (temporary / "profile.mesh-memory-heartbeat.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(heartbeat["active_phase"], "mesh_completed")
            self.assertGreaterEqual(heartbeat["sample_count"], 2)
            self.assertFalse(result["profile"]["faulthandler_enabled"])
            self.assertEqual(
                json.loads(marker.read_text(encoding="utf-8"))["completed_phase"],
                "mesh",
            )


if __name__ == "__main__":
    unittest.main()
