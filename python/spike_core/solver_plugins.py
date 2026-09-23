"""Versioned solver plugin registry and isolated process adapter.

Solver plugins consume DesignIR plus AnalysisSpec and return AnalysisResult.
The desktop UI and service never import solver-specific geometry or APIs.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Protocol

from .contracts import AnalysisResult, AnalysisSpec, DesignIR, ValidationIssue
from .dc_solver import solve_dc
from .solver_geometry import build_solver_geometry


PLUGIN_CONTRACT = "spike/solver-plugin/v1"
PLUGIN_API_VERSION = 1
RESULT_CONTRACT = "spike/v1"
PROCESS_PROBE_CONTRACT = "spike/solver-plugin-probe/v1"
PROCESS_PROBE_RESULT_CONTRACT = "spike/solver-plugin-probe-result/v1"
PROCESS_JOB_CONTRACT = "spike/solver-plugin-job/v1"
PROCESS_MESH_CONTRACT = "spike/solver-mesh/v1"
PROCESS_RESULT_CONTRACT = "spike/solver-plugin-result/v1"
RUNNABLE_STATES = {"available", "experimental"}
PLUGIN_STATES = RUNNABLE_STATES | {"integration_pending", "unavailable"}
DEFAULT_MAX_RESULT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class SolverPluginManifest:
    id: str
    name: str
    version: str
    provider: str
    analyses: List[str]
    formulations: List[str]
    capabilities: List[str]
    geometry_contracts: List[str] = field(default_factory=lambda: ["spike/v1", "spike/net-geometry/v1", "spike/solver-geometry/v1"])
    result_contract: str = RESULT_CONTRACT
    contract: str = PLUGIN_CONTRACT
    api_version: int = PLUGIN_API_VERSION
    execution: str = "builtin"
    entrypoint: str = ""
    state: str = "unavailable"
    model_status: str = "unsupported"
    validation: str = "No validation record is published."
    license: str = "proprietary"
    bundled: bool = False
    priority: int = 0
    limits: Dict[str, Any] = field(default_factory=dict)
    runtime_probe: Dict[str, Any] = field(default_factory=dict)
    interchange: Dict[str, Any] = field(default_factory=dict)
    qualification: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "SolverPluginManifest":
        allowed = {item.name for item in cls.__dataclass_fields__.values()}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unknown solver manifest fields: {', '.join(sorted(unknown))}")
        manifest = cls(**{key: value[key] for key in value if key in allowed})
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if self.contract != PLUGIN_CONTRACT or self.api_version != PLUGIN_API_VERSION:
            raise ValueError("Unsupported solver plugin contract or API version.")
        if not self.id or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in self.id):
            raise ValueError("Solver plugin IDs must use lowercase ASCII letters, numbers, dot, underscore, or dash.")
        if self.execution not in {"builtin", "process"}:
            raise ValueError("Solver plugin execution must be builtin or process.")
        if self.state not in PLUGIN_STATES:
            raise ValueError("Solver plugin state is not supported.")
        if not isinstance(self.analyses, list) or not isinstance(self.formulations, list) or not self.analyses or not self.formulations:
            raise ValueError("Solver plugins must declare at least one analysis and formulation.")
        if not all(isinstance(value, str) and value for value in self.analyses + self.formulations + self.capabilities):
            raise ValueError("Solver analyses, formulations, and capabilities must be non-empty strings.")
        if self.execution == "process" and not self.entrypoint:
            raise ValueError("Process solver plugins must declare an entrypoint.")
        if self.result_contract != RESULT_CONTRACT:
            raise ValueError("Solver plugin result contract is not supported.")
        if self.runtime_probe:
            if self.execution != "process" or self.runtime_probe.get("contract") != PROCESS_PROBE_CONTRACT:
                raise ValueError("A process runtime probe must use the SPIKE probe contract.")
            argv = self.runtime_probe.get("argv")
            if not isinstance(argv, list) or not argv or len(argv) > 16 or not all(
                isinstance(token, str) and token and "\x00" not in token and "\n" not in token and "\r" not in token
                for token in argv
            ):
                raise ValueError("Process runtime probes require 1-16 non-empty fixed argument tokens.")
            timeout_s = self.runtime_probe.get("timeout_s")
            if not isinstance(timeout_s, int) or isinstance(timeout_s, bool) or not 1 <= timeout_s <= 60:
                raise ValueError("Process runtime probes require an integer timeout from 1 to 60 seconds.")
            if self.runtime_probe.get("result_contract") != PROCESS_PROBE_RESULT_CONTRACT:
                raise ValueError("Process runtime probes must declare the SPIKE probe-result contract.")
        if self.interchange:
            if self.interchange.get("job_contract") != PROCESS_JOB_CONTRACT:
                raise ValueError("Solver interchange must declare the SPIKE process-job contract.")
            mesh_contracts = self.interchange.get("mesh_contracts")
            if not isinstance(mesh_contracts, list) or not mesh_contracts or not all(isinstance(value, str) and value for value in mesh_contracts):
                raise ValueError("Solver interchange must declare at least one mesh contract.")
            if self.interchange.get("artifact_result_contract") != PROCESS_RESULT_CONTRACT:
                raise ValueError("Solver interchange must declare the SPIKE process-result contract.")
        if self.qualification:
            required = {"runtime_probe_required", "adapter_validation_required", "workflow_validation_required"}
            if set(self.qualification) - required or not required.issubset(self.qualification) or not all(
                isinstance(self.qualification[key], bool) for key in required
            ):
                raise ValueError("Solver qualification must declare the three boolean qualification gates.")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SolverPlugin(Protocol):
    manifest: SolverPluginManifest

    def run(self, design: DesignIR, spec: AnalysisSpec) -> AnalysisResult:
        ...


class BuiltinSolverPlugin:
    def __init__(
        self,
        manifest: SolverPluginManifest,
        runner: Callable[[DesignIR, AnalysisSpec], AnalysisResult],
    ) -> None:
        manifest.validate()
        self.manifest = manifest
        self._runner = runner

    def run(self, design: DesignIR, spec: AnalysisSpec) -> AnalysisResult:
        return self._runner(design, spec)


class DeclaredSolverPlugin:
    """Catalog entry for an engine that is designed but not installed."""

    def __init__(self, manifest: SolverPluginManifest) -> None:
        manifest.validate()
        self.manifest = manifest

    def run(self, design: DesignIR, spec: AnalysisSpec) -> AnalysisResult:
        return _blocked_result(
            spec,
            "SOLVER_PLUGIN_UNAVAILABLE",
            f"{self.manifest.name} is declared but not available.",
            self.manifest.validation,
            solver_id=self.manifest.id,
        )


class ExternalProcessSolverPlugin:
    """Run a trusted drop-in executable through request/result JSON files."""

    def __init__(self, manifest: SolverPluginManifest, plugin_directory: Path) -> None:
        manifest.validate()
        if manifest.execution != "process":
            raise ValueError("External solver plugins must declare process execution.")
        root = plugin_directory.resolve()
        executable = (root / manifest.entrypoint).resolve()
        if not executable.is_relative_to(root) or not executable.is_file():
            raise ValueError("Solver entrypoint must be a file inside its plugin directory.")
        self.manifest = manifest
        self.plugin_directory = root
        self.executable = executable
        self._probe_result: Dict[str, Any] | None = None

    def probe(self, *, refresh: bool = False) -> Dict[str, Any]:
        """Run the manifest's fixed-argv adapter probe without a shell.

        Probe success establishes runtime communication only.  The manifest's
        state/model status and workflow validation remain separate gates.
        """
        if self._probe_result is not None and not refresh:
            return dict(self._probe_result)
        declaration = self.manifest.runtime_probe
        if not declaration:
            result = {
                "contract": PROCESS_PROBE_RESULT_CONTRACT,
                "status": "failed",
                "runtime": {"name": "undeclared", "version": "undeclared"},
                "adapter": {"version": self.manifest.version, "protocol": PLUGIN_CONTRACT},
                "reason": "The solver plugin does not declare a runtime probe.",
            }
            self._probe_result = result
            return dict(result)
        timeout_seconds = int(declaration["timeout_s"])
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PYTHONNOUSERSITE": "1",
        }
        try:
            process = subprocess.run(
                [str(self.executable), *[str(value) for value in declaration["argv"]]],
                cwd=self.plugin_directory,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                shell=False,
            )
            if len(process.stdout) > 64 * 1024:
                raise ValueError("Runtime probe output exceeds 65536 bytes.")
            payload = json.loads(process.stdout.decode("utf-8"))
            if process.returncode != 0 or not isinstance(payload, dict):
                raise ValueError(f"Runtime probe exited with code {process.returncode}.")
            if payload.get("contract") != PROCESS_PROBE_RESULT_CONTRACT or payload.get("status") not in {"passed", "failed"}:
                raise ValueError(f"Runtime probe must return {PROCESS_PROBE_RESULT_CONTRACT} with passed/failed status.")
            runtime = payload.get("runtime")
            adapter = payload.get("adapter")
            if not isinstance(runtime, dict) or not runtime.get("name") or not runtime.get("version"):
                raise ValueError("Runtime probe result requires runtime name and version.")
            if not isinstance(adapter, dict) or not adapter.get("version") or adapter.get("protocol") != PLUGIN_CONTRACT:
                raise ValueError("Runtime probe result requires an adapter version and SPIKE plugin protocol.")
            if adapter["version"] != self.manifest.version:
                raise ValueError("Runtime probe adapter version does not match the declared plugin manifest.")
            result = payload
        except (OSError, subprocess.TimeoutExpired, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            result = {
                "contract": PROCESS_PROBE_RESULT_CONTRACT,
                "status": "failed",
                "runtime": {"name": "unavailable", "version": "unavailable"},
                "adapter": {"version": self.manifest.version, "protocol": PLUGIN_CONTRACT},
                "reason": str(exc),
            }
        self._probe_result = result
        return dict(result)

    def run(self, design: DesignIR, spec: AnalysisSpec) -> AnalysisResult:
        if self.manifest.qualification.get("runtime_probe_required", False):
            probe = self.probe()
            if probe.get("status") != "passed":
                return _blocked_result(
                    spec,
                    "SOLVER_RUNTIME_PROBE_FAILED",
                    f"{self.manifest.name} did not pass its fixed runtime probe.",
                    str(probe.get("reason") or "Install or register the exact runtime and rerun its probe."),
                    solver_id=self.manifest.id,
                )
        timeout_seconds = max(1, min(int(spec.options.get("timeout_seconds", 600)), 86400))
        max_result_bytes = max(1024, min(int(self.manifest.limits.get("max_result_bytes", DEFAULT_MAX_RESULT_BYTES)), 1024 * 1024 * 1024))
        with tempfile.TemporaryDirectory(prefix="spike-solver-") as directory:
            job = Path(directory)
            request_path = job / "request.json"
            result_path = job / "result.json"
            diagnostic_path = job / "solver.log"
            request_path.write_text(json.dumps({
                "contract": PLUGIN_CONTRACT,
                "api_version": PLUGIN_API_VERSION,
                "request_id": spec.analysis_id or str(uuid.uuid4()),
                "solver": self.manifest.to_dict(),
                "design": design.to_dict(),
                "geometry": build_solver_geometry(design, spec),
                "spec": spec.to_dict(),
            }, default=str), encoding="utf-8")
            environment = {
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                "TEMP": str(job),
                "TMP": str(job),
                "SPIKE_SOLVER_JOB": str(job),
            }
            try:
                with diagnostic_path.open("wb") as diagnostic:
                    process = subprocess.run(
                        [str(self.executable), "--request", str(request_path), "--result", str(result_path)],
                        cwd=job,
                        env=environment,
                        stdout=diagnostic,
                        stderr=subprocess.STDOUT,
                        timeout=timeout_seconds,
                        shell=False,
                    )
            except subprocess.TimeoutExpired:
                return _blocked_result(
                    spec,
                    "SOLVER_PROCESS_TIMEOUT",
                    f"{self.manifest.name} exceeded the {timeout_seconds}-second execution limit.",
                    "Reduce the job size or increase the approved solver timeout.",
                    solver_id=self.manifest.id,
                    status="failed",
                )
            except OSError as exc:
                return _blocked_result(
                    spec,
                    "SOLVER_PROCESS_LAUNCH_FAILED",
                    f"{self.manifest.name} could not be launched.",
                    str(exc),
                    solver_id=self.manifest.id,
                    status="failed",
                )
            if process.returncode != 0 or not result_path.is_file():
                return _blocked_result(
                    spec,
                    "SOLVER_PROCESS_FAILED",
                    f"{self.manifest.name} exited with code {process.returncode}.",
                    _tail_text(diagnostic_path, 2000) or "No solver diagnostic was returned.",
                    solver_id=self.manifest.id,
                    status="failed",
                )
            if result_path.stat().st_size > max_result_bytes:
                return _blocked_result(
                    spec,
                    "SOLVER_RESULT_TOO_LARGE",
                    f"{self.manifest.name} exceeded its result-size limit.",
                    f"The maximum accepted result is {max_result_bytes} bytes.",
                    solver_id=self.manifest.id,
                    status="failed",
                )
            try:
                payload = json.loads(result_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                return _blocked_result(
                    spec,
                    "SOLVER_RESULT_INVALID",
                    f"{self.manifest.name} returned an unreadable result.",
                    str(exc),
                    solver_id=self.manifest.id,
                    status="failed",
                )
            if not isinstance(payload, dict):
                return _blocked_result(
                    spec,
                    "SOLVER_RESULT_INVALID",
                    f"{self.manifest.name} returned a non-object result.",
                    "A solver result must be a JSON object.",
                    solver_id=self.manifest.id,
                    status="failed",
                )
            if payload.get("contract") != RESULT_CONTRACT:
                return _blocked_result(
                    spec,
                    "SOLVER_RESULT_CONTRACT_INVALID",
                    f"{self.manifest.name} returned an unsupported result contract.",
                    f"Expected {RESULT_CONTRACT}.",
                    solver_id=self.manifest.id,
                    status="failed",
                )
            try:
                payload["issues"] = [
                    issue if isinstance(issue, ValidationIssue) else ValidationIssue(**issue)
                    for issue in payload.get("issues", [])
                ]
                result = AnalysisResult(**{
                    key: payload[key]
                    for key in AnalysisResult.__dataclass_fields__
                    if key in payload
                })
            except (TypeError, ValueError) as exc:
                return _blocked_result(
                    spec,
                    "SOLVER_RESULT_INVALID",
                    f"{self.manifest.name} returned fields that do not match the result contract.",
                    str(exc),
                    solver_id=self.manifest.id,
                    status="failed",
                )
            result.provenance = {
                **result.provenance,
                "solver_plugin": self.manifest.id,
                "solver_plugin_version": self.manifest.version,
                "execution": "isolated_process",
            }
            return result


class SolverRegistry:
    def __init__(self) -> None:
        self._plugins: Dict[str, SolverPlugin] = {}

    def register(self, plugin: SolverPlugin) -> None:
        plugin.manifest.validate()
        if plugin.manifest.id in self._plugins:
            raise ValueError(f"Solver plugin is already registered: {plugin.manifest.id}")
        self._plugins[plugin.manifest.id] = plugin

    def catalog(self) -> List[Dict[str, Any]]:
        return [
            plugin.manifest.to_dict()
            for plugin in sorted(self._plugins.values(), key=lambda item: (-item.manifest.priority, item.manifest.id))
        ]

    def get(self, solver_id: str) -> SolverPlugin | None:
        return self._plugins.get(solver_id)

    def select(self, spec: AnalysisSpec) -> SolverPlugin | None:
        if spec.solver_id and spec.solver_id != "auto":
            plugin = self.get(spec.solver_id)
            if plugin is None or spec.mode not in plugin.manifest.analyses:
                return None
            if spec.formulation != "auto" and spec.formulation not in plugin.manifest.formulations:
                return None
            if not set(spec.required_capabilities).issubset(set(plugin.manifest.capabilities)):
                return None
            return plugin
        required = set(spec.required_capabilities)
        candidates = []
        for plugin in self._plugins.values():
            manifest = plugin.manifest
            if manifest.state not in RUNNABLE_STATES or spec.mode not in manifest.analyses:
                continue
            if spec.formulation != "auto" and spec.formulation not in manifest.formulations:
                continue
            if not required.issubset(set(manifest.capabilities)):
                continue
            candidates.append(plugin)
        return max(candidates, key=lambda item: item.manifest.priority, default=None)

    def run(self, design: DesignIR, spec: AnalysisSpec) -> AnalysisResult:
        plugin = self.select(spec)
        from .importers import import_analysis_blockers
        blockers = import_analysis_blockers(design, spec.mode)
        if blockers:
            return _blocked_result(spec, "IMPORT_NOT_SOLVER_READY", " ".join(blockers), "Resolve the import quality report before analysis.")
        if plugin is None:
            requested = spec.solver_id if spec.solver_id != "auto" else f"{spec.mode}/{spec.formulation}"
            return _blocked_result(
                spec,
                "NO_COMPATIBLE_SOLVER",
                f"No available solver plugin satisfies {requested}.",
                "Install or enable a validated plugin that declares the requested analysis, formulation, and capabilities.",
            )
        if plugin.manifest.state not in RUNNABLE_STATES:
            return _blocked_result(
                spec,
                "SOLVER_PLUGIN_UNAVAILABLE",
                f"{plugin.manifest.name} is declared but not runnable.",
                plugin.manifest.validation,
                solver_id=plugin.manifest.id,
            )
        result = plugin.run(design, spec)
        result.provenance = {
            **result.provenance,
            "solver_plugin": plugin.manifest.id,
            "solver_plugin_version": plugin.manifest.version,
            "solver_formulation": spec.formulation if spec.formulation != "auto" else plugin.manifest.formulations[0],
            "geometry_contract": "spike/solver-geometry/v1",
        }
        return result

    def discover(self, roots: Iterable[str | Path]) -> List[Dict[str, Any]]:
        discovered = []
        for root_value in roots:
            root = Path(root_value).expanduser().resolve()
            if not root.is_dir():
                continue
            for manifest_path in root.glob("*/solver-plugin.json"):
                try:
                    manifest = SolverPluginManifest.from_dict(json.loads(manifest_path.read_text(encoding="utf-8")))
                    plugin = ExternalProcessSolverPlugin(manifest, manifest_path.parent)
                    probe = None
                    if manifest.qualification.get("runtime_probe_required", False):
                        probe = plugin.probe()
                        if probe.get("status") != "passed":
                            raise ValueError(f"Runtime probe failed: {probe.get('reason') or 'adapter returned failed status'}")
                    self.register(plugin)
                    discovered.append({"id": manifest.id, "status": "loaded", "path": str(manifest_path), "runtime_probe": probe})
                except Exception as exc:
                    discovered.append({"id": manifest_path.parent.name, "status": "rejected", "path": str(manifest_path), "error": str(exc)})
        return discovered


def _tail_text(path: Path, limit: int = 65536) -> str:
    if not path.is_file():
        return ""
    with path.open("rb") as stream:
        size = stream.seek(0, 2)
        stream.seek(max(0, size - limit))
        return stream.read(limit).decode("utf-8", errors="replace")


def _blocked_result(
    spec: AnalysisSpec,
    code: str,
    message: str,
    suggestion: str,
    solver_id: str = "",
    status: str = "blocked",
) -> AnalysisResult:
    return AnalysisResult(
        analysis_id=spec.analysis_id or str(uuid.uuid4()),
        mode=spec.mode,
        status=status,
        model_status="unsupported",
        issues=[ValidationIssue(code=code, severity="error", message=message, suggestion=suggestion)],
        provenance={"solver_plugin": solver_id or "none", "contract": RESULT_CONTRACT},
    )


def default_solver_registry() -> SolverRegistry:
    from .ngspice_plugin import NgspicePlugin
    from .peec_plugin import native_available, solve_peec_2_5d
    from .transient_peec import solve_peec_rl_transient

    registry = SolverRegistry()
    registry.register(BuiltinSolverPlugin(
        SolverPluginManifest(
            id="spike.routed_dc",
            name="SPIKE Copper Geometry DC",
            version="2.0.0",
            provider="SPIKE",
            analyses=["dc"],
            formulations=["resistive_network"],
            capabilities=["dc_resistance", "voltage_drop", "current_density", "tracks", "through_vias", "pads", "copper_zones", "package_resistance", "contact_resistance", "sparse_network", "explicit_return_path", "isolated_power_domain"],
            state="available",
            model_status="approximate",
            validation="Analytical resistor-network, multi-sink, pad, zone, and package/contact fixtures pass. Zone sign-off requires mesh convergence.",
            license="MIT",
            bundled=True,
            priority=100,
            limits={"geometry": "Tracks, through vias, pads, and polygonal zones.", "zones": "Finite-volume discretization; convergence must be checked.", "packages": "Explicit resistance models only; no value is inferred."},
        ),
        solve_dc,
    ))
    peec_manifest = SolverPluginManifest(
        id="spike.peec_2_5d",
        name="SPIKE Quasi-static PEEC 2.5D",
        version="0.4.0",
        provider="SPIKE",
        analyses=["ac", "broadband_hf"],
        formulations=["peec_2_5d"],
        capabilities=["rl_extraction", "rlcg_extraction", "partial_inductance", "capacitance_extraction", "dielectric_loss", "impedance", "frequency_dependent_impedance", "skin_effect", "surface_roughness", "tracks", "through_vias", "pads", "copper_zones", "hybrid_conductor_mesh", "topology_correct_mna"],
        state="experimental" if native_available() else "integration_pending",
        model_status="approximate",
        validation="Analytical trace/via resistance, AC-loss monotonicity, capacitance asymptote, matrix passivity, planar sheet convergence, and hybrid trace/pad/zone/via MNA fixtures pass. External field-solver and measurement correlation remains required.",
        license="MIT",
        bundled=True,
        priority=70,
        limits={"physics": "Quasi-static conductor R/partial-L plus approximate single-reference C/G. Hammerstad RMS roughness is supported; proximity effect, via/antipad C, and a multiconductor electrostatic matrix are not.", "geometry": "Tracks, plated vias, pads, and polygonal zones use one topology-preserving finite-volume/filament mesh.", "scale": "Dense partial-inductance extraction; isolate nets and run convergence studies for large planes."},
    )
    registry.register(BuiltinSolverPlugin(peec_manifest, solve_peec_2_5d) if native_available() else DeclaredSolverPlugin(peec_manifest))
    transient_manifest = SolverPluginManifest(
        id="spike.peec_rl_transient",
        name="SPIKE Geometry PEEC RLC Transient",
        version="0.2.0",
        provider="SPIKE",
        analyses=["transient"],
        formulations=["peec_rl_transient"],
        capabilities=[
            "transient_waveforms", "geometry_transient", "partial_inductance",
            "distributed_capacitance",
            "voltage_drop", "current_density", "tracks", "through_vias",
            "pads", "copper_zones", "hybrid_conductor_mesh",
            "topology_correct_mna", "package_resistance", "contact_resistance",
            "explicit_return_path", "isolated_power_domain",
        ],
        state="experimental" if native_available() else "integration_pending",
        model_status="approximate",
        validation="Analytical waveform, straight-trace RL step, compact-frame decimation, stackup-capacitance, and topology fixtures pass. The capacitance model remains approximate.",
        license="MIT",
        bundled=True,
        priority=80,
        limits={
            "physics": "Quasi-static conductor R plus full mutual partial-L matrix and optional single-reference stackup capacitance; no dielectric loss, radiation, or nonlinear devices.",
            "integration": "Backward Euler with automatic/manual timestep, bounded output decimation, wall-time, and memory controls.",
            "scale": "Dense matrix factorization; source-connected mesh is limited to the declared branch count.",
        },
    )
    registry.register(BuiltinSolverPlugin(transient_manifest, solve_peec_rl_transient) if native_available() else DeclaredSolverPlugin(transient_manifest))
    registry.register(DeclaredSolverPlugin(SolverPluginManifest(
        id="spike.mom_surface",
        name="SPIKE Surface Method of Moments",
        version="0.1.0",
        provider="SPIKE",
        analyses=["broadband_hf", "si", "emi_emc"],
        formulations=["mom_surface"],
        capabilities=["surface_currents", "coupled_line_extraction", "electric_field_coupling", "magnetic_field_coupling", "s_parameters", "ports", "far_field"],
        state="unavailable",
        model_status="unsupported",
        validation="No validated MoM engine is packaged.",
        license="undecided",
        priority=50,
    )))
    registry.register(DeclaredSolverPlugin(SolverPluginManifest(
        id="spike.fullwave_3d",
        name="SPIKE Full-wave 3D",
        version="0.1.0",
        provider="SPIKE",
        analyses=["broadband_hf", "si", "emi_emc", "antenna"],
        formulations=["fem_3d", "fdtd_3d"],
        capabilities=["volume_fields", "electric_field_coupling", "magnetic_field_coupling", "s_parameters", "ports", "far_field", "lossy_dielectrics"],
        state="unavailable",
        model_status="unsupported",
        validation="No validated full-wave engine is packaged.",
        license="undecided",
        priority=40,
    )))
    registry.register(NgspicePlugin())
    return registry
