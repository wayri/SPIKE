# SPDX-License-Identifier: Apache-2.0
"""Explicitly approved, bounded component-package compilation.

This module is a compiler adapter, not a hostile-code sandbox.  Importing a
component package never reaches this adapter.  Callers must present the exact
canonical behavior digest and explicit trusted-code consent before any parser
or compiler is selected.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from typing import Any


BUILD_TIMEOUT_S = 45
MAX_LOG_BYTES = 2 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".spikes-component-", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_bytes(destination: Path, data: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".spikes-component-", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _base_report(language: str, behavior_sha256: str, tool: str | None) -> dict[str, Any]:
    return {
        "status": "failed",
        "language": language,
        "tool": tool,
        "log": "",
        "artifact_path": None,
        "artifact_sha256": None,
        "behavior_sha256": behavior_sha256,
        "qualified": False,
        "limitations": [],
    }


def _run_bounded(argv: list[str], work: Path, environment: dict[str, str]) -> tuple[int, str, str | None]:
    """Run one compiler while actively bounding elapsed time and captured output."""
    process = subprocess.Popen(
        argv,
        cwd=work,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = bytearray()
    output_exceeded = threading.Event()

    def read_output() -> None:
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read(64 * 1024)
            if not chunk:
                return
            remaining = MAX_LOG_BYTES - len(output)
            if remaining > 0:
                output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                output_exceeded.set()
                try:
                    process.kill()
                except OSError:
                    pass

    reader = threading.Thread(target=read_output, daemon=True, name="spikes-component-build-log")
    reader.start()
    failure: str | None = None
    try:
        process.wait(timeout=BUILD_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        failure = f"Build exceeded {BUILD_TIMEOUT_S} seconds"
        process.kill()
        process.wait()
    reader.join(timeout=2)
    if reader.is_alive():
        failure = failure or "Build log reader did not terminate"
        if process.stdout is not None:
            process.stdout.close()
        reader.join(timeout=1)
    elif process.stdout is not None:
        process.stdout.close()
    if output_exceeded.is_set():
        failure = "Build log exceeded 2 MiB"
    log = bytes(output).decode("utf-8", errors="replace").replace("\r\r\n", "\n").replace("\r\n", "\n")
    return process.returncode, log, failure


def _metadata(package: dict[str, Any], behavior_sha256: str, artifact: Path,
              limitations: list[str], **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "contract": "spikes/component-build-metadata/v1",
        "component_id": package["id"],
        "component_version": package["version"],
        "language": package["implementation"]["language"],
        "behavior_sha256": behavior_sha256,
        "artifact": artifact.name,
        "artifact_sha256": _sha256(artifact),
        "qualified": False,
        "limitations": limitations,
    }
    result.update(extra)
    return result


def _write_metadata(destination: Path, value: dict[str, Any]) -> None:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")
    _atomic_bytes(destination, data)


def _component_output_directory(root: Path, package: dict[str, Any], behavior_sha256: str,
                                artifact_name: str, metadata_name: str) -> Path:
    """Select a content-addressed child without adopting unrelated files."""
    output = root / f"{package['id']}--{package['version']}--{behavior_sha256[:12]}"
    if output.is_symlink():
        raise ValueError("Component build output path is not an owned directory")
    if not output.exists():
        return output
    if not output.is_dir():
        raise ValueError("Component build output path is not an owned directory")
    entries = {path.name for path in output.iterdir()}
    if entries != {artifact_name, metadata_name}:
        raise ValueError("Component build output contains files not owned by this build")
    artifact = output / artifact_name
    metadata_path = output / metadata_name
    if artifact.is_symlink() or metadata_path.is_symlink() or not artifact.is_file() or not metadata_path.is_file():
        raise ValueError("Component build output contains linked or missing artifacts")
    if metadata_path.stat().st_size > 1024 * 1024:
        raise ValueError("Component build metadata exceeds 1 MiB")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Component build metadata is unreadable") from exc
    if (
        not isinstance(metadata, dict)
        or metadata.get("contract") != "spikes/component-build-metadata/v1"
        or metadata.get("component_id") != package["id"]
        or metadata.get("component_version") != package["version"]
        or metadata.get("behavior_sha256") != behavior_sha256
        or metadata.get("artifact") != artifact_name
        or metadata.get("artifact_sha256") != _sha256(artifact)
    ):
        raise ValueError("Existing component artifact does not match its build metadata")
    return output


def _spice_harness(package: dict[str, Any]) -> tuple[str, str]:
    implementation = package["implementation"]
    prefix = implementation["prefix"].upper()
    names = [terminal["name"] for terminal in package["symbol"]["terminals"]]
    nodes = [f"spikes_build_pin_{index}" for index in range(len(names))]
    instance = f"{prefix}SPIKES_BUILD " + " ".join(nodes + [implementation["entry"]])
    shunts = [f"RSPIKES_BUILD_{index} {node} 0 1e12" for index, node in enumerate(nodes)]
    harness = "\n".join([instance, *shunts, ".op", ".end", ""])
    return package["implementation"]["source"].rstrip() + "\n" + harness, instance


def _build_spice(package: dict[str, Any], destination: Path,
                 behavior_sha256: str) -> dict[str, Any]:
    report = _base_report("SPICE", behavior_sha256, "SPIKES native SPICE parser")
    limitations = [
        "Source packaging and parser preflight only; no numerical execution or model qualification was performed.",
        "The inert harness checks the declared placement form where supported; it does not prove behavior or convergence.",
    ]
    report["limitations"] = limitations
    try:
        from python.spikes.netlist import parse_netlist
        from .component_package import portable_spice_source

        portable_spice_source(package["implementation"]["source"])
        harness, instance = _spice_harness(package)
        parse_netlist(harness, source_name="<trusted-component-preflight>",
                      native_extensions=True, transient_capture="rolling")
    except Exception as exc:
        report["log"] = f"SPICE parser preflight failed: {exc}"
        return report

    artifact = destination / "component.spice"
    _atomic_bytes(artifact, package["implementation"]["source"].encode("utf-8"))
    metadata = _metadata(package, behavior_sha256, artifact, limitations,
                         preflight="parser_with_inert_instance", instance=instance)
    _write_metadata(destination / "component.spice.metadata.json", metadata)
    report.update(status="preflighted", log="SPICE source parsed with an inert instance harness; no simulation was run.",
                  artifact_path=str(artifact), artifact_sha256=metadata["artifact_sha256"])
    return report


def _build_cpp(package: dict[str, Any], destination: Path,
               behavior_sha256: str) -> dict[str, Any]:
    from .ide import find_tool

    tool = find_tool("clang++") or find_tool("cl")
    if not tool:
        raise ValueError("No C++ compiler configured")
    report = _base_report("C++", behavior_sha256, tool)
    limitations = [
        "Compiled trusted native code is not a hostile-code sandbox.",
        "The executable was compiled but not executed; compilation does not qualify controller behavior.",
    ]
    report["limitations"] = limitations
    implementation = package["implementation"]
    config = deepcopy(implementation.get("controller"))
    if not isinstance(config, dict):
        report["log"] = "C++ component build requires a generic-controller/v1 configuration."
        return report
    if config.get("language") != "C++" or config.get("source") != implementation["source"]:
        report["log"] = "Controller language/source does not match the component implementation."
        return report

    from .controller_block import Controller

    runtime = None
    try:
        runtime = Controller(config, trusted=True)
        # Preserve the manifest-bound executable name when moving it out of
        # the Controller's temporary build directory.
        artifact = destination / runtime.executable.name
        _atomic_copy(runtime.executable, artifact)
        manifest = runtime.manifest.content_dict()
        metadata = _metadata(package, behavior_sha256, artifact, limitations,
                             compiled_block_manifest=manifest)
        _write_metadata(destination / "component-controller.metadata.json", metadata)
        report.update(status="built", log=runtime.build_log, artifact_path=str(artifact),
                      artifact_sha256=metadata["artifact_sha256"])
        return report
    except (OSError, ValueError) as exc:
        report["log"] = str(exc)
        return report
    finally:
        if runtime is not None:
            runtime.close()


def _build_verilog(package: dict[str, Any], destination: Path,
                   behavior_sha256: str) -> dict[str, Any]:
    from .ide import find_tool

    tool = find_tool("iverilog")
    if not tool:
        raise ValueError("iverilog is not installed/configured")
    report = _base_report("Verilog", behavior_sha256, tool)
    limitations = [
        "Compile-only Verilog artifact; it was not simulated or synthesized.",
        "No analog/electrical terminal coupling or HDL behavior qualification is claimed.",
    ]
    report["limitations"] = limitations
    implementation = package["implementation"]
    with tempfile.TemporaryDirectory(prefix="spikes-component-verilog-") as directory:
        work = Path(directory)
        source = work / "component.v"
        output = work / "block.vvp"
        source.write_text(implementation["source"], encoding="utf-8")
        argv = [tool, "-g2012", "-s", implementation["entry"], "-o", output.name, source.name]
        environment = dict(os.environ)
        bin_directory = Path(tool).parent
        environment["PATH"] = os.pathsep.join((str(bin_directory), str(bin_directory.parent / "lib"),
                                                environment.get("PATH", "")))
        try:
            returncode, log, bounded_failure = _run_bounded(argv, work, environment)
        except OSError as exc:
            report["log"] = f"Compiler could not start: {exc}"
            return report
        report["log"] = log
        if bounded_failure:
            report["log"] = (log + "\n" + bounded_failure).strip()
            return report
        if returncode != 0 or not output.is_file():
            if not report["log"]:
                report["log"] = f"iverilog exited with code {returncode}"
            return report
        artifact = destination / "block.vvp"
        _atomic_copy(output, artifact)
    metadata = _metadata(package, behavior_sha256, artifact, limitations,
                         compiler_arguments=["-g2012", "-s", implementation["entry"]])
    _write_metadata(destination / "block.vvp.metadata.json", metadata)
    report.update(status="built", artifact_path=str(artifact), artifact_sha256=metadata["artifact_sha256"])
    return report


def build_component(value: object, destination: str | Path, *, trusted: bool = False,
                    approval_sha256: str | None = None) -> dict[str, Any]:
    """Build one validated component after exact behavior-bound consent.

    ``destination`` is an application-selected directory.  Package data never
    selects an output path.  Generated C++ and Verilog artifacts are not run.
    """
    # The package contract stays a data-only import dependency.  Keeping this
    # import local also prevents merely importing this module from doing work.
    from .component_package import behavior_digest, validate

    package = validate(deepcopy(value))
    digest = behavior_digest(package)
    if trusted is not True:
        raise ValueError("Explicit trusted-code consent is required before component build")
    if approval_sha256 != digest:
        raise ValueError("Component approval SHA-256 does not match the canonical behavior digest")
    target = Path(destination).resolve()
    if target.exists() and not target.is_dir():
        raise ValueError("Component build destination must be a directory")

    language = package["implementation"]["language"]
    if language == "SPICE":
        output = _component_output_directory(
            target, package, digest, "component.spice", "component.spice.metadata.json",
        )
        return _build_spice(package, output, digest)
    if language == "C++":
        executable_name = "controller.exe" if os.name == "nt" else "controller"
        output = _component_output_directory(
            target, package, digest, executable_name, "component-controller.metadata.json",
        )
        return _build_cpp(package, output, digest)
    if language == "Verilog":
        output = _component_output_directory(
            target, package, digest, "block.vvp", "block.vvp.metadata.json",
        )
        return _build_verilog(package, output, digest)
    raise ValueError("Unsupported component implementation language")
