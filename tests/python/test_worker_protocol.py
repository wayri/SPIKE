from __future__ import annotations

import json
import base64
import hashlib
import importlib.util
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import AssemblyIRV1, DesignIRV2
from python.spike_core.geometry_arrow import validate_geometry_arrow
from python.spike_core.project_package import read_spike_package, write_spike_package


ROOT = Path(__file__).resolve().parents[2]


class WorkerProtocolTests(unittest.TestCase):
    def run_worker(self, requests: list[str]) -> list[dict]:
        process = subprocess.run(
            [sys.executable, "-m", "python.spike_core.service"],
            cwd=ROOT,
            input="\n".join(requests) + "\n",
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        lines = [line for line in process.stdout.splitlines() if line.strip()]
        self.assertEqual(len(lines), len(requests), process.stdout)
        return [json.loads(line) for line in lines]

    def test_health_round_trip_preserves_operation_id_and_metadata(self):
        response = self.run_worker([
            json.dumps({"id": "health-1", "method": "health", "params": {}})
        ])[0]

        self.assertTrue(response["ok"])
        self.assertEqual(response["id"], "health-1")
        self.assertEqual(response["result"]["status"], "ready")
        self.assertEqual(response["meta"]["method"], "health")
        self.assertGreaterEqual(response["meta"]["duration_ms"], 0)

    def test_malformed_request_does_not_corrupt_the_following_response(self):
        malformed, health = self.run_worker([
            "{not-json}",
            json.dumps({"id": "health-after-error", "method": "health", "params": {}}),
        ])

        self.assertFalse(malformed["ok"])
        self.assertEqual(malformed["error_code"], "SPIKE-BE-IPC-E-0001")
        self.assertEqual(malformed["error_detail"]["contract"], "spike/error/v1")
        self.assertEqual(malformed["error_detail"]["classification"], "E")
        self.assertTrue(health["ok"])
        self.assertEqual(health["id"], "health-after-error")

    def test_unknown_method_is_a_structured_failure(self):
        response = self.run_worker([
            json.dumps({"id": "unknown-1", "method": "not-a-method", "params": {}})
        ])[0]

        self.assertFalse(response["ok"])
        self.assertEqual(response["id"], "unknown-1")
        self.assertEqual(response["error_code"], "SPIKE-BE-IPC-E-0002")
        self.assertEqual(response["error_detail"]["domain"], "IPC")
        self.assertIn("Unknown worker method", response["error"])

    def test_acceleration_and_external_engine_catalogs_are_exposed(self):
        accelerators, engines, manager = self.run_worker([
            json.dumps({"id": "accelerators-1", "method": "list_accelerators", "params": {}}),
            json.dumps({"id": "engines-1", "method": "list_external_engines", "params": {}}),
            json.dumps({"id": "manager-1", "method": "solver_manager", "params": {}}),
        ])

        self.assertTrue(accelerators["ok"])
        self.assertEqual(accelerators["result"]["contract"], "spike/acceleration-catalog/v1")
        accelerator_ids = {item["id"] for item in accelerators["result"]["backends"]}
        self.assertIn("scipy-superlu", accelerator_ids)
        self.assertIn("petsc-mumps", accelerator_ids)

        self.assertTrue(engines["ok"])
        self.assertEqual(engines["result"]["contract"], "spike/external-engine-catalog/v1")
        engine_ids = {item["id"] for item in engines["result"]["engines"]}
        self.assertIn("external.openems", engine_ids)
        self.assertIn("external.sparselizard", engine_ids)

        self.assertTrue(manager["ok"])
        self.assertEqual(manager["result"]["contract"], "spike/solver-manager/v1")
        workloads = {item["id"]: item for item in manager["result"]["workloads"]}
        self.assertEqual(workloads["dc_pi"]["recommended"]["id"], "spike.routed_dc")

    def test_native_capability_ledger_is_exposed_without_promoting_planned_solvers(self):
        response = self.run_worker([
            json.dumps({"id": "ledger-1", "method": "capability_ledger", "params": {}})
        ])[0]

        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["contract"], "spike/native-capability-ledger/v1")
        workflows = {item["id"]: item for item in response["result"]["workflows"]}
        self.assertEqual(workflows["pi.dc_conduction"]["validation_state"], "approximate")
        self.assertEqual(workflows["thermal.conjugate_heat_transfer"]["release_state"], "planned")

    def test_worker_migrates_saves_and_reopens_v3_project_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy_path = root / "legacy.spike.json"
            package_path = root / "migrated.spike"
            legacy = {
                "format": "spike-project-package/v2",
                "project": {"name": "worker-fixture.spike"},
                "design": {
                    "source_file": "fixture.kicad_pcb",
                    "source_board": "(kicad_pcb (version 20240108) (generator pcbnew) (layers (0 \"F.Cu\" signal)) (net 0 \"\"))",
                    "layers": [],
                    "nets": [],
                },
                "analysis": {"mode": "DC IR Drop", "pi_setup": {}},
                "workspace": {
                    "contract": "spike/workspace-state/v1",
                    "viewMode": "2D",
                    "docks": {
                        "left": {"visible": True, "pinned": True, "size": 220},
                        "right": {"visible": True, "pinned": True, "size": 360},
                        "bottom": {"visible": True, "pinned": True, "size": 180, "activeTab": "issues"},
                    },
                    "viewports": {
                        "twoD": {
                            "contract": "spike/layout-view/v1",
                            "x": 1.0,
                            "y": 2.0,
                            "width": 30.0,
                            "height": 40.0,
                        },
                    },
                },
            }
            legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
            migrated = self.run_worker([json.dumps({
                "id": "legacy-open-1",
                "method": "read_project_package",
                "params": {"path": str(legacy_path)},
            })])[0]
            self.assertTrue(migrated["ok"])
            self.assertTrue(migrated["result"]["migrated"])

            saved = self.run_worker([json.dumps({
                "id": "package-save-1",
                "method": "write_project_package",
                "params": {"path": str(package_path), "snapshot": migrated["result"]["project"]},
            })])[0]
            self.assertTrue(saved["ok"])
            self.assertTrue(package_path.is_file())

            reopened = self.run_worker([json.dumps({
                "id": "package-open-1",
                "method": "read_project_package",
                "params": {"path": str(package_path)},
            })])[0]
            self.assertTrue(reopened["ok"])
            self.assertFalse(reopened["result"]["migrated"])
            self.assertEqual(reopened["result"]["canonical"]["design_ir"]["contract"], "spike/design-ir/v2")
            self.assertEqual(saved["result"]["design_id"], reopened["result"]["canonical"]["design_ir"]["design_id"])
            self.assertEqual(reopened["result"]["project"]["workspace"]["viewports"]["twoD"]["width"], 30.0)

    def test_worker_rejects_a_missing_lossless_save_as_base_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "imported-board.spike"
            missing_base = root / "previous-project.spike"
            snapshot = {
                "format": "spike-project-package/v2",
                "project": {"name": "imported-board.spike"},
                "design": {
                    "source_file": "arts-1_irca.kicad_pcb",
                    "source_board": "(kicad_pcb (version 20240108) (generator pcbnew) (layers (0 \"F.Cu\" signal)) (net 0 \"\"))",
                    "stackup": [],
                },
            }
            response = self.run_worker([json.dumps({
                "id": "missing-lossless-base",
                "method": "write_project_package",
                "params": {
                    "path": str(destination),
                    "snapshot": snapshot,
                    "base_package_path": str(missing_base),
                },
            })])[0]

            self.assertFalse(response["ok"])
            self.assertEqual(response["error_detail"]["domain"], "PACKAGE")
            self.assertIn("source SPIKE package selected for lossless Save As does not exist", response["error"])
            self.assertFalse(destination.exists(), "a missing lossless base must not be silently discarded")

    def test_worker_save_preserves_embedded_source_bytes_for_digest(self):
        source_variants = {
            "lf": "(kicad_pcb\n (version 20240108)\n (generator pcbnew)\n (layers (0 \"F.Cu\" signal))\n (net 0 \"\")\n)",
            "crlf": "(kicad_pcb\r\n (version 20240108)\r\n (generator pcbnew)\r\n (layers (0 \"F.Cu\" signal))\r\n (net 0 \"\")\r\n)",
            "unicode": "(kicad_pcb\n (version 20240108)\n (generator pcbnew)\n (layers (0 \"F.Cu\" signal))\n (net 0 \"\")\n (net 1 \"VOUT-µ\")\n)",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for label, source_text in source_variants.items():
                with self.subTest(line_endings_or_encoding=label):
                    destination = root / f"{label}.spike"
                    response = self.run_worker([json.dumps({
                        "id": f"source-bytes-{label}",
                        "method": "write_project_package",
                        "params": {
                            "path": str(destination),
                            "snapshot": {
                                "format": "spike-project-package/v2",
                                "project": {"name": destination.name},
                                "design": {
                                    "source_file": f"{label}.kicad_pcb",
                                    "source_board": source_text,
                                    "stackup": [],
                                },
                            },
                        },
                    })])[0]

                    self.assertTrue(response["ok"], response)
                    package = read_spike_package(destination, include_members=True)
                    source = package.payload["design_ir"]["source"]
                    expected_bytes = source_text.encode("utf-8")
                    self.assertEqual(source["source_digest"], hashlib.sha256(expected_bytes).hexdigest())
                    artifact_path = str(source["artifact_path"]).removeprefix("package:")
                    self.assertEqual(package.members[artifact_path], expected_bytes)

    def test_worker_projects_the_canonical_embedded_design_source_for_desktop_open(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_path = root / "canonical-source.spike"
            source_name = "canonical.kicad_pcb"
            source_bytes = b'(kicad_pcb (version 20240108) (generator pcbnew) (layers (0 "F.Cu" signal)) (net 0 ""))'
            source_digest = hashlib.sha256(source_bytes).hexdigest()
            design = DesignIRV2.from_v1(DesignIR(
                design_id="canonical-source",
                name="Canonical source",
                source_format="kicad",
                layers=[{"id": 0, "name": "F.Cu"}],
                metadata={"source_sha256": source_digest},
            )).to_dict()
            design["source"]["artifact_path"] = f"package:sources/{source_digest}{Path(source_name).suffix}"
            write_spike_package(
                package_path,
                {"project": {"id": "canonical-source", "name": package_path.name}, "design_ir": design},
                source_artifacts={source_name: source_bytes},
            )
            opened = self.run_worker([json.dumps({
                "id": "canonical-source-open",
                "method": "read_project_package",
                "params": {"path": str(package_path)},
            })])[0]

        self.assertTrue(opened["ok"], opened)
        projected = opened["result"]["project"]["design"]
        self.assertEqual(projected["source_board"], source_bytes.decode("utf-8"))
        self.assertEqual(projected["source_file"], Path(design["source"]["artifact_path"]).name)
        self.assertEqual(projected["source_format"], "kicad")

    def test_worker_attaches_mcad_part_atomically_and_reopens_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "assembly.spike"
            source_path = root / "fixture.step"
            source_bytes = b"ISO-10303-21;\nHEADER;ENDSEC;DATA;ENDSEC;END-ISO-10303-21;\n"
            source_path.write_bytes(source_bytes)
            design = DesignIRV2.from_v1(DesignIR(
                design_id="mcad-worker",
                name="MCAD worker",
                source_format="neutral",
                layers=[{"id": 0, "name": "F.Cu"}],
                metadata={"source_sha256": "3" * 64},
            ))
            write_spike_package(project_path, {
                "project": {"id": "mcad-project", "name": "MCAD project"},
                "design_ir": design.to_dict(),
                "audit": [{"event": "created"}],
            })
            attached = self.run_worker([json.dumps({
                "id": "mcad-attach-1",
                "method": "attach_mcad_part_to_project",
                "params": {
                    "project_path": str(project_path),
                    "source_path": str(source_path),
                    "name": "Enclosure",
                    "part_type": "enclosure",
                    "material_id": "aluminium",
                    "frame": {
                        "frame_id": "enclosure-frame",
                        "parent_frame_id": "assembly",
                        "transform": [1, 0, 0, 10, 0, 1, 0, 20, 0, 0, 1, 30, 0, 0, 0, 1],
                    },
                },
            })])[0]
            self.assertTrue(attached["ok"], attached)
            attached_part = attached["result"]["part"]
            updated = self.run_worker([json.dumps({
                "id": "mcad-update-1",
                "method": "update_mcad_part_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": attached["result"]["manifest"]["manifest_payload_sha256"],
                    "part_id": attached_part["id"],
                    "name": "Edited enclosure",
                    "part_type": "enclosure",
                    "material_id": "aluminium-6061",
                    "visual": {"visible": False, "opacity": 0.35},
                    "frame": {
                        "frame_id": attached_part["frame"]["frame_id"],
                        "parent_frame_id": "assembly",
                        "units": "mm",
                        "handedness": "right",
                        "transform": [0, -1, 0, 40, 1, 0, 0, 50, 0, 0, 1, 60, 0, 0, 0, 1],
                    },
                },
            })])[0]
            self.assertTrue(updated["ok"], updated)
            for index, visual in enumerate((
                {"visible": True, "opacity": -0.01},
                {"visible": True, "opacity": 1.01},
                {"visible": 1, "opacity": 0.5},
                {"visible": True, "opacity": "opaque"},
            )):
                invalid_visual = self.run_worker([json.dumps({
                    "id": f"mcad-update-invalid-visual-{index}",
                    "method": "update_mcad_part_in_project",
                    "params": {
                        "project_path": str(project_path),
                        "expected_manifest_payload_sha256": updated["result"]["manifest"]["manifest_payload_sha256"],
                        "part_id": attached_part["id"],
                        "frame": updated["result"]["part"]["frame"],
                        "visual": visual,
                    },
                })])[0]
                self.assertFalse(invalid_visual["ok"], invalid_visual)
                self.assertIn("MCAD visual", invalid_visual["error"])
            semantics = self.run_worker([json.dumps({
                "id": "assembly-semantics-1",
                "method": "update_assembly_semantics_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": updated["result"]["manifest"]["manifest_payload_sha256"],
                    "materials": [{
                        "id": "aluminium-6061", "name": "Aluminium 6061",
                        "material_class": "metal", "thermal_conductivity_w_per_mk": 167,
                    }],
                    "thermal_contacts": [{
                        "id": "case-interface", "endpoint_a": f"{attached_part['id']}:base",
                        "endpoint_b": "board:mount", "contact_type": "thermal_pad",
                        "material_id": "gap-pad", "contact_area_mm2": 25,
                        "thermal_resistance_k_per_w": 0.4,
                    }],
                    "electrical_bonds": [{
                        "id": "chassis-bond", "endpoint_a": f"{attached_part['id']}:stud",
                        "endpoint_b": "board:chassis", "bond_type": "braid",
                        "electrical_material_id": "copper", "thermal_material_id": "copper",
                        "contact_area_mm2": 4, "thickness_mm": 0.5,
                        "electrical_resistance_ohm": 0.001,
                    }],
                },
            })])[0]
            self.assertTrue(semantics["ok"], semantics)
            stale_update = self.run_worker([json.dumps({
                "id": "mcad-update-stale",
                "method": "update_mcad_part_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": attached["result"]["manifest"]["manifest_payload_sha256"],
                    "part_id": attached_part["id"],
                    "frame": updated["result"]["part"]["frame"],
                },
            })])[0]
            self.assertFalse(stale_update["ok"])
            self.assertIn("changed since it was verified", stale_update["error"])
            reopened = read_spike_package(project_path, include_members=True)
            projected = self.run_worker([json.dumps({
                "id": "mcad-reopen-1",
                "method": "read_project_package",
                "params": {"path": str(project_path)},
            })])[0]
            resaved_path = root / "assembly-resaved.spike"
            resaved = self.run_worker([json.dumps({
                "id": "mcad-resave-1",
                "method": "write_project_package",
                "params": {
                    "path": str(resaved_path),
                    "base_package_path": str(project_path),
                    "snapshot": projected["result"]["project"],
                },
            })])[0]
            self.assertTrue(resaved["ok"], resaved)
            round_tripped = read_spike_package(resaved_path, include_members=True)

        self.assertEqual(len(reopened.payload["assembly_ir"]["parts"]), 1)
        part = reopened.payload["assembly_ir"]["parts"][0]
        self.assertEqual(part["name"], "Edited enclosure")
        self.assertEqual(part["material_id"], "aluminium-6061")
        self.assertEqual(part["extensions"]["spike.visual"], {"visible": False, "opacity": 0.35})
        self.assertEqual(part["frame"]["transform"][3], 40.0)
        self.assertEqual(reopened.payload["models"]["contract"], "spike/model-index/v1")
        model = reopened.payload["models"]["models"][0]
        member = model["uri"].removeprefix("package:")
        self.assertEqual(reopened.members[member], source_bytes)
        self.assertEqual(reopened.payload["audit"][-1]["event"], "assembly_semantics_updated")
        self.assertEqual(reopened.payload["assembly_ir"]["thermal_contacts"][0]["contact_area_mm2"], 25.0)
        self.assertEqual(reopened.payload["assembly_ir"]["electrical_bonds"][0]["electrical_resistance_ohm"], 0.001)

        self.assertTrue(projected["ok"], projected)
        self.assertEqual(projected["result"]["project"]["assembly_ir"]["parts"][0]["name"], "Edited enclosure")
        self.assertEqual(projected["result"]["project"]["models"]["models"][0]["id"], model["id"])
        self.assertEqual(round_tripped.payload["assembly_ir"]["parts"][0]["id"], part["id"])
        self.assertEqual(round_tripped.members[member], source_bytes)

    def test_worker_updates_nested_placement_and_reparents_only_through_dedicated_operation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "nested-assembly.spike"
            source_path = root / "fixture.step"
            child_source_path = root / "child.step"
            source_bytes = b"ISO-10303-21;\nHEADER;ENDSEC;DATA;ENDSEC;END-ISO-10303-21;\n"
            source_path.write_bytes(source_bytes)
            child_source_bytes = b"ISO-10303-21;\nHEADER;ENDSEC;DATA;/* child */ENDSEC;END-ISO-10303-21;\n"
            child_source_path.write_bytes(child_source_bytes)
            design = DesignIRV2.from_v1(DesignIR(
                design_id="nested-mcad-worker",
                name="Nested MCAD worker",
                source_format="neutral",
                layers=[{"id": 0, "name": "F.Cu"}],
                metadata={"source_sha256": "6" * 64},
            ))
            write_spike_package(project_path, {
                "project": {"id": "nested-mcad-project", "name": "Nested MCAD project"},
                "design_ir": design.to_dict(),
            })
            parent = self.run_worker([json.dumps({
                "id": "nested-parent-attach",
                "method": "attach_mcad_part_to_project",
                "params": {
                    "project_path": str(project_path), "source_path": str(source_path), "name": "Parent",
                    "frame": {"frame_id": "parent-frame", "parent_frame_id": "assembly"},
                },
            })])[0]
            self.assertTrue(parent["ok"], parent)
            child = self.run_worker([json.dumps({
                "id": "nested-child-attach",
                "method": "attach_mcad_part_to_project",
                "params": {
                    "project_path": str(project_path), "source_path": str(child_source_path), "name": "Child",
                    "frame": {
                        "frame_id": "child-frame", "parent_frame_id": "parent-frame",
                        "transform": [1, 0, 0, 3, 0, 1, 0, 4, 0, 0, 1, 5, 0, 0, 0, 1],
                    },
                },
            })])[0]
            self.assertTrue(child["ok"], child)
            saved = self.run_worker([json.dumps({
                "id": "nested-metadata-update",
                "method": "update_mcad_part_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": child["result"]["manifest"]["manifest_payload_sha256"],
                    "part_id": child["result"]["part"]["id"], "name": "Hidden child",
                    "frame": child["result"]["part"]["frame"],
                    "visual": {"visible": False, "opacity": 0.2},
                },
            })])[0]
            self.assertTrue(saved["ok"], saved)
            moved_frame = dict(child["result"]["part"]["frame"])
            moved_frame["transform"] = [1, 0, 0, 6, 0, 1, 0, 4, 0, 0, 1, 5, 0, 0, 0, 1]
            scaled_frame = dict(moved_frame)
            scaled_frame["transform"] = [2, 0, 0, 6, 0, 1, 0, 4, 0, 0, 1, 5, 0, 0, 0, 1]
            scaled = self.run_worker([json.dumps({
                "id": "nested-placement-scale-rejected",
                "method": "update_mcad_part_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": saved["result"]["manifest"]["manifest_payload_sha256"],
                    "part_id": child["result"]["part"]["id"], "frame": scaled_frame,
                },
            })])[0]
            self.assertFalse(scaled["ok"], scaled)
            self.assertIn("scale and shear are not permitted", scaled["error"])
            moved = self.run_worker([json.dumps({
                "id": "nested-placement-update",
                "method": "update_mcad_part_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": saved["result"]["manifest"]["manifest_payload_sha256"],
                    "part_id": child["result"]["part"]["id"], "frame": moved_frame,
                },
            })])[0]
            self.assertTrue(moved["ok"], moved)
            reparented_frame = dict(moved_frame)
            reparented_frame["parent_frame_id"] = "assembly"
            reparented = self.run_worker([json.dumps({
                "id": "nested-reparent-update",
                "method": "update_mcad_part_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": moved["result"]["manifest"]["manifest_payload_sha256"],
                    "part_id": child["result"]["part"]["id"], "frame": reparented_frame,
                },
            })])[0]
            self.assertFalse(reparented["ok"], reparented)
            self.assertIn("cannot change the stable parent-frame", reparented["error"])
            dedicated = self.run_worker([json.dumps({
                "id": "nested-reparent-dedicated",
                "method": "reparent_mcad_part_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": moved["result"]["manifest"]["manifest_payload_sha256"],
                    "part_id": child["result"]["part"]["id"], "new_parent_frame_id": "assembly",
                },
            })])[0]
            self.assertTrue(dedicated["ok"], dedicated)
            self.assertTrue(dedicated["result"]["world_transform_preserved"])
            self.assertEqual(dedicated["result"]["old_parent_frame_id"], "parent-frame")
            self.assertEqual(dedicated["result"]["new_parent_frame_id"], "assembly")
            reopened = read_spike_package(project_path, include_members=True)

        saved_child = next(part for part in reopened.payload["assembly_ir"]["parts"] if part["id"] == child["result"]["part"]["id"])
        self.assertEqual(saved_child["name"], "Hidden child")
        self.assertEqual(saved_child["extensions"]["spike.visual"], {"visible": False, "opacity": 0.2})
        self.assertEqual(saved_child["frame"]["parent_frame_id"], "assembly")
        self.assertEqual(saved_child["frame"]["transform"][3], 6.0)
        self.assertEqual(reopened.payload["audit"][-1]["event"], "mcad_part_reparented")
        self.assertEqual(reopened.members["models/artifacts/fixture-" + hashlib.sha256(source_bytes).hexdigest()[:16] + ".step"], source_bytes)
        self.assertEqual(reopened.members["models/artifacts/child-" + hashlib.sha256(child_source_bytes).hexdigest()[:16] + ".step"], child_source_bytes)

    def test_worker_enforces_persisted_mcad_placement_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "placement-policy.spike"
            source_path = root / "part.step"
            source_path.write_bytes(b"ISO-10303-21;\nHEADER;ENDSEC;DATA;ENDSEC;END-ISO-10303-21;\n")
            design = DesignIRV2.from_v1(DesignIR(
                design_id="placement-policy-worker",
                name="Placement policy worker",
                source_format="neutral",
                layers=[{"id": 0, "name": "F.Cu"}],
                metadata={"source_sha256": "9" * 64},
            ))
            write_spike_package(project_path, {
                "project": {"id": "placement-policy-project", "name": "Placement policy project"},
                "design_ir": design.to_dict(),
            })
            attached = self.run_worker([json.dumps({
                "id": "policy-attach",
                "method": "attach_mcad_part_to_project",
                "params": {"project_path": str(project_path), "source_path": str(source_path), "name": "Part"},
            })])[0]
            self.assertTrue(attached["ok"], attached)
            part = attached["result"]["part"]
            self.assertEqual(part["placement_policy"]["translation_snap_mm"], 1.0)
            frame_before = part["frame"]
            policy = self.run_worker([json.dumps({
                "id": "policy-update",
                "method": "update_mcad_placement_policy_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": attached["result"]["manifest"]["manifest_payload_sha256"],
                    "part_id": part["id"],
                    "placement_policy": {
                        "contract": "spike/assembly-placement-policy/v1",
                        "translation_snap_mm": 0.5,
                        "rotation_snap_deg": 30,
                    },
                },
            })])[0]
            self.assertTrue(policy["ok"], policy)
            self.assertEqual(policy["result"]["part"]["frame"], frame_before)

            moved_frame = dict(frame_before)
            moved_frame["transform"] = [
                math.sqrt(3) / 2, -0.5, 0, 1.0,
                0.5, math.sqrt(3) / 2, 0, 0,
                0, 0, 1, 0,
                0, 0, 0, 1,
            ]
            off_grid_frame = dict(frame_before)
            off_grid_frame["transform"] = [1, 0, 0, 0.25, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
            off_grid = self.run_worker([json.dumps({
                "id": "policy-off-grid",
                "method": "update_mcad_part_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": policy["result"]["manifest"]["manifest_payload_sha256"],
                    "part_id": part["id"], "frame": off_grid_frame,
                },
            })])[0]
            self.assertFalse(off_grid["ok"], off_grid)
            self.assertIn("translation increment", off_grid["error"])

            bypass = self.run_worker([json.dumps({
                "id": "policy-bypass",
                "method": "update_mcad_part_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": policy["result"]["manifest"]["manifest_payload_sha256"],
                    "part_id": part["id"], "frame": moved_frame,
                    "placement_policy": {
                        "contract": "spike/assembly-placement-policy/v1",
                        "translation_snap_mm": None, "rotation_snap_deg": None,
                    },
                },
            })])[0]
            self.assertFalse(bypass["ok"], bypass)
            self.assertIn("cannot be changed through the part placement operation", bypass["error"])

            moved = self.run_worker([json.dumps({
                "id": "policy-valid-move",
                "method": "update_mcad_part_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": policy["result"]["manifest"]["manifest_payload_sha256"],
                    "part_id": part["id"], "frame": moved_frame,
                },
            })])[0]
            self.assertTrue(moved["ok"], moved)
            stale = self.run_worker([json.dumps({
                "id": "policy-stale",
                "method": "update_mcad_placement_policy_in_project",
                "params": {
                    "project_path": str(project_path),
                    "expected_manifest_payload_sha256": policy["result"]["manifest"]["manifest_payload_sha256"],
                    "part_id": part["id"],
                    "placement_policy": part["placement_policy"],
                },
            })])[0]
            self.assertFalse(stale["ok"], stale)
            self.assertIn("project changed", stale["error"])
            reopened = read_spike_package(project_path)

        saved_part = reopened.payload["assembly_ir"]["parts"][0]
        self.assertEqual(saved_part["placement_policy"]["translation_snap_mm"], 0.5)
        self.assertEqual(saved_part["placement_policy"]["rotation_snap_deg"], 30.0)
        self.assertEqual(saved_part["frame"]["transform"][3], 1.0)
        self.assertEqual(reopened.payload["audit"][-1]["event"], "mcad_part_updated")

    def test_worker_reads_digest_verified_visual_model_artifacts(self):
        gltf = b'{"asset":{"version":"2.0"},"scenes":[{}],"nodes":[]}'
        design = DesignIRV2.from_v1(DesignIR(
            design_id="visual-worker",
            name="Visual worker",
            source_format="neutral",
            layers=[{"id": 0, "name": "F.Cu"}],
            metadata={"source_sha256": "4" * 64},
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "visual.spike"
            manifest = write_spike_package(path, {
                "project": {"id": "visual-project", "name": "Visual project"},
                "design_ir": design.to_dict(),
                "models": {
                    "contract": "spike/model-index/v1",
                    "models": [{
                        "id": "visual-model",
                        "model_type": "gltf",
                        "uri": "package:models/artifacts/visual.gltf",
                        "digest": hashlib.sha256(gltf).hexdigest(),
                    }],
                },
                "audit": [{"event": "created"}],
            }, model_artifacts={"visual.gltf": gltf})
            response = self.run_worker([json.dumps({
                "id": "visual-model-read-1",
                "method": "read_project_model_artifacts",
                "params": {
                    "path": str(path),
                    "model_ids": ["visual-model"],
                    "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                },
            })])[0]

        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["contract"], "spike/project-model-artifacts/v1")
        artifact = response["result"]["artifacts"][0]
        self.assertEqual(artifact["model_type"], "gltf")
        self.assertEqual(artifact["model_ids"], ["visual-model"])
        self.assertEqual(base64.b64decode(artifact["artifact_base64"]), gltf)

    def test_worker_save_as_preserves_verified_v3_artifacts_and_extensions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.spike"
            resaved = root / "resaved.spike"
            design = DesignIRV2.from_v1(DesignIR(
                design_id="worker-preserve",
                name="Worker preserve",
                source_format="neutral",
                layers=[{"id": 0, "name": "F.Cu"}],
                metadata={"source_sha256": "2" * 64},
            ))
            write_spike_package(
                original,
                {
                    "project": {"id": "worker-preserve", "name": "original.spike"},
                    "design_ir": design.to_dict(),
                    "extensions": {"vendor.future": {"preserve": True}},
                    "audit": [{"event": "created"}],
                },
                source_artifacts={"fixture.neutral": b"source-preserved"},
                geometry_tables={"conductors": b"arrow-preserved"},
                model_artifacts={"part.step": b"step-preserved"},
            )
            opened = self.run_worker([json.dumps({
                "id": "preserve-open",
                "method": "read_project_package",
                "params": {"path": str(original)},
            })])[0]
            self.assertTrue(opened["ok"])
            snapshot = opened["result"]["project"]
            snapshot["project"]["name"] = "resaved.spike"
            saved = self.run_worker([json.dumps({
                "id": "preserve-save",
                "method": "write_project_package",
                "params": {
                    "path": str(resaved),
                    "snapshot": snapshot,
                    "base_package_path": str(original),
                },
            })])[0]
            self.assertTrue(saved["ok"])
            source = read_spike_package(original, include_members=True)
            result = read_spike_package(resaved, include_members=True)

        self.assertTrue(result.payload["extensions"]["vendor.future"]["preserve"])
        self.assertEqual(result.payload["project"]["name"], "resaved.spike")
        self.assertEqual(result.payload["geometry"], source.payload["geometry"])
        for name, data in source.members.items():
            if name.startswith(("sources/", "geometry/", "models/artifacts/")) and name != "geometry/index.json":
                self.assertEqual(result.members[name], data)

    def test_worker_open_and_save_preserve_typed_assembly_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "assembly-original.spike"
            resaved = root / "assembly-resaved.spike"
            design = DesignIRV2.from_v1(DesignIR(
                design_id="assembly-worker-design",
                name="Assembly worker design",
                source_format="neutral",
                layers=[{"id": 0, "name": "F.Cu"}],
                metadata={"source_sha256": "5" * 64},
            ))
            assembly = AssemblyIRV1.from_dict({
                "assembly_id": "worker-assembly",
                "name": "Worker assembly",
                "frame": {"frame_id": "assembly"},
                "boards": [
                    {
                        "id": "board-a",
                        "source_id": "native-board-a",
                        "design_id": "assembly-worker-design",
                        "frame": {"frame_id": "board-a-frame", "parent_frame_id": "assembly"},
                    },
                    {
                        "id": "board-b",
                        "source_id": "native-board-b",
                        "design_id": "assembly-worker-design",
                        "frame": {
                            "frame_id": "board-b-frame",
                            "parent_frame_id": "assembly",
                            "transform": [1, 0, 0, 50, 0, 1, 0, 10, 0, 0, 1, 5, 0, 0, 0, 1],
                        },
                    },
                ],
                "harnesses": [{
                    "id": "harness-a-b",
                    "source_id": "native-harness",
                    "endpoint_a": "board-a:J1",
                    "endpoint_b": "board-b:J1",
                    "length_mm": 150,
                    "pin_map": {"1": "1"},
                }],
            })
            write_spike_package(original, {
                "project": {"id": "worker-assembly", "name": "assembly-original.spike"},
                "design_ir": design.to_dict(),
                "assembly_ir": assembly.to_dict(),
                "extensions": {
                    "legacy": {
                        "format": "spike-project-package/v2",
                        "project": {"id": "worker-assembly", "name": "assembly-original.spike"},
                        "design": design.to_v1().to_dict(),
                    },
                },
            })

            opened = self.run_worker([json.dumps({
                "id": "assembly-open",
                "method": "read_project_package",
                "params": {"path": str(original)},
            })])[0]
            self.assertTrue(opened["ok"])
            self.assertEqual(
                AssemblyIRV1.from_dict(opened["result"]["project"]["assembly_ir"]).to_dict(),
                assembly.to_dict(),
            )
            snapshot = opened["result"]["project"]
            snapshot["project"]["name"] = "assembly-resaved.spike"
            saved = self.run_worker([json.dumps({
                "id": "assembly-save",
                "method": "write_project_package",
                "params": {
                    "path": str(resaved),
                    "snapshot": snapshot,
                    "base_package_path": str(original),
                },
            })])[0]
            self.assertTrue(saved["ok"])
            result = read_spike_package(resaved)

        restored = AssemblyIRV1.from_dict(result.payload["assembly_ir"])
        self.assertEqual(restored.to_dict(), assembly.to_dict())
        self.assertEqual(restored.boards[1].source_id, "native-board-b")
        self.assertEqual(restored.harnesses[0].source_id, "native-harness")

    def test_worker_save_as_invalidates_geometry_when_source_digest_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.spike"
            resaved = root / "resaved.spike"
            design = DesignIRV2.from_v1(DesignIR(
                design_id="worker-source-change",
                name="Worker source change",
                source_format="neutral",
                layers=[{"id": 0, "name": "F.Cu"}],
                metadata={"source_sha256": "3" * 64},
            ))
            write_spike_package(
                original,
                {
                    "project": {"id": "worker-source-change", "name": "original.spike"},
                    "design_ir": design.to_dict(),
                },
                geometry_tables={"conductors": b"stale-arrow-data"},
                model_artifacts={"part.step": b"model-remains-valid"},
            )
            opened = self.run_worker([json.dumps({
                "id": "source-change-open",
                "method": "read_project_package",
                "params": {"path": str(original)},
            })])[0]
            self.assertTrue(opened["ok"])
            snapshot = opened["result"]["canonical"]
            snapshot["project"]["name"] = "resaved.spike"
            snapshot["design_ir"]["source"]["source_digest"] = "4" * 64
            saved = self.run_worker([json.dumps({
                "id": "source-change-save",
                "method": "write_project_package",
                "params": {
                    "path": str(resaved),
                    "snapshot": snapshot,
                    "base_package_path": str(original),
                },
            })])[0]
            self.assertTrue(saved["ok"])
            result = read_spike_package(resaved, include_members=True)

        # Arrow is an optional worker acceleration dependency.  A source
        # identity change must invalidate stale geometry either way; with the
        # pinned Arrow runtime it additionally regenerates the empty canonical
        # table, while a minimal worker deliberately saves without one.
        if importlib.util.find_spec("pyarrow") is None:
            self.assertEqual(result.payload["geometry"]["tables"], [])
            self.assertNotIn("geometry/conductors.arrow", result.members)
        else:
            self.assertEqual(len(result.payload["geometry"]["tables"]), 1)
            generated = result.payload["geometry"]["tables"][0]
            self.assertEqual(generated["schema"], "spike/copper-geometry-arrow/v1")
            self.assertEqual(generated["rows"], 0)
            self.assertNotIn("geometry/conductors.arrow", result.members)
            validate_geometry_arrow(
                result.members[generated["path"]], DesignIRV2.from_dict(result.payload["design_ir"]),
            )
        self.assertEqual(result.members["models/artifacts/part.step"], b"model-remains-valid")
        invalidations = [
            event for event in result.payload["audit"]
            if event.get("event") == "geometry_cache_invalidated"
        ]
        self.assertEqual(len(invalidations), 1)
        self.assertEqual(invalidations[0]["previous_source_digest"], "3" * 64)
        self.assertEqual(invalidations[0]["current_source_digest"], "4" * 64)

    def test_environment_profile_protocol_lists_materializes_and_validates_readiness(self):
        catalog, materialized = self.run_worker([
            json.dumps({"id": "environments-1", "method": "list_environment_profiles", "params": {}}),
            json.dumps({
                "id": "environment-materialize-1",
                "method": "materialize_environment_profile",
                "params": {
                    "source": "preset",
                    "profile_id": "standard-lab-air",
                    "overrides": {"physical": {"thermal": {"ambient_temperature_k": 301.15}}},
                },
            }),
        ])

        self.assertTrue(catalog["ok"])
        self.assertEqual(catalog["result"]["contract"], "spike/environment-profile-catalog/v1")
        self.assertEqual(catalog["result"]["profile_contract"], "spike/environment-profile/v1")
        self.assertIn("standard-lab-air", {item["profile_id"] for item in catalog["result"]["profiles"]})

        self.assertTrue(materialized["ok"])
        profile = materialized["result"]
        self.assertEqual(profile["contract"], "spike/environment-profile/v1")
        self.assertEqual(profile["physical"]["thermal"]["ambient_temperature_k"], 301.15)
        self.assertFalse(profile["validity"]["certification_claimed"])

        validation = self.run_worker([json.dumps({
            "id": "environment-validate-1",
            "method": "validate_environment_profile",
            "params": {"profile": profile, "domains": ["pi", "thermal"]},
        })])[0]
        self.assertTrue(validation["ok"])
        self.assertEqual(validation["result"]["contract"], "spike/environment-profile-validation/v1")
        self.assertTrue(validation["result"]["can_supply_solver_inputs"])
        self.assertTrue(validation["result"]["domain_readiness"]["pi"]["inputs_complete"])
        self.assertEqual(validation["result"]["certification"]["status"], "not_assessed")
        self.assertFalse(validation["result"]["certification"]["claimed"])

    def test_environment_profile_protocol_materializes_user_profiles_and_rejects_unknown_presets(self):
        user_profile, missing = self.run_worker([
            json.dumps({
                "id": "environment-user-1",
                "method": "materialize_environment_profile",
                "params": {
                    "source": "user",
                    "profile_id": "customer-chamber",
                    "name": "Customer chamber",
                    "physical": {"thermal": {"ambient_temperature_k": 303.15}},
                    "source_title": "Customer chamber inputs",
                },
            }),
            json.dumps({
                "id": "environment-missing-1",
                "method": "materialize_environment_profile",
                "params": {"source": "preset", "profile_id": "does-not-exist"},
            }),
        ])

        self.assertTrue(user_profile["ok"])
        self.assertEqual(user_profile["result"]["profile_id"], "customer-chamber")
        self.assertEqual(user_profile["result"]["provenance"]["origin"], "user")
        self.assertFalse(user_profile["result"]["validity"]["certification_claimed"])
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["type"], "EnvironmentProfileError")

    def test_worker_exposes_neutral_importer_catalog(self):
        response = self.run_worker([json.dumps({
            "id": "importers-1", "method": "list_importers", "params": {},
        })])[0]
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["contract"], "spike/importer-catalog/v1")
        importer_ids = {item["importer_id"] for item in response["result"]["importers"]}
        self.assertIn("kicad-pcb", importer_ids)
        self.assertIn("ipc-2581", importer_ids)


if __name__ == "__main__":
    unittest.main()
