# SPDX-License-Identifier: Apache-2.0
"""Focused projection checks for source-authoritative reusable subcircuits."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[4]
NATIVE_LIBRARY = ROOT / "build-spikes-native-analysis-20261013/Release/spikes_c_api.dll"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "standalone/spikes_project/studio/python"))

from spikes_studio.component_package import insert, new_component, prepare_insert
from spikes_studio.document import Document
from spikes_studio.editor_geometry import terminal, transform
from spikes_studio.pin_geometry import pins
from spikes_studio.reusable_block_projection import (
    move_selected,
    internal_block_wire,
    pin_overrides,
    projection_report,
    projected_blocks,
    projected_route,
    resolve_selection,
    rotate_selected,
    validate_projection,
)


TOP = """Projection test
V1 input 0 1
RLOAD output 0 1k
.op
.end
"""


def rc_package():
    value = new_component()
    value["id"] = "user.rc_cell"
    value["name"] = "RC cell"
    value["implementation"]["entry"] = "RCCell"
    value["implementation"]["source"] = (
        ".subckt RCCell IN OUT\n"
        "R1 IN MID 1k\n"
        "C1 MID OUT 1u\n"
        ".ends RCCell\n"
    )
    return value


def add(document, mapping, position, package=None):
    package = package or rc_package()
    plan = prepare_insert(document, package, mapping, position)
    insert(document, plan)
    return plan


class ReusableBlockProjectionTests(unittest.TestCase):
    def test_two_occurrences_keep_isolated_native_members_and_actual_port_maps(self):
        document = Document.from_netlist(TOP)
        add(document, {"1": "input", "2": "output"}, (300, 200))
        add(document, {"1": "second_in", "2": "second_out"}, (700, 400))

        blocks = projected_blocks(document.data)
        self.assertEqual([block["ref"] for block in blocks], ["XCMP1", "XCMP2"])
        self.assertEqual([block["nodes"] for block in blocks],
                         [["input", "output"], ["second_in", "second_out"]])
        self.assertTrue(set(blocks[0]["member_ids"]).isdisjoint(blocks[1]["member_ids"]))
        self.assertEqual(resolve_selection(document.data, {blocks[0]["id"]}),
                         set(blocks[0]["member_ids"]))
        self.assertTrue(all(binding is not None for block in blocks for binding in block["pin_bindings"]))
        self.assertIn("xcmp1:mid", {node.casefold() for part in document.data["components"]
                                    for node in part["nodes"]})
        self.assertIn("xcmp2:mid", {node.casefold() for part in document.data["components"]
                                    for node in part["nodes"]})

    def test_move_rotate_undo_save_and_reopen_preserve_authoritative_topology(self):
        document = Document.from_netlist(TOP)
        add(document, {"1": "input", "2": "output"}, (310, 220))
        block = projected_blocks(document.data)[0]
        source = document.data["source"]
        nodes = {part["id"]: list(part["nodes"]) for part in document.data["components"]}
        origins = {part["id"]: (part["x"], part["y"]) for part in document.data["components"]
                   if part["id"] in block["member_ids"]}

        move_selected(document, {block["id"]}, (40, -30))
        moved = projected_blocks(document.data)[0]
        self.assertEqual((moved["x"], moved["y"]), (350, 190))
        for ident, (x, y) in origins.items():
            part = next(part for part in document.data["components"] if part["id"] == ident)
            self.assertEqual((part["x"], part["y"]), (x + 40, y - 30))
        rotate_selected(document, {block["id"]})
        self.assertEqual(projected_blocks(document.data)[0]["rotation"], 90)
        self.assertEqual(document.data["source"], source)
        self.assertEqual({part["id"]: part["nodes"] for part in document.data["components"]}, nodes)

        document.undo()
        self.assertEqual(projected_blocks(document.data)[0]["rotation"], 0)
        document.undo()
        self.assertEqual((projected_blocks(document.data)[0]["x"],
                          projected_blocks(document.data)[0]["y"]), (310, 220))
        document.redo(); document.redo()
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "projection.spksch"
            document.save(path)
            reopened = Document.load(path)
        reopened_block = projected_blocks(reopened.data)[0]
        self.assertEqual((reopened_block["x"], reopened_block["y"], reopened_block["rotation"]),
                         (350, 190, 90))
        self.assertEqual(reopened.data["source"], source)

    def test_real_native_wire_endpoint_draws_at_projected_public_pin(self):
        document = Document.from_netlist(TOP)
        add(document, {"1": "input", "2": "output"}, (420, 260))
        block = projected_blocks(document.data)[0]
        external = next(part for part in document.data["components"] if part["ref"] == "V1")
        endpoint = block["pin_bindings"][0]
        document.connect_endpoints([external["id"], 0], endpoint)
        wire = document.data["wires"][-1]
        parts_by_id = {part["id"]: part for part in document.data["components"]}
        overrides = pin_overrides([block])
        route = projected_route(parts_by_id, wire, {}, overrides)
        public_pin = pins(block)[0]
        expected = transform(block, *public_pin.anchor)
        self.assertIn(expected, (route[0], route[-1]))
        native = terminal(parts_by_id[endpoint[0]], endpoint[1])
        self.assertNotEqual(native, expected)
        self.assertEqual(document.data["source"].count("XCMP1 "), 1)

    def test_all_public_net_aliases_project_and_internal_block_wires_stay_hidden(self):
        package = rc_package()
        package["implementation"]["source"] = (
            ".subckt RCCell IN OUT\nR1 IN MID 1k\nR2 IN OUT 4k\n"
            "C1 MID OUT 1u\n.ends RCCell\n")
        document = Document.from_netlist(TOP)
        add(document, {"1": "input", "2": "output"}, (420, 260), package)
        block = projected_blocks(document.data)[0]
        self.assertGreaterEqual(len(block["pin_aliases"][0]), 2)
        external = next(part for part in document.data["components"] if part["ref"] == "V1")
        non_primary = block["pin_aliases"][0][1]
        document.connect_endpoints([external["id"], 0], non_primary)
        wire = document.data["wires"][-1]
        parts = {part["id"]: part for part in document.data["components"]}
        route = projected_route(parts, wire, {}, pin_overrides([block]))
        self.assertIn(transform(block, *pins(block)[0].anchor), (route[0], route[-1]))

        document.connect_endpoints(block["pin_aliases"][0][0], non_primary)
        self.assertTrue(internal_block_wire(document.data["wires"][-1], [block], {}))

    def test_ambiguous_duplicate_ports_private_crossing_and_edited_body_fall_back_flat(self):
        duplicate = Document.from_netlist(TOP)
        add(duplicate, {"1": "input", "2": "input"}, (420, 260))
        report = projection_report(duplicate.data)
        self.assertEqual(report["blocks"], [])
        self.assertIn("multiple public pins", report["diagnostics"][0])

        edited = Document.from_netlist(TOP)
        add(edited, {"1": "input", "2": "output"}, (420, 260))
        edited.apply_source(edited.data["source"].replace("R1 IN MID 1k", "R1 IN MID 2k"))
        report = projection_report(edited.data)
        self.assertEqual(report["blocks"], [])
        self.assertIn("package source differs", report["diagnostics"][0])

        private = Document.from_netlist(TOP)
        add(private, {"1": "input", "2": "output"}, (420, 260))
        block = projected_blocks(private.data)[0]
        member_ids = set(block["member_ids"])
        internal = next((part["id"], index) for part in private.data["components"]
                        if part["id"] in member_ids for index, node in enumerate(part["nodes"])
                        if node.casefold() == "xcmp1:mid")
        outside = next(part for part in private.data["components"] if part["ref"] == "V1")
        private.connect_endpoints([outside["id"], 0], block["pin_bindings"][0])
        # Exercise fail-safe admission against malformed/stale saved drawing
        # metadata without asking Document to accept an invented connection.
        private.data["wires"][-1]["b"] = list(internal)
        report = projection_report(private.data)
        self.assertEqual(report["blocks"], [])
        self.assertIn("cross-boundary wire on a private", report["diagnostics"][0])

    def test_projection_metadata_fails_closed_without_mutating_input(self):
        valid = {"x": 1, "y": 2, "rotation": 0, "mirror_x": False, "mirror_y": False}
        original = deepcopy(valid)
        self.assertEqual(validate_projection(valid), valid)
        self.assertEqual(valid, original)
        for invalid in ({**valid, "extra": 1}, {**valid, "rotation": 45},
                        {**valid, "mirror_x": 0}, {**valid, "x": float("inf")}):
            with self.assertRaises(ValueError):
                validate_projection(invalid)

    def test_stale_pin_mapping_falls_back_to_native_flattened_display(self):
        document = Document.from_netlist(TOP)
        add(document, {"1": "input", "2": "output"}, (420, 260))
        document.data["metadata"]["component_instances"][0]["pins"]["1"] = "wrong"
        with self.assertRaisesRegex(ValueError, "differs from native hierarchy"):
            projected_blocks(document.data)
        report = projection_report(document.data)
        self.assertEqual(report["blocks"], [])
        self.assertIn("differs from native hierarchy", report["diagnostics"][0])

    @unittest.skipUnless(NATIVE_LIBRARY.is_file(), "Native library required")
    def test_wrapper_insert_is_native_rc_equivalent_to_flat_primitives(self):
        from spikes_studio.run_control import native_batch
        flat = ("Flat RC\nV1 input 0 PULSE(0 1 0 1u 1u 10m 20m)\n"
                "R1 input mid 1k\nC1 mid output 1u\nRLOAD output 0 1k\n"
                ".tran 10u 1m uic\n.end\n")
        wrapper = Document.from_netlist(
            "Wrapped RC\nV1 input 0 PULSE(0 1 0 1u 1u 10m 20m)\n"
            "RLOAD output 0 1k\n.tran 10u 1m uic\n.end\n")
        add(wrapper, {"1": "input", "2": "output"}, (420, 260))
        before = native_batch(flat, str(NATIVE_LIBRARY))
        after = native_batch(wrapper.data["source"], str(NATIVE_LIBRARY))
        self.assertEqual(before["data"]["time_s"], after["data"]["time_s"])
        for left, right in zip(before["data"]["node_voltage_v"]["output"],
                               after["data"]["node_voltage_v"]["output"]):
            self.assertAlmostEqual(left, right, places=12)
        for left, right in zip(before["data"]["node_voltage_v"]["mid"],
                               after["data"]["node_voltage_v"]["xcmp1:mid"]):
            self.assertAlmostEqual(left, right, places=12)


@unittest.skipUnless(os.environ.get("SPIKES_TEST_WX") == "1", "opt-in native wx")
class ReusableBlockProjectionUiTests(unittest.TestCase):
    def test_compact_hit_pins_and_double_click_enter_real_hierarchy(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.hierarchy_views import parent

        app = wx.GetApp() or wx.App(False)
        frame = Studio()
        try:
            frame.doc = Document.from_netlist(TOP)
            add(frame.doc, {"1": "input", "2": "output"}, (420, 260))
            frame.refresh_document(force_source=True); frame.Show(); wx.Yield()
            frame.canvas.Refresh(); frame.canvas.Update(); wx.Yield()
            block = frame.canvas.reusable_blocks()[0]
            self.assertEqual({part["ref"] for part in frame.canvas.visible_parts()}, {"V1", "RLOAD"})
            hit = next(rect for rect, item in frame.canvas.hits if item["id"] == block["id"])
            expected = {(endpoint[0], endpoint[1]) for endpoint in block["pin_bindings"] if endpoint}
            actual = {(part_id, index) for point, part_id, index in frame.canvas.wire_pins}
            self.assertTrue(expected <= actual)
            event = wx.MouseEvent(wx.wxEVT_LEFT_DCLICK)
            event.SetPosition(wx.Point(hit.x + hit.width // 2, hit.y + hit.height // 2))
            frame.canvas.double_click(event); wx.Yield()
            self.assertEqual(frame.canvas.sheet_scope, block["ref"])
            self.assertTrue(all(part["ref"].startswith(block["ref"] + ":")
                                for part in frame.canvas.visible_parts()))
            parent(frame)
            self.assertIsNone(frame.canvas.sheet_scope)
        finally:
            frame.timer.Stop(); frame.autosave_timer.Stop(); frame.Destroy(); wx.Yield()


if __name__ == "__main__":
    unittest.main()
