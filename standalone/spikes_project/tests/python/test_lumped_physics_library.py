# SPDX-License-Identifier: Apache-2.0
"""Studio catalog, placement, persistence and native checks for lumped parts."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio/python"))

from spikes_studio.component_catalog import catalog, native_recipe, validate_record
from spikes_studio.component_parameter_form import field_spec
from spikes_studio.document import Document
from spikes_studio.library_browser import CatalogIndex, apply_insertion, insertion_plan
from spikes_studio.library_pins import pin_contract


LIBRARY = os.environ.get("SPIKES_TEST_LIBRARY", os.environ.get("SPIKES_TEST_NATIVE_LIBRARY", ""))
EXPECTED_PINS = {
    "nmos4": ["D", "G", "S", "B"],
    "npn4": ["C", "B", "E", "SUB"],
    "resistor3": ["P", "N", "SUB"],
    "feedthrough_capacitor3": ["IN", "OUT", "GND"],
    "kelvin_shunt4": ["FP", "FN", "SP", "SN"],
}


def physics_records():
    return [record for record in catalog(include_lumped_physics=True)["records"]
            if record.get("model_type") == "lumped_physics_part_v1"]


class LumpedPhysicsLibraryTests(unittest.TestCase):
    def test_opt_in_catalog_preserves_base_and_indexes_primary_parameters(self):
        self.assertEqual(len(catalog()["records"]), 5000)
        payload = catalog(include_lumped_physics=True)
        self.assertEqual(len(payload["records"]), 5005)
        self.assertEqual(payload["counts"]["Physics models"], 5)
        self.assertEqual(payload["archetype_count"], 105)
        combined = catalog(include_passives=True, include_lumped_physics=True)
        self.assertEqual(len(combined["records"]), 7913)
        index = CatalogIndex(payload["records"])
        rows = index.query(category="Physics models", sort="Primary value")
        self.assertEqual(len(rows), 5)
        for record in rows:
            validate_record(record)
            self.assertEqual(index.values[record["id"]], record["parameters"][record["primary_parameter"]])
            self.assertEqual(record["model_status"], "generic_unqualified")
            self.assertEqual(record["origin"], "python.spikes.lumped_physics_parts established builder")

    def test_published_schema_accepts_all_records_and_rejects_weakened_physics_metadata(self):
        from jsonschema import Draft202012Validator, ValidationError

        schema_path = Path(__file__).resolve().parents[2] / "studio/schemas/component-catalog-v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        payload = json.loads(json.dumps(catalog(include_passives=True, include_lumped_physics=True), allow_nan=False))
        self.assertEqual(len(payload["records"]), 7913)
        validator.validate(payload)
        physics_index = next(index for index, record in enumerate(payload["records"])
                             if record.get("model_type") == "lumped_physics_part_v1")
        for field, replacement in (("qualification", "unqualified_presets"), ("builder_kind", None),
                                   ("primary_parameter", "invented"), ("pins", ["G", "D", "S", "B"])):
            weakened = deepcopy(payload)
            if replacement is None:
                weakened["records"][physics_index].pop(field)
            else:
                weakened["records"][physics_index][field] = replacement
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validator.validate(weakened)

    def test_builder_sources_parse_and_pin_previews_keep_exact_order(self):
        from python.spikes.netlist import parse_netlist

        for record in physics_records():
            recipe = native_recipe(record)
            pins = EXPECTED_PINS[record["family"]]
            self.assertEqual(record["pins"], pins)
            self.assertEqual(recipe["pins"], pins)
            declaration = next(line for line in recipe["source"].splitlines() if line.lower().startswith(".subckt"))
            self.assertEqual(declaration.split()[2:], pins)
            nodes = [f"n{index}" for index in range(len(pins))]
            source = recipe["source"] + "X1 " + " ".join(nodes) + " " + recipe["name"] + "\nVREF n0 0 0\n.op\n.end\n"
            self.assertTrue(parse_netlist(source, native_extensions=True).elements)
            contract = pin_contract(record)
            self.assertEqual([pin["name"] for pin in contract["pins"]], pins)
            self.assertEqual([pin["number"] for pin in contract["pins"]], [str(i) for i in range(1, len(pins) + 1)])
            self.assertIn("NOT a manufacturer package pinout", contract["numbering"])
            self.assertIn("generic_unqualified", contract["power_behavior"])

    def test_edited_parameters_rebuild_source_and_fields_keep_si_units(self):
        record = next(record for record in physics_records() if record["family"] == "resistor3")
        record["parameters"]["resistance_ohm"] = 2200
        validate_record(record)
        source = native_recipe(record)["source"]
        self.assertIn("RLEFT P MID 1100", source)
        self.assertIn("RRIGHT MID N 1100", source)
        expected_units = {
            "resistance_ohm": "ohm",
            "substrate_capacitance_f": "F",
            "threshold_voltage_v": "V",
            "transconductance_a_per_v2": "A/V^2",
            "forward_transit_time_s": "s",
            "forward_beta": "1",
        }
        for parameter, unit in expected_units.items():
            self.assertEqual(field_spec(parameter).unit, unit)

    def test_rejected_edits_and_mappings_leave_document_unchanged(self):
        record = next(record for record in physics_records() if record["family"] == "nmos4")
        document = Document.from_netlist("No mutation\nV1 d 0 1\n.op\n.end\n")
        before = deepcopy(document.data)
        bad = deepcopy(record)
        bad["parameters"]["invented_parameter"] = 1
        cases = [
            (bad, {"D": "d", "G": "0", "S": "0", "B": "0"}),
            (record, {"D": "d", "G": "0", "S": "0"}),
            (record, {"D": "bad\n.end", "G": "0", "S": "0", "B": "0"}),
        ]
        for candidate, mapping in cases:
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                insertion_plan(document, candidate, mapping)
            self.assertEqual(document.data, before)
        claimed = deepcopy(record)
        claimed["model_status"] = "qualified"
        with self.assertRaises(ValueError):
            validate_record(claimed)
        wrong_pins = deepcopy(record)
        wrong_pins["pins"] = ["G", "D", "S", "B"]
        with self.assertRaises(ValueError):
            validate_record(wrong_pins)

    def test_reviewed_placement_persists_exact_record_and_is_one_undo_step(self):
        record = next(record for record in physics_records() if record["family"] == "resistor3")
        record["parameters"]["resistance_ohm"] = 2200
        record["parameters"]["substrate_leakage_resistance_ohm"] = 1000
        document = Document.from_netlist("Place model\nV1 p 0 1\n.op\n.end\n")
        before = deepcopy(document.data)
        plan = insertion_plan(document, record, {"P": "p", "N": "n", "SUB": "sub"}, x=420, y=360)
        self.assertEqual(document.data, before)
        instance = next(line for line in plan["source"].splitlines() if line.startswith("XCAT1 "))
        self.assertEqual(instance.split()[1:4], ["p", "n", "sub"])
        evidence = plan["lumped_physics_model"]
        self.assertEqual(evidence["record"]["parameters"]["resistance_ohm"], 2200)
        self.assertEqual(evidence["pins"], ["P", "N", "SUB"])
        recipe = native_recipe(record)
        self.assertEqual(evidence["compiled_source_sha256"], hashlib.sha256(recipe["source"].encode()).hexdigest())
        apply_insertion(document, plan, record["id"])
        saved = document.data["metadata"]["lumped_physics_models"][plan["model"]]
        self.assertEqual(saved, evidence)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "placed.spksch"
            document.save(path)
            reopened = Document.load(path)
            self.assertEqual(reopened.data["metadata"]["lumped_physics_models"], document.data["metadata"]["lumped_physics_models"])
        document.undo()
        self.assertEqual(document.data, before)
        document.redo()
        self.assertEqual(document.data["metadata"]["lumped_physics_models"][plan["model"]], evidence)

    def test_lumped_definition_reuse_requires_exact_generated_source(self):
        record = next(record for record in physics_records() if record["family"] == "resistor3")
        mapping = {"P": "p", "N": "0", "SUB": "0"}
        document = Document.from_netlist("Definition ownership\nV1 p 0 1\n.op\n.end\n")
        first = insertion_plan(document, record, mapping)
        apply_insertion(document, first, record["id"])
        unchanged = deepcopy(document.data)
        second = insertion_plan(document, record, mapping)
        self.assertEqual(document.data, unchanged)
        self.assertEqual(second["source"].count(".subckt " + first["model"] + " "), 1)
        document.apply_source(document.data["source"].replace("RLEFT P MID 500", "RLEFT P MID 99"))
        edited = deepcopy(document.data)
        with self.assertRaisesRegex(ValueError, "definition conflict"):
            insertion_plan(document, record, mapping)
        self.assertEqual(document.data, edited)
        self.assertIn("RLEFT P MID 99", document.data["source"])

    def test_equation_bench_refuses_to_imply_an_independent_model(self):
        from spikes_studio.component_catalog import evaluate

        for record in physics_records():
            with self.assertRaisesRegex(ValueError, "native circuit placement"):
                evaluate(record)


@unittest.skipUnless(os.environ.get("SPIKES_TEST_WX") == "1", "Opt-in native wx library test")
class LumpedPhysicsPanelTests(unittest.TestCase):
    def test_panel_preview_and_insert_editor_use_established_record(self):
        import wx
        from spikes_studio.component_panel import ComponentPanel, InsertDialog
        from spikes_studio.document import RC_DECK
        from spikes_studio.themes import PALETTES

        app = wx.GetApp() or wx.App(False)
        owner = wx.Frame(None)
        host = wx.Panel(owner)
        owner.palette = PALETTES["Light"]
        owner.doc = Document.from_netlist(RC_DECK)
        owner.pin_browser = lambda: None
        owner.open_physics_models = lambda: None
        owner.guarded = lambda callback: callback()
        owner.update_title = lambda: None
        owner.assign_part_shortcut = lambda _ident: None
        panel = ComponentPanel(owner, host)
        dialog = None
        try:
            self.assertEqual(len(panel.catalog["records"]), 7918)
            panel.search.ChangeValue("id:physics.lumped.nmos4")
            panel.filter()
            panel.list.SetSelection(0)
            panel.select()
            self.assertEqual(panel.record["family"], "nmos4")
            self.assertIn("generic_unqualified", panel.details.GetValue())
            self.assertIn(".subckt SPK_physics_lumped_nmos4 D G S B", panel.recipe.GetValue())
            self.assertIn("threshold_voltage_v", panel.parameters.fields)
            dialog = InsertDialog(panel, panel.record)
            self.assertEqual(list(dialog.pins), ["D", "G", "S", "B"])
            dialog.parameter_fields["threshold_voltage_v"].SetValue("1.25")
            edited = dialog.edited_record()
            self.assertEqual(edited["parameters"]["threshold_voltage_v"], 1.25)
            self.assertIn("VTO=1.25", native_recipe(edited)["source"])
        finally:
            if dialog:
                dialog.Destroy()
            panel.Destroy()
            host.Destroy()
            owner.Destroy()
            wx.Yield()


@unittest.skipUnless(LIBRARY and Path(LIBRARY).is_file(), "Current native library is not configured")
class NativeLumpedPhysicsLibraryTests(unittest.TestCase):
    def test_all_five_catalog_recipes_execute_in_native_operating_point(self):
        from python.spikes.native_runner import run_native_project
        from python.spikes.netlist import parse_netlist

        tails = {
            "nmos4": "X1 d 0 0 0 {name}\nV1 d 0 1",
            "npn4": "X1 c 0 0 0 {name}\nV1 c 0 1",
            "resistor3": "X1 p 0 0 {name}\nV1 p 0 1",
            "feedthrough_capacitor3": "X1 input output 0 {name}\nV1 input 0 1\nRLOAD output 0 1",
            "kelvin_shunt4": "X1 fp 0 sp sn {name}\nV1 fp 0 1",
        }
        for record in physics_records():
            recipe = native_recipe(record)
            source = recipe["source"] + tails[record["family"]].format(name=recipe["name"]) + "\n.op\n.end\n"
            result = run_native_project(parse_netlist(source, native_extensions=True), LIBRARY).to_dict()
            self.assertEqual(result["status"], "completed", (record["id"], result))


if __name__ == "__main__":
    unittest.main()
