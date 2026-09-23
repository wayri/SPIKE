import copy
import gzip
import io
import json
from pathlib import Path
import tarfile
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile

from python.spike_core.contracts import DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.extensions import ExtensionRegistry
from python.spike_core.harness import analyze_harness, compile_harness, compile_multiboard_harness, export_harness, import_harness, validate_harness
from python.spike_core.importers import ImportPolicy, ImporterRegistry
from python.spike_core.odb_importer import decode_odb_json_archive, decode_odb_source_table, import_odb_design
from python.spike_core.odb_features import parse_features
from python.spike_core.source_package import SourcePackage, source_identity

ROOT = Path(__file__).resolve().parents[2]


def board_files():
    return {
        "matrix/matrix": "STEP {\nCOL=1\nNAME=board\n}\nLAYER {\nROW=1\nNAME=top\nTYPE=SIGNAL\nCONTEXT=BOARD\nPOLARITY=POSITIVE\n}\nLAYER {\nROW=2\nNAME=comp_+_top\nTYPE=COMPONENT\n}\n",
        "misc/info": "UNITS=MM\nODB_VERSION_MAJOR=8\n",
        "steps/board/profile": "UNITS=MM\nOB 0 0 I\nOS 10 0\nOS 10 5\nOS 0 5\nOS 0 0\nOE\n",
        "steps/board/eda/data": "UNITS=MM\nLYR top\nNET GND\nSNT TOP T 0 0\nFID C 0 0\nSNT TRC\nFID C 0 1\nSNT PLN S E 0\nFID C 0 2\nPKG CONN 1 0 0 2 2\nRC 0 0 2 2\nPIN 1 S 1 1 0 E\n",
        "steps/board/layers/top/features": "UNITS=MM\n$0 r1000\n$1 r250\nF 3\nP 1 1 0 P 0 0\nL 1 1 4 1 1 P 0\nS P 0\nOB 4 0 I\nOS 8 0\nOS 8 4\nOS 4 4\nOS 4 0\nOE\nOB 5 1 H\nOS 5 2\nOS 6 2\nOS 6 1\nOS 5 1\nOE\nSE\n",
        "steps/board/layers/comp_+_top/components": "UNITS=MM\n@0 .comp_height\nCMP 0 1 1 90 N J1 HEADER;0=2.5;ID=123\nPRP VALUE 'Header 1 pin'\nPRP Manufacturer 'Vendor A'\nPRP Manufacturer 'Vendor B'\nTOP 0 1 1 0 N 0 0 1\nMPN 0 Y P123\n",
    }


def write_board(directory, files=None):
    path = Path(directory) / "job"
    for name, text in (files or board_files()).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return path


def harness():
    return {"contract": "spike/harness/v1", "id": "H1", "name": "Power cable", "connectors": [
        {"id": "J1", "pins": [{"id": "01", "net": "VCC", "required": True}]},
        {"id": "J2", "pins": [{"id": "A", "net": "VCC", "required": True}]}],
        "wires": [{"id": "W1", "from": {"connector": "J1", "pin": "01"}, "to": {"connector": "J2", "pin": "A"},
                   "length_mm": 1000, "area_mm2": 1, "material": {"resistivity_ohm_m": 1.68e-8, "reference_temperature_c": 20},
                   "properties": {"Altium": {"PartNumber": "wire-1"}}}]}


class OdbImportTests(unittest.TestCase):
    def test_rounded_rectangle_flash_has_bounded_custom_geometry(self):
        issues = []
        rows = parse_features(
            "UNITS=MM\n$0 rect2.0x1.0xr0.2 M\nF 1\nP 4 5 0 P 0 0\n",
            "top", "MM", lambda *args: issues.append(args),
        )
        self.assertEqual(issues, [])
        self.assertEqual(rows[0]["shape"], "custom")
        self.assertEqual(rows[0]["size"], [0.002, 0.001])
        geometry = rows[0]["custom_geometry"]
        self.assertEqual(geometry["status"], "supported")
        self.assertLessEqual(geometry["curve_approximation"]["maximum_sagitta_mm"], 0.001)

    def test_zero_length_round_line_is_a_flash(self):
        issues = []
        rows = parse_features(
            "UNITS=MM\n$0 r1.0 M\nF 1\nL 2 3 2 3 0 P 0\n",
            "top", "MM", lambda *args: issues.append(args),
        )
        self.assertEqual(issues, [])
        self.assertEqual(rows[0]["kind"], "pad")
        self.assertEqual(rows[0]["at"], [2.0, 3.0])

    def test_repeated_unsupported_artwork_is_counted_without_aborting_import(self):
        files = board_files()
        files["matrix/matrix"] += "LAYER {\nROW=3\nNAME=doc\nTYPE=DOCUMENT\n}\n"
        files["steps/board/layers/doc/features"] = (
            "UNITS=MM\n$0 rect1000x500\nF 150\n"
            + "".join(f"L {index} 0 {index + 1} 0 0 P 0\n" for index in range(150))
        )
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp, files)))
        self.assertEqual(design.metadata["odb_issue_counts"]["ODB_FEATURE_UNSUPPORTED"], 150)
        sampled = [issue for issue in design.issues if issue.code == "ODB_FEATURE_UNSUPPORTED"]
        self.assertEqual(len(sampled), 100)
        retained = [row for row in design.metadata["odb_retained"] if row["code"] == "ODB_FEATURE_UNSUPPORTED"]
        self.assertEqual(len(retained), 100)

    def test_warning_sampling_does_not_hide_a_later_copper_error(self):
        files = board_files()
        files["matrix/matrix"] = files["matrix/matrix"].replace(
            "LAYER {\nROW=1\nNAME=top\nTYPE=SIGNAL\nCONTEXT=BOARD\nPOLARITY=POSITIVE\n}\n",
            "LAYER {\nROW=1\nNAME=doc\nTYPE=DOCUMENT\n}\n"
            "LAYER {\nROW=3\nNAME=top\nTYPE=SIGNAL\nCONTEXT=BOARD\nPOLARITY=POSITIVE\n}\n",
        )
        files["steps/board/eda/data"] = files["steps/board/eda/data"].replace("LYR top", "LYR doc top")
        files["steps/board/layers/doc/features"] = (
            "UNITS=MM\n$0 rect1000x500\nF 101\n"
            + "".join(f"L {index} 0 {index + 1} 0 0 P 0\n" for index in range(101))
        )
        files["steps/board/layers/top/features"] = "UNITS=MM\n$0 rect1000x500\nF 1\nL 0 0 1 0 0 P 0\n"
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp, files)))
        self.assertEqual(design.metadata["odb_issue_severity_counts"]["ODB_FEATURE_UNSUPPORTED:warning"], 101)
        self.assertEqual(design.metadata["odb_issue_severity_counts"]["ODB_FEATURE_UNSUPPORTED:error"], 1)
        self.assertTrue(any(issue.code == "ODB_FEATURE_UNSUPPORTED" and issue.severity == "error" for issue in design.issues))
        self.assertFalse(design.metadata["geometry_normalized"])

    def test_unsupported_mask_reference_does_not_invalidate_copper_connectivity(self):
        files = board_files()
        files["matrix/matrix"] += "LAYER {\nROW=3\nNAME=mask\nTYPE=SOLDER_MASK\n}\n"
        files["steps/board/eda/data"] = files["steps/board/eda/data"].replace(
            "LYR top", "LYR top mask",
        ).replace("FID C 0 0", "FID C 0 0\nFID C 1 0", 1)
        files["steps/board/layers/mask/features"] = "UNITS=MM\n$0 donut_r100x50\nF 1\nP 1 1 0 P 0 0\n"
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp, files)))
        self.assertNotIn("ODB_FEATURE_REFERENCE_UNRESOLVED", design.metadata["odb_issue_counts"])
        self.assertEqual(design.metadata["odb_issue_severity_counts"]["ODB_FEATURE_UNSUPPORTED:warning"], 1)

    def test_kicad_odb_copper_names_are_canonical_without_changing_archive_lookup(self):
        files = board_files()
        files["matrix/matrix"] = files["matrix/matrix"].replace("NAME=top", "NAME=F.CU")
        files["steps/board/eda/data"] = files["steps/board/eda/data"].replace("LYR top", "LYR F.CU")
        files["steps/board/layers/f.cu/features"] = files.pop("steps/board/layers/top/features")
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp, files)))
        self.assertEqual(design.layers[0]["id"], "F.Cu")
        self.assertEqual(design.layers[0]["name"], "F.Cu")
        self.assertEqual(design.tracks[0]["layer"], "F.Cu")
        self.assertEqual(design.pads[0]["layers"], ["F.Cu"])

    def test_quoted_vendor_property_separators_are_not_attributes(self):
        from python.spike_core.odb_features import tokens, Attributes
        record = "PRP Description 'Power; return, pair';ID=100"
        self.assertEqual(tokens(record), ["PRP", "Description", "Power; return, pair"])
        self.assertEqual(Attributes().source(record)["uid"], "100")

    def test_export_precision_rounding_does_not_discard_valid_arcs(self):
        from python.spike_core.odb_features import arc_mid
        middle = arc_mid([1.0, 0.0], [0.0, 1.00009], [0.0, 0.0], False)
        self.assertAlmostEqual(middle[0], middle[1], places=3)
        with self.assertRaisesRegex(ValueError, "declared circle"):
            arc_mid([1.0, 0.0], [0.0, 1.001], [0.0, 0.0], False)

    def test_unassigned_drills_block_analysis_without_losing_source(self):
        files = board_files()
        files["matrix/matrix"] += "LAYER {\nROW=3\nNAME=drill\nTYPE=DRILL\nSTART_NAME=top\nEND_NAME=top\n}\n"
        files["steps/board/layers/drill/features"] = "UNITS=MM\n$0 r400\nP 1 1 0 P 0 0\n"
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp, files)))
        self.assertEqual(len(design.metadata["manufacturing_drills"]), 1)
        self.assertIn("ODB_DRILL_OWNER_UNRESOLVED", {i.code for i in design.issues})
        self.assertFalse(design.metadata["geometry_solver_ready"])

    def test_top_subnet_hole_links_exact_component_pad_owner(self):
        files = board_files()
        files["matrix/matrix"] += "LAYER {\nROW=3\nNAME=drill\nTYPE=DRILL\nSTART_NAME=top\nEND_NAME=top\n}\n"
        files["steps/board/eda/data"] = files["steps/board/eda/data"].replace(
            "LYR top", "LYR top drill",
        ).replace("FID C 0 0", "FID C 0 0\nFID H 1 0", 1)
        files["steps/board/layers/drill/features"] = "UNITS=MM\n$0 r400\nF 1\nP 1 1 0 P 0 0\n"
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp, files)))
        drill = design.metadata["manufacturing_drills"][0]
        self.assertEqual((drill["owner_kind"], drill["owner_id"]), ("pad", design.pads[0]["id"]))
        self.assertEqual((drill["plating_status"], drill["plated"]), ("plated", True))
        self.assertEqual(drill["span_provenance"], "matched_owner")
        self.assertNotIn("ODB_DRILL_OWNER_UNRESOLVED", design.metadata["odb_issue_counts"])

    def test_oval_drill_hit_retains_exact_size_rotation_and_span(self):
        files = board_files()
        files["matrix/matrix"] += "LAYER {\nROW=3\nNAME=slot\nTYPE=DRILL\nSTART_NAME=top\nEND_NAME=top\n}\n"
        files["steps/board/layers/slot/features"] = "UNITS=MM\n$0 oval1200x700 M\nP 2 3 0 P 0 8 90\n"
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp, files)))
        drill = design.metadata["manufacturing_drills"][0]
        self.assertEqual(drill["shape"], "slot")
        self.assertAlmostEqual(drill["size_mm"][0], 1.2)
        self.assertAlmostEqual(drill["size_mm"][1], 0.7)
        self.assertEqual(drill["rotation_deg"], -90)
        self.assertEqual(drill["span_layer_ids"], ["top", "top"])
        self.assertNotIn("ODB_DRILL_UNSUPPORTED", design.metadata["odb_issue_counts"])

    def test_physical_stackup_must_follow_matrix_copper_order(self):
        files = board_files()
        files["matrix/matrix"] += "LAYER {\nROW=3\nNAME=bottom\nTYPE=SIGNAL\n}\n"
        files["steps/board/layers/bottom/features"] = "UNITS=MM\nF 0\n"
        files["steps/board/spike/board.json"] = json.dumps({"contract": "spike/board-enrichment/v1", "stackup": [
            {"name": "bottom", "type": "copper", "thickness_mm": .035},
            {"name": "core", "type": "dielectric", "thickness_mm": 1.5, "epsilon_r": 4.2, "loss_tangent": .02},
            {"name": "top", "type": "copper", "thickness_mm": .035}]})
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp, files)))
        self.assertFalse(design.metadata["stackup_physical_complete"])
        self.assertIn("ODB_STACKUP_UNRESOLVED", {i.code for i in design.issues})

    def test_standard_xml_stackup_resolves_materials_and_units(self):
        files = board_files()
        files["matrix/stackup"] = '''<StackupFile DefaultUnits="MM"><EdaData><Specs><Spec SpecName="s">
        <Material MaterialName="cu"><Conductor/><Default_Thickness Thickness="35" Units="MICRON"/></Material>
        <Material MaterialName="fr4"><Dielectric><Properties PropertyName="p"><Property DielectricConstant_Dk="4.2" LossTangent_Df="0.02"/></Properties></Dielectric><Default_Thickness Thickness="1.5"/></Material>
        </Spec></Specs><Stackup><Group GroupName="g">
        <Layer LayerName="top" LayerType="SIGNAL"><SpecRef MaterialSpecName="s"><Material MaterialName="cu"/></SpecRef></Layer>
        <Layer LayerName="core" LayerType="DIELECTRIC"><SpecRef MaterialSpecName="s"><Material MaterialName="fr4" PropertyName="p"/></SpecRef></Layer>
        </Group></Stackup></EdaData></StackupFile>'''
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp, files)))
        self.assertEqual([s["name"] for s in design.stackup], ["top", "core"])
        self.assertAlmostEqual(design.stackup[0]["thickness"], .035)
        self.assertEqual(design.stackup[1]["epsilon_r"], 4.2)

    def test_solver_execution_blocks_incomplete_import(self):
        from python.spike_core.solver_plugins import SolverRegistry
        from python.spike_core.contracts import AnalysisSpec
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp)))
        result = SolverRegistry().run(design, AnalysisSpec(mode="dc"))
        self.assertEqual(result.issues[0].code, "IMPORT_NOT_SOLVER_READY")

    def test_normalized_snapshot_and_harness_survive_project_save_reload(self):
        from python.spike_core.service_project_handlers import handle_project_request
        with tempfile.TemporaryDirectory() as tmp:
            path = write_board(tmp)
            imported = handle_project_request("import_design_v2", {"path": str(path), "include_snapshot": True}, request_id="import", application_version="test")
            self.assertTrue(imported["ok"], imported)
            snapshot = {"format": "spike-project-package/v2", "project": {"name": "odb.spike"}, "analysis": {}, "harness": harness(),
                        "design": {"source_format": "spike-normalized", "source_file": "board.spike-design.json", "source_board": json.dumps(imported["result"]["snapshot"])}}
            project = Path(tmp) / "odb.spike"
            saved = handle_project_request("write_project_package", {"path": str(project), "snapshot": snapshot, "generate_geometry_tables": False}, request_id="save", application_version="test")
            self.assertTrue(saved["ok"], saved)
            loaded = handle_project_request("read_project_package", {"path": str(project)}, request_id="load", application_version="test")
            self.assertTrue(loaded["ok"], loaded)
            from python.spike_core.project_package import read_project
            result = read_project(project).payload
            self.assertEqual(len(result["design_ir"]["tracks"]), 1)
            self.assertEqual(result["extensions"]["legacy"]["harness"], harness())

    def test_snapshot_only_transport_does_not_duplicate_canonical_design(self):
        from python.spike_core.service_project_handlers import handle_project_request
        with tempfile.TemporaryDirectory() as tmp:
            path = write_board(tmp)
            imported = handle_project_request(
                "import_design_v2",
                {"path": str(path), "include_snapshot": True, "snapshot_only": True},
                request_id="compact-import", application_version="test",
            )
            expected_zones = DesignIRV2.from_v1(import_odb_design(str(path))).to_v1().zones
        self.assertTrue(imported["ok"], imported)
        self.assertEqual(set(imported["result"]), {"snapshot"})
        self.assertIn("design", imported["result"]["snapshot"])
        self.assertIn("canonical_design", imported["result"]["snapshot"])
        self.assertEqual(imported["result"]["snapshot"]["design"]["zones"], [])
        self.assertEqual(len(imported["result"]["snapshot"]["canonical_design"]["zones"]), 1)
        self.assertEqual(
            imported["result"]["snapshot"]["canonical_design"]["metadata"]["transport_projection"]["contract"],
            "spike/odb-transport-projection/v1",
        )
        source_table = imported["result"]["snapshot"]["canonical_design"]["metadata"]["odb_zone_sources"]
        decoded = decode_odb_source_table(source_table)
        self.assertEqual(len(decoded), source_table["count"])
        self.assertIn("records", decoded[0]["odb_source"])
        projection = imported["result"]["snapshot"]["canonical_design"]["metadata"]["transport_projection"]
        restored_zones = decode_odb_json_archive(projection["legacy_zones_archive"], "spike/odb-legacy-zones/v1")
        self.assertEqual(restored_zones, expected_zones)
        self.assertIn("odb_packages", imported["result"]["snapshot"]["canonical_design"]["metadata"])
        self.assertIn("odb_subnets", imported["result"]["snapshot"]["canonical_design"]["metadata"])

    def test_geometry_connectivity_properties_and_typed_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp)))
        self.assertEqual(design.pads[0]["component"], "J1")
        self.assertEqual(design.pads[0]["number"], "1")
        self.assertEqual(design.tracks[0]["width"], .25)
        self.assertEqual(design.tracks[0]["net_id"], 1)
        self.assertEqual(design.metadata["board_bounds_mm"], [0, 0, 10, 5])
        self.assertEqual(len(design.components[0]["properties"]), 3)
        self.assertEqual(design.components[0]["rotation"], -90)
        typed = DesignIRV2.from_v1(design)
        restored = DesignIRV2.from_dict(typed.to_dict()).to_v1()
        self.assertEqual(restored.components[0]["properties"], design.components[0]["properties"])
        self.assertEqual(len(typed.zones), 1)
        self.assertEqual(len(typed.pins), 1)

    def test_component_package_is_referenced_once_instead_of_embedded_per_occurrence(self):
        files = board_files()
        files["steps/board/eda/data"] += "PACKAGE_RECORD_SENTINEL\n"
        files["steps/board/layers/comp_+_top/components"] += "\nCMP 0 2 3 0 N J2 part\n"
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp, files)))
        self.assertEqual(len(design.metadata["odb_packages"]), 1)
        self.assertEqual([c["odb_package_ref"]["index"] for c in design.components], [0, 0])
        self.assertTrue(all("odb_package" not in c for c in design.components))
        # Snapshot size remains proportional to occurrences rather than to the
        # full package record body multiplied by occurrences.
        payload = json.dumps(DesignIRV2.from_v1(design).to_dict())
        self.assertEqual(payload.count("PACKAGE_RECORD_SENTINEL"), 1)

    def test_directory_zip_tar_gzip_and_inner_gzip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_board(tmp)
            expected = import_odb_design(str(path))
            for suffix in (".zip", ".tar", ".tgz"):
                target = Path(tmp) / ("board" + suffix)
                if suffix == ".zip":
                    with zipfile.ZipFile(target, "w") as archive:
                        for p in path.rglob("*"):
                            if p.is_file(): archive.write(p, "job/" + p.relative_to(path).as_posix())
                else:
                    with tarfile.open(target, "w:gz" if suffix == ".tgz" else "w") as archive:
                        archive.add(path, arcname="job")
                actual = import_odb_design(str(target))
                self.assertEqual(actual.tracks, expected.tracks)
            file = path / "steps/board/layers/top/features"
            file.with_suffix(".gz").write_bytes(gzip.compress(file.read_bytes()))
            file.unlink()
            self.assertEqual(len(import_odb_design(str(path)).pads), 1)

    def test_process_extension_and_quality_report(self):
        registry = ExtensionRegistry()
        registry.discover([ROOT / "extensions"], trusted_roots=[ROOT / "extensions"])
        importers = ImporterRegistry(registry.design_importers())
        with tempfile.TemporaryDirectory() as tmp:
            result = importers.import_outcome(str(write_board(tmp)))
        self.assertEqual(result.report.importer_id, "odb-design")
        self.assertEqual(result.report.coverage["tracks"], 1)
        self.assertFalse(result.report.solver_readiness["pi_ac"]["ready"])
        self.assertFalse(result.report.solver_readiness["pi_dc"]["ready"])

    def test_unsupported_negative_geometry_is_retained_and_blocks_readiness(self):
        files = board_files()
        files["steps/board/layers/top/features"] = files["steps/board/layers/top/features"].replace("L 1 1 4 1 1 P", "L 1 1 4 1 1 N")
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp, files)))
        self.assertEqual(len(design.tracks), 0)
        self.assertFalse(design.metadata["geometry_solver_ready"])
        self.assertTrue(design.metadata["odb_retained"])

    def test_multiple_steps_require_explicit_selection(self):
        files = board_files()
        files["matrix/matrix"] += "STEP {\nCOL=2\nNAME=panel\n}\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = write_board(tmp, files)
            with self.assertRaisesRegex(ValueError, "select a step"):
                import_odb_design(str(path))
            self.assertEqual(import_odb_design(str(path), step="board").name, "board")

    def test_archive_traversal_duplicates_links_and_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            for unsafe in ("../escape", "/abs", "C:/evil", "dir\\evil"):
                path = Path(tmp) / "bad.zip"
                with zipfile.ZipFile(path, "w") as z:
                    entry = zipfile.ZipInfo("placeholder")
                    entry.filename = unsafe
                    z.writestr(entry, "x")
                with self.assertRaises(ValueError): SourcePackage(path)
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("a", "x"); z.writestr("A", "y")
            with self.assertRaises(ValueError): SourcePackage(path)
            path = Path(tmp) / "link.tar"
            with tarfile.open(path, "w") as z:
                member = tarfile.TarInfo("symlink"); member.type = tarfile.SYMTYPE; member.linkname = "../outside"
                z.addfile(member)
            with self.assertRaises(ValueError): SourcePackage(path)
            board = write_board(tmp)
            with self.assertRaises(ValueError): SourcePackage(board, ImportPolicy(max_archive_members=2))
            with self.assertRaises(ValueError): SourcePackage(board, ImportPolicy(max_expanded_bytes=10))

    def test_enrichment_models_survive_archive_lifetime(self):
        files = board_files()
        files["models/j1.step"] = "ISO-10303-21;\nEND-ISO-10303-21;"
        files["steps/board/spike/board.json"] = json.dumps({"contract": "spike/board-enrichment/v1", "stackup": [
            {"name": "top", "type": "copper", "thickness_mm": .035}], "components": [{"reference": "J1", "properties": {"vendor": "Allegro"},
            "models": [{"path": "models/j1.step", "transform": [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]}]}]})
        with tempfile.TemporaryDirectory() as tmp:
            design = import_odb_design(str(write_board(tmp, files)))
        typed = DesignIRV2.from_v1(design)
        self.assertEqual(len(typed.models), 1)
        self.assertTrue(design.metadata["odb_model_assets"])

    def test_digest_tracks_directory_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_board(tmp)
            before = source_identity(path)
            self.assertEqual(before, source_identity(path))
            (path / "misc/info").write_text("UNITS=INCH")
            self.assertNotEqual(before, source_identity(path))


class HarnessTests(unittest.TestCase):
    def test_frozen_extension_host_dispatch_runs_the_extension_protocol(self):
        registry = ExtensionRegistry()
        registry.discover([ROOT / "extensions"], trusted_roots=[ROOT / "extensions"])
        actual_run = subprocess.run
        def source_host(command, **kwargs):
            self.assertEqual(command[1], "--extension-host")
            return actual_run([sys.executable, str(ROOT / "scripts/spike_worker_entry.py"), *command[1:]], **kwargs)
        with patch.object(sys, "frozen", True, create=True), patch("python.spike_core.extensions.subprocess.run", side_effect=source_host):
            result = registry.invoke("spike.harness", "harness-compile", {"harness": harness()})
        self.assertEqual(result["data"]["status"], "compiled")

    def test_assembly_bridge_requires_exact_bindings_and_pin_map(self):
        from tests.python.test_multiboard_analysis import request
        data = harness()
        data["connectors"][0]["board_binding"] = {"board_id": "board-00", "connector_id": "J1"}
        data["connectors"][1]["board_binding"] = {"board_id": "board-01", "connector_id": "J2"}
        data["wires"][0]["length_mm"] = 250
        data["wires"][0]["electrical"] = {"inductance_h": 1e-6}
        req = request(count=2, mode="coupled_harness_network")
        req["assembly"]["harnesses"][0]["pin_map"] = {"01": "A"}
        result = compile_multiboard_harness(data, req)
        self.assertEqual(result["status"], "compiled")
        data["wires"][0]["length_mm"] = 300
        with self.assertRaisesRegex(ValueError, "lengths disagree"): compile_multiboard_harness(data, req)

    def test_schema_graph_export_and_material_resistance(self):
        raw = harness()
        self.assertEqual(analyze_harness(raw)["status"], "valid")
        result = compile_harness(raw)
        self.assertAlmostEqual(result["elements"][0]["resistance_ohm"], .0168)
        self.assertEqual(validate_harness(json.loads(export_harness(raw))), validate_harness(raw))
        self.assertNotIn("splices", raw)

    def test_derived_resistance_rejects_numerical_overflow_and_underflow(self):
        for rho, length, area in [(1e308, 1e308, 1), (1e-30, 1e-12, 1e308)]:
            data = harness()
            data["wires"][0].update(length_mm=length, area_mm2=area)
            data["wires"][0]["material"]["resistivity_ohm_m"] = rho
            with self.assertRaisesRegex(ValueError, "finite positive"):
                compile_harness(data)

    def test_csv_vendor_mapping_preserves_pin_ids_and_unknown_properties(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "connections.csv"
            path.write_text('Wire,From,Cavity,To,Pin,Length,Note\nW1,J1,01,J2,A,1000,"Vendor, note"\n')
            data = import_harness(path, column_map={"wire_id": "Wire", "from_connector": "From", "from_pin": "Cavity", "to_connector": "To", "to_pin": "Pin", "length_mm": "Length"})
        self.assertEqual(data["wires"][0]["from"]["pin"], "01")
        self.assertEqual(data["wires"][0]["properties"]["source_row"]["Note"], "Vendor, note")

    def test_semantic_failures(self):
        for mutate in [lambda d: d["wires"].append(copy.deepcopy(d["wires"][0])),
                       lambda d: d["wires"][0]["to"].update(pin="missing"),
                       lambda d: d["wires"][0].update(length_mm=float("nan")),
                       lambda d: d["wires"][0].update(electrical={"resistance_ohm": -1})]:
            data = harness(); mutate(data)
            with self.assertRaises(ValueError): validate_harness(data)
        data = harness(); data["connectors"][1]["pins"][0]["net"] = "GND"
        self.assertEqual(analyze_harness(data)["issues"][0]["code"], "HARNESS_NET_SHORT")
        with self.assertRaises(ValueError): compile_harness(data)

    def test_route_capacity_and_missing_electrical_models(self):
        data = harness()
        data["routes"] = [{"id": "r", "points_mm": [[0,0,0], [2000,0,0]]}]
        data["wires"][0]["route_id"] = "r"
        self.assertEqual(analyze_harness(data)["issues"][0]["code"], "HARNESS_LENGTH_TOO_SHORT")
        data = harness(); data["wires"][0].pop("material")
        with self.assertRaisesRegex(ValueError, "unresolved"): compile_harness(data)

    def test_harness_extension_process(self):
        registry = ExtensionRegistry()
        registry.discover([ROOT / "extensions"], trusted_roots=[ROOT / "extensions"])
        result = registry.invoke("spike.harness", "harness-compile", {"harness": harness()})
        self.assertEqual(result["data"]["status"], "compiled")
        untrusted = ExtensionRegistry()
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "example"; package.mkdir()
            manifest = json.loads((ROOT / "extensions/harness-engine/spike-extension.json").read_text())
            manifest["bundled"] = False
            (package / "spike-extension.json").write_text(json.dumps(manifest))
            (package / "extension.py").write_text("raise AssertionError('must not execute')")
            untrusted.discover([tmp])
            with self.assertRaises(PermissionError): untrusted.invoke("spike.harness", "harness-compile", {"harness": harness()})


if __name__ == "__main__": unittest.main()
