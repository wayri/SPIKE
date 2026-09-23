"""Instance-local diode model namespace qualification (not full compact models)."""
import unittest

from python.spikes.contracts import CircuitProject
from python.spikes.netlist import NetlistParseError, parse_netlist


class ScopedModels(unittest.TestCase):
    def parse(self, cards):
        return parse_netlist('Scoped models\n' + cards + '\n.op\n.end')

    def test_local_precedence_and_instance_isolation(self):
        project = self.parse('''
.model shared D(IS=1p)
.subckt cell a b
D1 a b shared
.model shared D(IS=2p)
.ends cell
X1 a 0 cell
X2 b 0 cell
D1 c 0 shared
''')
        self.assertEqual([e.model_name for e in project.elements], ['X1:SHARED', 'X2:SHARED', 'SHARED'])
        self.assertEqual([e.diode_model.saturation_current_a for e in project.elements], [2e-12, 2e-12, 1e-12])
        self.assertEqual(CircuitProject.from_dict(project.to_dict()), project)

    def test_parent_visibility_and_child_override(self):
        project = self.parse('''
.subckt leaf a b
D1 a b local
.ends leaf
.subckt own a b
.model local D(N=3)
D1 a b local
.ends own
.subckt parent a b
.model local D(N=2)
X1 a b leaf
X2 a b own
.ends parent
X1 in 0 parent
''')
        self.assertEqual([e.model_name for e in project.elements], ['X1:LOCAL', 'X1:X2:LOCAL'])
        self.assertEqual([e.diode_model.emission_coefficient for e in project.elements], [2, 3])

    def test_sibling_names_are_independent(self):
        project = self.parse('''
.subckt first a b
.model d D(N=1)
D1 a b d
.ends
.subckt second a b
.model d D(N=2)
D1 a b d
.ends
X1 a 0 first
X2 b 0 second
''')
        self.assertEqual([e.diode_model.emission_coefficient for e in project.elements], [1, 2])

    def test_local_does_not_leak_to_top(self):
        with self.assertRaises(NetlistParseError) as error:
            self.parse('.subckt cell a b\n.model d D()\n.ends\nD1 a 0 d')
        self.assertEqual(error.exception.code, 'SPIKES_NETLIST_MODEL_UNKNOWN')

    def test_duplicate_case_insensitive_in_scope(self):
        with self.assertRaises(NetlistParseError) as error:
            self.parse('.subckt cell a b\n.model d D()\n.model D D()\n.ends\nR1 a 0 1k')
        self.assertEqual(error.exception.code, 'SPIKES_NETLIST_MODEL_DUPLICATE')
        self.assertEqual(error.exception.line, 4)

    def test_dormant_unsupported_model_is_rejected(self):
        for model, code in [('d D(TT=1n)', 'SPIKES_NETLIST_MODEL_PARAMETER_UNSUPPORTED'),
                            # NPN is a supported static compact-model card; use
                            # PNP to retain this dormant-card rejection gate.
                            ('q PNP(BF=100)', 'SPIKES_NETLIST_MODEL_UNSUPPORTED')]:
            with self.subTest(model=model), self.assertRaises(NetlistParseError) as error:
                self.parse(f'.subckt cell a b\n.model {model}\n.ends\nR1 a 0 1k')
            self.assertEqual(error.exception.code, code)


if __name__ == '__main__':
    unittest.main()
