# SPDX-License-Identifier: Apache-2.0
import copy
import sys
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "standalone" / "spikes_project" / "studio" / "python"))

from spikes_studio import controller_board_blocks as blocks
from spikes_studio.controller_block import validate as validate_controller
from spikes_studio.document import Document, RC_DECK


def board():
    return {
        "id": "demo", "name": "Demo", "manufacturer": "Example", "family": "Demo",
        "revision": "A", "mcu": "Example MCU", "source_urls": [], "logic_voltage_v": 3.3,
        "execution_status": "pinout_template_only", "emulation_scope": "No emulation.",
        "connector_scope": "all documented external pin headers",
        "pins": [
            {"id": "J1_1", "label": "GND", "header": "J1", "position": 1, "role": "ground", "aliases": [], "capabilities": []},
            {"id": "J1_2", "label": "ADC0", "header": "J1", "position": 2, "role": "analog", "aliases": [], "capabilities": ["analog_input"]},
            {"id": "J1_3", "label": "GPIO 1", "header": "J1", "position": 3, "role": "gpio", "aliases": [], "capabilities": ["digital_io"]},
            {"id": "J1_4", "label": "RESET", "header": "J1", "position": 4, "role": "reset", "aliases": [], "capabilities": ["system"]},
        ],
    }


def mapped_block():
    value = blocks.create(board(), 10, -4, "U1")
    value["bindings"]["J1_2"].update(mode="AI", node="sense", reference="0")
    value["bindings"]["J1_3"].update(mode="DO", source="VDRIVE")
    return value


class Element:
    def __init__(self, name, kind="voltage_source", waveform=None):
        self.name, self.kind, self.waveform = name, kind, waveform
        self.positive_node, self.negative_node = "sense", "0"
        self.semiconductor_nodes = ()
        self.control_positive_node = self.control_negative_node = None


class Project:
    def __init__(self):
        self.elements = [Element("VDRIVE"), Element("VPULSE", waveform=object())]


class ControllerBoardBlockTests(unittest.TestCase):
    def test_create_snapshots_every_pin_unbound_with_stable_names(self):
        source = board()
        first = blocks.create(source, 1, 2, scope="XTOP:XADC")
        second = blocks.create(source, 1, 2)
        source["pins"][0]["label"] = "changed"
        self.assertEqual(first["board"]["pins"][0]["label"], "GND")
        self.assertEqual(first["scope"], "XTOP:XADC")
        self.assertEqual(set(first["bindings"]), {pin["id"] for pin in first["board"]["pins"]})
        self.assertTrue(all(binding["mode"] == "NC" for binding in first["bindings"].values()))
        self.assertEqual(
            [value["code_name"] for value in first["bindings"].values()],
            [value["code_name"] for value in second["bindings"].values()],
        )

    def test_validation_rejects_duplicate_identity_coordinates_and_non_io_binding(self):
        value = blocks.create(board(), 0, 0, "U1")
        duplicate = copy.deepcopy(value); duplicate["id"] = "other"
        with self.assertRaisesRegex(ValueError, "references"):
            blocks.validate([value, duplicate])
        value["x"] = float("nan")
        with self.assertRaisesRegex(ValueError, "coordinates"):
            blocks.validate([value])
        value = blocks.create(board(), 0, 0, "U1")
        value["bindings"]["J1_1"].update(mode="DI", node="0", reference="0")
        with self.assertRaisesRegex(ValueError, "non-I/O"):
            blocks.validate([value])

    def test_validation_admits_complete_display_contract_and_exact_capabilities(self):
        value = blocks.create(board(), 0, 0, "U1")
        value["bindings"]["J1_2"].update(mode="DO", source="V1")
        with self.assertRaisesRegex(ValueError, "not declared"):
            blocks.validate([value])
        value = blocks.create(board(), 0, 0, "U1")
        value["board"]["pins"][0]["capabilities"] = ["analog_input"]
        value["bindings"]["J1_1"].update(mode="AI", node="rail", reference="0")
        with self.assertRaisesRegex(ValueError, "non-I/O"):
            blocks.validate([value])
        for field in ("name", "connector_scope"):
            value = blocks.create(board(), 0, 0, "U1")
            value["board"][field] = ""
            with self.assertRaisesRegex(ValueError, field):
                blocks.validate([value])
        value = blocks.create(board(), 0, 0, "U1")
        value["board"]["execution_status"] = "firmware_emulated"
        with self.assertRaisesRegex(ValueError, "pinout_template_only"):
            blocks.validate([value])
        input_only = blocks.create(board(), 0, 0, "U1")
        input_only["board"]["pins"][2]["capabilities"] = ["digital_input"]
        input_only["bindings"]["J1_3"].update(mode="DI", node="in", reference="0")
        blocks.validate([input_only])
        input_only["bindings"]["J1_3"].update(mode="DO", node="", reference="", source="V1")
        with self.assertRaisesRegex(ValueError, "not declared"):
            blocks.validate([input_only])

    def test_conversion_is_inert_and_matches_generic_controller_contract(self):
        value = mapped_block()
        config = blocks.controller_config(value, step_s=2e-4)
        validate_controller(config)
        self.assertEqual(config["board_block_id"], value["id"])
        self.assertEqual(config["board"], value["board"])
        self.assertIn("outputs[i] = 0.0", config["source"])
        self.assertIn("does not emulate", config["source"])
        self.assertNotIn("RESET", [pin["name"] for pin in config["pins"]])

    def test_conversion_requires_both_directions_and_at_most_64(self):
        value = blocks.create(board(), 0, 0, "U1")
        value["bindings"]["J1_2"].update(mode="AI", node="sense", reference="0")
        with self.assertRaisesRegex(ValueError, "inputs"):
            blocks.controller_config(value)

    def test_project_binding_uses_exact_nodes_and_independent_dc_sources(self):
        value = mapped_block()
        config = blocks.controller_config(value, Project())
        self.assertEqual(len(config["pins"]), 2)
        wrong = mapped_block(); wrong["bindings"]["J1_3"]["source"] = "vdrive"
        with self.assertRaisesRegex(ValueError, "exact independent"):
            blocks.controller_config(wrong, Project())
        waveform = mapped_block(); waveform["bindings"]["J1_3"]["source"] = "VPULSE"
        with self.assertRaisesRegex(ValueError, "independent DC"):
            blocks.controller_config(waveform, Project())

    def test_attachment_requires_exact_mapped_pins_but_legacy_configs_are_independent(self):
        value = mapped_block(); config = blocks.controller_config(value)
        blocks.validate_attachment(config, [value])
        changed = copy.deepcopy(config); changed["pins"][0]["node"] = "other"
        with self.assertRaisesRegex(ValueError, "no longer match"):
            blocks.validate_attachment(changed, [value])
        with self.assertRaisesRegex(ValueError, "does not exist"):
            blocks.validate_attachment(config, [])
        legacy = copy.deepcopy(config); legacy.pop("board_block_id")
        blocks.validate_attachment(legacy, [])

    def test_update_detaches_in_one_undoable_transaction_and_remove_fails_closed(self):
        document = Document.from_netlist(RC_DECK)
        value = mapped_block()
        value["bindings"]["J1_2"].update(node="out", reference="0")
        value["bindings"]["J1_3"].update(source="V1")
        blocks.add(document, value)
        config = blocks.controller_config(value)
        document.commit(lambda data: data.__setitem__("controller_setup", copy.deepcopy(config)))
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            path = Path(directory) / "attached.spikes"
            document.save(path)
            loaded = Document.load(path)
            blocks.validate_attachment(loaded.data["controller_setup"], loaded.data["controller_boards"])
        with self.assertRaisesRegex(ValueError, "Detach"):
            blocks.remove(document, value["id"])
        replacement = copy.deepcopy(value)
        replacement["bindings"]["J1_2"].update(node="in")
        blocks.update(document, value["id"], replacement)
        self.assertIsNone(document.data["controller_setup"])
        draft = document.data["metadata"]["controller_board_detached_drafts"][value["id"]]
        self.assertEqual(draft, config)
        self.assertEqual(draft["source"], config["source"])
        self.assertEqual(document.data["controller_boards"][0]["bindings"]["J1_2"]["node"], "in")
        with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as directory:
            path = Path(directory) / "detached.spikes"
            document.save(path)
            reopened = Document.load(path)
            reopened_draft = reopened.data["metadata"]["controller_board_detached_drafts"][value["id"]]
            self.assertEqual(reopened_draft["source"], config["source"])
            self.assertIsNone(reopened.data["controller_setup"])
        document.undo()
        self.assertEqual(document.data["controller_setup"], config)
        self.assertEqual(document.data["controller_boards"][0], value)
        self.assertNotIn("controller_board_detached_drafts", document.data["metadata"])

    def test_detached_draft_limit_fails_without_losing_document_state(self):
        document = Document.from_netlist(RC_DECK)
        value = mapped_block()
        value["bindings"]["J1_2"].update(node="out", reference="0")
        value["bindings"]["J1_3"].update(source="V1")
        blocks.add(document, value)
        config = blocks.controller_config(value)
        document.commit(lambda data: data.__setitem__("controller_setup", copy.deepcopy(config)))
        document.data["metadata"]["controller_board_detached_drafts"] = {
            f"old-{index}": {"source": f"preserved {index}"}
            for index in range(blocks.MAX_BLOCKS)
        }
        before = copy.deepcopy(document.data)
        replacement = copy.deepcopy(value)
        replacement["bindings"]["J1_2"]["node"] = "in"
        with self.assertRaisesRegex(ValueError, "export or explicitly remove"):
            blocks.update(document, value["id"], replacement)
        self.assertEqual(document.data, before)


if __name__ == "__main__":
    unittest.main()
