import tempfile
import unittest
from pathlib import Path
from unittest import mock

from python.spikes.contracts import CircuitProject
from python.spikes.netlist import NetlistParseError, parse_netlist


class ParameterElaborationTests(unittest.TestCase):
    def test_spice_continuation_lines_join_parameter_model_and_element_cards(self):
        project = parse_netlist("""continuations
.param base=1k
+ gain=3
.model rect D(IS=1p
+ N=1.2)
V1 in 0 1
R1 in out {base*
+ gain}
D1 out 0 rect
.op
.end
""")
        self.assertEqual(project.elements[1].value, 3000.0)
        self.assertEqual(project.elements[2].diode_model.emission_coefficient, 1.2)

    def test_orphan_and_empty_continuations_fail_closed(self):
        with self.assertRaisesRegex(NetlistParseError, "no preceding statement"):
            parse_netlist("+ R1 a 0 1k\n.op\n")
        with self.assertRaisesRegex(NetlistParseError, "contains no statement text"):
            parse_netlist("R1 a 0 1k\n+\nV1 a 0 1\n.op\n")

    def test_arithmetic_parameters_drive_elements_sources_and_analysis(self):
        project = parse_netlist(""".param base=1k scale={2+1} supply={12/2} step=1
V1 in 0 {supply}
R1 in out {base*scale}
R2 out 0 {base}
.dc V1 0 {supply} {step}
""")
        self.assertEqual([element.value for element in project.elements], [6.0, 3000.0, 1000.0])
        self.assertEqual(project.analysis.stop, 6.0)
        self.assertEqual(project.analysis.step, 1.0)

    def test_scopes_defaults_overrides_and_local_parameters_are_lexical(self):
        project = parse_netlist(""".param root=1k
.subckt inner p n params: gain=2 R={root*gain}
.param local={R/2}
R1 p mid {local}
R2 mid n {local}
.ends inner
V1 supply 0 4
Xdefault supply 0 inner
Xoverride supply 0 inner gain=4 R={root*6}
.op
""")
        values = {element.name: element.value for element in project.elements}
        self.assertEqual(values["XDEFAULT:R1"], 1000.0)
        self.assertEqual(values["XDEFAULT:R2"], 1000.0)
        self.assertEqual(values["XOVERRIDE:R1"], 3000.0)
        self.assertEqual(values["XOVERRIDE:R2"], 3000.0)

    def test_parameter_expressions_fail_closed(self):
        invalid = (
            ".param a={missing+1}\nV1 a 0 1\nR1 a 0 1k\n.op\n",
            ".param a={b+1} b={a+1}\nV1 a 0 1\nR1 a 0 1k\n.op\n",
            ".param a={__import__('os')}\nV1 a 0 1\nR1 a 0 1k\n.op\n",
            ".param a={2**100}\nV1 a 0 1\nR1 a 0 1k\n.op\n",
            ".param a={1/0}\nV1 a 0 1\nR1 a 0 1k\n.op\n",
            ".param a=1\nV1 a 0 1\nR1 a 0 {unknown}\n.op\n",
        )
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(NetlistParseError):
                parse_netlist(source)

    def test_project_round_trip_preserves_global_nodes(self):
        project = parse_netlist(""".global vdd common
.subckt branch out
R1 out vdd 1k
R2 out common 1k
.ends
V1 vdd 0 10
V2 common 0 5
X1 a branch
X2 b branch
R3 a 0 1k
R4 b 0 1k
.op
""")
        self.assertEqual(project.global_nodes, ("common", "vdd"))
        self.assertEqual(project.elements[2].negative_node, "vdd")
        self.assertEqual(project.elements[4].negative_node, "vdd")
        restored = CircuitProject.from_dict(project.to_dict())
        self.assertEqual(restored, project)


class LocalIncludeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def parse_file(self, path: Path):
        return parse_netlist(path.read_text(encoding="utf-8"), source_name=str(path))

    def test_include_and_selected_library_section_elaborate(self):
        (self.root / "parts.inc").write_text(
            ".param load=2k\n.subckt load p n params: R={load}\nR1 p n {R}\n.ends\n",
            encoding="utf-8",
        )
        (self.root / "models.lib").write_text(
            ".lib FAST\n.model rect D(IS=1p N=1.2)\n.endl FAST\n"
            ".lib SLOW\n.model rect D(IS=1n N=2)\n.endl SLOW\n",
            encoding="utf-8",
        )
        main = self.root / "main.cir"
        main.write_text(
            '.include "parts.inc"\n.lib "models.lib" FAST\n'
            "V1 in 0 1\nX1 in 0 load R=4k\nD1 in 0 rect\n.op\n",
            encoding="utf-8",
        )
        project = self.parse_file(main)
        self.assertEqual(project.elements[1].value, 4000.0)
        self.assertEqual(project.elements[2].diode_model.saturation_current_a, 1.0e-12)

    def test_include_path_cycle_section_and_context_fail_closed(self):
        outside = self.root / "outside.inc"
        outside.write_text("R1 a 0 1k\n", encoding="utf-8")
        sub = self.root / "project"
        sub.mkdir()
        traversal = sub / "traversal.cir"
        traversal.write_text('.include "../outside.inc"\nV1 a 0 1\n.op\n', encoding="utf-8")
        with self.assertRaisesRegex(NetlistParseError, "escapes"):
            self.parse_file(traversal)

        a = self.root / "a.inc"
        b = self.root / "b.inc"
        a.write_text('.include "b.inc"\n', encoding="utf-8")
        b.write_text('.include "a.inc"\n', encoding="utf-8")
        cycle = self.root / "cycle.cir"
        cycle.write_text('.include "a.inc"\nV1 a 0 1\nR1 a 0 1k\n.op\n', encoding="utf-8")
        with self.assertRaisesRegex(NetlistParseError, "cycle"):
            self.parse_file(cycle)

        library = self.root / "only.lib"
        library.write_text(".lib PRESENT\nR1 a 0 1k\n.endl PRESENT\n", encoding="utf-8")
        unknown = self.root / "unknown.cir"
        unknown.write_text('.lib "only.lib" ABSENT\nV1 a 0 1\n.op\n', encoding="utf-8")
        with self.assertRaisesRegex(NetlistParseError, "was not found"):
            self.parse_file(unknown)

        with self.assertRaisesRegex(NetlistParseError, "real top-level source file"):
            parse_netlist('.include "part.inc"\nV1 a 0 1\nR1 a 0 1k\n.op\n')

    def test_include_depth_limit_is_enforced(self):
        child = self.root / "child.inc"
        child.write_text("R1 a 0 1k\n", encoding="utf-8")
        main = self.root / "main.cir"
        main.write_text('.include "child.inc"\nV1 a 0 1\n.op\n', encoding="utf-8")
        with mock.patch("python.spikes.netlist.MAX_INCLUDE_DEPTH", 0):
            with self.assertRaisesRegex(NetlistParseError, "depth"):
                self.parse_file(main)


if __name__ == "__main__":
    unittest.main()
