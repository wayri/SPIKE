"""Stable application contracts and local analysis service for SPIKE."""

__version__ = "0.2.12"

from .capabilities import capabilities
from .capability_ledger import native_capability_ledger
from .contracts import AnalysisResult, AnalysisSpec, DesignIR, ValidationIssue
from .design_ir_v2 import AssemblyIRV1, DesignIRV2
from .assembly_resources import estimate_assembly_resources
from .extensions import ExtensionManifest, ExtensionRegistry
from .native_solver_contracts import NativeSolveRequest, NativeSolveResult, NativeSolverDescriptor
from .field_circuit_cosim import run_iterative_field_circuit_cosimulation, validate_field_circuit_request
from .peec_field_provider import NativePeecFieldReductionProvider
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

__all__ = [
    "AnalysisResult",
    "AnalysisSpec",
    "DesignIR",
    "DesignIRV2",
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
