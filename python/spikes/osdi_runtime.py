"""Digest-bound OSDI execution boundaries.

``NativeOsdiCallbackRuntime`` invokes OSDI 0.3 callbacks without ngspice and
returns residual/Jacobian stamps for SPIKES assembly. Native libraries are
loaded only in a bounded worker process. Trusted modules use the portable
Python worker; Windows hosts may additionally configure the native SPIKES
AppContainer launcher/worker pair for filesystem- and network-denied hostile
code execution.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import tempfile
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from python.spike_core.sparselizard_process import (
    SparseLizardAdapterError, run_adapter_process,
)

from .hdl_frontend import OsdiModuleManifest


OSDI_EXECUTION_CONTRACT = "spikes/osdi-sandbox-execution/v1"
OSDI_NATIVE_CALLBACK_CONTRACT = "spikes/osdi-native-callback/v1"
_FORBIDDEN = frozenset({
    ".control", ".endc", ".include", ".inc", ".lib", ".load", "osdi",
    "pre_osdi", "shell", "source", "codemodel", "cd", "aspice",
})


class OsdiExecutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OsdiSandboxPolicy:
    timeout_s: int = 30
    memory_limit_mb: int = 512
    output_limit_bytes: int = 4 * 1024 * 1024
    raw_result_limit_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        if not 1 <= self.timeout_s <= 3600:
            raise OsdiExecutionError("timeout_s must be from 1 through 3600")
        if not 64 <= self.memory_limit_mb <= 16 * 1024:
            raise OsdiExecutionError("memory_limit_mb must be from 64 through 16384")
        if not 1024 <= self.output_limit_bytes <= 64 * 1024 * 1024:
            raise OsdiExecutionError("output limit is invalid")
        if not 1024 <= self.raw_result_limit_bytes <= 1024 * 1024 * 1024:
            raise OsdiExecutionError("raw-result limit is invalid")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_deck(value: str) -> str:
    encoded = value.encode("utf-8")
    if not value.strip() or len(encoded) > 4 * 1024 * 1024 or "\x00" in value:
        raise OsdiExecutionError("OSDI qualification deck is empty or exceeds its bound")
    lines = value.rstrip().splitlines()
    if not lines:
        raise OsdiExecutionError("OSDI qualification deck is empty")
    # SPICE line 1 is the title, not a directive.
    for number, line in enumerate(lines[1:], 2):
        stripped = line.strip().lower()
        if not stripped or stripped.startswith("*"):
            continue
        token = stripped.split(maxsplit=1)[0]
        if token in _FORBIDDEN:
            raise OsdiExecutionError(f"unsafe deck directive at line {number}: {token}")
    end_positions = [index for index, line in enumerate(lines) if line.strip().lower() == ".end"]
    if len(end_positions) != 1:
        raise OsdiExecutionError("OSDI qualification deck must contain exactly one .end")
    return "\n".join(lines) + "\n"


class NgspiceOsdiSandboxRuntime:
    """Load one exact OSDI library in one bounded ngspice worker."""

    def __init__(
        self, ngspice_executable: str | Path,
        *, expected_ngspice_sha256: str, policy: OsdiSandboxPolicy | None = None,
    ):
        self.executable = Path(ngspice_executable).resolve(strict=True)
        self.expected_sha256 = str(expected_ngspice_sha256).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", self.expected_sha256):
            raise OsdiExecutionError("ngspice digest is invalid")
        if _sha256(self.executable) != self.expected_sha256:
            raise OsdiExecutionError("ngspice executable digest mismatch")
        self.policy = policy or OsdiSandboxPolicy()

    def execute(
        self, module: OsdiModuleManifest, artifact: str | Path,
        qualification_deck: str,
    ) -> dict[str, Any]:
        artifact_path = module.verify_artifact(artifact)
        deck = _safe_deck(qualification_deck)
        policy = self.policy
        with tempfile.TemporaryDirectory(prefix="spikes-osdi-host-") as directory:
            root = Path(directory)
            staged_artifact = root / module.artifact_name
            shutil.copyfile(artifact_path, staged_artifact)
            if _sha256(staged_artifact) != module.artifact_sha256:
                raise OsdiExecutionError("staged OSDI artifact digest mismatch")
            lines = deck.splitlines()
            lines.insert(1, f'pre_osdi "{staged_artifact.name}"')
            deck_path = root / "qualification.cir"
            deck_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            raw_path = root / "result.raw"
            log_path = root / "ngspice.log"
            try:
                execution = run_adapter_process(
                    [
                        str(self.executable), "-n", "-b", "-o", str(log_path),
                        "-r", str(raw_path), str(deck_path),
                    ],
                    cwd=root, timeout_s=policy.timeout_s,
                    memory_limit_mb=policy.memory_limit_mb,
                    output_limit_bytes=policy.output_limit_bytes,
                    stream_limit_bytes=policy.output_limit_bytes,
                )
            except SparseLizardAdapterError as exc:
                raise OsdiExecutionError(f"OSDI host containment failure: {exc}") from exc
            log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
            if execution["return_code"] != 0 or not raw_path.is_file():
                raise OsdiExecutionError(f"OSDI host rejected module or deck: {log[-2000:]}")
            if raw_path.stat().st_size > policy.raw_result_limit_bytes:
                raise OsdiExecutionError("OSDI raw result exceeds the configured bound")
            return {
                "contract": OSDI_EXECUTION_CONTRACT, "status": "completed",
                "host": "ngspice_osdi", "host_sha256": self.expected_sha256,
                "module_manifest_sha256": module.manifest_sha256,
                "module_artifact_sha256": module.artifact_sha256,
                "raw_result_sha256": _sha256(raw_path),
                "raw_result_bytes": raw_path.stat().st_size,
                "containment": {
                    "separate_process": True,
                    "job_memory_limit": bool(execution.get("memory_limit_enforced")),
                    "job_process_count_limit": os.name == "nt",
                    "job_cpu_time_limit": os.name == "nt",
                    "job_ui_restrictions": os.name == "nt",
                    "kill_on_job_close": os.name == "nt",
                    "job_assignment_race_closed": bool(
                        execution.get("job_assignment_race_closed")
                    ),
                    "network_namespace": False,
                    "filesystem_namespace": False,
                    "trusted_reviewed_modules_only": True,
                },
                "limitations": [
                    "OSDI callbacks execute in ngspice, not the SPIKES native MNA solver.",
                    "The worker has no network or filesystem namespace and is not hostile-code safe.",
                    "The Windows host starts suspended and is resumed only after Job assignment.",
                ],
            }


class NativeOsdiCallbackRuntime:
    """Evaluate OSDI 0.3 DC residual/Jacobian callbacks outside ngspice.

    This is the native model-callback layer required by SPIKES MNA assembly.
    It is deliberately not an in-process ``ctypes`` loader: a malformed model
    can crash only the bounded worker, not the solver process.
    """

    def __init__(
        self, *, python_executable: str | Path | None = None,
        expected_python_sha256: str | None = None,
        worker_script: str | Path | None = None,
        expected_worker_sha256: str | None = None,
        appcontainer_launcher: str | Path | None = None,
        expected_appcontainer_launcher_sha256: str | None = None,
        native_worker_executable: str | Path | None = None,
        expected_native_worker_sha256: str | None = None,
        policy: OsdiSandboxPolicy | None = None,
    ) -> None:
        # A Windows venv executable is a redirector that spawns the base
        # interpreter. The OSDI job intentionally permits exactly one process,
        # so launch the real host directly instead of weakening containment.
        default_python = getattr(sys, "_base_executable", sys.executable) if os.name == "nt" else sys.executable
        self.python_executable = Path(python_executable or default_python).resolve(strict=True)
        self.python_sha256 = _sha256(self.python_executable)
        expected_python = (expected_python_sha256 or self.python_sha256).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_python):
            raise OsdiExecutionError("Python host digest is invalid")
        if self.python_sha256 != expected_python:
            raise OsdiExecutionError("Python host digest mismatch")
        default_worker = Path(__file__).with_name("osdi_native_worker.py")
        self.worker_script = Path(worker_script or default_worker).resolve(strict=True)
        self.worker_sha256 = _sha256(self.worker_script)
        expected_worker = (expected_worker_sha256 or self.worker_sha256).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_worker):
            raise OsdiExecutionError("OSDI worker digest is invalid")
        if self.worker_sha256 != expected_worker:
            raise OsdiExecutionError("OSDI worker digest mismatch")
        if (appcontainer_launcher is None) != (native_worker_executable is None):
            raise OsdiExecutionError(
                "AppContainer launcher and native OSDI worker must be configured together"
            )
        self.appcontainer_launcher = None
        self.native_worker_executable = None
        self.appcontainer_launcher_sha256 = None
        self.native_worker_sha256 = None
        if appcontainer_launcher is not None and native_worker_executable is not None:
            if os.name != "nt":
                raise OsdiExecutionError("SPIKES AppContainer execution is Windows-only")
            self.appcontainer_launcher = Path(appcontainer_launcher).resolve(strict=True)
            self.native_worker_executable = Path(native_worker_executable).resolve(strict=True)
            self.appcontainer_launcher_sha256 = _sha256(self.appcontainer_launcher)
            self.native_worker_sha256 = _sha256(self.native_worker_executable)
            expected_launcher = (
                expected_appcontainer_launcher_sha256 or self.appcontainer_launcher_sha256
            ).lower()
            expected_native = (
                expected_native_worker_sha256 or self.native_worker_sha256
            ).lower()
            if not re.fullmatch(r"[0-9a-f]{64}", expected_launcher):
                raise OsdiExecutionError("AppContainer launcher digest is invalid")
            if not re.fullmatch(r"[0-9a-f]{64}", expected_native):
                raise OsdiExecutionError("native OSDI worker digest is invalid")
            if self.appcontainer_launcher_sha256 != expected_launcher:
                raise OsdiExecutionError("AppContainer launcher digest mismatch")
            if self.native_worker_sha256 != expected_native:
                raise OsdiExecutionError("native OSDI worker digest mismatch")
        self.policy = policy or OsdiSandboxPolicy()

    def evaluate_dc(
        self, module: OsdiModuleManifest, artifact: str | Path,
        terminal_voltages: list[float] | tuple[float, ...],
        *, temperature_kelvin: float = 300.15,
        hostile_code: bool = False,
    ) -> dict[str, Any]:
        """Return bounded native OSDI residual/Jacobian stamps.

        ``hostile_code`` selects the configured AppContainer route and fails
        closed when that OS-enforced worker pair is unavailable.
        """

        if hostile_code and (
            self.appcontainer_launcher is None or self.native_worker_executable is None
        ):
            raise OsdiExecutionError(
                "hostile OSDI execution is unavailable: configure the digest-bound AppContainer launcher and native worker"
            )
        if (module.osdi_abi_major, module.osdi_abi_minor) != (0, 3):
            raise OsdiExecutionError("native callback host supports exactly OSDI ABI 0.3")
        if not 1 <= len(terminal_voltages) <= 4096:
            raise OsdiExecutionError("terminal voltage count is outside release bounds")
        values = [float(value) for value in terminal_voltages]
        if not all(float("-inf") < value < float("inf") for value in values):
            raise OsdiExecutionError("terminal voltages must be finite")
        artifact_path = module.verify_artifact(artifact)
        header = artifact_path.read_bytes()[:4]
        if os.name == "nt" and not header.startswith(b"MZ"):
            raise OsdiExecutionError("native OSDI callback worker rejected module: artifact is not a PE image")
        if sys.platform.startswith("linux") and header != b"\x7fELF":
            raise OsdiExecutionError("native OSDI callback worker rejected module: artifact is not an ELF image")
        policy = self.policy
        with tempfile.TemporaryDirectory(prefix="spikes-native-osdi-") as directory:
            root = Path(directory)
            staged_artifact = root / module.artifact_name
            if hostile_code:
                assert self.appcontainer_launcher is not None
                assert self.native_worker_executable is not None
                assert self.native_worker_sha256 is not None
                staged_native_worker = root / "spikes_osdi_worker.exe"
                result_path = root / "result.json"
                shutil.copyfile(artifact_path, staged_artifact)
                shutil.copyfile(self.native_worker_executable, staged_native_worker)
                if _sha256(staged_artifact) != module.artifact_sha256:
                    raise OsdiExecutionError("staged OSDI artifact digest mismatch")
                if _sha256(staged_native_worker) != self.native_worker_sha256:
                    raise OsdiExecutionError("staged native OSDI worker digest mismatch")
                command = [
                    str(self.appcontainer_launcher), str(staged_native_worker),
                    str(staged_artifact), module.module_name,
                    repr(float(temperature_kelvin)), str(result_path),
                    *(repr(value) for value in values),
                ]
                try:
                    execution = run_adapter_process(
                        command, cwd=root, timeout_s=policy.timeout_s,
                        memory_limit_mb=policy.memory_limit_mb,
                        output_limit_bytes=policy.output_limit_bytes,
                        stream_limit_bytes=policy.output_limit_bytes,
                        windows_active_process_limit=2,
                    )
                except SparseLizardAdapterError as exc:
                    raise OsdiExecutionError(
                        f"AppContainer OSDI containment failure: {exc}"
                    ) from exc
                if execution["return_code"] != 0 or not result_path.is_file():
                    detail = str(execution.get("stderr", ""))
                    error_path = root / "osdi-error.txt"
                    if error_path.is_file():
                        detail = error_path.read_text(encoding="utf-8", errors="replace")
                    raise OsdiExecutionError(
                        f"AppContainer OSDI worker rejected module: {detail[-4096:]}"
                    )
                if result_path.stat().st_size > policy.output_limit_bytes:
                    raise OsdiExecutionError("AppContainer OSDI result exceeds configured bound")
                result = json.loads(result_path.read_text(encoding="utf-8"))
                if result.get("status") != "completed" or result.get("module_name") != module.module_name:
                    raise OsdiExecutionError("AppContainer OSDI result violates its contract")
                return {
                    "contract": OSDI_NATIVE_CALLBACK_CONTRACT,
                    "status": "completed", "host": "spikes_appcontainer_osdi_0_3",
                    "appcontainer_launcher_sha256": self.appcontainer_launcher_sha256,
                    "worker_sha256": self.native_worker_sha256,
                    "module_manifest_sha256": module.manifest_sha256,
                    "module_artifact_sha256": module.artifact_sha256,
                    "osdi_result": result,
                    "containment": {
                        "separate_process": True,
                        "job_memory_limit": True,
                        "job_process_count_limit": True,
                        "job_cpu_time_limit": True,
                        "job_ui_restrictions": True,
                        "kill_on_job_close": True,
                        "job_assignment_race_closed": True,
                        "network_isolation": True,
                        "filesystem_isolation": True,
                        "appcontainer": True,
                        "hostile_code_safe": True,
                    },
                    "limitations": [
                        "This route qualifies OSDI 0.3 DC residual and resistive-Jacobian callbacks only.",
                        "Transient, noise, limiting, parameter mutation, and node collapse remain unqualified.",
                    ],
                }
            staged_worker = root / "osdi_native_worker.py"
            shutil.copyfile(artifact_path, staged_artifact)
            shutil.copyfile(self.worker_script, staged_worker)
            if _sha256(staged_artifact) != module.artifact_sha256:
                raise OsdiExecutionError("staged OSDI artifact digest mismatch")
            if _sha256(staged_worker) != self.worker_sha256:
                raise OsdiExecutionError("staged OSDI worker digest mismatch")
            request = {
                "artifact": str(staged_artifact), "module_name": module.module_name,
                "terminal_voltages": values, "temperature_kelvin": float(temperature_kelvin),
            }
            request_bytes = json.dumps(request, sort_keys=True).encode("utf-8")
            if len(request_bytes) > policy.output_limit_bytes:
                raise OsdiExecutionError("OSDI callback request exceeds configured bound")
            (root / "request.json").write_bytes(request_bytes)
            try:
                execution = run_adapter_process(
                    [str(self.python_executable), "-I", "-S", str(staged_worker)],
                    cwd=root, timeout_s=policy.timeout_s,
                    memory_limit_mb=policy.memory_limit_mb,
                    output_limit_bytes=policy.output_limit_bytes,
                    stream_limit_bytes=policy.output_limit_bytes,
                )
            except SparseLizardAdapterError as exc:
                raise OsdiExecutionError(f"native OSDI containment failure: {exc}") from exc
            result_path = root / "result.json"
            if execution["return_code"] != 0 or not result_path.is_file():
                error_path = root / "error.json"
                detail = error_path.read_text(encoding="utf-8", errors="replace") if error_path.is_file() else str(execution.get("stderr", ""))
                raise OsdiExecutionError(f"native OSDI callback worker rejected module: {detail[-4096:]}")
            if result_path.stat().st_size > policy.output_limit_bytes:
                raise OsdiExecutionError("native OSDI callback result exceeds configured bound")
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("status") != "completed" or result.get("module_name") != module.module_name:
                raise OsdiExecutionError("native OSDI callback result violates its contract")
            return {
                "contract": OSDI_NATIVE_CALLBACK_CONTRACT,
                "status": "completed", "host": "spikes_native_osdi_0_3",
                "python_host_sha256": self.python_sha256,
                "worker_sha256": self.worker_sha256,
                "module_manifest_sha256": module.manifest_sha256,
                "module_artifact_sha256": module.artifact_sha256,
                "osdi_result": result,
                "containment": {
                    "separate_process": True,
                    "job_memory_limit": bool(execution.get("memory_limit_enforced")),
                    "job_process_count_limit": os.name == "nt",
                    "job_cpu_time_limit": os.name == "nt",
                    "job_ui_restrictions": os.name == "nt",
                    "kill_on_job_close": os.name == "nt",
                    "job_assignment_race_closed": bool(
                        execution.get("job_assignment_race_closed")
                    ),
                    "network_isolation": False,
                    "filesystem_isolation": False,
                    "hostile_code_safe": False,
                },
                "limitations": [
                    "This release qualifies DC residual and resistive-Jacobian callbacks only.",
                    "Transient, noise, limiting, parameter mutation, and node collapse remain unqualified.",
                    "Only trusted digest-reviewed modules are accepted; hostile_code=True fails closed.",
                    "The Windows host starts suspended and is resumed only after Job assignment.",
                ],
            }


__all__ = [
    "NativeOsdiCallbackRuntime", "NgspiceOsdiSandboxRuntime",
    "OSDI_EXECUTION_CONTRACT", "OSDI_NATIVE_CALLBACK_CONTRACT",
    "OsdiExecutionError", "OsdiSandboxPolicy",
]
