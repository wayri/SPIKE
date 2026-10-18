# SPDX-License-Identifier: Apache-2.0
import json
import sys
import unittest
from pathlib import Path

STUDIO = Path(__file__).resolve().parents[2] / "studio" / "python"
sys.path.insert(0, str(STUDIO))

from spikes_studio.hdl_analysis import (bounded_transitions, capability_inventory, serialize_measurements,
                                        signal_metrics, summarize_netlist,
                                        timing_measurements)
from spikes_studio.ide import analyze, find_tool, read_vcd


VCD = """$timescale 1 ns $end
$scope module top $end
$var wire 1 ! clk $end
$var wire 4 # bus [3:0] $end
$upscope $end
$enddefinitions $end
#0 0! b0000 #
#5 1! b0011 #
#10 0! bx01z #
#15 1! b1111 #
#20 0!
"""


class HDLAnalysisTest(unittest.TestCase):
    def test_yosys_summary_preserves_modules_ports_hierarchy_and_totals(self):
        netlist = {"modules": {"child": {"ports": {"q": {"direction": "output", "bits": [2]}}, "cells": {}},
                    "top": {"ports": {"a": {"direction": "input", "bits": [1, 2]}},
                            "cells": {"u0": {"type": "child"}, "and0": {"type": "$_AND_"}}}}}
        result = summarize_netlist(netlist)
        self.assertEqual(result["module_count"], 2); self.assertEqual(result["cell_count"], 2)
        self.assertEqual(result["modules"]["top"]["ports"][0]["width"], 2)
        self.assertEqual(result["modules"]["top"]["children"], [{"instance": "u0", "module": "child"}])
        self.assertEqual(result["cell_type_totals"], {"$_AND_": 1, "child": 1})

    def test_vcd_metrics_use_original_transitions_and_keep_unknown_vectors(self):
        data = read_vcd(VCD); clk = data["signals"]["top.clk"]
        metric = signal_metrics(clk, data["end_time_s"])
        self.assertEqual((metric["rising_edges"], metric["falling_edges"], metric["cycles"]), (2, 2, 1))
        self.assertAlmostEqual(metric["period_s"], 10e-9); self.assertAlmostEqual(metric["duty_cycle"], .5)
        rows = timing_measurements(data, ["top.bus"], 9e-9, 12e-9)
        self.assertEqual(rows[0]["value_a"], "0011"); self.assertEqual(rows[0]["value_b"], "x01z")

    def test_unknown_state_breaks_edges_and_is_excluded_from_duty_denominator(self):
        signal = {"width": 1, "transitions": [(0.0, "0"), (1.0, "x"), (3.0, "1"),
                                                (5.0, "0"), (7.0, "z"), (9.0, "1")]}
        metric = signal_metrics(signal, 10.0)
        self.assertEqual(metric["rising_edges"], 0)
        self.assertEqual(metric["falling_edges"], 1)
        self.assertAlmostEqual(metric["duty_cycle"], 3.0 / 6.0)

    def test_bounded_rendering_and_exports(self):
        original = [(float(i), str(i % 2)) for i in range(100)]
        shown = bounded_transitions(original, 7)
        self.assertEqual(len(shown), 7); self.assertEqual((shown[0], shown[-1]), (original[0], original[-1]))
        rows = [{"signal": "clk", "width": 1, "cursor_a_s": 0.0, "value_a": "0"}]
        self.assertEqual(json.loads(serialize_measurements(rows, "json"))[0]["signal"], "clk")
        self.assertIn("signal,width,cursor_a_s,value_a", serialize_measurements(rows, "csv"))

    def test_invalid_netlist_and_display_limit_are_rejected(self):
        with self.assertRaises(ValueError): summarize_netlist({})
        with self.assertRaises(ValueError): bounded_transitions([(0, "0"), (1, "1")], 1)

    def test_capabilities_claim_only_connected_vhdl_and_not_sta(self):
        capabilities = capability_inventory({"iverilog": "iverilog", "vvp": "vvp", "yosys": "yosys",
                                             "ghdl": "ghdl", "sta": "sta"})
        by_operation = {(row["language"], row["operation"]): row for row in capabilities}
        self.assertTrue(by_operation[("Verilog/SystemVerilog", "testbench/VCD")]["available"])
        self.assertTrue(by_operation[("VHDL", "syntax/check")]["available"])
        self.assertTrue(by_operation[("VHDL", "testbench/VCD")]["available"])
        self.assertIn("VHDL-2008", by_operation[("VHDL", "syntax/check")]["detail"])
        self.assertFalse(by_operation[("HDL", "static timing analysis")]["available"])
        self.assertIn("Liberty", by_operation[("HDL", "static timing analysis")]["detail"])

    @unittest.skipUnless(find_tool("ghdl"), "GHDL is not installed")
    def test_actual_ghdl_check_and_vcd_simulation(self):
        source = """library ieee;
use ieee.std_logic_1164.all;
entity top is end entity;
architecture testbench of top is
  signal clk : std_logic := '0';
begin
  stimulus: process
  begin
    wait for 5 ns; clk <= '1';
    wait for 5 ns; clk <= '0';
    wait for 5 ns; std.env.stop; wait;
  end process;
end architecture;
"""
        checked = analyze(source, "VHDL", "check", "top")
        self.assertEqual(checked["exit_code"], 0, checked["output"])
        simulated = analyze(source, "VHDL", "simulate", "top")
        self.assertEqual(simulated["exit_code"], 0, simulated["output"])
        self.assertIn("timing", simulated)
        clk_names = [name for name in simulated["timing"]["signals"] if name.endswith(".clk")]
        self.assertEqual(len(clk_names), 1)
        self.assertEqual([value for _, value in simulated["timing"]["signals"][clk_names[0]]["transitions"]],
                         ["0", "1", "0"])

    def test_vhdl_synthesis_is_explicitly_unsupported(self):
        with self.assertRaisesRegex(ValueError, "VHDL synthesis is not supported"):
            analyze("entity top is end;", "VHDL", "synthesize", "top")


if __name__ == "__main__": unittest.main()
