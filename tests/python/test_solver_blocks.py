# SPDX-License-Identifier: Apache-2.0
"""Contract and graph behavior for inert solver-block planning."""
import re
import json
import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from python.spike_core.solver_blocks import (
    BLOCKS, handle_solver_blocks, solver_blocks_catalog, validate_graph,
)


class SolverBlockTests(unittest.TestCase):
    def test_default_selects_every_bundled_block_without_install_claims(self):
        result = solver_blocks_catalog()
        self.assertEqual(result["contract"], "spike/solver-blocks/v1")
        from python.spike_core import __version__
        self.assertEqual(result["catalog_version"], __version__)
        self.assertEqual(result["packaging_mode"], "bundled_all")
        self.assertFalse(result["managed_downloads"])
        expected = {block["id"] for block in BLOCKS if block["delivery"] == "bundled"}
        self.assertEqual(set(result["plan"]["requested_blocks"]), expected)
        self.assertEqual(result["plan"]["action"], "preview_only")
        self.assertTrue(all("installed" not in block for block in result["blocks"]))

    def test_explicit_empty_selection_keeps_only_mandatory_base(self):
        for params in ({"selected_blocks": []}, {"selected_groups": []}):
            plan = solver_blocks_catalog(params)["plan"]
            self.assertEqual(plan["requested_blocks"], [])
            self.assertEqual(plan["ordered_blocks"], ["core"])
            self.assertEqual(plan["required_blocks"], ["core"])

    def test_group_bulk_union_and_dependency_order(self):
        result = solver_blocks_catalog({"selected_groups": ["harness", "mcad"]})
        plan = result["plan"]
        self.assertIn("harness-adapter", plan["requested_blocks"])
        self.assertIn("mcad-adapter", plan["requested_blocks"])
        self.assertIn("si-networks", plan["required_blocks"])
        positions = {identifier: position for position, identifier in enumerate(plan["ordered_blocks"])}
        for block in result["blocks"]:
            if block["id"] in positions:
                for dependency in block["requires"]:
                    self.assertLess(positions[dependency], positions[block["id"]])
        self.assertEqual(len(positions), len(plan["ordered_blocks"]))

    def test_cross_domain_cht_preserves_runtime_and_geometry_gates(self):
        plan = solver_blocks_catalog({"selected_blocks": ["cht-assembly"]})["plan"]
        self.assertTrue({"mesh", "geometry", "materials", "thermal-solids", "external-openfoam"} <= set(plan["required_blocks"]))
        self.assertEqual(plan["blocked_blocks"], ["external-openfoam", "thermal-openfoam", "cht-assembly"])
        self.assertNotIn("cfd-native", plan["ordered_blocks"])

    def test_concrete_thermal_backends_are_independently_selectable(self):
        plan = solver_blocks_catalog({"selected_blocks": ["thermal-calculix"]})["plan"]
        self.assertIn("external-calculix", plan["required_blocks"])
        self.assertNotIn("external-openfoam", plan["ordered_blocks"])
        self.assertNotIn("thermal-openfoam", plan["ordered_blocks"])
        index_plan = solver_blocks_catalog({"selected_blocks": ["thermal-external"]})["plan"]
        self.assertEqual(index_plan["ordered_blocks"], ["core", "thermal-external"])
        index = validate_graph(BLOCKS)
        self.assertEqual(set(index["external-calculix"]["groups"]), {"thermal", "mechanics"})
        self.assertEqual(set(index["external-openfoam"]["groups"]), {"thermal", "cfd", "cht"})

    def test_freecad_is_a_separate_optional_external_application(self):
        plan = solver_blocks_catalog({"selected_blocks": ["mcad-adapter"]})["plan"]
        self.assertNotIn("external-freecad", plan["ordered_blocks"])
        plan = solver_blocks_catalog({"selected_blocks": ["mcad-freecad"]})["plan"]
        self.assertEqual(plan["blocked_blocks"], ["external-freecad", "mcad-freecad"])
        engine = validate_graph(BLOCKS)["external-freecad"]
        self.assertEqual(engine["delivery"], "external")
        self.assertEqual(engine["groups"], ["mcad"])

    def test_optional_edges_do_not_force_install_selection(self):
        plan = solver_blocks_catalog({"selected_blocks": ["execution-cosim"]})["plan"]
        self.assertEqual(plan["ordered_blocks"], ["core", "execution-cosim"])

    def test_external_and_planned_never_become_available_by_selection(self):
        result = solver_blocks_catalog({"selected_blocks": ["em-openems", "planned-fullwave"]})
        self.assertTrue({"external-openems", "em-openems", "planned-fullwave"} <= set(result["plan"]["blocked_blocks"]))
        engine = next(block for block in result["blocks"] if block["id"] == "external-openems")
        self.assertEqual(engine["delivery"], "external")
        self.assertTrue(engine["external_requirements"])

    def test_unknown_or_malformed_selection_fails_closed(self):
        bad = [[], {"selected_blocks": None}, {"selected_blocks": "core"},
               {"selected_blocks": [True]}, {"selected_groups": ["missing"]},
               {"selected_blocks": ["missing"]}, {"install": True}]
        for params in bad:
            with self.subTest(params=params), self.assertRaises(ValueError):
                solver_blocks_catalog(params)
        response = handle_solver_blocks({"selected_blocks": ["missing"]})
        self.assertFalse(response["ok"])
        self.assertIsInstance(response["error"], str)
        self.assertEqual(response["error_detail"]["code"], "SPIKE-BE-IPC-E-0001")
        self.assertFalse(handle_solver_blocks(None)["ok"])

    def test_json_line_worker_keeps_error_recovery_and_dependency_plan(self):
        requests = [
            {"id": "bad-block", "method": "solver_blocks", "params": {"selected_blocks": ["missing"]}},
            {"id": "cht-plan", "method": "solver_blocks", "params": {"selected_blocks": ["cht-assembly"]}},
        ]
        process = subprocess.run([sys.executable, "-m", "python.spike_core.service"],
                                 cwd=Path(__file__).resolve().parents[2],
                                 input="\n".join(json.dumps(item) for item in requests) + "\n",
                                 capture_output=True, text=True, timeout=30, check=True)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual([item["id"] for item in responses], ["bad-block", "cht-plan"])
        self.assertFalse(responses[0]["ok"])
        self.assertIsInstance(responses[0]["error"], str)
        self.assertEqual(responses[0]["error_detail"]["code"], "SPIKE-BE-IPC-E-0001")
        self.assertTrue(responses[1]["ok"])
        self.assertIn("external-openfoam", responses[1]["result"]["plan"]["required_blocks"])

    def test_invalid_graphs_rejected_even_outside_selection(self):
        for kind in ("cycle", "unknown", "duplicate", "optional_cycle"):
            blocks = deepcopy(BLOCKS)
            if kind == "cycle":
                blocks[0]["requires"] = ["geometry"]
            elif kind == "optional_cycle":
                blocks[0]["optional"] = ["geometry"]
            elif kind == "unknown":
                blocks[0]["requires"] = ["missing"]
            else:
                blocks.append(deepcopy(blocks[0]))
            with self.subTest(kind=kind), patch("python.spike_core.solver_blocks.BLOCKS", blocks):
                with self.assertRaises(ValueError):
                    solver_blocks_catalog({"selected_blocks": []})

    def test_bundled_snapshot_matches_python_authority(self):
        snapshot = Path(__file__).resolve().parents[2] / "app/src/solverBlockCatalogSnapshot.json"
        self.assertEqual(json.loads(snapshot.read_text(encoding="utf-8")), solver_blocks_catalog())

    def test_every_suite_capability_maps_once(self):
        source = (Path(__file__).resolve().parents[2] / "app/src/solverSuiteCatalog.ts").read_text(encoding="utf-8")
        expected = re.findall(r'\{ id: "([^"]+)", title:', source)
        actual = [identifier for block in BLOCKS for identifier in block["capability_ids"]]
        self.assertCountEqual(actual, expected)
        self.assertEqual(len(actual), len(set(actual)))
        validate_graph(BLOCKS)

    def test_worker_dispatch_and_returned_catalog_are_isolated(self):
        from python.spike_core.service import handle
        result = handle({"method": "solver_blocks", "params": {"selected_blocks": []}})
        self.assertTrue(result["ok"])
        result["result"]["blocks"][0]["requires"].append("bad")
        self.assertEqual(solver_blocks_catalog({"selected_blocks": []})["plan"]["ordered_blocks"], ["core"])


if __name__ == "__main__":
    unittest.main()
