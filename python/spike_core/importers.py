"""EDA-source importer contracts and registry.

Importers own source detection and conversion into DesignIR. Solvers, renderers,
reports, the CLI, and the desktop worker must not depend on vendor parsers.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Sequence

from .contracts import DesignIR
from .design_ir_v2 import DesignIRV2


IMPORT_REPORT_CONTRACT = "spike/import-report/v1"
DEFAULT_MAX_SOURCE_BYTES = 2 * 1024 * 1024 * 1024


class UnsupportedDesignFormatError(ValueError):
    """Raised when no installed importer can unambiguously read an artifact."""


@dataclass(frozen=True)
class ImportPolicy:
    """Resource and archive limits applied before a source parser executes."""

    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES
    max_archive_members: int = 100_000
    max_archive_depth: int = 4
    max_expanded_bytes: int = 8 * 1024 * 1024 * 1024
    max_compression_ratio: float = 200.0
    timeout_seconds: int = 300

    def __post_init__(self) -> None:
        if self.max_source_bytes <= 0 or self.max_archive_members <= 0 or self.timeout_seconds <= 0:
            raise ValueError("Importer limits must be positive.")
        if self.max_archive_depth < 0 or self.max_expanded_bytes <= 0 or self.max_compression_ratio < 1.0:
            raise ValueError("Importer archive limits are invalid.")


@dataclass
class ImportReport:
    importer_id: str
    source_format: str
    source_sha256: str
    source_size_bytes: int
    status: str = "completed"
    contract: str = IMPORT_REPORT_CONTRACT
    coverage: Dict[str, int] = field(default_factory=dict)
    inferred: List[Dict[str, Any]] = field(default_factory=list)
    unsupported: List[Dict[str, Any]] = field(default_factory=list)
    geometry_errors: List[Dict[str, Any]] = field(default_factory=list)
    object_map: Dict[str, str] = field(default_factory=dict)
    layer_order: List[str] = field(default_factory=list)
    model_resolution: Dict[str, int] = field(default_factory=dict)
    solver_readiness: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ImportOutcome:
    design: DesignIRV2
    report: ImportReport

    def to_dict(self) -> Dict[str, Any]:
        return {"design": self.design.to_dict(), "report": self.report.to_dict()}


@dataclass(frozen=True)
class ImporterDescriptor:
    importer_id: str
    display_name: str
    source_formats: Sequence[str]
    extensions: Sequence[str]
    contract: str = "spike/importer-descriptor/v1"
    status: str = "available"
    loss_policy: str = "report"
    accepts_directories: bool = False
    extension_id: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class DesignImporter(Protocol):
    descriptor: ImporterDescriptor

    def import_design(self, path: str) -> DesignIR:
        """Convert one source artifact into normalized DesignIR."""


@dataclass
class FunctionImporter:
    descriptor: ImporterDescriptor
    implementation: Callable[[str], DesignIR]

    def import_design(self, path: str) -> DesignIR:
        return self.implementation(path)


class ImporterRegistry:
    """Detect and invoke importers without exposing vendor implementations."""

    def __init__(self, importers: Optional[Iterable[DesignImporter]] = None, *, policy: ImportPolicy | None = None):
        self._importers: Dict[str, DesignImporter] = {}
        self.policy = policy or ImportPolicy()
        for importer in importers or ():
            self.register(importer)

    def register(self, importer: DesignImporter) -> None:
        importer_id = importer.descriptor.importer_id.strip().lower()
        if not importer_id:
            raise ValueError("Importer IDs cannot be empty")
        if importer_id in self._importers:
            raise ValueError(f"Importer already registered: {importer_id}")
        self._importers[importer_id] = importer

    def catalog(self) -> List[Dict[str, object]]:
        return [importer.descriptor.to_dict() for importer in self._importers.values()]

    def detect(self, path: str, format_hint: str = "") -> DesignImporter:
        normalized_hint = format_hint.strip().lower()
        if normalized_hint:
            matches = [
                importer for importer in self._importers.values()
                if normalized_hint == importer.descriptor.importer_id.lower()
                or normalized_hint in {item.lower() for item in importer.descriptor.source_formats}
            ]
        else:
            lower_name = Path(path).name.lower()
            matches = [
                importer for importer in self._importers.values()
                if (Path(path).is_dir() and importer.descriptor.accepts_directories)
                or any(lower_name.endswith(extension.lower()) for extension in importer.descriptor.extensions)
            ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            choices = ", ".join(item.descriptor.importer_id for item in matches)
            raise UnsupportedDesignFormatError(
                f"The design source is ambiguous ({choices}); provide an explicit format hint."
            )
        supported = ", ".join(
            extension for importer in self._importers.values() for extension in importer.descriptor.extensions
        ) or "none"
        raise UnsupportedDesignFormatError(
            f"No installed importer supports {Path(path).name or path}. Supported extensions: {supported}."
        )

    def import_design(self, path: str, format_hint: str = "", *, options: Dict[str, Any] | None = None) -> DesignIR:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"Design source does not exist: {source}")
        importer = self.detect(str(source), format_hint)
        if not source.is_file() and not (source.is_dir() and importer.descriptor.accepts_directories):
            raise ValueError("Selected importer does not accept directory sources.")
        source_size = source.stat().st_size if source.is_file() else 0
        if source_size > self.policy.max_source_bytes:
            raise ValueError(
                f"Design source is {source_size} bytes; importer policy permits {self.policy.max_source_bytes}."
            )
        if hasattr(importer, "import_with_policy"):
            design = importer.import_with_policy(str(source.resolve()), self.policy, options or {})
        else:
            if options:
                raise ValueError("This importer does not accept import options.")
            design = importer.import_design(str(source))
        if not isinstance(design, DesignIR):
            raise TypeError(f"Importer {importer.descriptor.importer_id} did not return DesignIR")
        if design.contract != "spike/v1":
            raise ValueError(
                f"Importer {importer.descriptor.importer_id} returned unsupported contract {design.contract}"
            )
        design.metadata.setdefault("importer_id", importer.descriptor.importer_id)
        design.metadata.setdefault("importer_contract", importer.descriptor.contract)
        return design

    def import_outcome(self, path: str, format_hint: str = "", *, options: Dict[str, Any] | None = None) -> ImportOutcome:
        """Import a source into typed DesignIR v2 with an auditable quality report."""

        source = Path(path)
        design_v1 = self.import_design(path, format_hint, options=options)
        from .source_package import source_identity
        digest, source_size = source_identity(source, self.policy)
        if design_v1.metadata.get("source_sha256", digest) != digest:
            raise ValueError("Design source changed during import.")
        design_v1.metadata["source_sha256"] = digest
        design = DesignIRV2.from_v1(design_v1, source_digest=digest)
        importer_id = str(design_v1.metadata.get("importer_id", "unknown"))
        issue_rows = [asdict(issue) if hasattr(issue, "__dataclass_fields__") else dict(issue) for issue in design_v1.issues]
        unsupported = [item for item in issue_rows if item.get("severity") == "error"]
        inferred = [item for item in issue_rows if "MISSING" in str(item.get("code", ""))]
        parser_diagnostics = design_v1.metadata.get("parser_diagnostics", [])
        diagnostics = [dict(item) if isinstance(item, dict) else {"message": str(item)} for item in parser_diagnostics]
        report = ImportReport(
            importer_id=importer_id,
            source_format=design.source.source_format,
            source_sha256=digest,
            source_size_bytes=source_size,
            status="completed_with_errors" if unsupported else "completed_with_warnings" if issue_rows else "completed",
            coverage={
                "layers": len(design.layers),
                "nets": len(design.nets),
                "tracks": len(design.tracks),
                "arcs": len(design.arcs),
                "zones": len(design.zones),
                "pads": len(design.pads),
                "vias": len(design.vias),
                "drills": len(design.drills),
                "castellations": len(design.castellations),
                "components": len(design.components),
                "models": len(design.models),
            },
            inferred=inferred,
            unsupported=unsupported,
            geometry_errors=[item for item in diagnostics if str(item.get("severity", "")).lower() == "error"],
            object_map={
                entity.source_id: entity.id
                for collection in design._entity_collections()
                for entity in collection
                if entity.source_id
            },
            layer_order=[item.name for item in sorted(design.layers, key=lambda layer: layer.order)],
            model_resolution={
                "declared": max(len(design.models), int(design_v1.metadata.get("footprint_models", 0) or 0)),
                "resolved": max(sum(bool(item.extensions.get("spike.v1", {}).get("model_resolved")) for item in design.components),
                                sum(item.digest in design.metadata.get("odb_model_assets", {}) for item in design.models)),
            },
            solver_readiness=_solver_readiness(design_v1),
            diagnostics=diagnostics,
        )
        design.metadata["import_report"] = report.to_dict()
        return ImportOutcome(design=design, report=report)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _solver_readiness(design: DesignIR) -> Dict[str, Dict[str, Any]]:
    copper_tokens = {"conductor", "copper", "signal", "power", "plane", "mixed"}
    copper_layers = [
        item for item in design.layers
        if str(item.get("name", "")).endswith(".Cu")
        or any(token in str(item.get("type", "")).lower() for token in copper_tokens)
    ]
    stackup_complete = (
        bool(design.stackup)
        and not design.metadata.get("stackup_missing_copper_layers")
        and design.metadata.get("physical_units_resolved", True) is not False
        and design.metadata.get("stackup_physical_complete", True) is not False
    )
    has_conductors = bool(
        design.tracks or design.pads or design.vias or design.zones or design.metadata.get("arcs")
    )
    geometry_complete = design.metadata.get("geometry_normalized", True) is not False
    geometry_solver_ready = design.metadata.get("geometry_solver_ready", True) is not False
    has_nets = bool(design.nets)

    def record(ready: bool, reasons: List[str]) -> Dict[str, Any]:
        return {"ready": ready, "reasons": reasons}

    common: List[str] = []
    if not copper_layers:
        common.append("No copper layers were imported.")
    if not has_nets:
        common.append("No net connectivity was imported.")
    if not has_conductors:
        common.append("No conductor geometry was imported.")
    elif not geometry_complete:
        common.append("Conductor geometry import is incomplete.")
    if not geometry_solver_ready:
        common.append("Retained conductor geometry is not qualified for solver meshing.")
    if design.source_format == "odb++":
        thicknesses = {str(s.get("name")): s.get("thickness_mm", s.get("thickness")) for s in design.stackup}
        if any(not isinstance(thicknesses.get(l["name"]), (int, float)) or thicknesses[l["name"]] <= 0 for l in copper_layers):
            common.append("ODB++ copper requires explicit layer thickness before solving.")
    ac_reasons = list(common)
    if not stackup_complete:
        ac_reasons.append("Stackup or dielectric material data is incomplete.")
    return {
        "pi_dc": record(not common, list(common)),
        "pi_ac": record(not ac_reasons, ac_reasons),
        "si": record(not ac_reasons, list(ac_reasons)),
        "thermal": record(not common, list(common)),
        "emi": record(not ac_reasons, list(ac_reasons)),
    }


def import_analysis_blockers(design: DesignIR, mode: str) -> List[str]:
    """Enforce declared importer losses at the execution boundary, too."""
    if design.source_format != "odb++":
        return []
    domain = {"dc": "pi_dc", "transient": "pi_ac", "ac": "pi_ac", "broadband_hf": "pi_ac", "si": "si", "thermal": "thermal", "emi": "emi"}.get(mode, "pi_ac")
    return _solver_readiness(design)[domain]["reasons"]
