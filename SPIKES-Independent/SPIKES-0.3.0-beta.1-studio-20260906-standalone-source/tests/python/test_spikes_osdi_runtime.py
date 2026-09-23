from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

from python.spikes.hdl_frontend import OsdiModuleManifest
from python.spikes.osdi_runtime import (
    NativeOsdiCallbackRuntime, NgspiceOsdiSandboxRuntime,
    OSDI_NATIVE_CALLBACK_CONTRACT, OsdiExecutionError, OsdiSandboxPolicy,
)


class OsdiRuntimeTests(unittest.TestCase):
    def test_native_default_host_preserves_single_process_windows_containment(self) -> None:
        runtime = NativeOsdiCallbackRuntime()
        expected = getattr(sys, "_base_executable", sys.executable) if sys.platform == "win32" else sys.executable
        self.assertEqual(runtime.python_executable, Path(expected).resolve())

    def test_host_and_module_are_exactly_digest_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "model.osdi"
            artifact.write_bytes(b"test artifact")
            module = OsdiModuleManifest.create(
                module_id="test.model", module_name="model", artifact=artifact,
                source_sha256=hashlib.sha256(b"source").hexdigest(),
                compiler_sha256=hashlib.sha256(b"compiler").hexdigest(),
                osdi_abi_major=0, osdi_abi_minor=3,
                callbacks=("setup", "load", "noise", "trunc", "accept", "destroy"),
            )
            runtime = NgspiceOsdiSandboxRuntime(
                sys.executable, expected_ngspice_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            )
            artifact.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "identity"):
                runtime.execute(module, artifact, "test\n.op\n.end\n")
            with self.assertRaisesRegex(OsdiExecutionError, "digest mismatch"):
                NgspiceOsdiSandboxRuntime(sys.executable, expected_ngspice_sha256="0" * 64)

    def test_unsafe_deck_directives_and_invalid_limits_fail_closed(self) -> None:
        with self.assertRaisesRegex(OsdiExecutionError, "timeout"):
            OsdiSandboxPolicy(timeout_s=0)
        # Exercise deck rejection before any native model is loaded.
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "model.osdi"
            artifact.write_bytes(b"model")
            module = OsdiModuleManifest.create(
                module_id="test.model", module_name="model", artifact=artifact,
                source_sha256=hashlib.sha256(b"source").hexdigest(),
                compiler_sha256=hashlib.sha256(b"compiler").hexdigest(),
                osdi_abi_major=0, osdi_abi_minor=3,
                callbacks=("setup", "load", "noise", "trunc", "accept", "destroy"),
            )
            runtime = NgspiceOsdiSandboxRuntime(
                sys.executable, expected_ngspice_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            )
            with self.assertRaisesRegex(OsdiExecutionError, "unsafe"):
                runtime.execute(module, artifact, "test\n.control\nshell calc\n.endc\n.end\n")

    def test_vendored_ngspice_host_records_missing_osdi_command(self) -> None:
        root = Path(__file__).resolve().parents[2]
        artifact = root / "artifacts" / "hdl-qualification-wave4-current" / "spikes_linear_resistor.osdi"
        ngspice = root / "runtime" / "external" / "Spice64" / "bin" / "ngspice_con.exe"
        openvaf = root / "tools" / "hdl" / "openvaf" / "openvaf.exe"
        source = root / "benchmarks" / "hdl" / "spikes_linear_resistor.va"
        if not all(path.is_file() for path in (artifact, ngspice, openvaf, source)):
            self.skipTest("vendored OSDI qualification inputs are absent")
        module = OsdiModuleManifest.create(
            module_id="qualification.linear_resistor",
            module_name="spikes_linear_resistor", artifact=artifact,
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            compiler_sha256=hashlib.sha256(openvaf.read_bytes()).hexdigest(),
            osdi_abi_major=0, osdi_abi_minor=3,
            callbacks=("setup", "load", "noise", "trunc", "accept", "destroy"),
        )
        runtime = NgspiceOsdiSandboxRuntime(
            ngspice, expected_ngspice_sha256=hashlib.sha256(ngspice.read_bytes()).hexdigest(),
        )
        deck = (
            "OSDI resistor qualification\nV1 in 0 1\nN1 in 0 RMOD\n"
            ".model RMOD spikes_linear_resistor\n.op\n.end\n"
        )
        with self.assertRaisesRegex(OsdiExecutionError, "host rejected"):
            runtime.execute(module, artifact, deck)

    def _qualified_resistor(self) -> tuple[OsdiModuleManifest, Path]:
        root = Path(__file__).resolve().parents[2]
        artifact = root / "artifacts" / "hdl-qualification-wave4-current" / "spikes_linear_resistor.osdi"
        openvaf = root / "tools" / "hdl" / "openvaf" / "openvaf.exe"
        source = root / "benchmarks" / "hdl" / "spikes_linear_resistor.va"
        if not all(path.is_file() for path in (artifact, openvaf, source)):
            self.skipTest("vendored OSDI qualification inputs are absent")
        return OsdiModuleManifest.create(
            module_id="qualification.linear_resistor",
            module_name="spikes_linear_resistor", artifact=artifact,
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            compiler_sha256=hashlib.sha256(openvaf.read_bytes()).hexdigest(),
            osdi_abi_major=0, osdi_abi_minor=3,
            callbacks=("setup", "load", "noise", "trunc", "accept", "destroy"),
        ), artifact

    def test_spikes_native_osdi_callbacks_return_residual_and_jacobian(self) -> None:
        module, artifact = self._qualified_resistor()
        result = NativeOsdiCallbackRuntime().evaluate_dc(module, artifact, [1.0, 0.0])
        self.assertEqual(result["contract"], OSDI_NATIVE_CALLBACK_CONTRACT)
        self.assertEqual(result["host"], "spikes_native_osdi_0_3")
        model = result["osdi_result"]
        self.assertEqual(model["residual"], [0.001, -0.001])
        stamps = {(item["row"], item["column"]): item["value"] for item in model["jacobian"]}
        self.assertEqual(len(stamps), 4)
        self.assertAlmostEqual(stamps[(0, 0)], 0.001, places=12)
        self.assertAlmostEqual(stamps[(0, 1)], -0.001, places=12)
        self.assertAlmostEqual(stamps[(1, 0)], -0.001, places=12)
        self.assertAlmostEqual(stamps[(1, 1)], 0.001, places=12)
        self.assertFalse(result["containment"]["hostile_code_safe"])

    def test_hostile_native_osdi_request_fails_before_loading_artifact(self) -> None:
        module, artifact = self._qualified_resistor()
        with self.assertRaisesRegex(OsdiExecutionError, "hostile OSDI execution is unavailable"):
            NativeOsdiCallbackRuntime().evaluate_dc(
                module, artifact.with_name("does-not-exist.osdi"), [1.0, 0.0], hostile_code=True,
            )

    def test_native_osdi_worker_failure_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "invalid.osdi"
            artifact.write_bytes(b"not a native library")
            module = OsdiModuleManifest.create(
                module_id="test.invalid", module_name="invalid", artifact=artifact,
                source_sha256=hashlib.sha256(b"source").hexdigest(),
                compiler_sha256=hashlib.sha256(b"compiler").hexdigest(),
                osdi_abi_major=0, osdi_abi_minor=3,
                callbacks=("setup", "load", "noise", "trunc", "accept", "destroy"),
            )
            with self.assertRaisesRegex(OsdiExecutionError, "worker rejected"):
                NativeOsdiCallbackRuntime().evaluate_dc(module, artifact, [0.0])


if __name__ == "__main__":
    unittest.main()
