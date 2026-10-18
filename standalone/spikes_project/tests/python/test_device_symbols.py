# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio/python"))

from spikes_studio.device_symbols import symbols
from spikes_studio.symbol_validation import validate_symbol


EXPECTED_TERMINALS = {
    "mosfet.n_channel.4_terminal": ["D", "G", "S", "B"],
    "mosfet.p_channel.4_terminal": ["D", "G", "S", "B"],
    "bjt.npn.4_terminal": ["C", "B", "E", "Sub"],
    "bjt.pnp.4_terminal": ["C", "B", "E", "Sub"],
    "jfet.n_channel.3_terminal": ["D", "G", "S"],
    "jfet.p_channel.3_terminal": ["D", "G", "S"],
    "mosfet.dual_gate.5_terminal": ["D", "G1", "G2", "S", "B"],
    "resistor.kelvin.4_terminal": ["FP", "FN", "SP", "SN"],
    "resistor.substrate.3_terminal": ["1", "2", "SUB"],
    "capacitor.feedthrough.3_terminal": ["IN", "OUT", "GND"],
    "inductor.coupled.2_winding": ["1+", "1-", "2+", "2-"],
}

EXPECTED_POSITIONS = {
    "mosfet.n_channel.4_terminal": [[10, -50], [-50, 0], [10, 50], [50, 0]],
    "mosfet.p_channel.4_terminal": [[10, -50], [-50, 0], [10, 50], [50, 0]],
    "bjt.npn.4_terminal": [[10, -50], [-50, 0], [10, 50], [50, 0]],
    "bjt.pnp.4_terminal": [[10, -50], [-50, 0], [10, 50], [50, 0]],
    "jfet.n_channel.3_terminal": [[10, -50], [-50, 0], [10, 50]],
    "jfet.p_channel.3_terminal": [[10, -50], [-50, 0], [10, 50]],
    "mosfet.dual_gate.5_terminal": [[10, -50], [-50, -10], [-50, 10], [10, 50], [50, 0]],
    "resistor.kelvin.4_terminal": [[-50, 0], [50, 0], [-10, -40], [10, 40]],
    "resistor.substrate.3_terminal": [[-50, 0], [50, 0], [0, 50]],
    "capacitor.feedthrough.3_terminal": [[-50, 0], [50, 0], [0, 50]],
    "inductor.coupled.2_winding": [[-10, -50], [-10, 50], [10, -50], [10, 50]],
}


class DeviceSymbolTests(unittest.TestCase):
    def setUp(self):
        self.by_id = {symbol["id"]: symbol for symbol in symbols()}

    def test_complete_stable_terminal_order_and_validation(self):
        self.assertEqual(set(self.by_id), set(EXPECTED_TERMINALS))
        for ident, expected in EXPECTED_TERMINALS.items():
            with self.subTest(symbol=ident):
                symbol = self.by_id[ident]
                self.assertIs(validate_symbol(symbol), symbol)
                self.assertEqual([pin["name"] for pin in symbol["terminals"]], expected)
                self.assertEqual([pin["at"] for pin in symbol["terminals"]], EXPECTED_POSITIONS[ident])
                self.assertEqual(symbol["standard"], "common-convention")
                self.assertEqual(symbol["conformance"], "unverified")

    def test_terminal_legs_end_on_body_without_crossing_its_interior(self):
        for symbol in self.by_id.values():
            low = symbol["body_keepout"]["min"]
            high = symbol["body_keepout"]["max"]
            drawn_lines = {
                (tuple(item["points"][0]), tuple(item["points"][-1]))
                for item in symbol["primitives"]
                if item["kind"] in ("line", "polyline")
            }
            for pin in symbol["terminals"]:
                with self.subTest(symbol=symbol["id"], terminal=pin["name"]):
                    at, end = pin["at"], pin["leg_endpoint"]
                    self.assertTrue(
                        end[0] in (low[0], high[0]) or end[1] in (low[1], high[1]),
                        "leg endpoint must touch the body boundary",
                    )
                    midpoint = [(at[0] + end[0]) / 2, (at[1] + end[1]) / 2]
                    self.assertFalse(low[0] < midpoint[0] < high[0] and low[1] < midpoint[1] < high[1])
                    leg = (tuple(at), tuple(end))
                    self.assertTrue(leg in drawn_lines or leg[::-1] in drawn_lines)

    def test_complementary_device_arrows_are_distinct_reflections(self):
        for first, second, reflect in (
            ("mosfet.n_channel.4_terminal", "mosfet.p_channel.4_terminal", lambda p: [48 - p[0], p[1]]),
            ("bjt.npn.4_terminal", "bjt.pnp.4_terminal", lambda p: [18 - p[0], 39 - p[1]]),
            ("jfet.n_channel.3_terminal", "jfet.p_channel.3_terminal", lambda p: [10 - p[0], p[1]]),
        ):
            arrows = []
            for ident in (first, second):
                filled = [item["points"] for item in self.by_id[ident]["primitives"] if item.get("fill")]
                self.assertEqual(len(filled), 1)
                arrows.append(filled[0])
            self.assertNotEqual(arrows[0], arrows[1])
            self.assertEqual([reflect(point) for point in arrows[0]], arrows[1])

    def test_mos_bulk_arrows_follow_p_to_n_junction_direction(self):
        def arrow_x(symbol):
            points = next(item["points"] for item in symbol["primitives"] if item.get("fill"))
            return points[0][0], (points[1][0] + points[2][0]) / 2

        n_tip, n_base = arrow_x(self.by_id["mosfet.n_channel.4_terminal"])
        p_tip, p_base = arrow_x(self.by_id["mosfet.p_channel.4_terminal"])
        dual_tip, dual_base = arrow_x(self.by_id["mosfet.dual_gate.5_terminal"])
        self.assertLess(n_tip, n_base, "NMOS arrow must point left from P bulk toward N channel")
        self.assertGreater(p_tip, p_base, "PMOS arrow must point right toward the N bulk")
        self.assertLess(dual_tip, dual_base, "dual-gate N-channel arrow must point toward its channel")

    def test_calls_and_descriptors_are_isolated(self):
        first = symbols()
        second = symbols()
        self.assertIsNot(first, second)
        self.assertIsNot(first[0], second[0])
        first[0]["terminals"][0]["name"] = "changed"
        first[0]["primitives"][0]["points"][0][0] = 999
        self.assertEqual(second[0]["terminals"][0]["name"], "D")
        self.assertNotEqual(second[0]["primitives"][0]["points"][0][0], 999)

    def test_explicit_non_claim_notes_and_special_terminals(self):
        self.assertIn("no available simulator model", self.by_id["mosfet.dual_gate.5_terminal"]["source_note"])
        self.assertIn("not an ordinary", self.by_id["resistor.substrate.3_terminal"]["source_note"])
        self.assertEqual(self.by_id["capacitor.feedthrough.3_terminal"]["terminals"][-1]["name"], "GND")
        self.assertIn("does not claim", self.by_id["inductor.coupled.2_winding"]["source_note"])


if __name__ == "__main__":
    unittest.main()
