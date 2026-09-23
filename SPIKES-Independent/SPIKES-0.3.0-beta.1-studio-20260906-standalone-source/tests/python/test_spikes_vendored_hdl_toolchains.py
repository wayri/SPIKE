from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from python.spikes.hdl_frontend import (
    HdlCompileError, HdlCompilePlan, compile_hdl, discover_hdl_toolchains,
)


ROOT = Path(__file__).resolve().parents[2]
OPENVAF = ROOT / "tools" / "hdl" / "openvaf" / "openvaf.exe"
GHDL = ROOT / "tools" / "hdl" / "ghdl" / "installed" / "ucrt64" / "bin" / "ghdl.exe"
IVERILOG = ROOT / "tools" / "hdl" / "iverilog-standalone" / "bin" / "iverilog.exe"
VERILATOR = ROOT / "tools" / "hdl" / "oss-cad-suite" / "oss-cad-suite" / "bin" / "verilator_bin.exe"


@unittest.skipUnless(
    all(path.is_file() for path in (OPENVAF, GHDL, IVERILOG, VERILATOR)),
    "reviewed vendored HDL tools are absent",
)
class VendoredHdlToolchainTests(unittest.TestCase):
    def test_exact_vendored_tools_compile_first_party_fixtures(self) -> None:
        inventory = discover_hdl_toolchains({
            "openvaf": OPENVAF, "ghdl": GHDL,
            "iverilog": IVERILOG, "verilator": VERILATOR,
        })
        tools = {item["compiler_id"]: item for item in inventory["tools"]}
        self.assertEqual(
            tools["openvaf"]["executable_sha256"],
            "a0b9be7b66e04a8a99af180b0b660045b276e3556804cc05b9b69d7fc0534483",
        )
        self.assertEqual(
            tools["ghdl"]["executable_sha256"],
            "e1194a7e30ac33c170692b1fa36a5985e54545dcf5272f3017e8c4378318347c",
        )
        self.assertEqual(
            tools["iverilog"]["executable_sha256"],
            "f8bad18d279f8c63ab041bd292606f21fc0e8b9cc0edb37a311158f756c35eb0",
        )
        self.assertEqual(
            tools["verilator"]["executable_sha256"],
            "d0a1e7c669aa7a054561f7ea5f4e9fcc29432a8476617e105a01ca94314c9da6",
        )
        # Reconstruct through the public validated contract so the inventory
        # values, rather than an unverified executable path, drive compilation.
        from python.spikes.hdl_frontend import CompilerTool
        compiler_objects = {
            compiler_id: CompilerTool(**{
                key: value for key, value in tools[compiler_id].items()
                if key in CompilerTool.__dataclass_fields__
            }) for compiler_id in ("openvaf", "ghdl", "iverilog", "verilator")
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            va_plan = HdlCompilePlan.create(
                compilation_id="qualification.linear_resistor",
                compiler=compiler_objects["openvaf"],
                source=ROOT / "benchmarks" / "hdl" / "spikes_linear_resistor.va",
            )
            va_result = compile_hdl(
                va_plan, ROOT / "benchmarks" / "hdl" / "spikes_linear_resistor.va", output,
            )
            self.assertEqual(va_result["status"], "compiled")
            self.assertGreater(Path(va_result["artifact"]).stat().st_size, 0)

            vhdl_plan = HdlCompilePlan.create(
                compilation_id="qualification.inverter",
                compiler=compiler_objects["ghdl"],
                source=ROOT / "benchmarks" / "hdl" / "spikes_inverter.vhd",
                top_module="spikes_inverter",
            )
            vhdl_result = compile_hdl(
                vhdl_plan, ROOT / "benchmarks" / "hdl" / "spikes_inverter.vhd", output,
            )
            self.assertEqual(vhdl_result["status"], "compiled")
            self.assertEqual(vhdl_result["output_kind"], "analyzed-library")

            verilog_source = ROOT / "benchmarks" / "hdl" / "spikes_tristate.v"
            iverilog_plan = HdlCompilePlan.create(
                compilation_id="qualification.tristate.iverilog",
                compiler=compiler_objects["iverilog"], source=verilog_source,
                top_module="spikes_tristate",
            )
            iverilog_result = compile_hdl(iverilog_plan, verilog_source, output)
            self.assertEqual(iverilog_result["status"], "compiled")
            self.assertEqual(iverilog_result["output_kind"], "vvp")

            verilator_plan = HdlCompilePlan.create(
                compilation_id="qualification.tristate.verilator",
                compiler=compiler_objects["verilator"], source=verilog_source,
                top_module="spikes_tristate",
            )
            verilator_result = compile_hdl(verilator_plan, verilog_source, output)
            self.assertEqual(verilator_result["status"], "compiled")
            self.assertEqual(verilator_result["output_kind"], "lint")


if __name__ == "__main__":
    unittest.main()
