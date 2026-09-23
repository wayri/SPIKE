from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from python.spikes.hdl_frontend import (
    CompilerTool,
    HdlCompileError,
    HdlCompilePlan,
    HdlFrontendError,
    OsdiModuleManifest,
    compiled_isolation_profile,
    compile_hdl,
    discover_hdl_toolchains,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class HdlFrontendTests(unittest.TestCase):
    def test_discovery_is_honest_and_does_not_imply_compiler_support(self) -> None:
        report = discover_hdl_toolchains()
        self.assertEqual(report["contract"], "spikes/hdl-toolchain-inventory/v1")
        self.assertEqual({item["compiler_id"] for item in report["tools"]}, {
            "openvaf", "iverilog", "verilator", "ghdl",
        })
        self.assertEqual(
            report["can_compile_verilog_a_to_osdi"], "openvaf" in report["available_compilers"],
        )

    def test_compile_plan_binds_compiler_source_and_policy_generated_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compiler = root / "openvaf.exe"
            compiler.write_bytes(b"test compiler identity")
            source = root / "diode.va"
            source.write_text("module diode(a,c); endmodule\n", encoding="utf-8")
            destination = root / "output"
            destination.mkdir()
            tool = CompilerTool(
                compiler_id="openvaf", available=True, executable=str(compiler.resolve()),
                executable_sha256=_sha(compiler), version="test",
                input_language="verilog-a", output_kind="osdi",
            )
            plan = HdlCompilePlan.create(
                compilation_id="test.diode", compiler=tool, source=source,
            )

            def runner(arguments, working_directory, environment, timeout):
                self.assertEqual(Path(arguments[0]), compiler.resolve())
                self.assertEqual(arguments[-2], "-o")
                Path(arguments[-1]).write_bytes(b"compiled osdi")
                self.assertEqual(environment["SPIKES_HDL_COMPILE_PLAN_SHA256"], plan.plan_sha256)
                return subprocess.CompletedProcess(arguments, 0, b"", b"")

            result = compile_hdl(plan, source, destination, runner=runner)
            self.assertEqual(result["status"], "compiled")
            self.assertEqual(result["output_kind"], "osdi")
            self.assertFalse(result["loadable_by_spikes_solver"])
            source.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(HdlCompileError, "source_identity_mismatch"):
                compile_hdl(plan, source, destination, runner=runner)

    def test_osdi_package_is_content_addressed_and_requires_callback_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "diode.osdi"
            artifact.write_bytes(b"osdi artifact")
            callbacks = ("setup", "load", "noise", "trunc", "accept", "destroy")
            manifest = OsdiModuleManifest.create(
                module_id="test.diode", module_name="diode", artifact=artifact,
                source_sha256=hashlib.sha256(b"source").hexdigest(),
                compiler_sha256=hashlib.sha256(b"compiler").hexdigest(),
                osdi_abi_major=0, osdi_abi_minor=3, callbacks=callbacks,
            )
            self.assertEqual(manifest.verify_artifact(artifact), artifact.resolve())
            artifact.write_bytes(b"tampered")
            with self.assertRaisesRegex(HdlFrontendError, "identity"):
                manifest.verify_artifact(artifact)
            with self.assertRaisesRegex(HdlFrontendError, "callback"):
                replace(manifest, callbacks=("setup",))

    def test_isolation_profile_does_not_claim_an_os_sandbox(self) -> None:
        profile = compiled_isolation_profile()
        self.assertEqual(profile["sandbox_strength"], "trusted_digest_reviewed_code_only")
        self.assertFalse(profile["hostile_or_multitenant_safe"])
        self.assertTrue(profile["not_enforced"]["memory_limit"])
        self.assertTrue(profile["not_enforced"]["network_namespace"])


if __name__ == "__main__":
    unittest.main()
