import json
import unittest
from unittest import mock

from python.spikes.contracts import CircuitProject, ProbeDescriptor
from python.spikes.netlist import NetlistParseError, parse_netlist
from python.spikes.runner import compile_project, run_project


NESTED_DIVIDERS = """Nested divider hierarchy
.subckt divider input return
RUP input midpoint 1k
RDOWN midpoint return 1k
.ends divider
.subckt dual input return
XA input return divider
XB input return divider
.ends dual
V1 supply 0 10
XTOP supply 0 dual
.op
.end
"""


class SpikesSubcircuitTests(unittest.TestCase):
    def test_nested_subcircuits_flatten_depth_first_with_scoped_nodes(self):
        project = parse_netlist(NESTED_DIVIDERS)
        self.assertEqual(
            [element.name for element in project.elements],
            ["V1", "XTOP:XA:RUP", "XTOP:XA:RDOWN", "XTOP:XB:RUP", "XTOP:XB:RDOWN"],
        )
        self.assertEqual(project.elements[1].negative_node, "xtop:xa:midpoint")
        self.assertEqual(project.elements[3].negative_node, "xtop:xb:midpoint")
        self.assertEqual(
            [instance.path for instance in project.hierarchy],
            ["XTOP", "XTOP:XA", "XTOP:XB"],
        )
        self.assertEqual(project.hierarchy[1].nodes, ("supply", "0"))

    def test_hierarchical_node_current_and_power_probes_run(self):
        probes = (
            ProbeDescriptor.parse("V(xtop:xa:midpoint)"),
            ProbeDescriptor.parse("I(xtop:xa:rup)"),
            ProbeDescriptor.parse("P(xtop:xb:rdown)"),
        )
        result = run_project(parse_netlist(NESTED_DIVIDERS, probes=probes)).to_dict()
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["probes"]["V(xtop:xa:midpoint)"]["value"], 5.0)
        self.assertAlmostEqual(result["probes"]["I(xtop:xa:rup)"]["value"], 0.005)
        self.assertAlmostEqual(result["probes"]["P(xtop:xb:rdown)"]["value"], 0.025)

    def test_each_instance_has_private_local_nodes(self):
        source = """local isolation
.subckt divider p n
R1 p mid 1k
R2 mid n 1k
.ends
V1 a 0 10
V2 b 0 20
X1 a 0 divider
X2 b 0 divider
.op
"""
        probes = (ProbeDescriptor.parse("V(x1:mid)"), ProbeDescriptor.parse("V(x2:mid)"))
        result = run_project(parse_netlist(source, probes=probes)).to_dict()
        self.assertAlmostEqual(result["probes"]["V(x1:mid)"]["value"], 5.0)
        self.assertAlmostEqual(result["probes"]["V(x2:mid)"]["value"], 10.0)

    def test_forward_reference_and_project_json_round_trip(self):
        source = """X1 a 0 load
V1 a 0 3
.subckt load p n
R1 p n 1k
.ends load
.op
"""
        project = parse_netlist(source)
        restored = CircuitProject.from_dict(json.loads(json.dumps(project.to_dict())))
        self.assertEqual(restored, project)
        compiled = compile_project(project)
        self.assertEqual(compiled["hierarchy"]["instance_count"], 1)
        self.assertEqual(compiled["hierarchy"]["flattened_element_count"], 2)
        self.assertEqual(compiled["native_request_template"]["elements"][0]["id"], "X1:R1")

    def test_dc_sweep_can_target_a_hierarchical_independent_source(self):
        source = """hierarchical source sweep
.subckt driven output
VLOCAL output 0 0
.ends driven
X1 out driven
R1 out 0 1k
.dc X1:VLOCAL 0V 2V 1V
"""
        result = run_project(parse_netlist(source, probes=(ProbeDescriptor.parse("V(out)"),))).to_dict()
        self.assertEqual(result["data"]["sweep"]["source"], "X1:VLOCAL")
        self.assertEqual(result["data"]["sweep"]["unit"], "V")
        self.assertEqual(result["probes"]["V(out)"]["values"], [0.0, 1.0, 2.0])

    def test_parameterized_definition_and_instance_override_are_scoped(self):
        source = """.param base=1k
.subckt load p n params: R={base*2}
R1 p n {R}
.ends
V1 p 0 1
X1 p 0 load
X2 p 0 load R=4k
.op
"""
        project = parse_netlist(source)
        self.assertEqual(project.elements[1].value, 2000.0)
        self.assertEqual(project.elements[2].value, 4000.0)
        with self.assertRaisesRegex(NetlistParseError, "undeclared parameters"):
            parse_netlist(".subckt load p n\nR1 p n 1k\n.ends\nV1 p 0 1\nX1 p 0 load R=2k\n.op\n")

    def test_unknown_definition_and_pin_mismatch_are_rejected(self):
        cases = {
            "unknown": "V1 a 0 1\nX1 a 0 absent\n.op\n",
            "few": ".subckt load p n\nR1 p n 1k\n.ends\nV1 a 0 1\nX1 a load\n.op\n",
            "many": ".subckt load p n\nR1 p n 1k\n.ends\nV1 a 0 1\nX1 a b 0 load\n.op\n",
        }
        for label, source in cases.items():
            with self.subTest(label=label), self.assertRaises(NetlistParseError):
                parse_netlist(source)

    def test_direct_and_indirect_recursion_are_rejected_even_when_unused(self):
        cases = (
            ".subckt loop p n\nX1 p n loop\n.ends\nV1 p 0 1\nR1 p 0 1k\n.op\n",
            ".subckt a p n\nX1 p n b\n.ends\n.subckt b p n\nX1 p n a\n.ends\nV1 p 0 1\nR1 p 0 1k\n.op\n",
        )
        for source in cases:
            with self.subTest(source=source), self.assertRaisesRegex(NetlistParseError, "Recursive"):
                parse_netlist(source)

    def test_malformed_definition_boundaries_and_internal_directives_are_rejected(self):
        cases = (
            ".ends\nV1 a 0 1\nR1 a 0 1k\n.op\n",
            ".subckt load p n\nR1 p n 1k\nV1 a 0 1\n.op\n",
            ".subckt load p n\n.op\n.ends\nV1 a 0 1\nR1 a 0 1k\n.op\n",
            ".subckt load p n\n.subckt inner p n\nR1 p n 1k\n.ends\n.ends\nV1 a 0 1\n.op\n",
            ".subckt load p n\nR1 p n 1k\n.ends other\nV1 a 0 1\nX1 a 0 load\n.op\n",
        )
        for source in cases:
            with self.subTest(source=source), self.assertRaises(NetlistParseError):
                parse_netlist(source)

    def test_duplicate_local_names_and_reserved_source_colons_are_rejected(self):
        cases = (
            ".subckt load p n\nR1 p n 1k\nr1 p n 2k\n.ends\nV1 a 0 1\nX1 a 0 load\n.op\n",
            "V1 a:b 0 1\nR1 a:b 0 1k\n.op\n",
        )
        for source in cases:
            with self.subTest(source=source), self.assertRaises(NetlistParseError):
                parse_netlist(source)

    def test_instance_expansion_limit_is_enforced_before_solver_execution(self):
        source = """bounded expansion
.subckt load p n
R1 p n 1k
.ends
V1 a 0 1
X1 a 0 load
X2 a 0 load
.op
"""
        with mock.patch("python.spikes.netlist.MAX_EXPANDED_INSTANCES", 1):
            with self.assertRaisesRegex(NetlistParseError, "exceeds 1 subcircuit instances"):
                parse_netlist(source)


if __name__ == "__main__":
    unittest.main()
