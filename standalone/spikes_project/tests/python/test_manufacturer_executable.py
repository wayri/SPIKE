# SPDX-License-Identifier: Apache-2.0
"""Traceability, placement, and known-behavior checks for manufacturer reductions."""
from copy import deepcopy
import math
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio/python"))
sys.path.insert(0, str(ROOT))

from spikes_studio.document import Document
from spikes_studio.manufacturer_discovery import load_catalog as load_discovery_catalog
from spikes_studio.manufacturer_executable import (
    BACKEND, CONTRACT, MODEL_STATUS, ExecutableModelUnavailableError,
    ManufacturerExecutableError, as_component_record, availability,
    executable_record, format_record, install, load_catalog, native_recipe,
    prepare_install, source_pins, validate_catalog,
)
from python.spikes.netlist import parse_netlist


DEFAULT_LIBRARY = ROOT / "build-spikes-native-analysis-20261013/Release/spikes_c_api.dll"
LIBRARY = Path(os.environ.get("SPIKES_TEST_LIBRARY", DEFAULT_LIBRARY))


class ManufacturerExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.records = cls.catalog["records"]

    def test_catalog_is_a_small_fail_closed_tier_bound_to_discovery(self):
        self.assertEqual(self.catalog["contract"], CONTRACT)
        self.assertEqual(len(self.records), 5)
        discovery = {row["id"]: row for row in load_discovery_catalog()["records"]}
        self.assertEqual(len(discovery), 208)
        self.assertEqual({row["model_status"] for row in self.records}, {MODEL_STATUS})
        self.assertTrue(all(row["backend"] == BACKEND and row["qualified"] is False for row in self.records))
        for row in self.records:
            linked = discovery[row["discovery_id"]]
            self.assertEqual((row["manufacturer"], row["part_number"], row["category"]),
                             (linked["manufacturer"], linked["part_number"], linked["category"]))
            self.assertIn("official data sheet", row["license"])
            self.assertTrue(row["validity"]["limitations"])
        self.assertEqual(sum(availability(ident)["executable"] for ident in discovery), 5)
        self.assertFalse(availability("adi-ad8221")["executable"])
        self.assertEqual(availability("adi-ad8221")["model_status"], "model_not_reviewed")
        with self.assertRaises(ExecutableModelUnavailableError):
            executable_record("adi-ad8221")

    def test_lm358_and_ad620_retain_full_package_context(self):
        self.assertEqual(source_pins("ti-lm358"), [
            "OUT_A", "IN_A_MINUS", "IN_A_PLUS", "V_MINUS",
            "IN_B_PLUS", "IN_B_MINUS", "OUT_B", "V_PLUS",
        ])
        self.assertEqual(source_pins("adi-ad620"), [
            "RG1", "IN_MINUS", "IN_PLUS", "V_MINUS", "REF", "OUT", "V_PLUS", "RG2",
        ])
        lm = native_recipe("ti-lm358")["source"]
        self.assertIn("EA_ERR", lm)
        self.assertIn("EB_ERR", lm)
        self.assertIn("V_PLUS", lm)
        self.assertNotIn("vendor", lm.casefold().replace("not a vendor", ""))
        adapter = as_component_record("ti-lm358")
        self.assertEqual(adapter["exact_mpn"], "LM358")
        self.assertEqual(adapter["source_pins"], source_pins("ti-lm358"))
        self.assertFalse(adapter["qualified"])
        detail = format_record("ti-lm358")
        self.assertIn("Qualified: false", detail)
        self.assertIn("1=OUT_A", detail)
        self.assertIn("8=V_PLUS", detail)

    def test_every_recipe_parses_only_to_owned_native_primitives(self):
        admitted = {
            "resistor", "capacitor", "voltage_source", "diode", "vcvs", "ccvs",
            "npn_ebers_moll", "nmos_level1",
        }
        for row in self.records:
            recipe = native_recipe(row)
            nodes = ["n" + str(index) for index in range(len(recipe["pins"]))]
            deck = (recipe["source"] + "X1 " + " ".join(nodes) + " " + recipe["name"]
                    + "\nVREF n0 0 0\n.op\n.end\n")
            project = parse_netlist(deck, native_extensions=True)
            self.assertTrue(project.elements, row["discovery_id"])
            self.assertTrue({element.kind for element in project.elements} <= admitted, row["discovery_id"])
            self.assertEqual(recipe["model_status"], MODEL_STATUS)
            self.assertFalse(recipe["qualified"])
            self.assertNotIn(".include", recipe["source"].casefold())
            self.assertNotIn(".lib", recipe["source"].casefold())

    def test_independent_parameter_reductions_reproduce_declared_oracles(self):
        thermal_voltage = 8.617333262145e-5 * 300.15
        diode = executable_record("nexperia-bas316")["model"]["parameters"]
        expected_n = (0.855 - 0.715) / (thermal_voltage * math.log(10.0))
        expected_is = 0.001 / math.exp(0.715 / (expected_n * thermal_voltage))
        self.assertAlmostEqual(diode["emission_coefficient"], expected_n, delta=1e-14)
        self.assertAlmostEqual(diode["saturation_current_a"], expected_is, delta=1e-20)
        for current, voltage in ((0.001, 0.715), (0.01, 0.855)):
            actual = diode["saturation_current_a"] * math.expm1(
                voltage / (diode["emission_coefficient"] * thermal_voltage))
            self.assertAlmostEqual(actual, current, delta=current * 1e-5)

        mos = executable_record("onsemi-2n7002l")["model"]["parameters"]
        self.assertEqual(mos["threshold_voltage_v"], (1.0 + 2.5) / 2.0)
        self.assertEqual(mos["transconductance_a_per_v2"], 0.08 ** 2 / (2.0 * 0.2))
        self.assertAlmostEqual(mos["gate_source_capacitance_f"] + mos["gate_drain_capacitance_f"], 50e-12, delta=1e-25)
        self.assertAlmostEqual(mos["drain_source_capacitance_f"] + mos["gate_drain_capacitance_f"], 25e-12, delta=1e-25)

        lm = executable_record("ti-lm358")["model"]["parameters"]
        dominant_c = lm["open_loop_gain"] / (
            2 * math.pi * lm["gain_bandwidth_hz"] * lm["dominant_resistance_ohm"])
        self.assertIn(format(dominant_c, ".17g"), native_recipe("ti-lm358")["source"])

    def test_install_is_atomic_traceable_and_rejects_partial_pin_maps(self):
        document = Document.from_netlist("Manufacturer approximation\nVCC vp 0 5\n.op\n.end\n")
        mapping = {
            "OUT_A": "out_a", "IN_A_MINUS": "out_a", "IN_A_PLUS": "in_a", "V_MINUS": "0",
            "IN_B_PLUS": "in_b", "IN_B_MINUS": "out_b", "OUT_B": "out_b", "V_PLUS": "vp",
        }
        before = deepcopy(document.data)
        preview = prepare_install(document, "ti-lm358", mapping)
        self.assertEqual(document.data, before)
        self.assertEqual(preview["manufacturer_executable"]["model_status"], MODEL_STATUS)
        self.assertFalse(preview["manufacturer_executable"]["qualified"])
        plan = install(document, "ti-lm358", mapping)
        self.assertEqual(plan["refs"], ["XMAN1"])
        self.assertIn(plan["model"], document.data["metadata"]["manufacturer_executable_models"])
        tagged = [part for part in document.data["components"] if part["ref"].startswith("XMAN1:")]
        self.assertTrue(tagged)
        self.assertTrue(all(part["parameters"]["manufacturer_executable"]["qualified"] is False for part in tagged))
        document.undo()
        self.assertEqual(document.data, before)
        with self.assertRaisesRegex(ManufacturerExecutableError, "every package pin"):
            prepare_install(document, "ti-lm358", {"OUT_A": "out"})

    def test_validation_rejects_promotion_identity_drift_and_hidden_analysis_claims(self):
        for change, message in (
            (("qualified", True), "unqualified"),
            (("manufacturer", "Invented Vendor"), "differs from discovery"),
        ):
            altered = deepcopy(self.catalog)
            altered["records"][0][change[0]] = change[1]
            with self.subTest(change=change[0]), self.assertRaisesRegex(ManufacturerExecutableError, message):
                validate_catalog(altered)
        altered = deepcopy(self.catalog)
        altered["records"][0]["validity"]["analyses"].append("noise")
        with self.assertRaisesRegex(ManufacturerExecutableError, "analysis claim"):
            validate_catalog(altered)

    @unittest.skipUnless(LIBRARY.is_file(), "Set SPIKES_TEST_LIBRARY to a current native library")
    def test_native_known_behaviors_with_declared_tolerances(self):
        from python.spikes.native_runner import run_native_project
        thermal_voltage = 8.617333262145e-5 * 300.15

        def run(identifier, body):
            recipe = native_recipe(identifier)
            deck = recipe["source"] + body.replace("@MODEL@", recipe["name"]) + "\n.op\n.end\n"
            result = run_native_project(parse_netlist(deck, native_extensions=True), str(LIBRARY)).to_dict()
            self.assertEqual(result["status"], "completed", result.get("message"))
            return result["data"]

        lm = run("ti-lm358", """VCC vp 0 5
VINA ina 0 .5
VINB inb 0 2
X1 outa outa ina 0 inb outb outb vp @MODEL@
RLA outa 0 10k
RLB outb 0 10k""")
        self.assertAlmostEqual(lm["node_voltage_v"]["outa"], 0.5, delta=20e-6)
        self.assertAlmostEqual(lm["node_voltage_v"]["outb"], 2.0, delta=30e-6)

        ad = run("adi-ad620", """VP vp 0 5
VM vm 0 -5
VIP ip 0 .05
VIM im 0 -.05
VREF ref 0 0
X1 rg1 im ip vm ref out vp rg2 @MODEL@
RG rg1 rg2 5488.888888888889
RLOAD out 0 10k""")
        self.assertAlmostEqual(ad["node_voltage_v"]["out"], 1.0, delta=2e-4)
        self.assertAlmostEqual(ad["node_voltage_v"]["rg1"] - ad["node_voltage_v"]["rg2"], 0.1, delta=1e-12)

        bjt = run("onsemi-mmbt3904lt1g", """VCC vp 0 5
VB b 0 .7
RC vp c 1k
X1 b 0 c @MODEL@""")
        bp = executable_record("onsemi-mmbt3904lt1g")["model"]["parameters"]
        expected_bjt = (bp["forward_beta"] / (bp["forward_beta"] + 1.0)
                        * bp["saturation_current_a"] * math.expm1(0.7 / thermal_voltage))
        self.assertAlmostEqual(bjt["element_current_a"]["X1:QCORE"], expected_bjt,
                               delta=expected_bjt * 2e-9)

        mos = run("onsemi-2n7002l", """VDD vp 0 5
VG g 0 3
RD vp d 100
X1 g 0 d @MODEL@""")
        self.assertAlmostEqual(mos["element_current_a"]["X1:MCORE"], 0.0125, delta=1e-11)

        diode = run("nexperia-bas316", """VD a 0 .715
X1 0 a @MODEL@""")
        self.assertAlmostEqual(diode["element_current_a"]["X1:DCORE"], 0.001, delta=1e-8)

        lm_recipe = native_recipe("ti-lm358")
        transient_deck = lm_recipe["source"] + f"""VCC vp 0 5
VINA ina 0 PULSE(.5 1.5 .2u .001u .001u 10u 20u)
VINB inb 0 2
X1 outa outa ina 0 inb outb outb vp {lm_recipe['name']}
RLA outa 0 10k
RLB outb 0 10k
.tran .02u 2u
.end
"""
        transient = run_native_project(
            parse_netlist(transient_deck, native_extensions=True), str(LIBRARY)).to_dict()
        self.assertEqual(transient["status"], "completed", transient.get("message"))
        data = transient["data"]
        tau = 1.0 / (2.0 * math.pi * 700000.0)
        target_time = 0.2e-6 + tau
        index = min(range(len(data["time_s"])), key=lambda item: abs(data["time_s"][item] - target_time))
        first_order_oracle = 0.5 + (1.0 - math.exp(-1.0))
        self.assertAlmostEqual(data["node_voltage_v"]["outa"][index], first_order_oracle, delta=0.03)
        self.assertAlmostEqual(data["node_voltage_v"]["outa"][-1], 1.5, delta=6e-4)


if __name__ == "__main__":
    unittest.main()
