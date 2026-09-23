"""Versioned, UI-independent data contracts used by desktop and cloud workers.

The contracts intentionally contain plain JSON-compatible values. This keeps the
desktop worker, Tauri bridge, CLI, and future HTTP service interchangeable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


CONTRACT_VERSION = "spike/v1"


@dataclass
class ValidationIssue:
    code: str
    severity: str
    message: str
    path: str = ""
    suggestion: str = ""
    status: str = "open"


@dataclass
class DesignIR:
    """Normalized design representation independent of an EDA vendor."""

    contract: str = CONTRACT_VERSION
    design_id: str = ""
    name: str = "Untitled design"
    source_format: str = "unknown"
    source_path: str = ""
    units: str = "mm"
    layers: List[Dict[str, Any]] = field(default_factory=list)
    nets: List[Dict[str, Any]] = field(default_factory=list)
    tracks: List[Dict[str, Any]] = field(default_factory=list)
    vias: List[Dict[str, Any]] = field(default_factory=list)
    pads: List[Dict[str, Any]] = field(default_factory=list)
    zones: List[Dict[str, Any]] = field(default_factory=list)
    components: List[Dict[str, Any]] = field(default_factory=list)
    component_bonds: List[Dict[str, Any]] = field(default_factory=list)
    connectors: List[Dict[str, Any]] = field(default_factory=list)
    stackup: List[Dict[str, Any]] = field(default_factory=list)
    technology: str = "rigid"
    regions: List[Dict[str, Any]] = field(default_factory=list)
    bends: List[Dict[str, Any]] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisSpec:
    """Inputs to an analysis run, with explicit model validity metadata."""

    contract: str = CONTRACT_VERSION
    analysis_id: str = ""
    mode: str = "dc"
    solver_id: str = "auto"
    formulation: str = "auto"
    required_capabilities: List[str] = field(default_factory=list)
    net_names: List[str] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    loads: List[Dict[str, Any]] = field(default_factory=list)
    return_path: Dict[str, Any] = field(default_factory=dict)
    probes: List[Dict[str, Any]] = field(default_factory=list)
    frequency_start_hz: Optional[float] = None
    frequency_stop_hz: Optional[float] = None
    frequency_points: int = 101
    transient: Dict[str, Any] = field(default_factory=dict)
    mesh: Dict[str, Any] = field(default_factory=dict)
    limits: Dict[str, Any] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisResult:
    """Machine-readable result bundle consumed by UI, reports, and CI."""

    contract: str = CONTRACT_VERSION
    analysis_id: str = ""
    status: str = "not_run"
    mode: str = "dc"
    model_status: str = "approximate"
    summary: Dict[str, Any] = field(default_factory=dict)
    fields: Dict[str, Any] = field(default_factory=dict)
    networks: Dict[str, Any] = field(default_factory=dict)
    probes: List[Dict[str, Any]] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    # fields.visualization is the stable renderer-facing envelope:
    # scalar_fields, vector_fields, and mesh. Solvers may omit datasets they do
    # not compute; clients must never infer unavailable physics.
