"""Fail-closed process protocol for explicitly approved compiled control blocks.

This module is an execution *boundary*, not a native-code sandbox or a compiler.
Every executable and every argument is content-bound by an immutable manifest,
then approved by exact manifest and executable digests before it can run.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping


COMPILED_BLOCK_MANIFEST_CONTRACT = "spikes/compiled-block-manifest/v1"
COMPILED_BLOCK_APPROVAL_CONTRACT = "spikes/compiled-block-approval/v1"
COMPILED_BLOCK_REQUEST_CONTRACT = "spikes/compiled-block-request/v1"
COMPILED_BLOCK_RESPONSE_CONTRACT = "spikes/compiled-block-response/v1"

_DIGEST = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]{0,127}")
_LANGUAGES = frozenset({"c", "cpp", "verilog", "verilog-a", "vhdl", "osdi", "other"})
_RUNTIMES = frozenset({"json-subprocess-v1"})
_CAPABILITIES = frozenset({"control", "combinational", "stateful", "discrete-time"})


class CompiledBlockError(ValueError):
    """Invalid manifest, approval, request, or response."""


class CompiledBlockExecutionError(RuntimeError):
    """Stable, machine-readable failure from the process execution boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CompiledBlockRuntimeLimits:
    timeout_s: float = 1.0
    max_input_bytes: int = 64 * 1024
    max_output_bytes: int = 64 * 1024
    max_ports: int = 256
    max_state_variables: int = 4096
    max_arguments: int = 32

    def __post_init__(self) -> None:
        timeout = _finite(self.timeout_s, "timeout_s")
        if timeout <= 0.0 or timeout > 60.0:
            raise CompiledBlockError("timeout_s must be greater than zero and at most 60 seconds.")
        object.__setattr__(self, "timeout_s", timeout)
        for name in (
            "max_input_bytes", "max_output_bytes", "max_ports",
            "max_state_variables", "max_arguments",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise CompiledBlockError(f"{name} must be a positive integer.")


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise CompiledBlockError(f"{name} must be a finite number.")
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise CompiledBlockError(f"{name} must be a finite number.") from exc
    if not math.isfinite(result):
        raise CompiledBlockError(f"{name} must be a finite number.")
    return result


def _digest(value: object, name: str) -> str:
    normalized = str(value).lower()
    if _DIGEST.fullmatch(normalized) is None:
        raise CompiledBlockError(f"{name} must be a lowercase SHA-256 digest.")
    return normalized


def _identifier(value: object, name: str) -> str:
    normalized = str(value)
    if _IDENTIFIER.fullmatch(normalized) is None:
        raise CompiledBlockError(f"{name} is not a valid bounded identifier.")
    return normalized


def _identifiers(values: Iterable[object], name: str) -> tuple[str, ...]:
    result = tuple(_identifier(value, name) for value in values)
    if len(result) != len(set(result)):
        raise CompiledBlockError(f"{name} values must be unique.")
    return result


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class CompiledBlockManifest:
    block_id: str
    version: str
    implementation_language: str
    runtime: str
    executable_name: str
    executable_sha256: str
    arguments: tuple[str, ...]
    input_ports: tuple[str, ...]
    output_ports: tuple[str, ...]
    state_variables: tuple[str, ...]
    capabilities: tuple[str, ...]
    manifest_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_id", _identifier(self.block_id, "block_id"))
        version = str(self.version)
        if not version or len(version) > 64 or any(ord(c) < 32 for c in version):
            raise CompiledBlockError("version must be printable and at most 64 characters.")
        object.__setattr__(self, "version", version)
        language = str(self.implementation_language).lower()
        if language not in _LANGUAGES:
            raise CompiledBlockError("Unsupported implementation language metadata.")
        object.__setattr__(self, "implementation_language", language)
        runtime = str(self.runtime).lower()
        if runtime not in _RUNTIMES:
            raise CompiledBlockError("Unsupported compiled-block runtime.")
        object.__setattr__(self, "runtime", runtime)
        executable_name = str(self.executable_name)
        if (
            not executable_name or len(executable_name) > 255
            or Path(executable_name).name != executable_name
            or "\x00" in executable_name
        ):
            raise CompiledBlockError("executable_name must be one bounded base name.")
        object.__setattr__(self, "executable_name", executable_name)
        object.__setattr__(self, "executable_sha256", _digest(self.executable_sha256, "executable_sha256"))
        arguments = tuple(str(value) for value in self.arguments)
        if len(arguments) > 32 or any(len(value) > 4096 or "\x00" in value for value in arguments):
            raise CompiledBlockError("arguments exceed the manifest bounds.")
        object.__setattr__(self, "arguments", arguments)
        inputs = _identifiers(self.input_ports, "input port")
        outputs = _identifiers(self.output_ports, "output port")
        state = _identifiers(self.state_variables, "state variable")
        if set(inputs) & set(outputs):
            raise CompiledBlockError("Input and output port names must be disjoint.")
        object.__setattr__(self, "input_ports", inputs)
        object.__setattr__(self, "output_ports", outputs)
        object.__setattr__(self, "state_variables", state)
        capabilities = tuple(sorted(set(str(value).lower() for value in self.capabilities)))
        if not capabilities or not set(capabilities) <= _CAPABILITIES:
            raise CompiledBlockError("Manifest capabilities are empty or unsupported.")
        if state and "stateful" not in capabilities:
            raise CompiledBlockError("State variables require the stateful capability.")
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "manifest_sha256", _digest(self.manifest_sha256, "manifest_sha256"))
        if self.computed_manifest_sha256() != self.manifest_sha256:
            raise CompiledBlockError("manifest_sha256 does not match the canonical manifest content.")

    def content_dict(self) -> dict[str, object]:
        return {
            "contract": COMPILED_BLOCK_MANIFEST_CONTRACT,
            "block_id": self.block_id,
            "version": self.version,
            "implementation_language": self.implementation_language,
            "runtime": self.runtime,
            "executable_name": self.executable_name,
            "executable_sha256": self.executable_sha256,
            "arguments": list(self.arguments),
            "input_ports": list(self.input_ports),
            "output_ports": list(self.output_ports),
            "state_variables": list(self.state_variables),
            "capabilities": list(self.capabilities),
        }

    def computed_manifest_sha256(self) -> str:
        return hashlib.sha256(_canonical(self.content_dict())).hexdigest()

    @classmethod
    def create(
        cls, *, block_id: str, version: str, implementation_language: str,
        executable: str | Path, arguments: Iterable[str] = (),
        input_ports: Iterable[str] = (), output_ports: Iterable[str] = (),
        state_variables: Iterable[str] = (), capabilities: Iterable[str] = ("control",),
    ) -> "CompiledBlockManifest":
        path = Path(executable).resolve(strict=True)
        if not path.is_file():
            raise CompiledBlockError("Compiled-block executable is not a regular file.")
        content: dict[str, object] = {
            "contract": COMPILED_BLOCK_MANIFEST_CONTRACT,
            "block_id": str(block_id), "version": str(version),
            "implementation_language": str(implementation_language).lower(),
            "runtime": "json-subprocess-v1", "executable_name": path.name,
            "executable_sha256": _sha256_file(path), "arguments": list(arguments),
            "input_ports": list(input_ports), "output_ports": list(output_ports),
            "state_variables": list(state_variables),
            "capabilities": sorted(set(str(value).lower() for value in capabilities)),
        }
        return cls(
            block_id=str(content["block_id"]), version=str(content["version"]),
            implementation_language=str(content["implementation_language"]),
            runtime=str(content["runtime"]), executable_name=str(content["executable_name"]),
            executable_sha256=str(content["executable_sha256"]),
            arguments=tuple(content["arguments"]),  # type: ignore[arg-type]
            input_ports=tuple(content["input_ports"]),  # type: ignore[arg-type]
            output_ports=tuple(content["output_ports"]),  # type: ignore[arg-type]
            state_variables=tuple(content["state_variables"]),  # type: ignore[arg-type]
            capabilities=tuple(content["capabilities"]),  # type: ignore[arg-type]
            manifest_sha256=hashlib.sha256(_canonical(content)).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class CompiledBlockApproval:
    manifest_sha256: str
    executable_sha256: str
    evidence_sha256: str
    reviewer: str
    approved: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest_sha256", _digest(self.manifest_sha256, "manifest_sha256"))
        object.__setattr__(self, "executable_sha256", _digest(self.executable_sha256, "executable_sha256"))
        object.__setattr__(self, "evidence_sha256", _digest(self.evidence_sha256, "evidence_sha256"))
        reviewer = str(self.reviewer).strip()
        if not reviewer or len(reviewer) > 128:
            raise CompiledBlockError("reviewer must be present and at most 128 characters.")
        object.__setattr__(self, "reviewer", reviewer)
        if self.approved is not True:
            raise CompiledBlockError("Compiled-block execution approval must be explicit.")


@dataclass(frozen=True, slots=True)
class CompiledBlockRequest:
    request_id: str
    time_s: float
    step_s: float
    ports: Mapping[str, float]
    state: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _identifier(self.request_id, "request_id"))
        time_s = _finite(self.time_s, "time_s")
        step_s = _finite(self.step_s, "step_s")
        if time_s < 0.0 or step_s <= 0.0:
            raise CompiledBlockError("time_s must be nonnegative and step_s must be positive.")
        object.__setattr__(self, "time_s", time_s)
        object.__setattr__(self, "step_s", step_s)
        object.__setattr__(self, "ports", _numeric_mapping(self.ports, "ports"))
        object.__setattr__(self, "state", _numeric_mapping(self.state, "state"))

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": COMPILED_BLOCK_REQUEST_CONTRACT, "request_id": self.request_id,
            "time_s": self.time_s, "step_s": self.step_s,
            "ports": dict(self.ports), "state": dict(self.state),
        }


@dataclass(frozen=True, slots=True)
class CompiledBlockResponse:
    request_id: str
    ports: Mapping[str, float]
    state: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _identifier(self.request_id, "request_id"))
        object.__setattr__(self, "ports", _numeric_mapping(self.ports, "ports"))
        object.__setattr__(self, "state", _numeric_mapping(self.state, "state"))


def _numeric_mapping(value: Mapping[str, object], name: str) -> Mapping[str, float]:
    if not isinstance(value, Mapping):
        raise CompiledBlockError(f"{name} must be an object.")
    result: dict[str, float] = {}
    for key, item in value.items():
        normalized = _identifier(key, f"{name} key")
        result[normalized] = _finite(item, f"{name}.{normalized}")
    return MappingProxyType(result)


def _strict_json(payload: bytes) -> Mapping[str, object]:
    def reject_constant(value: str) -> object:
        raise ValueError(f"non-finite constant {value}")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"), parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CompiledBlockExecutionError("invalid_json_response") from exc
    if not isinstance(value, dict):
        raise CompiledBlockExecutionError("invalid_response_schema")
    return value


class CompiledBlockProcessRuntime:
    """Run digest-approved JSON blocks in a bounded child process.

    The child has a fresh working directory and a minimal environment. This is
    process isolation only: native code still requires an OS sandbox before it
    may be treated as hostile or multi-tenant-safe.
    """

    def __init__(
        self, approvals: Iterable[CompiledBlockApproval],
        limits: CompiledBlockRuntimeLimits | None = None,
    ):
        self._limits = limits or CompiledBlockRuntimeLimits()
        indexed: dict[str, CompiledBlockApproval] = {}
        for approval in approvals:
            if approval.manifest_sha256 in indexed:
                raise CompiledBlockError("Duplicate compiled-block approval.")
            indexed[approval.manifest_sha256] = approval
        self._approvals = MappingProxyType(indexed)

    def execute(
        self, manifest: CompiledBlockManifest, executable: str | Path,
        request: CompiledBlockRequest,
    ) -> CompiledBlockResponse:
        limits = self._limits
        approval = self._approvals.get(manifest.manifest_sha256)
        if (
            approval is None
            or approval.executable_sha256 != manifest.executable_sha256
            or approval.manifest_sha256 != manifest.manifest_sha256
        ):
            raise CompiledBlockExecutionError("execution_not_approved")
        if len(manifest.arguments) > limits.max_arguments:
            raise CompiledBlockExecutionError("manifest_limit_exceeded")
        if len(manifest.input_ports) + len(manifest.output_ports) > limits.max_ports:
            raise CompiledBlockExecutionError("manifest_limit_exceeded")
        if len(manifest.state_variables) > limits.max_state_variables:
            raise CompiledBlockExecutionError("manifest_limit_exceeded")
        if set(request.ports) != set(manifest.input_ports) or set(request.state) != set(manifest.state_variables):
            raise CompiledBlockExecutionError("request_schema_mismatch")

        path = Path(executable).resolve(strict=True)
        if not path.is_file() or path.name != manifest.executable_name:
            raise CompiledBlockExecutionError("executable_identity_mismatch")
        if _sha256_file(path) != manifest.executable_sha256:
            raise CompiledBlockExecutionError("executable_identity_mismatch")
        payload = _canonical(request.as_dict()) + b"\n"
        if len(payload) > limits.max_input_bytes:
            raise CompiledBlockExecutionError("input_limit_exceeded")

        environment = {"SPIKES_COMPILED_BLOCK_PROTOCOL": COMPILED_BLOCK_REQUEST_CONTRACT}
        for key in ("SystemRoot", "WINDIR"):
            if key in os.environ:
                environment[key] = os.environ[key]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        start_new_session = os.name != "nt"
        with tempfile.TemporaryDirectory(prefix="spikes-block-") as working_directory:
            try:
                process = subprocess.Popen(
                    [str(path), *manifest.arguments], stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                    cwd=working_directory, env=environment, creationflags=creationflags,
                    start_new_session=start_new_session,
                )
            except OSError as exc:
                raise CompiledBlockExecutionError("process_start_failed") from exc
            try:
                stdout, stderr, exceeded = self._exchange(process, payload)
            finally:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()
        if exceeded:
            raise CompiledBlockExecutionError("output_limit_exceeded")
        if process.returncode != 0:
            raise CompiledBlockExecutionError("process_failed")
        response_value = _strict_json(stdout)
        expected_keys = {"contract", "request_id", "ports", "state"}
        if set(response_value) != expected_keys or response_value.get("contract") != COMPILED_BLOCK_RESPONSE_CONTRACT:
            raise CompiledBlockExecutionError("invalid_response_schema")
        try:
            response = CompiledBlockResponse(
                request_id=str(response_value["request_id"]),
                ports=response_value["ports"],  # type: ignore[arg-type]
                state=response_value["state"],  # type: ignore[arg-type]
            )
        except (CompiledBlockError, TypeError) as exc:
            raise CompiledBlockExecutionError("invalid_response_schema") from exc
        if response.request_id != request.request_id:
            raise CompiledBlockExecutionError("response_request_mismatch")
        if set(response.ports) != set(manifest.output_ports) or set(response.state) != set(manifest.state_variables):
            raise CompiledBlockExecutionError("response_schema_mismatch")
        return response

    def _exchange(
        self, process: subprocess.Popen[bytes], payload: bytes,
    ) -> tuple[bytes, bytes, bool]:
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        output: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
        lock = threading.Lock()
        exceeded = threading.Event()
        io_failed = threading.Event()

        def drain(name: str, stream: object) -> None:
            reader = stream  # narrow type only at the read call
            while True:
                chunk = reader.read(4096)  # type: ignore[attr-defined]
                if not chunk:
                    return
                with lock:
                    used = len(output["stdout"]) + len(output["stderr"])
                    remaining = self._limits.max_output_bytes + 1 - used
                    if remaining > 0:
                        output[name].extend(chunk[:remaining])
                    if used + len(chunk) > self._limits.max_output_bytes:
                        exceeded.set()
                        try:
                            process.kill()
                        except OSError:
                            pass

        def write_input() -> None:
            try:
                process.stdin.write(payload)
                process.stdin.flush()
            except (BrokenPipeError, OSError):
                io_failed.set()
            finally:
                try:
                    process.stdin.close()
                except OSError:
                    io_failed.set()

        threads = (
            threading.Thread(target=drain, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=drain, args=("stderr", process.stderr), daemon=True),
            threading.Thread(target=write_input, daemon=True),
        )
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=self._limits.timeout_s)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            for thread in threads:
                thread.join(timeout=1.0)
            raise CompiledBlockExecutionError("process_timeout") from exc
        for thread in threads:
            thread.join(timeout=1.0)
        if any(thread.is_alive() for thread in threads):
            process.kill()
            raise CompiledBlockExecutionError("process_io_failed")
        if io_failed.is_set() and process.returncode == 0:
            raise CompiledBlockExecutionError("process_io_failed")
        return bytes(output["stdout"]), bytes(output["stderr"]), exceeded.is_set()


__all__ = [
    "COMPILED_BLOCK_APPROVAL_CONTRACT", "COMPILED_BLOCK_MANIFEST_CONTRACT",
    "COMPILED_BLOCK_REQUEST_CONTRACT", "COMPILED_BLOCK_RESPONSE_CONTRACT",
    "CompiledBlockApproval", "CompiledBlockError", "CompiledBlockExecutionError",
    "CompiledBlockManifest", "CompiledBlockProcessRuntime", "CompiledBlockRequest",
    "CompiledBlockResponse", "CompiledBlockRuntimeLimits",
]
