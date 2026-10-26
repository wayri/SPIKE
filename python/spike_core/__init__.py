"""Stable application contracts and local analysis service for SPIKE."""

__version__ = "0.4.2"

from .capabilities import capabilities
from .capability_ledger import native_capability_ledger
from .contracts import AnalysisResult, AnalysisSpec, SpiDeR, ValidationIssue
from .spider_v2 import AssemblyIRV1, SpiDeRV2

# External DesignIR compatibility names; internal code uses SpiDeR.
DesignIR = SpiDeR
DesignIRV2 = SpiDeRV2
from .assembly_resources import estimate_assembly_resources
from .native_solver_contracts import NativeSolveRequest, NativeSolveResult, NativeSolverDescriptor
from .spikes_layout_adapter import (
    LAYOUT_EVALUATION_CONTRACT,
    SpikesLayoutAdapterError,
    canonical_design_ir_json,
    canonical_layout_json,
    design_ir_artifact_identity,
    map_layout_results,
    preflight_layout_candidate,
    prepare_native_jobs,
    validate_layout_request,
)
from .layout_metric_registry import (
    LAYOUT_METRIC_REGISTRY_CONTRACT,
    LayoutMetricRegistryError,
    canonical_metric_registry_json,
    negotiate_layout_requirements,
    validate_metric_registry,
    validate_requirements_for_launch,
)
from .spikes_layout_geometry_handoff import (
    DESIGNIR_LAYOUT_HANDOFF_CONTRACT,
    build_designir_layout_handoff,
    canonical_designir_layout_handoff_json,
    validate_designir_layout_handoff_identity,
)


def __getattr__(name):
    # Contract-only and narrow worker entry points must not initialize unrelated
    # field engines (including NumPy/SciPy). Explicit imports inside these
    # branches also keep the dependencies visible to frozen-build analysis.
    if name in {"run_iterative_field_circuit_cosimulation", "validate_field_circuit_request"}:
        from .solvers.execution.coupling.field_circuit_cosim import run_iterative_field_circuit_cosimulation, validate_field_circuit_request
        globals().update(
            run_iterative_field_circuit_cosimulation=run_iterative_field_circuit_cosimulation,
            validate_field_circuit_request=validate_field_circuit_request,
        )
        return globals()[name]
    if name == "NativePeecFieldReductionProvider":
        from .solvers.power_integrity.peec.peec_field_provider import NativePeecFieldReductionProvider
        globals()[name] = NativePeecFieldReductionProvider
        return NativePeecFieldReductionProvider
    # Public extension compatibility exports remain available on demand.
    if name in {"ExtensionManifest", "ExtensionRegistry"}:
        from . import extensions
        return getattr(extensions, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))


__all__ = [
    "DesignIR",
    "DesignIRV2",
    "AnalysisResult",
    "AnalysisSpec",
    "SpiDeR",
    "SpiDeRV2",
    "AssemblyIRV1",
    "estimate_assembly_resources",
    "ValidationIssue",
    "ExtensionManifest",
    "ExtensionRegistry",
    "NativeSolveRequest",
    "NativeSolveResult",
    "NativeSolverDescriptor",
    "run_iterative_field_circuit_cosimulation",
    "validate_field_circuit_request",
    "NativePeecFieldReductionProvider",
    "LAYOUT_EVALUATION_CONTRACT",
    "SpikesLayoutAdapterError",
    "canonical_design_ir_json",
    "canonical_layout_json",
    "design_ir_artifact_identity",
    "map_layout_results",
    "preflight_layout_candidate",
    "prepare_native_jobs",
    "validate_layout_request",
    "LAYOUT_METRIC_REGISTRY_CONTRACT",
    "LayoutMetricRegistryError",
    "canonical_metric_registry_json",
    "negotiate_layout_requirements",
    "validate_metric_registry",
    "validate_requirements_for_launch",
    "DESIGNIR_LAYOUT_HANDOFF_CONTRACT",
    "build_designir_layout_handoff",
    "canonical_designir_layout_handoff_json",
    "validate_designir_layout_handoff_identity",
    "capabilities",
    "native_capability_ledger",
]
