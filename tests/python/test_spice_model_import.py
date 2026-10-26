# SPDX-License-Identifier: Apache-2.0
"""Independent inert fixtures; these tests do not invoke a SPICE engine."""
import hashlib
import unittest
from unittest.mock import patch

from python.spike_core import spice_model_import as importer
from python.spike_core.contracts import SpiDeR
from python.spike_core.spice_workspace import validate_spice_workspace, compose_spice_workspace


LIBRARY = """* Independently authored dependency fixture
.param base = 10k bias={base / 2}
.model junction D(IS=1e-14 N=1)
.subckt Output IN OUT
+ RETURN PARAMS: gain = 2
+ offset={bias + 1}
Xupper IN OUT RETURN Branch PARAMS: multiplier={gain + 1}
Xlower OUT IN RETURN Branch multiplier=2
.ends Output
.subckt Branch a b c params: multiplier=1
Xinner a b c Leaf
Rweight a b {base * multiplier}
.ends
.subckt Leaf p q r
Dprotect p r junction
Cstore q r 1n
.ends Leaf
.subckt Unrelated a b
Rother a b 1k
.ends Unrelated
"""


class SpiceModelImportTests(unittest.TestCase):
    def rejected(self, text, fragment=None):
        result = importer.inspect_spice_model_library(text, "fixture.lib")
        self.assertFalse(result["valid"], result)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["diagnostics"][0]["severity"], "error")
        if fragment:
            self.assertIn(fragment, result["diagnostics"][0]["message"])
        return result

    def test_continued_header_preserves_order_and_does_not_invent_parameter_pins(self):
        result = importer.inspect_spice_model_library(LIBRARY, "fixture.lib")
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["contract"], "spike/spice-model-library-inspection/v1")
        self.assertEqual([item["subcircuit_name"] for item in result["candidates"]], ["Output", "Branch", "Leaf", "Unrelated"])
        candidate = result["candidates"][0]
        self.assertEqual(candidate["pins"], ["IN", "OUT", "RETURN"])
        self.assertEqual(candidate["default_parameters"], {"gain": "2", "offset": "{bias + 1}"})
        self.assertEqual(candidate["dependency_names"], ["Leaf", "Branch"])
        self.assertNotIn("source", candidate)
        self.assertEqual(result["source_sha256"], hashlib.sha256(LIBRARY.encode()).hexdigest())
        self.assertFalse(result["production_qualified"])

    def test_selection_is_self_contained_deduplicated_and_traceable(self):
        model = importer.import_spice_model(LIBRARY, "output", "fixture.lib")
        self.assertEqual(model["pins"], ["IN", "OUT", "RETURN"])
        source = model["source"]
        self.assertNotIn("Unrelated", source)
        self.assertEqual(source.count(".subckt Leaf"), 1)
        self.assertEqual(source.count(".subckt Branch"), 1)
        self.assertEqual(source.count(".model junction"), 1)
        self.assertLess(source.index(".subckt Leaf"), source.index(".subckt Branch"))
        self.assertLess(source.index(".subckt Branch"), source.index(".subckt Output"))
        provenance = model["import_provenance"]
        self.assertEqual(provenance["normalized_source_sha256"], hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(provenance["source_sha256"], hashlib.sha256(LIBRARY.encode()).hexdigest())
        self.assertEqual(provenance["source_name"], "fixture.lib")
        self.assertEqual(provenance["required_engine"], "ngspice")
        self.assertFalse(provenance["expressions_evaluated"])
        self.assertFalse(provenance["external_files_resolved"])
        self.assertEqual(model["id"], importer.import_spice_model(LIBRARY, "Output")["id"])
        self.assertNotEqual(model["id"], importer.import_spice_model(LIBRARY + "* changed provenance\n", "Output")["id"])

    def test_header_defaults_without_params_marker_and_comment_continuations(self):
        text = ".subckt A p\n* comment\n+ n value=1k $ comment\nR1 p n {value}\n.ends a\n"
        candidate = importer.inspect_spice_model_library(text)["candidates"][0]
        self.assertEqual(candidate["pins"], ["p", "n"])
        self.assertEqual(candidate["default_parameters"], {"value": "1k"})

    def test_imported_model_is_accepted_by_existing_workspace_and_composes(self):
        model = importer.import_spice_model(".subckt Load p n params: r=10\nR1 p n {r}\n.ends Load", "Load")
        design = SpiDeR(design_id="inert-fixture", components=[{"reference": "U1"}],
                       pads=[{"id": "p", "ref": "U1", "name": "1"}, {"id": "n", "ref": "U1", "name": "2"}])
        workspace = {"contract": "spike/spice-workspace/v1", "name": "import", "domain": "pi", "ground_node": "GND",
                     "models": [model], "assignments": [{"id": "u1", "model_id": model["id"], "component_ref": "U1", "enabled": True,
                     "pin_bindings": [{"model_pin": "p", "pad_id": "p", "circuit_node": "VIN"}, {"model_pin": "n", "pad_id": "n", "circuit_node": "GND"}]}],
                     "parasitics": [], "analysis": {"mode": "operating_point"}}
        self.assertTrue(validate_spice_workspace(workspace, design)["valid"])
        preview = compose_spice_workspace(workspace, design)
        self.assertEqual(preview["status"], "ready")
        self.assertIn(".subckt Load p n params: r = 10", preview["netlist"])
        self.assertRegex(preview["netlist"], r"XU1 \S+ 0 Load")

    def test_forbidden_analysis_file_and_unknown_directives_rejected(self):
        for command in [".include external.lib", ".lib path", ".control", ".tran 1n 1u", ".end", ".save all", ".options scale=1", ".func f(x) x", ".if 1", ".hdl lib", "shell echo bad", "source other"]:
            with self.subTest(command=command):
                self.rejected(f".subckt A p n\n{command}\n.ends A")
        for card in ["V1 p n PWL FILE=data", "B1 p n V={read(x)}", "R1 p n 1k; .include path", "R1 p n 'expression'", "A1 p n external"]:
            with self.subTest(card=card):
                self.rejected(f".subckt A p n\n{card}\n.ends A")

    def test_duplicates_boundaries_and_ambiguous_headers_are_rejected(self):
        cases = [
            ".subckt A p n\n.ends A\n.subckt a p n\n.ends a",
            ".subckt A p P\n.ends A", ".subckt A p n params:x=1\n.ends A",
            ".subckt A p n params: x=1 X=2\n.ends A",
            ".subckt A p n\n.ends wrong", ".ends A", ".subckt A p n",
            ".subckt A p n\n.subckt B p n\n.ends B\n.ends A",
            "+ orphan\n.subckt A p n\n.ends A",
            ".subckt A p n\n.ends A\n+ extra",
            ".subckt A p n\nR1 p n 1\nr1 p n 2\n.ends A",
            ".param x=1\n.param X=2\n.subckt A p n\n.ends A",
            ".model d D\n.model D D\n.subckt A p n\n.ends A",
            ".subckt A p n params: x=1\n.param X=2\n.ends A",
            ".subckt A p n params: x={1 + 2)\n.ends A",
            ".subckt A p n params: x=1 + 2\n.ends A",
        ]
        for text in cases:
            with self.subTest(text=text): self.rejected(text)

    def test_missing_cycles_wrong_pins_and_undeclared_call_parameters(self):
        cases = [
            ".subckt A p n\nX1 p n Missing\n.ends A",
            ".subckt A p n\nX1 p n A\n.ends A",
            ".subckt A p n\nX1 p n B\n.ends A\n.subckt B p n\nX1 p n A\n.ends B",
            ".subckt A p n\nX1 p B\n.ends A\n.subckt B p n\n.ends B",
            ".subckt A p n\nX1 p n B unknown=2\n.ends A\n.subckt B p n\n.ends B",
            ".subckt A p n\nD1 p n Missing\n.ends A",
        ]
        for text in cases:
            with self.subTest(text=text): self.rejected(text)

    def test_scoped_parameters_and_local_device_models_are_preserved(self):
        text = ".param gain=2\n.subckt A p n params: gain=3\n.model local D(IS=1e-12)\nD1 p n local\n.ends A"
        model = importer.import_spice_model(text, "A")
        self.assertIn(".param gain = 2", model["source"])
        self.assertEqual(model["default_parameters"], {"gain": "3"})
        self.assertIn(".model local", model["source"])

    def test_bounds_invalid_types_and_no_engine_execution(self):
        for text in [None, 42, "", "* comment only", ".model d D", "\x00", "\ud800", "\u2028.subckt A p n", "x" * (importer.MAX_MODEL_SOURCE_BYTES + 1)]:
            with self.subTest(kind=type(text).__name__): self.rejected(text)
        valid = ".subckt A p n\nR1 p n 1\n.ends A"
        for constant, limit in [("MAX_PHYSICAL_LINES", 2), ("MAX_LOGICAL_LINES", 2), ("MAX_LINE_CHARS", 8), ("MAX_MODELS", 0)]:
            with self.subTest(constant=constant), patch.object(importer, constant, limit): self.rejected(valid)
        with patch("builtins.open", side_effect=AssertionError("No file read")), patch("subprocess.Popen", side_effect=AssertionError("No execution")):
            self.assertTrue(importer.inspect_spice_model_library(LIBRARY)["valid"])
        with self.assertRaises(ValueError): importer.import_spice_model(valid, "missing")
        with self.assertRaises(ValueError): importer.import_spice_model(valid, "A", "bad\nname")

    def test_inspection_output_expansion_is_rejected_without_partial_choices(self):
        with patch.object(importer, "MAX_INSPECTION_BYTES", 1400):
            self.rejected(LIBRARY, "output limit")

    def test_continued_directives_never_become_executable_cards(self):
        for text in [".subckt A p n\n+ .include external\n.ends A", ".subckt A p n\n* ignored\n.include external\n.ends A"]:
            self.rejected(text)
        # A dot token inside a normalized continued device card remains data,
        # not an independent directive; unknown device syntax still needs engine review.
        text = ".subckt A p n\nR1 p n 10\n+ .tran\n.ends A"
        self.assertNotIn("\n.tran", importer.import_spice_model(text, "A")["source"])

    def test_dependency_depth_bound_includes_previously_visited_shared_suffix(self):
        text = ".subckt Top p n\nXfirst p n Tail\nXsecond p n Mid\n.ends Top\n.subckt Mid p n\nXlast p n Tail\n.ends Mid\n.subckt Tail p n\n.ends Tail"
        with patch.object(importer, "MAX_DEPENDENCY_DEPTH", 2): self.rejected(text, "depth")

    def test_merge_deduplicates_shared_dependencies_and_retains_both_entries(self):
        output = importer.import_spice_model(LIBRARY, "Output")
        branch = importer.import_spice_model(LIBRARY, "Branch")
        merged = importer.merge_spice_model_sources([output["source"], branch["source"]])
        self.assertEqual(merged.count(".subckt Leaf"), 1)
        self.assertEqual(merged.count(".subckt Branch"), 1)
        self.assertEqual(merged.count(".subckt Output"), 1)
        self.assertEqual(merged.count(".model junction"), 1)
        self.assertEqual(merged.count(".param base"), 1)
        self.assertEqual(merged, importer.merge_spice_model_sources([output["source"], branch["source"]]))

    def test_merge_conflicts_and_cross_source_dependencies(self):
        first = ".subckt A p n\nX1 p n B\n.ends A"
        second = ".subckt B p n\nR1 p n 1k\n.ends B"
        self.assertTrue(importer.inspect_spice_model_library(importer.merge_spice_model_sources([first, second]))["valid"])
        for sources in [[".param a=1", ".param A=2"], [".model dm D(IS=1)", ".model DM D(IS=2)"], [second, second.replace("1k", "2k")], [first], [".include forbidden"]]:
            with self.subTest(sources=sources), self.assertRaises(ValueError): importer.merge_spice_model_sources(sources)
        self.assertEqual(importer.merge_spice_model_sources(["", " "]), "")
        self.assertEqual(importer.merge_spice_model_sources([".param a=1", ".param a = 1"]).count(".param"), 1)

    def test_merge_never_casefolds_payloads_or_accepts_quoted_dialect_expressions(self):
        for sources in [[".param a={Gain}", ".param a={gain}"], [".param a='Gain'", ".param a='gain'"]]:
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                importer.merge_spice_model_sources(sources)


if __name__ == "__main__":
    unittest.main()
