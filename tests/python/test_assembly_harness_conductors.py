# SPDX-License-Identifier: Apache-2.0
"""Assembly metadata uses the same conductor admission boundary as documents."""
import copy
import tempfile
from pathlib import Path
import unittest

from python.spike_core.harness_authoring import validate_harness_connections
from python.spike_core.spider_v2 import AssemblyIRV1
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.service_project_handlers import handle_project_request
from tests.python import test_assembly_designs


KEY = "spike.harness-conductors"


def fixture():
    first, _, assembly, retained = test_assembly_designs.AssemblyDesignTests().fixture()
    h = assembly["harnesses"][0]
    h["pin_map"] = {"1": "1", "2": "2"}
    h["extensions"] = {"vendor.opaque": {"data": [1, 2]}, KEY: {
        "contract": "spike/assembly-harness-conductors/v1", "wires": [
            {"id": "p", "from_pin": "1", "to_pin": "1", "role": "signal", "length_mm": 125},
            {"id": "n", "from_pin": "2", "to_pin": "2", "role": "signal", "length_mm": 125}],
        "pairs": [{"id": "d", "wire_ids": ["p", "n"], "kind": "differential", "twisted": True, "twist_pitch_mm": 20}],
        "cables": [{"id": "c", "wire_ids": ["p", "n"]}], "analysis_extensions": {"vendor.analysis": {"source": "user"}}}}
    return first, assembly, retained


class AssemblyConductorTests(unittest.TestCase):
    def test_roundtrip_and_legacy_absence_preserve_outer_extensions(self):
        _, raw, _ = fixture()
        expected = copy.deepcopy(raw)
        assembly = AssemblyIRV1.from_dict(raw)
        validate_harness_connections(assembly)
        self.assertEqual(raw, expected)
        self.assertEqual(assembly.to_dict()["harnesses"][0]["extensions"], raw["harnesses"][0]["extensions"])
        del raw["harnesses"][0]["extensions"][KEY]
        validate_harness_connections(AssemblyIRV1.from_dict(raw))

    def test_stale_duplicate_pair_and_cable_rejected(self):
        for case, code in (("stale", "PIN_MAP"), ("missing", "PIN_MAP"), ("duplicate_pin", "PIN_MAP"),
                           ("duplicate_id", "Duplicate wires"), ("pair_role", "PAIR_ROLE"),
                           ("mixed_cable", "PAIR_CABLE"), ("return", "RETURN_REFERENCE"),
                           ("endpoint_override", "PIN_MAP"), ("contract", "CONTRACT")):
            _, raw, _ = fixture()
            data = raw["harnesses"][0]["extensions"][KEY]
            if case == "stale": data["wires"][0]["to_pin"] = "2"
            if case == "missing": data["wires"].pop()
            if case == "duplicate_pin": data["wires"][1].update(from_pin="1", to_pin="1")
            if case == "duplicate_id": data["wires"][1]["id"] = "p"
            if case == "pair_role": data["wires"][0]["role"] = "power"
            if case == "mixed_cable": data["cables"][0]["wire_ids"] = ["p"]
            if case == "return": data["wires"][0]["return_wire_id"] = "absent"
            if case == "endpoint_override": data["wires"][0]["from"] = {"connector": "other", "pin": "1"}
            if case == "contract": data["contract"] = "unknown"
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, code):
                validate_harness_connections(AssemblyIRV1.from_dict(raw))

    def test_save_validates_metadata_and_rejects_stale_without_writing(self):
        first, assembly, retained = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conductors.spike"
            manifest = write_spike_package(path, {"project": {"id": "edit"}, "design_ir": first,
                                                 "assembly_ir": assembly, "assembly_designs": retained})
            params = {"project_path": str(path), "expected_manifest_payload_sha256": manifest["manifest_payload_sha256"],
                      **{key: copy.deepcopy(assembly.get(key, [])) for key in ("boards", "harnesses", "connector_mappings", "rigid_flex_links")}}
            params["harnesses"][0]["extensions"][KEY]["pairs"][0]["twist_pitch_mm"] = 25
            result = handle_project_request("update_assembly_structure_in_project", params, request_id="save", application_version="test")
            self.assertTrue(result["ok"], result)
            restored = read_project(path)
            self.assertEqual(restored.payload["assembly_ir"]["harnesses"][0]["extensions"], params["harnesses"][0]["extensions"])
            params["expected_manifest_payload_sha256"] = result["result"]["manifest"]["manifest_payload_sha256"]
            params["harnesses"][0]["pin_map"] = {"1": "2", "2": "1"}
            before = path.read_bytes()
            result = handle_project_request("update_assembly_structure_in_project", params, request_id="stale", application_version="test")
            self.assertFalse(result["ok"], result)
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
