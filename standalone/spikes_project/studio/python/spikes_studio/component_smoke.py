# SPDX-License-Identifier: Apache-2.0
"""Frozen-safe component-maker workflow acceptance.

The fixtures in this module are fixed application-owned sources.  This is an
engineering-preview smoke test, not a general mechanism for running imported
code and not physics qualification.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import traceback
import uuid


CONTRACT = "spikes/component-workflow-self-test/v1"
VALIDATION_SCOPE = "component-maker-engineering-preview-workflows"
MAX_ERROR_CHARS = 8192


CPP_SOURCE = """void control_step(double time_s, double step_s,
                  const double *inputs, double *outputs, double *state) {
    (void)time_s;
    state[0] += step_s;
    outputs[0] = inputs[0] * 0.5 + state[0];
}
"""


VERILOG_SOURCE = """`timescale 1ns/1ps
module component_smoke(input wire IN, output wire OUT);
  assign OUT = IN;
endmodule

module component_smoke_tb;
  reg IN;
  wire OUT;
  component_smoke dut(.IN(IN), .OUT(OUT));
  initial begin
    IN = 1'b0;
    #1;
    if (OUT !== 1'b0) $fatal(1, "low level did not propagate");
    IN = 1'b1;
    #1;
    if (OUT !== 1'b1) $fatal(1, "high level did not propagate");
    $display("SPIKES_COMPONENT_SMOKE_PASS");
    $finish;
  end
endmodule
"""


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: str | Path | None) -> dict[str, object]:
    if not path:
        return {"path": None, "sha256": None, "size_bytes": None}
    resolved = Path(path).resolve()
    if not resolved.is_file():
        return {"path": str(resolved), "sha256": None, "size_bytes": None}
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


@contextmanager
def _isolated_environment(root: Path):
    """Confine mutable runtime state without depending on a source checkout."""
    directories = {
        "LOCALAPPDATA": root / "local-app-data",
        "APPDATA": root / "roaming-app-data",
        "XDG_CACHE_HOME": root / "xdg-cache",
        "XDG_CONFIG_HOME": root / "xdg-config",
        "XDG_DATA_HOME": root / "xdg-data",
        "MPLCONFIGDIR": root / "matplotlib",
        "TEMP": root / "temp",
        "TMP": root / "temp",
        "TMPDIR": root / "temp",
    }
    for directory in set(directories.values()):
        directory.mkdir(parents=True, exist_ok=True)
    previous = {name: os.environ.get(name) for name in directories}
    previous_tempdir = tempfile.tempdir
    try:
        os.environ.update({name: str(path) for name, path in directories.items()})
        # tempfile caches its first discovery.  Bind it explicitly so helpers
        # imported before this context cannot escape the disposable root.
        tempfile.tempdir = str(directories["TEMP"])
        yield
    finally:
        tempfile.tempdir = previous_tempdir
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _spice_component() -> dict:
    from .component_package import new_component, symbol_for_pins, validate

    value = new_component()
    value.update(id="selftest.rc_lowpass", name="Self-test RC low-pass")
    value["symbol"] = symbol_for_pins(["IN", "OUT", "REF"], value["name"])
    value["implementation"] = {
        "language": "SPICE",
        "entry": "SelfTestRC",
        "prefix": "X",
        "source": (
            ".subckt SelfTestRC IN OUT REF\n"
            "RSELF IN OUT 1k\n"
            "CSELF OUT REF 1u\n"
            ".ends SelfTestRC\n"
        ),
    }
    return validate(value)


def _cpp_component() -> dict:
    from .component_package import controller_config, new_component, symbol_for_pins, validate

    value = new_component()
    value.update(id="selftest.sampled_controller", name="Self-test sampled controller")
    value["symbol"] = symbol_for_pins(["SENSE", "DRIVE"], value["name"])
    value["symbol"]["terminals"][0]["mode"] = "AI"
    value["symbol"]["terminals"][1]["mode"] = "AO"
    value["implementation"] = {
        "language": "C++",
        "entry": "control_step",
        "source": CPP_SOURCE,
        "controller": controller_config(value["symbol"], CPP_SOURCE, step_s=1e-4, state_count=2),
    }
    return validate(value)


def _verilog_component() -> dict:
    from .component_package import new_component, symbol_for_pins, validate

    value = new_component()
    value.update(id="selftest.digital_passthrough", name="Self-test digital passthrough")
    value["symbol"] = symbol_for_pins(["IN", "OUT"], value["name"])
    value["symbol"]["terminals"][0]["mode"] = "DI"
    value["symbol"]["terminals"][1]["mode"] = "DO"
    value["implementation"] = {
        "language": "Verilog",
        "entry": "component_smoke_tb",
        "source": VERILOG_SOURCE,
    }
    return validate(value)


def _roundtrip(value: dict, root: Path) -> tuple[dict, Path, int]:
    """Exercise explicit .spkcmp save/load/install/load without executing it."""
    from .component_package import ComponentStore, load, save

    root.mkdir(parents=True, exist_ok=True)
    source = root / (value["id"] + ".spkcmp")
    save(source, value)
    loaded = load(source)
    store = ComponentStore(root / "library")
    installed = store.install(loaded)
    installed_value = load(installed)
    if installed_value != loaded:
        raise AssertionError("Installed component package did not round-trip exactly")
    entries = store.entries()
    if len(entries) != 1 or entries[0]["component"] != loaded:
        raise AssertionError("Component store did not return the installed package")
    return installed_value, installed, len(entries)


def _spice_workflow(root: Path, native_library: Path) -> dict[str, object]:
    from .component_build import build_component
    from .component_package import behavior_digest, insert, prepare_insert
    from .document import Document
    from python.spikes.native_runner import run_native_project
    from python.spikes.netlist import parse_netlist

    value, installed, entries = _roundtrip(_spice_component(), root / "spice")
    digest = behavior_digest(value)
    before = deepcopy(value)
    build = build_component(value, root / "builds", trusted=True, approval_sha256=digest)
    if value != before or build["status"] != "preflighted":
        raise AssertionError("SPICE preflight mutated or failed the imported inert package")

    deck = """SPIKES component self-test RC
V1 in 0 1
.tran 10u 5m uic
.end
"""
    document = Document.from_netlist(deck)
    mapping = {"1": "in", "2": "filtered", "3": "0"}
    insert(document, prepare_insert(document, value, mapping))
    instance = document.data["metadata"]["component_instances"][-1]
    if instance["pins"] != mapping:
        raise AssertionError("Saved component pin mapping changed")
    if not native_library.is_file():
        raise FileNotFoundError(f"Native circuit library is missing: {native_library}")
    project = parse_netlist(document.data["source"], native_extensions=True,
                            transient_capture="full")
    result = run_native_project(project, str(native_library),
                                integration_method="backward_euler").to_dict()
    if result["status"] != "completed":
        raise AssertionError("Native RC run did not complete")
    voltages = result["data"]["node_voltage_v"].get("filtered", [])
    if len(voltages) < 2 or not 0.9 < float(voltages[-1]) <= 1.01:
        raise AssertionError("Native RC output did not reach the expected bounded final voltage")
    return {
        "package": installed.name,
        "store_entries": entries,
        "behavior_sha256": digest,
        "artifact_sha256": build["artifact_sha256"],
        "pin_mapping": mapping,
        "native_points": len(result["data"].get("time_s", [])),
        "final_output_v": float(voltages[-1]),
    }


def _cpp_workflow(root: Path) -> dict[str, object]:
    from .component_build import build_component
    from .component_package import behavior_digest
    from .controller_block import Controller

    value, installed, entries = _roundtrip(_cpp_component(), root / "cpp")
    digest = behavior_digest(value)
    build = build_component(value, root / "builds", trusted=True, approval_sha256=digest)
    if build["status"] != "built" or not build["artifact_sha256"]:
        raise AssertionError("C++ component build did not produce a content-addressed artifact: " +
                             str(build.get("log", ""))[-4000:])
    runtime = Controller(value["implementation"]["controller"], trusted=True)
    try:
        first = runtime.step({"SENSE": 2.0}, 0.0, 1e-4)
        second = runtime.step({"SENSE": 0.4}, 1e-4, 1e-4)
        if abs(first["VDRIVE"] - 1.0001) > 1e-12:
            raise AssertionError("First sampled Controller ABI output was incorrect")
        if abs(second["VDRIVE"] - 0.2002) > 1e-12:
            raise AssertionError("Controller ABI explicit state did not survive the next tick")
        runtime_hash = runtime.manifest.executable_sha256
    finally:
        runtime.close()
    return {
        "package": installed.name,
        "store_entries": entries,
        "behavior_sha256": digest,
        "artifact_sha256": build["artifact_sha256"],
        "controller_executable_sha256": runtime_hash,
        "tool": build["tool"],
        "samples": 2,
        "outputs_v": [first["VDRIVE"], second["VDRIVE"]],
    }


def _verilog_compile(root: Path) -> tuple[dict[str, object], Path]:
    from .component_build import build_component
    from .component_package import behavior_digest

    value, installed, entries = _roundtrip(_verilog_component(), root / "verilog")
    digest = behavior_digest(value)
    build = build_component(value, root / "builds", trusted=True, approval_sha256=digest)
    artifact = Path(build["artifact_path"]) if build.get("artifact_path") else None
    if build["status"] != "built" or artifact is None or not artifact.is_file():
        raise AssertionError("Verilog component compilation did not produce a VVP artifact: " +
                             str(build.get("log", ""))[-4000:])
    return ({
        "package": installed.name,
        "store_entries": entries,
        "behavior_sha256": digest,
        "artifact_sha256": build["artifact_sha256"],
        "tool": build["tool"],
    }, artifact)


def _verilog_simulation(artifact: Path, vvp: str) -> dict[str, object]:
    environment = dict(os.environ)
    tool_directory = Path(vvp).resolve().parent
    environment["PATH"] = os.pathsep.join((str(tool_directory),
                                             str(tool_directory.parent / "lib"),
                                             environment.get("PATH", "")))
    try:
        process = subprocess.run(
            [vvp, str(artifact)], cwd=artifact.parent, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError("Digital VVP simulation exceeded 15 seconds") from exc
    output = process.stdout[:2 * 1024 * 1024].decode(errors="replace")
    if len(process.stdout) > 2 * 1024 * 1024:
        raise AssertionError("Digital VVP simulation log exceeded 2 MiB")
    marker = "SPIKES_COMPONENT_SMOKE_PASS"
    if process.returncode != 0 or marker not in output:
        raise AssertionError(
            f"Digital VVP simulation failed ({process.returncode}): {output[-2000:]}"
        )
    return {
        "tool": str(Path(vvp).resolve()),
        "exit_code": process.returncode,
        "marker": marker,
        "output_sha256": hashlib.sha256(process.stdout).hexdigest(),
    }


def _passed(name: str, evidence: dict[str, object]) -> dict[str, object]:
    return {"id": name, "status": "passed", "evidence": evidence, "error": None}


def _skipped(name: str, reason: str) -> dict[str, object]:
    return {"id": name, "status": "skipped", "evidence": {}, "error": reason}


def _failed(name: str) -> dict[str, object]:
    error = traceback.format_exc()
    if len(error) > MAX_ERROR_CHARS:
        error = error[-MAX_ERROR_CHARS:]
    return {"id": name, "status": "failed", "evidence": {}, "error": error}


def _write_report(destination: Path, report: dict[str, object]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                        allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _discover_tools() -> dict[str, str | None]:
    from .ide import find_tool

    return {name: find_tool(name) for name in ("clang++", "cl", "iverilog", "vvp")}


def run(library: str | Path, destination: str | Path) -> int:
    """Run component workflows and write one structured, installed-safe report."""
    destination = Path(destination).resolve()
    native_library = Path(library).resolve()
    discovered = _discover_tools()
    clang_tool = discovered["clang++"]
    cl_tool = discovered["cl"]
    cpp_tool = clang_tool or cl_tool
    iverilog = discovered["iverilog"]
    vvp = discovered["vvp"]
    tool_records = {
        "cpp": _file_record(cpp_tool),
        "iverilog": _file_record(iverilog),
        "vvp": _file_record(vvp),
    }
    cases: list[dict[str, object]] = []
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".spikes-component-self-test-",
                                         dir=destination.parent) as directory:
            root = Path(directory)
            with _isolated_environment(root / "isolated-runtime"):
                # Tool discovery may have come from the user's settings.  Save
                # the exact resolved paths into the isolated profile so later
                # component_build/Controller lookups use the same binaries
                # without reading or mutating the real user profile.
                from .toolchains import save as save_toolchains, settings_path
                settings_path().parent.mkdir(parents=True, exist_ok=True)
                save_toolchains({
                    "clang++": clang_tool or "",
                    "cl": cl_tool or "",
                    "iverilog": iverilog or "",
                    "vvp": vvp or "",
                })
                try:
                    cases.append(_passed("spice_package_pinmap_native_rc",
                                         _spice_workflow(root, native_library)))
                except Exception:
                    cases.append(_failed("spice_package_pinmap_native_rc"))

                if cpp_tool:
                    try:
                        cases.append(_passed("cpp_controller_compile_and_sample",
                                             _cpp_workflow(root)))
                    except Exception:
                        cases.append(_failed("cpp_controller_compile_and_sample"))
                else:
                    cases.append(_skipped("cpp_controller_compile_and_sample",
                                          "No configured C++ compiler was found"))

                verilog_artifact = None
                if iverilog:
                    try:
                        evidence, verilog_artifact = _verilog_compile(root)
                        cases.append(_passed("verilog_component_compile", evidence))
                    except Exception:
                        cases.append(_failed("verilog_component_compile"))
                else:
                    cases.append(_skipped("verilog_component_compile",
                                          "iverilog is not installed/configured"))

                if verilog_artifact is None:
                    cases.append(_skipped("verilog_vvp_digital_simulation",
                                          "Verilog compilation did not produce a runnable artifact"))
                elif not vvp:
                    cases.append(_skipped("verilog_vvp_digital_simulation",
                                          "vvp is not installed/configured"))
                else:
                    try:
                        cases.append(_passed("verilog_vvp_digital_simulation",
                                             _verilog_simulation(verilog_artifact, vvp)))
                    except Exception:
                        cases.append(_failed("verilog_vvp_digital_simulation"))
    except Exception:
        cases.append(_failed("self_test_runtime_setup"))

    counts = {status: sum(case["status"] == status for case in cases)
              for status in ("passed", "failed", "skipped")}
    counts["total"] = len(cases)
    errors = [{"case": case["id"], "error": case["error"]}
              for case in cases if case["status"] == "failed"]
    complete = counts["failed"] == 0 and counts["skipped"] == 0
    report = {
        "contract": CONTRACT,
        "status": "passed" if complete else "failed",
        "passed": complete,
        "validation_scope": VALIDATION_SCOPE,
        "counts": counts,
        "errors": errors,
        "native": _file_record(native_library),
        "tools": tool_records,
        "cases": cases,
        "limitations": [
            "Engineering-preview workflow verification; this is not component or solver physics qualification.",
            "The C++ check executes only the fixed sampled Controller ABI fixture, not arbitrary continuous models.",
            "The Verilog check is digital VVP simulation and does not claim analog terminal co-simulation.",
            "Missing optional compiler toolchains are explicit skips; discovered tool failures are failures.",
        ],
    }
    try:
        _write_report(destination, report)
    except Exception:
        return 1
    return 0 if report["passed"] else 1

