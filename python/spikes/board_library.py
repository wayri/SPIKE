# SPDX-License-Identifier: Apache-2.0
"""Compile a bounded circuit snapshot into an owned-engine board shared library.

This exporter accepts data, not caller-supplied C/C++ or compiler flags. Native
code is loaded only by the separate explicit board_library_client API.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Sequence

from .contracts import CircuitProject
from .fault_injection import FaultSite

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "spikes/compiled-board/v1"
MAX_ELEMENTS = 4096
MAX_PORTS = 256
MAX_FAULTS = 256
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z", re.ASCII)


def _finite(value: float, label: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{label} must be a number")
    value = float(value)
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"{label} must be finite" + (" and positive" if positive else ""))
    return value


@dataclass(frozen=True)
class AnalogInput:
    name: str
    node: str
    resistance_ohm: float
    minimum_v: float
    maximum_v: float
    initial_v: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _NAME.fullmatch(self.name):
            raise ValueError("Input name must be a bounded ASCII identifier")
        for key in ("resistance_ohm", "minimum_v", "maximum_v", "initial_v"):
            object.__setattr__(self, key, _finite(getattr(self, key), key, key == "resistance_ohm"))
        if not self.minimum_v <= self.initial_v <= self.maximum_v or self.minimum_v == self.maximum_v:
            raise ValueError("Input initial voltage must lie within distinct declared limits")


@dataclass(frozen=True)
class BoardOutput:
    name: str
    quantity: str
    target: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _NAME.fullmatch(self.name):
            raise ValueError("Output name must be a bounded ASCII identifier")
        if self.quantity not in {"voltage", "current"}:
            raise ValueError("Output quantity must be voltage or current")


@dataclass(frozen=True)
class BoardLimits:
    min_step_s: float = 1e-12
    max_step_s: float = 1e-5
    stop_time_s: float = 1.0
    max_steps: int = 100_000
    absolute_tolerance: float = 1e-9
    relative_tolerance: float = 1e-7
    max_newton_iterations: int = 80
    max_backtracks: int = 20

    def __post_init__(self) -> None:
        for key in ("min_step_s", "max_step_s", "stop_time_s", "absolute_tolerance", "relative_tolerance"):
            object.__setattr__(self, key, _finite(getattr(self, key), key, True))
        for key, maximum in (("max_steps", 10_000_000), ("max_newton_iterations", 1000), ("max_backtracks", 100)):
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f"{key} must be an integer in [1, {maximum}]")
        if self.min_step_s > self.max_step_s or self.max_step_s > self.stop_time_s:
            raise ValueError("Require minimum step <= maximum step <= stop time")


@dataclass(frozen=True)
class FaultBinding:
    """Bind a fault site to an existing parameter or an explicit shunt.

    ``positive_node`` and ``negative_node`` are both required only when a
    resistance site provisions a new finite shunt resistor. Existing resistor
    and NMOS threshold sites leave both terminals unset.
    """

    site: FaultSite
    positive_node: str | None = None
    negative_node: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.site, FaultSite):
            raise TypeError("Fault binding requires a FaultSite")
        if (self.positive_node is None) != (self.negative_node is None):
            raise ValueError("Fault shunt binding requires both terminals or neither")
        for node in (self.positive_node, self.negative_node):
            if node is not None:
                _literal(node)


def _literal(value: str) -> str:
    # JSON escaping is a C++ string literal only for this restricted ASCII set.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.$:+-]{1,256}", value, re.ASCII):
        raise ValueError("Circuit identifier is not safe for the compiled-board subset")
    return json.dumps(value)


def _mechanism_literal(value: str) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= 256
            or any(ord(char) < 32 or ord(char) > 126 for char in value)):
        raise ValueError("Fault mechanism must be bounded printable ASCII")
    return json.dumps(value)


def _definition(project: CircuitProject, inputs: Sequence[AnalogInput],
                outputs: Sequence[BoardOutput], limits: BoardLimits,
                faults: Sequence[FaultBinding] = ()) -> str:
    if not isinstance(project, CircuitProject) or not isinstance(limits, BoardLimits):
        raise TypeError("Expected a CircuitProject and BoardLimits")
    if (not 1 <= len(project.elements) <= MAX_ELEMENTS or not 1 <= len(outputs) <= MAX_PORTS
            or len(inputs) > MAX_PORTS or len(faults) > MAX_FAULTS):
        raise ValueError("Board exceeds element/port bounds or has no outputs")
    if any(not isinstance(p, AnalogInput) for p in inputs) or any(not isinstance(p, BoardOutput) for p in outputs):
        raise TypeError("Expected typed board pins")
    if any(not isinstance(f, FaultBinding) for f in faults):
        raise TypeError("Expected typed fault bindings")
    if project.steps or project.measurements or project.analysis.mode not in {"operating_point", "transient"}:
        raise ValueError("Compiled board does not execute sweep, AC, or measurement directives")
    if project.temperature_c != 27.0:
        raise ValueError("Compiled board v1 requires the default circuit temperature")
    names = [p.name for p in inputs] + [p.name for p in outputs]
    if len(names) != len(set(names)):
        raise ValueError("Board port names must be unique")
    nodes = {n for e in project.elements for n in (e.positive_node, e.negative_node)}
    nodes.update(n for e in project.elements for n in e.semiconductor_nodes)
    elements = {e.name for e in project.elements}
    if any(n.upper().startswith("SPIKES_BOARD_") for n in nodes | elements):
        raise ValueError("SPIKES_BOARD_ is reserved for compiled pin drivers")
    calls = []
    for e in project.elements:
        if e.kind not in {"resistor", "capacitor", "inductor", "voltage_source", "current_source", "diode", "nmos_level1"}:
            raise ValueError(f"Unsupported compiled-board element {e.name}: {e.kind}")
        if e.waveform is not None or e.behavioral_expression is not None or e.ac_magnitude or e.ac_phase_deg:
            raise ValueError(f"Compiled-board v1 requires constant independent sources: {e.name}")
        if e.kind == "diode":
            if e.diode_model is None:
                raise ValueError(f"Compiled diode lacks an explicit model: {e.name}")
            model = e.diode_model
            args = ["c", _literal(e.name), _literal(e.positive_node), _literal(e.negative_node),
                    repr(model.saturation_current_a), repr(model.emission_coefficient), repr(model.temperature_k)]
            calls.append(f"  kernel_check(spikes_circuit_add_diode({','.join(args)}));")
        elif e.kind == "nmos_level1":
            params = dict(e.semiconductor_parameters)
            charge = sorted(key for key in params if key.startswith("charge_"))
            allowed = {"threshold_voltage_v", "transconductance_a_per_v2", "channel_length_modulation_per_v",
                       "body_effect_sqrt_v", "surface_potential_v", "width_over_length", "off_conductance_s"}
            unknown = sorted(set(params) - allowed)
            if charge or unknown:
                names = ", ".join(charge + unknown)
                raise ValueError(f"Unsupported compiled NMOS Level-1 parameters on {e.name}: {names}")
            defaults = {"threshold_voltage_v": 1.0, "transconductance_a_per_v2": 1.0e-3,
                        "channel_length_modulation_per_v": 0.0, "body_effect_sqrt_v": 0.0,
                        "surface_potential_v": 0.6, "width_over_length": 1.0,
                        "off_conductance_s": 1.0e-12}
            defaults.update(params)
            args = ["c", _literal(e.name), *(_literal(n) for n in e.semiconductor_nodes),
                    *(repr(defaults[key]) for key in defaults)]
            calls.append(f"  kernel_check(spikes_circuit_add_mosfet_level1({','.join(args)}));")
        else:
            args = ["c", _literal(e.name), _literal(e.positive_node), _literal(e.negative_node), repr(e.value)]
            if e.kind in {"capacitor", "inductor"}:
                args.append(repr(e.initial_condition))
            calls.append(f"  kernel_check(spikes_circuit_add_{e.kind}({','.join(args)}));")
    fault_records = []
    fault_names: set[str] = set()
    fault_targets: set[tuple[str, str]] = set()
    by_name = {e.name: e for e in project.elements}
    for binding in faults:
        site = binding.site
        if not _NAME.fullmatch(site.name):
            raise ValueError("Fault name must be a bounded ASCII identifier")
        if site.name in fault_names:
            raise ValueError(f"Duplicate fault name: {site.name}")
        target = (site.element_id, site.parameter)
        if target in fault_targets:
            raise ValueError(f"Duplicate fault target: {site.element_id} {site.parameter}")
        fault_names.add(site.name); fault_targets.add(target)
        existing = by_name.get(site.element_id.upper())
        terminals = binding.positive_node, binding.negative_node
        if site.parameter == "resistance_ohm":
            if existing is None:
                if terminals[0] is None or terminals[0] not in nodes or terminals[1] not in nodes or terminals[0] == terminals[1]:
                    raise ValueError(f"Fault {site.name} requires two distinct existing shunt nodes")
                if site.element_id.upper() in elements or site.element_id.upper().startswith("SPIKES_BOARD_"):
                    raise ValueError(f"Fault shunt element ID is reserved or duplicated: {site.element_id}")
                calls.append(f"  kernel_check(spikes_circuit_add_resistor(c,{_literal(site.element_id.upper())},"
                             f"{_literal(terminals[0])},{_literal(terminals[1])},{site.healthy_value!r}));")
                elements.add(site.element_id.upper())
            elif existing.kind != "resistor" or terminals != (None, None):
                raise ValueError(f"Fault {site.name} must bind an existing resistor without terminals or a new explicit shunt")
            elif existing.value != site.healthy_value:
                raise ValueError(f"Fault {site.name} healthy value must equal resistor {existing.name}")
        else:
            if existing is None or existing.kind != "nmos_level1" or terminals != (None, None):
                raise ValueError(f"Fault {site.name} threshold must bind an existing NMOS Level-1 without terminals")
            threshold = dict(existing.semiconductor_parameters).get("threshold_voltage_v", 1.0)
            if threshold != site.healthy_value:
                raise ValueError(f"Fault {site.name} healthy value must equal NMOS threshold")
        fault_records.append("{" + ",".join((_literal(site.name), _literal(site.element_id.upper()),
            "FaultParameter::Resistance" if site.parameter == "resistance_ohm" else "FaultParameter::Threshold",
            repr(site.healthy_value), repr(site.minimum), repr(site.maximum), _mechanism_literal(site.mechanism))) + "}")
    input_records = []
    for i, p in enumerate(inputs):
        if p.node not in nodes or p.node == "0":
            raise ValueError(f"Input {p.name} must reference an existing nonground node")
        source, internal, resistor = f"SPIKES_BOARD_V{i}", f"SPIKES_BOARD_N{i}", f"SPIKES_BOARD_R{i}"
        calls.extend([
            f"  kernel_check(spikes_circuit_add_voltage_source(c,{_literal(source)},{_literal(internal)},\"0\",{p.initial_v!r}));",
            f"  kernel_check(spikes_circuit_add_resistor(c,{_literal(resistor)},{_literal(internal)},{_literal(p.node)},{p.resistance_ohm!r}));",
        ])
        input_records.append(f"{{{_literal(p.name)},{_literal(source)},{p.minimum_v!r},{p.maximum_v!r}}}")
    output_records = []
    for p in outputs:
        valid = nodes if p.quantity == "voltage" else elements
        if p.target not in valid:
            raise ValueError(f"Unknown {p.quantity} output target: {p.target}")
        output_records.append(f"{{{_literal(p.name)},{_literal(p.target)},{str(p.quantity == 'current').lower()}}}")
    constants = {
        "MIN_STEP": limits.min_step_s, "MAX_STEP": limits.max_step_s, "STOP_TIME": limits.stop_time_s,
        "ABS_TOL": limits.absolute_tolerance, "REL_TOL": limits.relative_tolerance,
    }
    lines = ["// SPDX-License-Identifier: Apache-2.0", "// Generated only from validated circuit data.",
             f"#define SPIKES_BOARD_HAS_FAULTS {1 if faults else 0}"]
    lines += [f"static constexpr double {key}={value!r};" for key, value in constants.items()]
    lines += [f"static constexpr size_t {key}={value};" for key, value in (
        ("MAX_STEPS", limits.max_steps), ("MAX_NEWTON", limits.max_newton_iterations), ("MAX_BACKTRACKS", limits.max_backtracks))]
    lines += ["static const std::vector<Input> INPUTS={" + ",".join(input_records) + "};",
              "static const std::vector<Output> OUTPUTS={" + ",".join(output_records) + "};",
              "static const std::vector<Fault> FAULTS={" + ",".join(fault_records) + "};",
              "static void populate(spikes_circuit *c) {", *calls, "}"]
    return "\n".join(lines) + "\n"


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _compiler_environment() -> dict[str, str]:
    env = dict(os.environ)
    # MSVC accepts implicit flags through these variables; this build does not.
    for key in tuple(env):
        if key.upper() in {"CL", "_CL_", "LINK", "_LINK_", "CXXFLAGS", "LDFLAGS"}:
            del env[key]
    return env


def compile_board_library(project: CircuitProject, output_dir: str | Path, *, name: str,
                          inputs: Sequence[AnalogInput], outputs: Sequence[BoardOutput],
                          limits: BoardLimits, engine_library: str | Path,
                          engine_import_library: str | Path | None = None,
                          compiler: str | Path | None = None,
                          faults: Sequence[FaultBinding] = ()) -> Path:
    """Build into a new directory; publish a manifest only on compiler success.

    MSVC requires a developer-command environment (INCLUDE/LIB/PATH). The engine
    remains separately installed; this function does not copy or load its DLL.
    """
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError("Board name must be a bounded ASCII identifier")
    definition = _definition(project, inputs, outputs, limits, faults)
    destination = Path(output_dir).resolve()
    if destination.exists():
        raise FileExistsError("Compiled board output directory must not already exist")
    engine = Path(engine_library).resolve(strict=True)
    if not engine.is_file() or engine.suffix.lower() not in {".dll", ".so", ".dylib"}:
        raise ValueError("Engine must be an exact local shared library")
    cxx = Path(compiler or shutil.which("cl.exe" if os.name == "nt" else "c++") or "").resolve(strict=True)
    if not cxx.is_file():
        raise ValueError("A local C++ compiler is required")
    import_lib = Path(engine_import_library).resolve(strict=True) if engine_import_library else engine.with_suffix(".lib")
    if os.name == "nt" and not import_lib.is_file():
        raise ValueError("Windows requires the matching engine import library")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".board-build-", dir=destination.parent) as temp:
        staging = Path(temp)
        for filename in ("board_library.h", "board_library.hpp", "board_library_runtime.cpp", "c_api.h"):
            shutil.copyfile(ROOT / "src" / "spikes" / filename, staging / filename)
        (staging / "board_definition.inc").write_text(definition, encoding="ascii", newline="\n")
        (staging / "circuit.json").write_text(json.dumps(project.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")
        suffix = ".dll" if os.name == "nt" else ".dylib" if sys.platform == "darwin" else ".so"
        binary = name + suffix
        if os.name == "nt":
            command = [str(cxx), "/nologo", "/std:c++20", "/EHsc", "/O2", "/MD", "/LD", "/DSPIKES_BOARD_BUILD", "/DSPIKES_SHARED",
                       "board_library_runtime.cpp", str(import_lib), "/link", f"/OUT:{binary}", f"/IMPLIB:{name}.lib"]
        else:
            command = [str(cxx), "-std=c++20", "-O2", "-fPIC", "-shared", "-DSPIKES_BOARD_BUILD",
                       "board_library_runtime.cpp", str(engine), f"-Wl,-rpath,{engine.parent}", "-o", binary]
        # Log is a file to bound Python memory even for a noisy compiler.
        with (staging / "build.log").open("wb") as log:
            result = subprocess.run(command, cwd=staging, env=_compiler_environment(), stdout=log,
                                    stderr=subprocess.STDOUT, timeout=120, check=False)
        if result.returncode or not (staging / binary).is_file():
            with (staging / "build.log").open("rb") as log:
                detail = log.read(16_384).decode("utf-8", errors="replace")
            raise RuntimeError(f"Board compilation failed ({result.returncode}): {detail}")
        files = {p.name: _hash(p) for p in sorted(staging.iterdir()) if p.is_file()}
        manifest = {
            "contract": CONTRACT, "board_abi": 1, "name": name, "library": binary,
            "features": ["fault_injection_v1"] if faults else [],
            "files_sha256": files, "engine": {"kind": "spikes-owned", "abi": 1,
                "path": str(engine), "sha256": _hash(engine),
                "required_api": "persistent-transient-session-with-checkpoint-and-fault-setters" if faults
                    else "persistent-transient-session-with-checkpoint"},
            "compiler": {"path": str(cxx), "sha256": _hash(cxx), "arguments": command[1:]},
            "engine_import_library": {"path": str(import_lib), "sha256": _hash(import_lib)} if os.name == "nt" else None,
            "platform": sys.platform,
            "source_sha256": project.source_sha256, "inputs": [asdict(p) for p in inputs],
            "outputs": [{**asdict(p), "unit": "V" if p.quantity == "voltage" else "A"} for p in outputs],
            "fault_sites": [{**asdict(binding.site),
                "positive_node": binding.positive_node, "negative_node": binding.negative_node}
                for binding in faults],
            "limits": asdict(limits), "integration": "backward_euler", "initialization": "explicit_element_initial_conditions",
            "model_status": "approximate", "capabilities": ["lumped_rlc", "constant_sources", "static_shockley_diode",
                "static_nmos_level1", "finite_resistance_voltage_drive", "checkpoint"] + (["bounded_fault_injection"] if faults else []),
            "limitations": ["No MCU instruction emulation, GPIO high impedance, protocols, parasitics, or multiphysics unless explicitly modeled.",
                "The compiled subset is R/L/C, constant independent sources, static Shockley diodes, and static NMOS Level-1 without charge parameters.",
                "Fault mechanisms are declared finite circuit-parameter approximations; damage behavior and topology are never inferred.",
                "Port drive is held constant between caller-selected communication times; no automatic event localization.",
                "Native C/C++ loaders must authenticate engine and board artifacts independently; manifest hashes record build provenance."],
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        # A new destination prevents clobbering an existing board package.
        for attempt in range(6):
            try:
                staging.rename(destination)
                break
            except PermissionError:
                if os.name != "nt" or attempt == 5:
                    raise
                # Compiler/antivirus handles may close just after cl.exe exits.
                time.sleep(0.05 * (attempt + 1))
    return destination / "manifest.json"


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    from .netlist import parse_netlist
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path)
    parser.add_argument("config", type=Path, help="JSON with name, inputs, outputs, limits")
    parser.add_argument("output", type=Path, help="New output directory")
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--engine-import-library", type=Path)
    parser.add_argument("--compiler", type=Path)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    project = parse_netlist(args.netlist.read_text(encoding="utf-8"), source_name=str(args.netlist.resolve()))
    manifest = compile_board_library(project, args.output, name=config["name"],
        inputs=[AnalogInput(**item) for item in config["inputs"]],
        outputs=[BoardOutput(**item) for item in config["outputs"]],
        limits=BoardLimits(**config["limits"]), engine_library=args.engine,
        engine_import_library=args.engine_import_library, compiler=args.compiler,
        faults=[FaultBinding(FaultSite(**item["site"]), item.get("positive_node"), item.get("negative_node"))
                for item in config.get("faults", [])])
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
