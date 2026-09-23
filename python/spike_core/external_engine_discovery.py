"""Discovery-only metadata for external engines without executable adapters."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .openfoam_runtime import detect_openfoam_runtime
from .solver_state import registered_solver_path
from .sparselizard_adapter import discover_sparselizard_adapter
from .sparselizard_runtime import detect_sparselizard_runtime
from .sparselizard_validation import evaluate_sparselizard_validation


def _app_root() -> Path:
    configured = os.environ.get("SPIKE_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _find(names: Iterable[str], configured: str = "", extra_roots: Iterable[Path] = ()) -> str:
    roots: List[Path] = []
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        if candidate.is_dir():
            roots.append(candidate)
    roots.extend(Path(root) for root in extra_roots if str(root))
    for name in names:
        found = shutil.which(name)
        if found:
            return str(Path(found).resolve())
        for root in roots:
            for candidate in (root / name, root / "bin" / name):
                if candidate.is_file():
                    return str(candidate.resolve())
    return ""


def _registered(engine_id: str, environment_name: str = "") -> str:
    value = registered_solver_path(engine_id)
    if value:
        return value
    return os.environ.get(environment_name, "").strip() if environment_name else ""


def _sparselizard() -> Dict[str, Any]:
    configured = _registered("external.sparselizard", "SPIKE_SPARSELIZARD_ADAPTER")
    root = Path(configured).expanduser() if configured else None
    discovery = discover_sparselizard_adapter(executable=configured or None)
    runtime = detect_sparselizard_runtime()
    qualification = evaluate_sparselizard_validation()
    adapter = discovery.executable if discovery.available else ""
    library = "" if adapter else _find(("sparselizard.lib", "libsparselizard.a", "libsparselizard.so", "libsparselizard.dylib"), configured)
    source_ready = bool(
        root and root.is_dir() and (root / "CMakeLists.txt").is_file() and (root / "src").is_dir()
    )
    if adapter:
        interface = "spike_sparselizard_adapter_v1"
        location = adapter
        state = "adapter_ready_unvalidated"
        reason = "The bounded SPIKE adapter is runnable; imported results still require convergence, passivity, reciprocity, digest binding, and validation evidence."
    elif library:
        interface = "cxx_library"
        location = library
        state = "configured_library_adapter_pending"
        reason = "The sparseLizard library is detected; case preparation and strict result import exist, but the exact process adapter executable is missing."
    elif source_ready:
        interface = "cxx_source_tree"
        location = str(root.resolve())
        state = "configured_source_adapter_pending"
        reason = "A sparseLizard source tree is registered; case preparation and strict result import exist, but the exact process adapter build and validation remain required."
    elif runtime["available"]:
        interface = "spike_sparselizard_native_runtime_v1"
        location = runtime["executable"]
        state = "runtime_verified_adapter_pending"
        reason = (
            "The native Windows sparseLizard runtime passed its DC FEM integrity fixture. "
            "DesignIR case translation and strict result import are implemented, but this runtime does not yet expose "
            "the fixed PCB run protocol; PETSc/MUMPS registration and PCB validation fixtures remain gated."
        )
    else:
        interface = "spike_external_process_v1"
        location = configured
        state = "unavailable"
        reason = "No exact spike-sparselizard-adapter executable is available. Case preparation remains available; managed download is intentionally disabled."
    return {
        "id": "external.sparselizard",
        "name": "sparseLizard FEM",
        "role": "Process-isolated multiphysics FEM comparison candidate",
        "license": "GPL-2.0-or-later; linked adapter must use GPL-compatible terms",
        "homepage": "https://www.sparselizard.org/",
        "executable": location,
        "state": state,
        "interface": interface,
        "capabilities": [],
        "candidate_capabilities": [
            "dc_conduction", "solid_electrothermal", "electrostatic_capacitance",
            "harmonic_magnetodynamics", "harmonic_maxwell_fields", "lumped_circuit_coupling",
        ],
        "actions": ["detect", "register", "forget_registration", "tune", "prepare", "import_results"] + (["run"] if adapter else []),
        "reason": reason,
        "result_contract": "spike/sparselizard-pcb-result/v1 or spike/pi-multiport-result/v1",
        "trust": "exact_named_process_digest_bound_case_strict_result_validation",
        "model_status": "unvalidated" if adapter else "unsupported",
        "runtime_validation": runtime.get("self_test", {}),
        "runtime_backend": runtime.get("manifest", {}).get("backend", {}),
        "qualification": qualification,
    }


def _flotherm() -> Dict[str, Any]:
    configured = _registered("external.flotherm", "SPIKE_FLOTHERM_HOME")
    location = ""
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.exists():
            location = str(candidate.resolve())
    available = bool(location)
    return {
        "id": "external.flotherm",
        "name": "Simcenter FloTHERM",
        "role": "Customer-licensed electronics cooling and airflow connector candidate",
        "license": "Proprietary Siemens license and customer entitlement required; SPIKE connector MIT",
        "homepage": "https://plm.sw.siemens.com/en-US/simcenter/fluids-thermal-simulation/flotherm/",
        "executable": location,
        "state": "licensed_connector_pending" if available else "unavailable",
        "interface": "licensed_vendor_api_pending",
        "capabilities": [],
        "candidate_capabilities": [
            "conjugate_heat_transfer", "airflow", "fans", "enclosures",
            "electronics_cooling", "compact_thermal_models",
        ],
        "actions": ["detect", "register", "forget_registration"] if available else ["detect", "register"],
        "reason": (
            "A customer-provided FloTHERM installation is registered, but the licensed vendor API connector, "
            "case translation, and result validation are not implemented."
            if available else
            "FloTHERM is proprietary and is never bundled or downloaded by SPIKE. Register a customer-licensed "
            "installation after confirming Siemens API and automation entitlements."
        ),
        "result_contract": "spike/external-result/v1 (future licensed connector)",
        "trust": "customer_entitlement_and_vendor_api_required",
        "model_status": "unsupported",
    }


def _elmer() -> Dict[str, Any]:
    """Describe a locally discoverable Elmer runtime without enabling it.

    ElmerSolver accepts solver-input files, but SPIKE does not yet own a
    bounded Elmer case translator, execution adapter, or result importer.  A
    discovered executable therefore remains evidence of a local installation,
    not a runnable PI, SI, thermal, or EMI backend.
    """
    names = ("ElmerSolver", "ElmerSolver.exe", "elmersolver", "elmersolver.exe")
    configured = _registered("external.elmer", "SPIKE_ELMER_HOME")
    local_runtime = _app_root() / "runtime" / "external" / "elmer"
    configured_path = Path(configured).expanduser() if configured else None
    if configured_path and configured_path.is_file():
        executable = str(configured_path.resolve()) if configured_path.name.lower() in {name.lower() for name in names} else ""
    else:
        executable = _find(names, configured, (local_runtime,))
    registered = bool(configured)
    return {
        "id": "external.elmer",
        "name": "Elmer FEM",
        "role": "FEM multiphysics adapter candidate for independent comparison workflows",
        "license": "GPL-2.0-or-later; SPIKE adapter license and redistribution review required",
        "homepage": "https://www.elmerfem.org/",
        "executable": executable,
        "state": "installed_adapter_pending" if executable else "unavailable",
        "interface": "elmer_solver_executable" if executable else "spike_external_process_v1",
        "capabilities": [],
        "candidate_capabilities": [
            "dc_conduction", "electrostatic_capacitance", "magnetostatic_fields",
            "harmonic_electromagnetics", "solid_thermal", "electrothermal_coupling",
            "lumped_circuit_coupling",
        ],
        "actions": ["detect", "register", "forget_registration"] if executable else ["detect", "register"],
        "reason": (
            "ElmerSolver is detected, but SPIKE has no bounded Elmer case translator, "
            "process adapter, normalized result importer, or validation corpus."
            if executable else
            (
                "An Elmer path is registered, but ElmerSolver was not found at that location."
                if registered else
                "Elmer is not registered or discoverable. Managed download is intentionally disabled."
            )
        ),
        "result_contract": "spike/external-result/v1 (future adapter)",
        "trust": "signed_manifest_and_sha256_required",
        "model_status": "unsupported",
    }


def discover_adapter_pending_engines(*, refresh: bool = False) -> List[Dict[str, Any]]:
    openfoam_root = _registered("external.openfoam", "WM_PROJECT_DIR")
    ngspice_root = _registered("external.ngspice", "SPIKE_NGSPICE_HOME")
    fasthenry_root = _registered("external.fasthenry", "SPIKE_FASTHENRY_HOME")
    fastcap_root = _registered("external.fastcap", "SPIKE_FASTCAP_HOME")
    local_runtime = _app_root() / "runtime" / "external"
    openfoam = _find(
        ("foamRun", "foamRun.exe", "chtMultiRegionFoam", "buoyantSimpleFoam"),
        openfoam_root,
        (local_runtime / "openfoam",),
    )
    if refresh:
        detect_openfoam_runtime.cache_clear()
    openfoam_runtime = detect_openfoam_runtime()
    if openfoam:
        openfoam_runtime = {
            "available": True,
            "transport": "native_process",
            "executable": openfoam,
            "version": "",
            "distribution": "",
        }
    ngspice = _find(
        ("ngspice", "ngspice.exe", "ngspice_con.exe"),
        ngspice_root,
        (local_runtime / "Spice64", local_runtime / "ngspice"),
    )
    fasthenry = _find(("fasthenry", "fasthenry.exe", "FastHenry2.exe"), fasthenry_root)
    fastcap = _find(("fastcap", "fastcap.exe", "FastCap2.exe"), fastcap_root)
    return [
        _sparselizard(),
        _elmer(),
        _flotherm(),
        {
            "id": "external.fasthenry", "name": "FastHenry",
            "role": "Independent quasistatic conductor R/L and impedance comparison",
            "license": "Engine license review required; SPIKE adapter MIT",
            "homepage": "https://www.fastfieldsolvers.com/", "executable": fasthenry,
            "state": "installed_adapter_pending" if fasthenry else "unavailable",
            "capabilities": [],
            "candidate_capabilities": ["rl_extraction", "skin_effect", "proximity_effect", "impedance_matrix"],
            "actions": ["detect", "export"] if fasthenry else ["detect", "register"],
            "reason": "The normalized result importer is not implemented." if fasthenry else "FastHenry is not installed or discoverable.",
        },
        {
            "id": "external.fastcap", "name": "FastCap",
            "role": "Independent capacitance and potential-coefficient matrix comparison",
            "license": "Engine license review required; SPIKE adapter MIT",
            "homepage": "https://www.fastfieldsolvers.com/", "executable": fastcap,
            "state": "installed_adapter_pending" if fastcap else "unavailable",
            "capabilities": [],
            "candidate_capabilities": ["capacitance_matrix", "potential_coefficients", "panel_refinement"],
            "actions": ["detect", "export"] if fastcap else ["detect", "register"],
            "reason": "The panel exporter and normalized result importer are not implemented." if fastcap else "FastCap is not installed or discoverable.",
        },
        {
            "id": "external.openfoam", "name": "OpenFOAM",
            "role": "Conjugate thermal and airflow execution/comparison",
            "license": "GPL-3.0-or-later; SPIKE adapter MIT", "homepage": "https://www.openfoam.com/",
            "executable": openfoam_runtime["executable"],
            "version": openfoam_runtime["version"],
            "state": "installed_case_generator_pending" if openfoam_runtime["available"] else "unavailable",
            "interface": openfoam_runtime["transport"],
            "capabilities": [],
            "candidate_capabilities": ["conjugate_heat_transfer", "airflow", "fans", "enclosures"],
            "actions": ["detect", "register", "tune"] if openfoam_runtime["available"] else ["detect", "register"],
            "reason": "The runtime is installed, but the validated multi-region case generator remains gated." if openfoam_runtime["available"] else "OpenFOAM is not installed or discoverable.",
        },
        {
            "id": "external.ngspice", "name": "ngspice",
            "role": "Circuit DC, AC, and transient co-simulation",
            "license": "Primarily BSD-3-Clause with component exceptions; SPIKE adapter MIT",
            "homepage": "https://ngspice.sourceforge.io/", "executable": ngspice,
            "state": "available" if ngspice else "unavailable",
            "capabilities": ["dc", "ac", "transient", "explicit_netlist"],
            "actions": ["detect", "run"] if ngspice else ["detect", "register"],
            "reason": "" if ngspice else "ngspice is not installed or discoverable.",
            "model_status": "solver_dependent" if ngspice else "unsupported",
            "validation": "Real RC transient execution is covered; PCB-extracted parasitic/device-model accuracy remains model dependent." if ngspice else "",
        },
    ]
