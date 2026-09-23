"""Digest-bound HDL/Verilog-A compiler frontend and OSDI package validation.

This module invokes a real supported compiler when it is installed; it never
pretends that language metadata is compilation.  OSDI artifacts are validated
and content-addressed here, but loading their native callbacks into the MNA
solver remains a separate ABI integration step.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


TOOLCHAIN_INVENTORY_CONTRACT = "spikes/hdl-toolchain-inventory/v1"
COMPILE_PLAN_CONTRACT = "spikes/hdl-compile-plan/v1"
COMPILE_RESULT_CONTRACT = "spikes/hdl-compile-result/v1"
OSDI_MODULE_CONTRACT = "spikes/osdi-module-manifest/v1"
ISOLATION_PROFILE_CONTRACT = "spikes/compiled-isolation-profile/v1"

_DIGEST = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]{0,127}")
_TOP = re.compile(r"[A-Za-z_][A-Za-z0-9_$]{0,127}")
_SUPPORTED = {
    "openvaf": ("verilog-a", "osdi"),
    "iverilog": ("verilog", "vvp"),
    "verilator": ("verilog", "lint"),
    "ghdl": ("vhdl", "analyzed-library"),
}
_EXPECTED_NAMES = {
    "openvaf": {"openvaf", "openvaf.exe"},
    "iverilog": {"iverilog", "iverilog.exe"},
    "verilator": {"verilator", "verilator.exe", "verilator_bin", "verilator_bin.exe"},
    "ghdl": {"ghdl", "ghdl.exe"},
}
_OSDI_CALLBACKS = frozenset({"setup", "load", "noise", "trunc", "accept", "destroy"})


class HdlFrontendError(ValueError):
    """Invalid compiler plan, compiler result, or OSDI package."""


class HdlCompileError(RuntimeError):
    """Stable compile failure from an actual tool invocation."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail[:4096]
        super().__init__(code if not self.detail else f"{code}: {self.detail}")


def _find_path_file(name: str) -> Path | None:
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        candidate = Path(entry) / name
        if candidate.is_file():
            return candidate.resolve()
    return None


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value: object, name: str) -> str:
    normalized = str(value).lower()
    if _DIGEST.fullmatch(normalized) is None:
        raise HdlFrontendError(f"{name} must be a lowercase SHA-256 digest.")
    return normalized


def _identifier(value: object, name: str) -> str:
    normalized = str(value)
    if _IDENTIFIER.fullmatch(normalized) is None:
        raise HdlFrontendError(f"{name} is not a bounded identifier.")
    return normalized


def _read_version(executable: Path) -> str:
    fallback = ""
    for arguments in (("--version",), ("-V",)):
        try:
            completed = subprocess.run(
                [str(executable), *arguments], capture_output=True, timeout=3.0,
                check=False, shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            continue
        text = (completed.stdout + completed.stderr).decode("utf-8", errors="replace").strip()
        if completed.returncode == 0 and text:
            return text.splitlines()[0][:256]
        if text and not fallback:
            fallback = text.splitlines()[0][:256]
    return fallback or "version-unavailable"


@dataclass(frozen=True, slots=True)
class CompilerTool:
    compiler_id: str
    available: bool
    executable: str
    executable_sha256: str
    version: str
    input_language: str
    output_kind: str
    auxiliary_executables: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        compiler_id = str(self.compiler_id).lower()
        if compiler_id not in _SUPPORTED:
            raise HdlFrontendError("unsupported compiler_id.")
        object.__setattr__(self, "compiler_id", compiler_id)
        expected_language, expected_output = _SUPPORTED[compiler_id]
        if self.input_language != expected_language or self.output_kind != expected_output:
            raise HdlFrontendError("compiler language/output metadata does not match policy.")
        if self.available:
            path = Path(self.executable)
            if not path.is_absolute() or not path.is_file():
                raise HdlFrontendError("available compiler executable must be an existing absolute file.")
            if path.name.lower() not in _EXPECTED_NAMES[compiler_id]:
                raise HdlFrontendError("compiler executable base name does not match compiler_id.")
            object.__setattr__(self, "executable_sha256", _digest(
                self.executable_sha256, "executable_sha256",
            ))
            if _sha256_file(path) != self.executable_sha256:
                raise HdlFrontendError("compiler executable digest does not match.")
        elif self.executable or self.executable_sha256:
            raise HdlFrontendError("unavailable compiler cannot carry executable identity.")
        auxiliaries: list[tuple[str, str]] = []
        for item in self.auxiliary_executables:
            if len(item) != 2:
                raise HdlFrontendError("auxiliary executable records must be path/digest pairs.")
            auxiliary_path = Path(str(item[0]))
            auxiliary_digest = _digest(item[1], "auxiliary executable digest")
            if not auxiliary_path.is_absolute() or not auxiliary_path.is_file():
                raise HdlFrontendError("auxiliary executable path must be an existing absolute file.")
            if _sha256_file(auxiliary_path) != auxiliary_digest:
                raise HdlFrontendError("auxiliary executable digest does not match.")
            auxiliaries.append((str(auxiliary_path), auxiliary_digest))
        object.__setattr__(self, "auxiliary_executables", tuple(auxiliaries))

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def discover_hdl_toolchains(
    explicit_paths: Mapping[str, str | Path] | None = None,
) -> dict[str, object]:
    """Discover supported tools from exact paths first, then normal ``PATH``.

    Explicit paths are useful for reviewed workspace-vendored toolchains. They
    must map a supported compiler ID to an existing correctly named binary.
    """
    configured = dict(explicit_paths or {})
    unknown = set(configured) - set(_SUPPORTED)
    if unknown:
        raise HdlFrontendError(f"unknown explicit compiler IDs: {sorted(unknown)}")
    tools: list[CompilerTool] = []
    for compiler_id, (language, output) in _SUPPORTED.items():
        selected = configured.get(compiler_id)
        discovered = str(selected) if selected is not None else shutil.which(compiler_id)
        path = Path(discovered).resolve() if discovered and Path(discovered).is_file() else None
        auxiliaries: tuple[tuple[str, str], ...] = ()
        if path is not None and compiler_id == "openvaf" and os.name == "nt":
            program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
            candidates = sorted(
                program_files.glob("Microsoft Visual Studio/*/*/VC/Tools/MSVC/*/bin/Hostx64/x64/link.exe"),
                reverse=True,
            )
            if candidates:
                linker = candidates[0].resolve()
                auxiliaries = ((str(linker), _sha256_file(linker)),)
        elif path is not None and compiler_id == "iverilog":
            ivl = path.parent.parent / "lib" / "ivl" / ("ivl.exe" if os.name == "nt" else "ivl")
            ivlpp = path.parent.parent / "lib" / "ivl" / ("ivlpp.exe" if os.name == "nt" else "ivlpp")
            auxiliaries = tuple(
                (str(item.resolve()), _sha256_file(item.resolve()))
                for item in (ivl, ivlpp) if item.is_file()
            )
        elif path is not None and compiler_id == "ghdl" and os.name == "nt":
            # The current UCRT package is not self-contained on this host.
            # Bind every PATH-resolved MinGW runtime DLL it actually requires.
            runtime_names = (
                "libgcc_s_seh-1.dll", "libwinpthread-1.dll",
                "libstdc++-6.dll", "zlib1.dll",
            )
            runtime_paths = [found for name in runtime_names if (found := _find_path_file(name))]
            auxiliaries = tuple((str(item), _sha256_file(item)) for item in runtime_paths)
        tools.append(CompilerTool(
            compiler_id=compiler_id, available=path is not None,
            executable=str(path) if path else "",
            executable_sha256=_sha256_file(path) if path else "",
            version=_read_version(path) if path else "not-installed",
            input_language=language, output_kind=output,
            auxiliary_executables=auxiliaries,
        ))
    return {
        "contract": TOOLCHAIN_INVENTORY_CONTRACT,
        "host": {"system": platform.system(), "machine": platform.machine()},
        "tools": [tool.to_dict() for tool in tools],
        "available_compilers": [tool.compiler_id for tool in tools if tool.available],
        "can_compile_verilog_a_to_osdi": any(
            tool.available and tool.compiler_id == "openvaf" for tool in tools
        ),
        "limitations": [
            "Discovery proves only executable identity and version output; it is not tool qualification.",
            "No compiler is downloaded or installed automatically.",
        ],
    }


@dataclass(frozen=True, slots=True)
class HdlCompilePlan:
    compilation_id: str
    compiler: CompilerTool
    source_name: str
    source_sha256: str
    language: str
    top_module: str
    output_name: str
    output_kind: str
    plan_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "compilation_id", _identifier(self.compilation_id, "compilation_id"))
        if not self.compiler.available:
            raise HdlFrontendError("selected compiler is not available.")
        if self.language != self.compiler.input_language or self.output_kind != self.compiler.output_kind:
            raise HdlFrontendError("compile plan does not match the compiler policy.")
        for field in ("source_name", "output_name"):
            value = str(getattr(self, field))
            if not value or Path(value).name != value or len(value) > 255 or "\x00" in value:
                raise HdlFrontendError(f"{field} must be one bounded base name.")
        object.__setattr__(self, "source_sha256", _digest(self.source_sha256, "source_sha256"))
        if self.top_module and _TOP.fullmatch(self.top_module) is None:
            raise HdlFrontendError("top_module is invalid.")
        object.__setattr__(self, "plan_sha256", _digest(self.plan_sha256, "plan_sha256"))
        if hashlib.sha256(_canonical(self.content_dict())).hexdigest() != self.plan_sha256:
            raise HdlFrontendError("plan_sha256 does not match canonical content.")

    def content_dict(self) -> dict[str, object]:
        return {
            "contract": COMPILE_PLAN_CONTRACT,
            "compilation_id": self.compilation_id,
            "compiler": self.compiler.to_dict(),
            "source_name": self.source_name, "source_sha256": self.source_sha256,
            "language": self.language, "top_module": self.top_module,
            "output_name": self.output_name, "output_kind": self.output_kind,
        }

    @classmethod
    def create(
        cls, *, compilation_id: str, compiler: CompilerTool,
        source: str | Path, top_module: str = "",
    ) -> "HdlCompilePlan":
        path = Path(source).resolve(strict=True)
        if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            raise HdlFrontendError("HDL source is not a bounded regular file.")
        extensions = {"verilog-a": {".va", ".vams"}, "verilog": {".v", ".sv"}, "vhdl": {".vhd", ".vhdl"}}
        if path.suffix.lower() not in extensions[compiler.input_language]:
            raise HdlFrontendError("HDL source extension does not match the selected compiler.")
        if compiler.compiler_id in {"iverilog", "verilator", "ghdl"} and not top_module:
            raise HdlFrontendError("top_module is required for digital HDL compilation.")
        suffix = {"osdi": ".osdi", "vvp": ".vvp", "lint": ".lint-ok", "analyzed-library": ".ghdl-ok"}[compiler.output_kind]
        output_name = f"{path.stem}{suffix}"
        source_sha = _sha256_file(path)
        content = {
            "contract": COMPILE_PLAN_CONTRACT, "compilation_id": compilation_id,
            "compiler": compiler.to_dict(), "source_name": path.name,
            "source_sha256": source_sha, "language": compiler.input_language,
            "top_module": top_module, "output_name": output_name,
            "output_kind": compiler.output_kind,
        }
        return cls(
            compilation_id=compilation_id, compiler=compiler,
            source_name=path.name, source_sha256=source_sha,
            language=compiler.input_language, top_module=top_module,
            output_name=output_name, output_kind=compiler.output_kind,
            plan_sha256=hashlib.sha256(_canonical(content)).hexdigest(),
        )


def _compiler_arguments(plan: HdlCompilePlan, source: Path, output: Path) -> list[str]:
    compiler = str(Path(plan.compiler.executable))
    if plan.compiler.compiler_id == "openvaf":
        return [compiler, str(source), "-o", str(output)]
    if plan.compiler.compiler_id == "iverilog":
        ivl_root = Path(compiler).parent.parent / "lib" / "ivl"
        return [
            # The packaged Windows driver requires the -B value to be joined.
            compiler, f"-B{ivl_root}", "-g2012", "-s", plan.top_module,
            "-o", str(output), str(source),
        ]
    if plan.compiler.compiler_id == "verilator":
        return [compiler, "--lint-only", "--top-module", plan.top_module, str(source)]
    if plan.compiler.compiler_id == "ghdl":
        return [compiler, "-a", "--std=08", str(source)]
    raise HdlFrontendError("unsupported compiler policy.")


Runner = Callable[[Sequence[str], Path, Mapping[str, str], float], subprocess.CompletedProcess[bytes]]


def _default_runner(
    arguments: Sequence[str], working_directory: Path,
    environment: Mapping[str, str], timeout_s: float,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(arguments), cwd=working_directory, env=dict(environment),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_s,
        check=False, shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def compile_hdl(
    plan: HdlCompilePlan, source: str | Path, output_directory: str | Path,
    *, timeout_s: float = 120.0, runner: Runner | None = None,
) -> dict[str, object]:
    """Invoke the selected real compiler with a policy-generated argument list."""

    source_path = Path(source).resolve(strict=True)
    if source_path.name != plan.source_name or _sha256_file(source_path) != plan.source_sha256:
        raise HdlCompileError("source_identity_mismatch")
    compiler_path = Path(plan.compiler.executable).resolve(strict=True)
    if _sha256_file(compiler_path) != plan.compiler.executable_sha256:
        raise HdlCompileError("compiler_identity_mismatch")
    timeout = float(timeout_s)
    if not math.isfinite(timeout) or not 0.0 < timeout <= 3600.0:
        raise HdlFrontendError("compile timeout must be positive and at most one hour.")
    destination = Path(output_directory).resolve(strict=True)
    if not destination.is_dir():
        raise HdlFrontendError("output_directory must be an existing directory.")
    selected_runner = runner or _default_runner
    path_entries = [compiler_path.parent]
    path_entries.extend(Path(item[0]).parent for item in plan.compiler.auxiliary_executables)
    if os.name == "nt":
        # Icarus uses cmd.exe to launch its reviewed ivl backends. Keep that
        # dependency explicit without inheriting the caller's arbitrary PATH.
        path_entries.append(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")
    if plan.compiler.compiler_id in {"iverilog", "verilator"}:
        suite_root = compiler_path.parent.parent
        path_entries.extend((suite_root / "bin", suite_root / "lib"))
    environment = {
        "SPIKES_HDL_COMPILE_PLAN_SHA256": plan.plan_sha256,
        # Allow reviewed adjacent runtime DLLs and compiler helper programs,
        # without inheriting the caller's arbitrary PATH.
        "PATH": os.pathsep.join(dict.fromkeys(str(item) for item in path_entries)),
    }
    if plan.compiler.compiler_id == "verilator":
        verilator_root = compiler_path.parent.parent / "share" / "verilator"
        if verilator_root.is_dir():
            environment["VERILATOR_ROOT"] = str(verilator_root)
    for key in (
        "SystemRoot", "WINDIR", "ProgramFiles", "ProgramFiles(x86)",
        "ProgramData", "USERPROFILE", "TEMP", "TMP",
        "COMSPEC",
    ):
        if key in os.environ:
            environment[key] = os.environ[key]
    with tempfile.TemporaryDirectory(prefix="spikes-hdl-") as temporary:
        root = Path(temporary)
        staged_source = root / plan.source_name
        shutil.copyfile(source_path, staged_source)
        staged_output = root / plan.output_name
        arguments = _compiler_arguments(plan, staged_source, staged_output)
        try:
            completed = selected_runner(arguments, root, environment, timeout)
        except (OSError, subprocess.SubprocessError) as exc:
            raise HdlCompileError("compiler_process_failed") from exc
        output_bytes = completed.stdout + completed.stderr
        if len(output_bytes) > 4 * 1024 * 1024:
            raise HdlCompileError("compiler_output_limit_exceeded")
        if completed.returncode != 0:
            diagnostic = output_bytes.decode("utf-8", errors="replace")
            raise HdlCompileError(
                "compiler_rejected_source",
                f"return_code={completed.returncode}\n{diagnostic}",
            )
        # Lint/analyze backends do not naturally produce a portable artifact;
        # write an attestation marker, not executable code.
        if plan.output_kind in {"lint", "analyzed-library"} and not staged_output.exists():
            staged_output.write_bytes(_canonical({
                "plan_sha256": plan.plan_sha256,
                "compiler_sha256": plan.compiler.executable_sha256,
                "source_sha256": plan.source_sha256,
                "result": "accepted",
            }))
        if not staged_output.is_file() or staged_output.stat().st_size <= 0:
            raise HdlCompileError("compiler_artifact_missing")
        if staged_output.stat().st_size > 256 * 1024 * 1024:
            raise HdlCompileError("compiler_artifact_limit_exceeded")
        final_output = destination / plan.output_name
        if final_output.exists():
            raise HdlCompileError("output_already_exists")
        shutil.copyfile(staged_output, final_output)
    return {
        "contract": COMPILE_RESULT_CONTRACT, "status": "compiled",
        "plan_sha256": plan.plan_sha256, "compiler_id": plan.compiler.compiler_id,
        "compiler_sha256": plan.compiler.executable_sha256,
        "auxiliary_executables": [
            {"path": path, "sha256": digest}
            for path, digest in plan.compiler.auxiliary_executables
        ],
        "source_sha256": plan.source_sha256, "artifact": str(final_output),
        "artifact_sha256": _sha256_file(final_output), "output_kind": plan.output_kind,
        "loadable_by_spikes_solver": False,
        "limitations": [
            "Compilation success does not qualify model equations or numerical behavior.",
            "Native OSDI callback loading into the SPIKES MNA solver is not implemented by this frontend.",
        ],
    }


@dataclass(frozen=True, slots=True)
class OsdiModuleManifest:
    module_id: str
    module_name: str
    artifact_name: str
    artifact_sha256: str
    source_sha256: str
    compiler_sha256: str
    osdi_abi_major: int
    osdi_abi_minor: int
    callbacks: tuple[str, ...]
    manifest_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "module_id", _identifier(self.module_id, "module_id"))
        if _TOP.fullmatch(self.module_name) is None:
            raise HdlFrontendError("module_name is invalid.")
        if not self.artifact_name or Path(self.artifact_name).name != self.artifact_name:
            raise HdlFrontendError("artifact_name must be one base name.")
        for field in ("artifact_sha256", "source_sha256", "compiler_sha256"):
            object.__setattr__(self, field, _digest(getattr(self, field), field))
        if (
            isinstance(self.osdi_abi_major, bool) or not isinstance(self.osdi_abi_major, int)
            or isinstance(self.osdi_abi_minor, bool) or not isinstance(self.osdi_abi_minor, int)
            or self.osdi_abi_major < 0 or self.osdi_abi_minor < 0
        ):
            raise HdlFrontendError("OSDI ABI version values must be nonnegative integers.")
        callbacks = tuple(sorted(set(str(item).lower() for item in self.callbacks)))
        if not _OSDI_CALLBACKS <= set(callbacks):
            raise HdlFrontendError("OSDI manifest omits required callback declarations.")
        object.__setattr__(self, "callbacks", callbacks)
        object.__setattr__(self, "manifest_sha256", _digest(self.manifest_sha256, "manifest_sha256"))
        if hashlib.sha256(_canonical(self.content_dict())).hexdigest() != self.manifest_sha256:
            raise HdlFrontendError("OSDI manifest digest does not match canonical content.")

    def content_dict(self) -> dict[str, object]:
        return {
            "contract": OSDI_MODULE_CONTRACT, "module_id": self.module_id,
            "module_name": self.module_name, "artifact_name": self.artifact_name,
            "artifact_sha256": self.artifact_sha256, "source_sha256": self.source_sha256,
            "compiler_sha256": self.compiler_sha256,
            "osdi_abi_major": self.osdi_abi_major, "osdi_abi_minor": self.osdi_abi_minor,
            "callbacks": list(self.callbacks),
        }

    @classmethod
    def create(
        cls, *, module_id: str, module_name: str, artifact: str | Path,
        source_sha256: str, compiler_sha256: str, osdi_abi_major: int,
        osdi_abi_minor: int, callbacks: Iterable[str],
    ) -> "OsdiModuleManifest":
        path = Path(artifact).resolve(strict=True)
        configured = tuple(sorted(set(str(item).lower() for item in callbacks)))
        content = {
            "contract": OSDI_MODULE_CONTRACT, "module_id": module_id,
            "module_name": module_name, "artifact_name": path.name,
            "artifact_sha256": _sha256_file(path), "source_sha256": source_sha256,
            "compiler_sha256": compiler_sha256, "osdi_abi_major": osdi_abi_major,
            "osdi_abi_minor": osdi_abi_minor, "callbacks": list(configured),
        }
        return cls(
            module_id=module_id, module_name=module_name, artifact_name=path.name,
            artifact_sha256=str(content["artifact_sha256"]), source_sha256=source_sha256,
            compiler_sha256=compiler_sha256, osdi_abi_major=osdi_abi_major,
            osdi_abi_minor=osdi_abi_minor, callbacks=configured,
            manifest_sha256=hashlib.sha256(_canonical(content)).hexdigest(),
        )

    def verify_artifact(self, artifact: str | Path) -> Path:
        path = Path(artifact).resolve(strict=True)
        if path.name != self.artifact_name or not path.is_file() or _sha256_file(path) != self.artifact_sha256:
            raise HdlFrontendError("OSDI artifact identity does not match its manifest.")
        return path


def compiled_isolation_profile() -> dict[str, object]:
    """Report enforced and absent isolation; do not infer sandbox strength."""

    return {
        "contract": ISOLATION_PROFILE_CONTRACT,
        "host_system": platform.system(),
        "enforced": {
            "separate_process": True, "shell_disabled": True,
            "digest_bound_executable": True, "fixed_argument_policy": True,
            "minimal_environment": True, "temporary_working_directory": True,
            "wall_clock_limit": True, "input_output_limits": True,
        },
        "not_enforced": {
            "filesystem_namespace": True, "network_namespace": True,
            "syscall_filter": True, "windows_appcontainer": True,
            "windows_restricted_token": True, "linux_seccomp": True,
            "macos_sandbox_profile": True, "memory_limit": True, "cpu_quota": True,
        },
        "sandbox_strength": "trusted_digest_reviewed_code_only",
        "hostile_or_multitenant_safe": False,
    }


__all__ = [
    "COMPILE_PLAN_CONTRACT", "COMPILE_RESULT_CONTRACT", "CompilerTool",
    "HdlCompileError", "HdlCompilePlan", "HdlFrontendError", "OsdiModuleManifest",
    "compiled_isolation_profile", "compile_hdl", "discover_hdl_toolchains",
]
