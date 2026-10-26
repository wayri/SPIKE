# SPDX-License-Identifier: Apache-2.0
"""Verify retained-data packages without EMerge or any solver execution."""
import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("emerge_gallery_builder", ROOT / "examples/emerge/gallery/build.py")
gallery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gallery)


class EMergeGalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = gallery.load("examples/emerge/gallery/catalog.json")["examples"]

    def test_core_results_are_exact_and_unqualified_with_explicit_bindings(self):
        retained = [entry for entry in self.entries if entry["status"] == "retained_result"]
        self.assertEqual(len(retained), 4)
        for entry in retained:
            with self.subTest(example=entry["id"]):
                snapshot, probes, record = gallery.prepare(entry)
                self.assertEqual(snapshot["analysis"]["latest_result"], gallery.load(entry["result_path"]))
                self.assertEqual(snapshot["analysis"]["result_history"][0]["bundle"], snapshot["analysis"]["latest_result"])
                self.assertFalse(snapshot["gallery"]["execution_requested"])
                self.assertFalse(snapshot["gallery"]["production_qualified"])
                self.assertFalse(record["binding_evidence"]["result_provenance_rewritten"])
                self.assertEqual(probes["model_status"], "unvalidated")
                self.assertEqual(snapshot["analysis"]["extension_workflows"]["emerge_setup"]["python_executable"], "")

    def test_probe_values_are_exact_pointer_selected_samples_not_generated_fields(self):
        for entry in self.entries:
            snapshot, probes, _ = gallery.prepare(entry)
            result = snapshot["analysis"]["latest_result"]
            for sample in probes["samples"]:
                value = result
                for part in sample["source_pointer"].strip("/").split("/"):
                    value = value[int(part)] if isinstance(value, list) else value[part]
                if sample["kind"] == "s_parameter_matrix":
                    self.assertEqual(sample["value"], value)
                    self.assertEqual(sample["frequency_hz"], result["networks"]["s_parameters"]["frequencies_hz"][sample["frequency_index"]])
                else:
                    index = sample["sample_index"]
                    keys = ["relative_amplitude_db", "e_theta_v_m", "e_phi_v_m"] if sample["kind"] == "angular_grid_sample" else ["e_v_m", "h_a_m", "valid"]
                    for key in keys:
                        self.assertEqual(sample[key], value[key][index])
                    if sample["kind"] == "nearfield_coordinate_sample":
                        self.assertTrue(sample["valid"])
                        self.assertEqual(sample["coordinate_mm"], value["coordinates_mm"][index])
            if result and "nearfield" in result["fields"]:
                self.assertEqual(probes["nearfield_metadata"]["excitation_normalization"], result["fields"]["nearfield"]["excitation_normalization"])

    def test_attribution_and_surrogate_source_remain_explicit(self):
        entry = next(row for row in self.entries if row["id"] == "esp32-surrogate")
        snapshot, _, record = gallery.prepare(entry)
        self.assertTrue(record["binding_evidence"]["exact_historical_design_snapshot_available"])
        attribution = snapshot["gallery"]["attribution"]
        self.assertEqual(attribution["license"], "CERN-OHL-P-2.0")
        self.assertEqual(attribution["license_text"], (ROOT / "examples/esp32/source/LICENSE.md").read_text(encoding="utf-8"))
        normalized = json.loads(snapshot["design"]["source_board"])
        self.assertEqual(normalized["design"], gallery.load(entry["board_path"]))
        self.assertIn("omissions", attribution["assumptions"])

    def test_multilayer_is_explicitly_setup_only_with_both_ports(self):
        entry = next(row for row in self.entries if row["id"] == "multilayer-two-port")
        snapshot, probes, record = gallery.prepare(entry)
        self.assertIsNone(snapshot["analysis"]["latest_result"])
        self.assertEqual(snapshot["analysis"]["result_history"], [])
        self.assertEqual(probes["samples"], [])
        setup = snapshot["analysis"]["extension_workflows"]["emerge_setup"]
        self.assertEqual((setup["signal_pad_id"], setup["return_pad_id"], setup["receive_signal_pad_id"], setup["receive_return_pad_id"]), ("P1", "G1", "P2", "G2"))
        self.assertNotIn("examples/emerge/multilayer/result.json", [row["path"] for row in record["inputs"]])

    def test_esp32_form_preserves_every_retained_nonruntime_parameter(self):
        entry = next(row for row in self.entries if row["id"] == "esp32-surrogate")
        snapshot, _, _ = gallery.prepare(entry)
        expected = gallery.load(entry["config_path"])["parameters"]
        setup = snapshot["analysis"]["extension_workflows"]["emerge_setup"]
        for key, value in expected.items():
            if key == "python_executable":
                self.assertEqual(setup[key], "")
            elif key == "shorting_via_ids":
                self.assertEqual([item for item in re.split(r"[\s,]+", setup[key]) if item], value)
            elif isinstance(value, bool):
                self.assertIs(setup[key], value)
            elif isinstance(value, (int, float)):
                self.assertEqual(float(setup[key]), value)
            else:
                self.assertEqual(setup[key], value)
        self.assertEqual(setup["shorting_via_ids"], "9959768f-ffca-4046-a521-ffad7c2dfe13")
        self.assertIs(setup["fragment_copper"], False)
        self.assertNotIn("setup_replay_limitations", snapshot["gallery"])

    def test_geometry_exception_inputs_are_bounded_without_truncation(self):
        for invalid in ["via", ["one", "one"], ["bad id"], ["v" * 129], [f"v{i}" for i in range(17)], [None]]:
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                gallery.setup_for_ui({"shorting_via_ids": invalid}, {})
        with self.assertRaises(ValueError):
            gallery.setup_for_ui({"fragment_copper": "false"}, {})
        self.assertEqual(gallery.setup_for_ui({}, {})["shorting_via_ids"], "")
        self.assertIs(gallery.setup_for_ui({}, {})["fragment_copper"], True)

    def test_optional_form_defaults_do_not_invent_ports_or_override_retained_settings(self):
        defaults = gallery.setup_for_ui({}, {})
        expected = {"reference_impedance_ohm": "50", "radiation_theta_step_deg": "15",
                    "radiation_phi_step_deg": "15", "radiation_cut_phi_deg": "0",
                    "n_workers": "2", "nearfield_z_mm": "2", "nearfield_grid_points": "11"}
        for key, value in expected.items():
            self.assertEqual(defaults[key], value)
        for key in ["signal_pad_id", "return_pad_id", "receive_signal_pad_id", "receive_return_pad_id", "frequency_start_hz", "frequency_points"]:
            self.assertEqual(defaults[key], "")
        selected = gallery.setup_for_ui({"frequency_points": 7, "reference_impedance_ohm": 75},
                                        {"frequency_points": 3, "nearfield_z_mm": 1, "reference_impedance_ohm": 25})
        self.assertEqual(selected["frequency_points"], "7")
        self.assertEqual(selected["reference_impedance_ohm"], "75")
        self.assertEqual(selected["nearfield_z_mm"], "1")

    def test_changed_source_or_script_or_config_evidence_blocks_packaging(self):
        entry = self.entries[0]
        real_digest, real_load = gallery.digest, gallery.load
        for tampered in [entry["board_path"], "examples/emerge/gui_workflow/patch_simulation.py", "examples/emerge/gui_workflow/patch_result.json"]:
            with self.subTest(path=tampered), patch.object(gallery, "digest", side_effect=lambda path: "0" * 64 if path == tampered else real_digest(path)):
                with self.assertRaises(ValueError): gallery.prepare(entry)
        def changed_config(path):
            value = real_load(path)
            if path == entry["config_path"]:
                value = copy.deepcopy(value)
                value["parameters"]["frequency_points"] += 1
            return value
        with patch.object(gallery, "load", side_effect=changed_config):
            with self.assertRaisesRegex(ValueError, "Config differs"): gallery.prepare(entry)

    def test_canonical_roundtrips_are_reproducible_without_solver_processes(self):
        with tempfile.TemporaryDirectory() as folder, patch("subprocess.Popen", side_effect=AssertionError("Gallery must not launch a solver")):
            destination = Path(folder)
            first = gallery.build(destination)
            second = gallery.build(destination)
            self.assertEqual(first, second)
            self.assertFalse(first["solver_executed"])
            self.assertEqual(len(first["examples"]), 5)
            for row in first["examples"]:
                self.assertEqual(row["roundtrip"], "passed")
                for artifact in row["artifacts"]:
                    relative = Path(artifact["path"]).relative_to("examples/emerge/gallery")
                    self.assertEqual(artifact["sha256"], hashlib.sha256((destination / relative).read_bytes()).hexdigest())
                opened = gallery.request("read_project_package", path=str(destination / "projects" / (row["id"] + ".spike")))
                self.assertEqual(opened["manifest"]["format"], "spike-project-package/v3")


if __name__ == "__main__":
    unittest.main()
