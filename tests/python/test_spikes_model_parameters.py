"""Parameter binding for the bounded, static diode model implementation."""
import unittest

from python.spikes.netlist import NetlistParseError, parse_netlist


class ModelParameters(unittest.TestCase):
    def parse(self, cards):
        return parse_netlist('Model parameters\n' + cards + '\n.op\n.end')

    def test_instance_parameters_and_body_parameters(self):
        p = self.parse('''
.param base=1p
.subckt cell a b params: factor=2 n=1
.param current={base * factor}
.model local D(IS={current} N={n + 0.1} KF={base/1000})
D1 a b local
.ends
X1 a 0 cell factor=3 n=1
X2 b 0 cell factor=7 n=2
''')
        self.assertEqual([e.model_name for e in p.elements], ['X1:LOCAL', 'X2:LOCAL'])
        self.assertAlmostEqual(p.elements[0].diode_model.saturation_current_a / 1e-12, 3)
        self.assertAlmostEqual(p.elements[1].diode_model.saturation_current_a / 1e-12, 7)
        self.assertEqual([e.diode_model.emission_coefficient for e in p.elements], [1.1, 2.1])

    def test_inherited_model_uses_owner_not_child_parameters(self):
        p = self.parse('''
.param n=1
.model outer D(N={n})
.subckt leaf a b params: n=9
D1 a b outer
D2 a b inner
.ends
.subckt parent a b params: n=2
.model inner D(N={n})
X1 a b leaf
.ends
X1 a 0 parent
''')
        self.assertEqual([e.diode_model.emission_coefficient for e in p.elements], [1, 2])

    def test_step_rebinds_top_and_local_models(self):
        p = self.parse('''
.param scale=1
.model d D(IS={scale * 1p})
D1 a 0 d
.step param scale list 1 3
''')
        self.assertEqual(len(p.step_variants), 2)
        self.assertAlmostEqual(p.step_variants[1].elements[0].diode_model.saturation_current_a / 1e-12, 3)

    def test_strict_unknown_invalid_and_duplicate_diagnostics(self):
        for card, code in [
            ('D(IS={missing})', 'SPIKES_NETLIST_MODEL_INVALID'),
            ('D(N={1/0})', 'SPIKES_NETLIST_MODEL_INVALID'),
            ('D(N={-1})', 'SPIKES_NETLIST_MODEL_INVALID'),
            ('D(N=1 n=2)', 'SPIKES_NETLIST_MODEL_PARAMETER_DUPLICATE'),
            ('D(TT={1n})', 'SPIKES_NETLIST_MODEL_PARAMETER_UNSUPPORTED'),
            ('D(IS={1p)', 'SPIKES_NETLIST_TOKEN_INVALID'),
        ]:
            with self.subTest(card=card), self.assertRaises(NetlistParseError) as error:
                self.parse(f'.model d {card}\nD1 a 0 d')
            self.assertEqual(error.exception.code, code)
            self.assertEqual(error.exception.line, 2)


if __name__ == '__main__':
    unittest.main()
