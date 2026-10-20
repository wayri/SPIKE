# SPDX-License-Identifier: Apache-2.0
"""Catalog, placement, persistence and native checks for packaged generic devices."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio/python"))

from spikes_studio.component_catalog import catalog, evaluate, native_recipe, validate_record
from spikes_studio.document import Document
from spikes_studio.library_browser import CatalogIndex, apply_insertion, insertion_plan
from spikes_studio.library_pins import pin_contract


LIBRARY = os.environ.get("SPIKES_TEST_LIBRARY", os.environ.get("SPIKES_TEST_NATIVE_LIBRARY", ""))
EXPECTED_PINS = {
    "packaged_nmos4": ["D", "G", "S", "B"],
    "packaged_npn4": ["C", "B", "E", "SUB"],
    "packaged_resistor3": ["P", "N", "SUB"],
    "packaged_kelvin_shunt4": ["FP", "FN", "SP", "SN"],
    "packaged_feedthrough_capacitor3": ["IN", "OUT", "GND"],
}
EXACT_PINS = {
    "packaged_nmos4": ["B"],
    "packaged_npn4": ["SUB"],
    "packaged_resistor3": ["SUB"],
    "packaged_kelvin_shunt4": ["SP", "SN"],
    "packaged_feedthrough_capacitor3": ["GND"],
}


def packaged_records():
    return [record for record in catalog(include_packaged_devices=True)["records"]
            if record.get("model_type") == "packaged_lumped_device_v1"]


class PackagedDeviceLibraryTests(unittest.TestCase):
    def test_opt_in_is_bounded_and_primary_index_uses_explicit_package_inductance(self):
        self.assertEqual(len(catalog()["records"]), 5000)
        payload = catalog(include_packaged_devices=True)
        self.assertEqual(len(payload["records"]), 5005)
        self.assertEqual(payload["counts"]["Physics models"], 5)
        self.assertEqual(payload["archetype_count"], 105)
        combined = catalog(include_passives=True, include_lumped_physics=True,
                           include_packaged_devices=True)
        self.assertEqual(len(combined["records"]), 7918)
        index = CatalogIndex(payload["records"])
        rows = index.query(category="Physics models", sort="Primary value")
        self.assertEqual({row["id"] for row in rows}, {
            "physics.packaged.nmos4", "physics.packaged.npn4",
            "physics.packaged.resistor3", "physics.packaged.kelvin_shunt4",
            "physics.packaged.feedthrough_capacitor3",
        })
        for record in rows:
            validate_record(record)
            self.assertEqual(index.values[record["id"]], 1e-9)
            self.assertEqual(record["model_status"], "generic_unqualified")
            self.assertIn("device_parasitics established composition", record["origin"])

    def test_schema_accepts_combined_catalog_and_rejects_weakened_package_contract(self):
        from jsonschema import Draft202012Validator, ValidationError

        schema_path = Path(__file__).resolve().parents[2] / "studio/schemas/component-catalog-v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        payload = json.loads(json.dumps(catalog(
            include_passives=True, include_lumped_physics=True,
            include_packaged_devices=True), allow_nan=False))
        validator.validate(payload)
        index = next(i for i, record in enumerate(payload["records"])
                     if record.get("model_type") == "packaged_lumped_device_v1")
        for field, replacement in (
            ("qualification", "unqualified_presets"),
            ("package_builder", None),
            ("core_builder_kind", "npn4"),
            ("primary_parameter", "threshold_voltage_v"),
            ("pins", ["G", "D", "S", "B"]),
        ):
            weakened = deepcopy(payload)
            if replacement is None:
                weakened["records"][index].pop(field)
            else:
                weakened["records"][index][field] = replacement
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validator.validate(weakened)
        feedthrough_index = next(i for i, record in enumerate(payload["records"])
                                 if record.get("id") == "physics.packaged.feedthrough_capacitor3")
        leaked_core_parameter = deepcopy(payload)
        leaked_core_parameter["records"][feedthrough_index]["parameters"]["capacitance_f"] = 2e-9
        with self.assertRaises(ValidationError):
            validator.validate(leaked_core_parameter)

    def test_sources_compose_core_and_package_with_exact_topology_and_pin_order(self):
        from python.spikes.netlist import parse_netlist

        for record in packaged_records():
            edited = deepcopy(record)
            edited["parameters"]["series_resistance_ohm"] = 2.0
            edited["parameters"]["series_inductance_h"] = 3e-9
            edited["parameters"]["parallel_capacitance_f"] = 4e-12
            recipe = native_recipe(edited)
            pins = EXPECTED_PINS[record["family"]]
            self.assertEqual(recipe["pins"], pins)
            self.assertEqual(recipe["source"].lower().count(".subckt "), 2)
            self.assertIn("RPKG1", recipe["source"])
            self.assertIn("LPKG1", recipe["source"])
            self.assertIn("CPKG1", recipe["source"])
            for exact_pin in EXACT_PINS[record["family"]]:
                index = pins.index(exact_pin) + 1
                self.assertIn(f"VPKG{index} {exact_pin} __SPK_CORE_{index} 0", recipe["source"])
            nodes = [f"n{i}" for i in range(len(pins))]
            project = parse_netlist(
                recipe["source"] + "X1 " + " ".join(nodes) + " " + recipe["name"]
                + "\nVREF n0 0 0\n.op\n.end\n", native_extensions=True,
            )
            self.assertTrue(any(element.kind == "inductor" for element in project.elements))
            self.assertTrue(any(element.kind == "capacitor" for element in project.elements))
            contract = pin_contract(record)
            self.assertEqual([pin["name"] for pin in contract["pins"]], pins)
            self.assertIn("NOT a manufacturer package pinout", contract["numbering"])
            self.assertIn("exact-linked", contract["power_behavior"])

        feedthrough = next(record for record in packaged_records()
                           if record["family"] == "packaged_feedthrough_capacitor3")
        self.assertEqual(set(feedthrough["parameters"]), {
            "series_resistance_ohm", "series_inductance_h", "parallel_capacitance_f",
        })
        feedthrough_source = native_recipe(feedthrough)["source"]
        self.assertIn("RSER IN MID 0.01", feedthrough_source)
        self.assertIn("CBODY MID GND 1.0000000000000001e-09", feedthrough_source)
        self.assertIn("inner core uses its established illustrative defaults", feedthrough["limitations"])
        invalid = deepcopy(feedthrough)
        invalid["parameters"]["capacitance_f"] = 2e-9
        with self.assertRaises(ValueError):
            validate_record(invalid)

    def test_zero_package_uses_only_exact_links_and_rejected_edits_are_atomic(self):
        from python.spikes.netlist import parse_netlist

        for record in packaged_records():
            zero = deepcopy(record)
            for name in ("series_resistance_ohm", "series_inductance_h", "parallel_capacitance_f"):
                zero["parameters"][name] = 0.0
            recipe = native_recipe(zero)
            wrapper = recipe["source"].split("* Original SPIKE generic unqualified constant package-parasitic wrapper", 1)[1]
            self.assertNotIn("\nRPKG", wrapper)
            self.assertNotIn("\nLPKG", wrapper)
            self.assertNotIn("\nCPKG", wrapper)
            self.assertEqual(wrapper.count("\nVPKG"), len(recipe["pins"]))
            nodes = ["n" + str(index) for index in range(len(recipe["pins"]))]
            self.assertTrue(parse_netlist(
                recipe["source"] + "X1 " + " ".join(nodes) + f" {recipe['name']}\nV1 n0 0 1\n.op\n.end\n",
                native_extensions=True,
            ).elements)

        record = packaged_records()[0]

        document = Document.from_netlist("No mutation\nV1 d 0 1\n.op\n.end\n")
        before = deepcopy(document.data)
        invalid = deepcopy(record)
        invalid["parameters"]["series_inductance_h"] = -1
        cases = (
            (invalid, {"D": "d", "G": "0", "S": "0", "B": "0"}),
            (record, {"D": "d", "G": "0", "S": "0"}),
        )
        for candidate, mapping in cases:
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                insertion_plan(document, candidate, mapping)
            self.assertEqual(document.data, before)
        wrong_builder = deepcopy(record)
        wrong_builder["package_builder"] = "invented"
        with self.assertRaises(ValueError):
            validate_record(wrong_builder)

    def test_placement_persists_composition_provenance_and_round_trips_undo(self):
        record = next(record for record in packaged_records() if record["family"] == "packaged_kelvin_shunt4")
        record["parameters"]["series_resistance_ohm"] = 0.25
        document = Document.from_netlist("Packaged device\nV1 fp 0 1\n.op\n.end\n")
        before = deepcopy(document.data)
        plan = insertion_plan(document, record, {"FP": "fp", "FN": "0", "SP": "sp", "SN": "sn"})
        evidence = plan["packaged_device_model"]
        self.assertEqual(evidence["pins"], ["FP", "FN", "SP", "SN"])
        self.assertEqual(evidence["core_builder_kind"], "kelvin_shunt4")
        self.assertEqual(evidence["package_builder"], "device_parasitics")
        self.assertEqual(evidence["record"]["parameters"]["series_resistance_ohm"], 0.25)
        self.assertEqual(evidence["compiled_source_sha256"], hashlib.sha256(
            native_recipe(record)["source"].encode()).hexdigest())
        self.assertEqual(document.data, before)
        apply_insertion(document, plan, record["id"])
        self.assertEqual(document.data["metadata"]["packaged_device_models"][plan["model"]], evidence)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packaged.spksch"
            document.save(path)
            reopened = Document.load(path)
            self.assertEqual(reopened.data["metadata"]["packaged_device_models"],
                             document.data["metadata"]["packaged_device_models"])
        document.undo()
        self.assertEqual(document.data, before)
        document.redo()
        self.assertEqual(document.data["metadata"]["packaged_device_models"][plan["model"]], evidence)

    def test_generated_namespace_reuse_is_exact_and_definition_drift_fails_atomically(self):
        record = next(record for record in packaged_records() if record["family"] == "packaged_nmos4")
        mapping = {"D": "d", "G": "g", "S": "0", "B": "0"}

        def placed_document():
            document = Document.from_netlist("Definition ownership\nVD d 0 4\nVG g 0 3\n.op\n.end\n")
            first = insertion_plan(document, record, mapping)
            apply_insertion(document, first, record["id"])
            return document, first

        unchanged, first = placed_document()
        before = deepcopy(unchanged.data)
        second = insertion_plan(unchanged, record, mapping)
        self.assertEqual(unchanged.data, before)
        self.assertEqual(second["source"].count(".subckt " + first["model"] + " "), 1)
        self.assertEqual(second["source"].count(".subckt " + first["model"] + "_CORE "), 1)
        self.assertIn("XCAT2 d g 0 0 " + first["model"], second["source"])

        for label, old, new in (
            ("wrapper", "RPKG1 D __SPK_SER_1 0.01", "RPKG1 D __SPK_SER_1 99"),
            ("core", "MCORE D G S BULK CORE W=1 L=1", "MCORE D G S BULK CORE W=2 L=1"),
        ):
            document, _ = placed_document()
            self.assertIn(old, document.data["source"])
            document.apply_source(document.data["source"].replace(old, new))
            edited = deepcopy(document.data)
            with self.subTest(definition=label), self.assertRaisesRegex(ValueError, "definition conflict"):
                insertion_plan(document, record, mapping)
            self.assertEqual(document.data, edited)
            self.assertIn(new, document.data["source"])

        from spikes_studio.library_browser import _verified_generated_reuse

        generated = native_recipe(record)["source"]
        wrapper_start = generated.index("* Original SPIKE generic unqualified constant package-parasitic wrapper")
        wrapper = generated[wrapper_start:]
        with self.assertRaisesRegex(ValueError, "duplicated"):
            _verified_generated_reuse(generated + wrapper, generated)

    def test_equation_bench_refuses_packaged_records(self):
        for record in packaged_records():
            with self.assertRaisesRegex(ValueError, "native circuit placement"):
                evaluate(record)


@unittest.skipUnless(os.environ.get("SPIKES_TEST_WX") == "1", "Opt-in native wx library test")
class PackagedDevicePanelTests(unittest.TestCase):
    def test_browser_preview_and_insert_editor_expose_package_coefficients(self):
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
            panel.search.ChangeValue("id:physics.packaged.nmos4")
            panel.filter()
            panel.list.SetSelection(0)
            panel.select()
            self.assertEqual(panel.record["id"], "physics.packaged.nmos4")
            self.assertIn("RPKG1", panel.recipe.GetValue())
            self.assertIn("series_inductance_h", panel.parameters.fields)
            dialog = InsertDialog(panel, panel.record)
            self.assertEqual(list(dialog.pins), ["D", "G", "S", "B"])
            dialog.parameter_fields["series_resistance_ohm"].SetValue("2")
            edited = dialog.edited_record()
            self.assertEqual(edited["parameters"]["series_resistance_ohm"], 2.0)
            self.assertIn("RPKG1 D __SPK_SER_1 2", native_recipe(edited)["source"])
        finally:
            if dialog:
                dialog.Destroy()
            panel.Destroy()
            host.Destroy()
            owner.Destroy()
            wx.Yield()


@unittest.skipUnless(LIBRARY and Path(LIBRARY).is_file(), "Current native library is not configured")
class NativePackagedDeviceLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from python.spikes.native_abi import load_native_library

        cls.library = load_native_library(LIBRARY)

    def _current(self, record):
        from python.spikes.native_runner import _populate
        from python.spikes.netlist import parse_netlist

        recipe = native_recipe(record)
        source = recipe["source"] + (
            f"X1 d g 0 0 {recipe['name']}\nVD d 0 4\nVG g 0 3\n.op\n.end\n"
        )
        circuit = self.library.circuit()
        self.addCleanup(circuit.close)
        _populate(circuit, parse_netlist(source, native_extensions=True))
        with circuit.solve_operating_point() as result:
            self.assertEqual(result.status, "converged", result.message)
            return -result.element_current("VD"), result.node_voltage("x1:__spk_core_1")

    def _direct_core_current(self, parameters):
        from python.spikes.lumped_physics_parts import build
        from python.spikes.native_runner import _populate
        from python.spikes.netlist import parse_netlist

        core = build("nmos4", parameters, name="DIRECT_CORE")
        source = core["source"] + "X1 d g 0 0 DIRECT_CORE\nVD d 0 4\nVG g 0 3\n.op\n.end\n"
        circuit = self.library.circuit()
        self.addCleanup(circuit.close)
        _populate(circuit, parse_netlist(source, native_extensions=True))
        with circuit.solve_operating_point() as result:
            self.assertEqual(result.status, "converged", result.message)
            return -result.element_current("VD")

    def test_nonzero_package_parameters_reach_native_solver_and_zero_matches_core(self):
        record = next(record for record in packaged_records() if record["family"] == "packaged_nmos4")
        zero = deepcopy(record)
        for name in ("series_resistance_ohm", "series_inductance_h", "parallel_capacitance_f"):
            zero["parameters"][name] = 0.0
        zero_current, zero_core_drain = self._current(zero)
        self.assertAlmostEqual(zero_core_drain, 4.0, delta=1e-12)
        core_parameters = {name: value for name, value in zero["parameters"].items()
                           if name not in {"series_resistance_ohm", "series_inductance_h", "parallel_capacitance_f"}}
        self.assertAlmostEqual(zero_current, self._direct_core_current(core_parameters), delta=1e-12)

        packaged = deepcopy(record)
        packaged["parameters"]["series_resistance_ohm"] = 100.0
        packaged["parameters"]["series_inductance_h"] = 1e-6
        packaged["parameters"]["parallel_capacitance_f"] = 1e-9
        packaged_current, packaged_core_drain = self._current(packaged)
        self.assertLess(packaged_current, zero_current)
        self.assertLess(packaged_core_drain, 4.0)
        self.assertAlmostEqual(4.0 - packaged_core_drain, 100.0 * packaged_current, delta=1e-8)

    def test_resistor_and_kelvin_force_lead_packages_execute_with_solved_drop(self):
        from python.spikes.native_runner import _populate
        from python.spikes.netlist import parse_netlist

        wiring = {
            "packaged_resistor3": "X1 p 0 0 {name}\nVP p 0 1",
            "packaged_kelvin_shunt4": "X1 p 0 sp sn {name}\nVP p 0 1",
        }
        for record in packaged_records():
            if record["family"] not in wiring:
                continue
            edited = deepcopy(record)
            edited["parameters"]["series_resistance_ohm"] = 10.0
            edited["parameters"]["series_inductance_h"] = 1e-6
            edited["parameters"]["parallel_capacitance_f"] = 1e-9
            recipe = native_recipe(edited)
            project = parse_netlist(
                recipe["source"] + wiring[record["family"]].format(name=recipe["name"])
                + "\n.op\n.end\n", native_extensions=True,
            )
            self.assertTrue(any(element.kind == "inductor" for element in project.elements))
            self.assertTrue(any(element.kind == "capacitor" for element in project.elements))
            circuit = self.library.circuit()
            self.addCleanup(circuit.close)
            _populate(circuit, project)
            with circuit.solve_operating_point() as result:
                self.assertEqual(result.status, "converged", (record["id"], result.message))
                current = -result.element_current("VP")
                core_positive = result.node_voltage("x1:__spk_core_1")
                self.assertGreater(current, 0)
                self.assertLess(core_positive, 1.0)
                self.assertAlmostEqual(1.0 - core_positive, 10.0 * current, delta=1e-9)

    def test_feedthrough_package_executes_fixed_core_and_configurable_outer_leads(self):
        from python.spikes.native_runner import _populate
        from python.spikes.netlist import parse_netlist

        record = next(record for record in packaged_records()
                      if record["family"] == "packaged_feedthrough_capacitor3")
        edited = deepcopy(record)
        edited["parameters"].update(series_resistance_ohm=10.0,
                                    series_inductance_h=1e-6,
                                    parallel_capacitance_f=1e-9)
        recipe = native_recipe(edited)
        project = parse_netlist(
            recipe["source"] + f"X1 p out 0 {recipe['name']}\nVP p 0 1\nRLOAD out 0 1\n.op\n.end\n",
            native_extensions=True,
        )
        self.assertTrue(any(element.kind == "inductor" for element in project.elements))
        self.assertGreaterEqual(sum(element.kind == "capacitor" for element in project.elements), 2)
        circuit = self.library.circuit()
        self.addCleanup(circuit.close)
        _populate(circuit, project)
        with circuit.solve_operating_point() as result:
            self.assertEqual(result.status, "converged", result.message)
            current = -result.element_current("VP")
            core_input = result.node_voltage("x1:__spk_core_1")
            self.assertGreater(current, 0)
            self.assertAlmostEqual(1.0 - core_input, 10.0 * current, delta=1e-9)
            self.assertAlmostEqual(result.node_voltage("out"), current, delta=1e-9)


if __name__ == "__main__":
    unittest.main()
