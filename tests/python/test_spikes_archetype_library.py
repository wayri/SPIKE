import contextlib
import json
import math
import unittest
from io import StringIO

from python.spike_core.native_mna import REQUEST_CONTRACT, run_native_mna
from python.spikes.cli import EXIT_INPUT, EXIT_OK, main
from python.spikes.library import (
    BUILTIN_LIBRARY,
    ArchetypeLibraryError,
    ArchetypeUnavailableError,
)
from python.spikes.library_contracts import ELABORATION_CONTRACT, LIBRARY_CONTRACT


def solve(elements):
    return run_native_mna({
        "contract": REQUEST_CONTRACT,
        "request_id": "library-test",
        "ground_node": "0",
        "analysis": {"mode": "operating_point"},
        "elements": elements,
        "resource_limits": {"memory_limit_gb": 2.0, "linear_backend": "dense"},
    })


class SpikesArchetypeLibraryTests(unittest.TestCase):
    def test_catalog_and_validation_are_versioned_and_json_compatible(self):
        catalog = BUILTIN_LIBRARY.catalog()
        validation = BUILTIN_LIBRARY.validate()
        self.assertEqual(catalog["contract"], LIBRARY_CONTRACT)
        self.assertEqual(catalog["counts"], {"total": 16, "runnable": 8, "unavailable": 8})
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["counts"]["issues"], 0)
        json.dumps(catalog, allow_nan=False)
        json.dumps(validation, allow_nan=False)

    def test_search_is_deterministic_and_can_filter_availability(self):
        first = BUILTIN_LIBRARY.search("source", status="runnable")
        second = BUILTIN_LIBRARY.search("source", status="runnable")
        self.assertEqual(first, second)
        self.assertTrue(first)
        self.assertTrue(all(item.available for item in first))
        unavailable = BUILTIN_LIBRARY.search("semiconductor", status="unavailable")
        self.assertGreaterEqual(len(unavailable), 6)
        self.assertEqual(
            [item.archetype_id for item in unavailable],
            sorted(item.archetype_id for item in unavailable),
        )
        with self.assertRaises(ArchetypeLibraryError):
            BUILTIN_LIBRARY.search(status="pretend")

    def test_inspect_exposes_honest_unavailable_device_families(self):
        identifiers = (
            "spikes.generic:diode@1",
            "spikes.generic:opamp.voltage_feedback@1",
            "spikes.generic:bjt.npn@1",
            "spikes.generic:bjt.pnp@1",
            "spikes.generic:mosfet.nmos@1",
            "spikes.generic:mosfet.pmos@1",
            "spikes.power:gan.hemt@1",
            "spikes.power:sic.mosfet@1",
        )
        for identifier in identifiers:
            with self.subTest(identifier=identifier):
                descriptor = BUILTIN_LIBRARY.inspect(identifier)
                self.assertEqual(descriptor.status, "unavailable")
                self.assertFalse(descriptor.available)
                self.assertTrue(descriptor.unavailable_reason)
                self.assertFalse(descriptor.elaborator)
                self.assertIn("Descriptor-only", descriptor.limitations[0])

    def test_preset_then_override_precedence_is_explicit_and_deterministic(self):
        parameters = BUILTIN_LIBRARY.resolve_parameters(
            "spikes.ideal:voltage_divider@1",
            preset="one_tenth",
            overrides={"bottom_resistance_ohm": 20e3},
        )
        self.assertEqual(list(parameters), ["bottom_resistance_ohm", "top_resistance_ohm"])
        self.assertEqual(parameters, {"bottom_resistance_ohm": 20e3, "top_resistance_ohm": 90e3})
        with self.assertRaises(ArchetypeLibraryError):
            BUILTIN_LIBRARY.resolve_parameters("spikes.ideal:resistor@1", preset="wirewound")
        with self.assertRaises(ArchetypeLibraryError):
            BUILTIN_LIBRARY.resolve_parameters("spikes.ideal:resistor@1", overrides={"temperature_c": 25})
        for invalid in (0.0, -1.0, math.inf, math.nan, True):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                BUILTIN_LIBRARY.resolve_parameters(
                    "spikes.ideal:resistor@1",
                    overrides={"resistance_ohm": invalid},
                )

    def test_elaboration_validates_pins_and_records_provenance(self):
        elaborated = BUILTIN_LIBRARY.elaborate(
            "spikes.ideal:resistor@1",
            "load-1",
            {"positive": "OUT", "negative": "0"},
            preset="ten_k",
            overrides={"resistance_ohm": 2200},
        )
        self.assertEqual(elaborated["contract"], ELABORATION_CONTRACT)
        self.assertEqual(elaborated["parameters"]["resistance_ohm"], 2200.0)
        self.assertEqual(elaborated["elements"][0]["id"], "R_LOAD_1")
        self.assertEqual(elaborated["pin_bindings"], {"negative": "0", "positive": "OUT"})
        self.assertEqual(elaborated["provenance"]["archetype_id"], "spikes.ideal:resistor@1")
        self.assertEqual(elaborated["provenance"]["explicit_overrides"], ["resistance_ohm"])
        json.dumps(elaborated, allow_nan=False)

        with self.assertRaises(ArchetypeLibraryError):
            BUILTIN_LIBRARY.elaborate("spikes.ideal:resistor@1", "load", {"positive": "out"})
        with self.assertRaises(ArchetypeLibraryError):
            BUILTIN_LIBRARY.elaborate(
                "spikes.ideal:resistor@1", "load", {"positive": "out", "negative": "__spikes_private"}
            )

    def test_unavailable_archetype_never_elaborates(self):
        with self.assertRaises(ArchetypeUnavailableError) as raised:
            BUILTIN_LIBRARY.elaborate(
                "spikes.generic:diode@1", "d1", {"anode": "out", "cathode": "0"}
            )
        self.assertIn("unavailable", str(raised.exception))

    def test_voltage_source_and_resistor_archetypes_execute_in_native_mna(self):
        source = BUILTIN_LIBRARY.elaborate(
            "spikes.ideal:dc_voltage_source@1", "supply", {"positive": "out", "negative": "0"},
            preset="logic_5v",
        )
        load = BUILTIN_LIBRARY.elaborate(
            "spikes.ideal:resistor@1", "load", {"positive": "out", "negative": "0"},
            preset="one_k",
        )
        result = solve(source["elements"] + load["elements"])
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["out"], 5.0)
        self.assertAlmostEqual(result["data"]["element_current_a"]["R_LOAD"], 0.005)

    def test_divider_preset_executes_as_expected(self):
        source = BUILTIN_LIBRARY.elaborate(
            "spikes.ideal:dc_voltage_source@1", "supply", {"positive": "vin", "negative": "0"},
            overrides={"voltage_v": 10},
        )
        divider = BUILTIN_LIBRARY.elaborate(
            "spikes.ideal:voltage_divider@1", "sense", {"input": "vin", "output": "out", "reference": "0"},
            preset="one_tenth",
        )
        result = solve(source["elements"] + divider["elements"])
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["out"], 1.0)

    def test_vcvs_is_a_linear_gain_block_not_an_opamp_claim(self):
        input_source = BUILTIN_LIBRARY.elaborate(
            "spikes.ideal:dc_voltage_source@1", "input", {"positive": "in", "negative": "0"},
            overrides={"voltage_v": 2},
        )
        gain = BUILTIN_LIBRARY.elaborate(
            "spikes.ideal:vcvs@1", "gain", {
                "output_positive": "out", "output_negative": "0",
                "control_positive": "in", "control_negative": "0",
            },
            overrides={"gain": 3},
        )
        load = BUILTIN_LIBRARY.elaborate(
            "spikes.ideal:resistor@1", "load", {"positive": "out", "negative": "0"}
        )
        result = solve(input_source["elements"] + gain["elements"] + load["elements"])
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["data"]["node_voltage_v"]["out"], 6.0)
        descriptor = BUILTIN_LIBRARY.inspect("spikes.ideal:vcvs@1")
        self.assertIn("Not an op-amp", descriptor.limitations[0])

    def test_thevenin_internal_node_is_reserved_and_repeatable(self):
        first = BUILTIN_LIBRARY.elaborate(
            "spikes.ideal:thevenin_source@1", "rail-a", {"positive": "out", "negative": "0"}
        )
        second = BUILTIN_LIBRARY.elaborate(
            "spikes.ideal:thevenin_source@1", "rail-a", {"positive": "out", "negative": "0"}
        )
        self.assertEqual(first, second)
        self.assertEqual(first["internal_nodes"], ["__spikes_rail_a_thevenin"])


class SpikesArchetypeLibraryCliTests(unittest.TestCase):
    def invoke(self, *arguments):
        output = StringIO()
        with contextlib.redirect_stdout(output):
            code = main(arguments)
        return code, json.loads(output.getvalue())

    def test_search_inspect_and_validate_subcommands(self):
        code, searched = self.invoke("library", "search", "mosfet")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(searched["count"], 3)
        self.assertTrue(all(item["status"] == "unavailable" for item in searched["results"]))

        code, inspected = self.invoke("library", "inspect", "spikes.generic:diode@1")
        self.assertEqual(code, EXIT_OK)
        self.assertFalse(inspected["available"])
        self.assertTrue(inspected["unavailable_reason"])

        code, validation = self.invoke("library", "validate")
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(validation["valid"])

    def test_elaborate_subcommand_applies_preset_then_override(self):
        code, elaborated = self.invoke(
            "library", "elaborate", "spikes.ideal:resistor@1",
            "--instance", "load", "--pin", "positive=out", "--pin", "negative=0",
            "--preset", "ten_k", "--param", "resistance_ohm=2200",
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(elaborated["parameters"]["resistance_ohm"], 2200.0)

    def test_unavailable_elaboration_returns_structured_error(self):
        code, result = self.invoke(
            "library", "elaborate", "spikes.generic:diode@1",
            "--instance", "d1", "--pin", "anode=out", "--pin", "cathode=0",
        )
        self.assertEqual(code, EXIT_INPUT)
        self.assertEqual(result["status"], "error")
        self.assertIn("unavailable", result["issues"][0]["message"])

    def test_integrated_benchmark_subcommand_delegates_to_harness(self):
        code, report = self.invoke("benchmark", "--warmups", "0", "--repetitions", "1")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(report["contract"], "spikes/benchmark-report/v1")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
