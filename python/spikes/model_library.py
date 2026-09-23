"""Qualified local model index and deterministic KiCad symbol mappings."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from .model_builder_contracts import MODEL_PACKAGE_CONTRACT, ModelPackage


MODEL_INDEX_CONTRACT = "spikes/qualified-model-index/v1"
MODEL_RECORD_CONTRACT = "spikes/qualified-model-record/v1"
REDISTRIBUTION_CONTRACT = "spikes/model-redistribution-approval/v1"
KICAD_MAPPING_CONTRACT = "spikes/kicad-model-mapping/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_MODEL_ID = re.compile(
    r"^spikes\.(?:ideal|generic|power|electromechanical|core):[a-z][a-z0-9_.-]*@[1-9][0-9]*$",
    flags=re.ASCII,
)
_SYMBOL_ID = re.compile(r"^[A-Za-z0-9_.+-]+:[A-Za-z0-9_.+-]+$", flags=re.ASCII)
_PIN = re.compile(r"^[A-Za-z0-9_.+-]{1,32}$", flags=re.ASCII)


def _text(value: Any, label: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _digest(value: Any, label: str) -> str:
    normalized = str(value)
    if _SHA256.fullmatch(normalized) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return normalized


@dataclass(frozen=True, slots=True)
class RedistributionApproval:
    model_id: str
    content_sha256: str
    license_expression: str
    evidence_sha256: str
    reviewer: str
    approved: bool
    notes: str = ""
    contract: str = REDISTRIBUTION_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != REDISTRIBUTION_CONTRACT or _MODEL_ID.fullmatch(self.model_id) is None:
            raise ValueError("Invalid redistribution approval contract or model ID")
        object.__setattr__(self, "content_sha256", _digest(self.content_sha256, "model content"))
        object.__setattr__(self, "evidence_sha256", _digest(self.evidence_sha256, "approval evidence"))
        object.__setattr__(self, "license_expression", _text(self.license_expression, "license expression"))
        object.__setattr__(self, "reviewer", _text(self.reviewer, "approval reviewer"))
        if not isinstance(self.approved, bool):
            raise ValueError("approved must be boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract, "model_id": self.model_id,
            "content_sha256": self.content_sha256,
            "license_expression": self.license_expression,
            "evidence_sha256": self.evidence_sha256, "reviewer": self.reviewer,
            "approved": self.approved, "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RedistributionApproval":
        return cls(
            model_id=str(value.get("model_id", "")),
            content_sha256=str(value.get("content_sha256", "")),
            license_expression=str(value.get("license_expression", "")),
            evidence_sha256=str(value.get("evidence_sha256", "")),
            reviewer=str(value.get("reviewer", "")), approved=value.get("approved"),
            notes=str(value.get("notes", "")), contract=str(value.get("contract", "")),
        )


@dataclass(frozen=True, slots=True)
class QualifiedModelRecord:
    model_id: str
    title: str
    family: str
    pins: tuple[str, ...]
    content_sha256: str
    implementation: str
    qualification_policy: str
    qualified_by: str
    redistribution: RedistributionApproval
    contract: str = MODEL_RECORD_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != MODEL_RECORD_CONTRACT or _MODEL_ID.fullmatch(self.model_id) is None:
            raise ValueError("Invalid qualified model record contract or model ID")
        object.__setattr__(self, "title", _text(self.title, "model title"))
        object.__setattr__(self, "family", _text(self.family, "model family"))
        object.__setattr__(self, "implementation", _text(self.implementation, "model implementation"))
        object.__setattr__(self, "qualification_policy", _text(self.qualification_policy, "qualification policy"))
        object.__setattr__(self, "qualified_by", _text(self.qualified_by, "qualifier"))
        object.__setattr__(self, "content_sha256", _digest(self.content_sha256, "model content"))
        if not self.pins or len(self.pins) != len(set(self.pins)) or any(_PIN.fullmatch(pin) is None for pin in self.pins):
            raise ValueError("Qualified model pins must be nonempty, valid, and unique")
        if (
            not self.redistribution.approved
            or self.redistribution.model_id != self.model_id
            or self.redistribution.content_sha256 != self.content_sha256
        ):
            raise ValueError("Qualified model requires matching approved redistribution evidence")

    @classmethod
    def from_package(
        cls, package: ModelPackage, approval: RedistributionApproval,
    ) -> "QualifiedModelRecord":
        if package.contract != MODEL_PACKAGE_CONTRACT or not package.verify_digest():
            raise ValueError("Model package contract or content digest is invalid")
        if package.qualification.state != "qualified":
            raise ValueError("Only qualified model packages may enter the local index")
        return cls(
            model_id=package.model_id, title=package.title, family=package.family,
            pins=package.pins, content_sha256=package.content_sha256,
            implementation=package.black_box.implementation,
            qualification_policy=package.qualification.policy_id,
            qualified_by=package.qualification.reviewer,
            redistribution=approval,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract, "model_id": self.model_id, "title": self.title,
            "family": self.family, "pins": list(self.pins),
            "content_sha256": self.content_sha256,
            "implementation": self.implementation,
            "qualification_policy": self.qualification_policy,
            "qualified_by": self.qualified_by,
            "redistribution": self.redistribution.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "QualifiedModelRecord":
        redistribution = value.get("redistribution")
        if not isinstance(redistribution, Mapping):
            raise ValueError("Qualified model record requires redistribution evidence")
        return cls(
            model_id=str(value.get("model_id", "")), title=str(value.get("title", "")),
            family=str(value.get("family", "")), pins=tuple(value.get("pins", ())),
            content_sha256=str(value.get("content_sha256", "")),
            implementation=str(value.get("implementation", "")),
            qualification_policy=str(value.get("qualification_policy", "")),
            qualified_by=str(value.get("qualified_by", "")),
            redistribution=RedistributionApproval.from_dict(redistribution),
            contract=str(value.get("contract", "")),
        )


@dataclass(frozen=True, slots=True)
class KiCadModelMapping:
    symbol_id: str
    model_id: str
    model_content_sha256: str
    pin_map: Mapping[str, str]
    parameter_overrides: Mapping[str, float] = field(default_factory=dict)
    contract: str = KICAD_MAPPING_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != KICAD_MAPPING_CONTRACT or _SYMBOL_ID.fullmatch(self.symbol_id) is None:
            raise ValueError("Invalid KiCad mapping contract or Library:Symbol identifier")
        if _MODEL_ID.fullmatch(self.model_id) is None:
            raise ValueError("Invalid mapped model ID")
        object.__setattr__(self, "model_content_sha256", _digest(self.model_content_sha256, "mapped model content"))
        pins = {str(key): str(value) for key, value in self.pin_map.items()}
        if not pins or any(_PIN.fullmatch(key) is None or _PIN.fullmatch(value) is None for key, value in pins.items()):
            raise ValueError("KiCad pin maps must contain valid pin identifiers")
        if len(set(pins.values())) != len(pins):
            raise ValueError("KiCad pin maps must be one-to-one")
        parameters: dict[str, float] = {}
        for key, raw in self.parameter_overrides.items():
            number = float(raw)
            if not math.isfinite(number):
                raise ValueError("KiCad parameter overrides must be finite")
            parameters[str(key)] = number
        object.__setattr__(self, "pin_map", MappingProxyType(dict(sorted(pins.items()))))
        object.__setattr__(self, "parameter_overrides", MappingProxyType(dict(sorted(parameters.items()))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract, "symbol_id": self.symbol_id,
            "model_id": self.model_id, "model_content_sha256": self.model_content_sha256,
            "pin_map": dict(self.pin_map),
            "parameter_overrides": dict(self.parameter_overrides),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "KiCadModelMapping":
        return cls(
            symbol_id=str(value.get("symbol_id", "")), model_id=str(value.get("model_id", "")),
            model_content_sha256=str(value.get("model_content_sha256", "")),
            pin_map=value.get("pin_map", {}), parameter_overrides=value.get("parameter_overrides", {}),
            contract=str(value.get("contract", "")),
        )


@dataclass(frozen=True, slots=True)
class QualifiedModelLibrary:
    records: tuple[QualifiedModelRecord, ...]
    mappings: tuple[KiCadModelMapping, ...] = ()
    contract: str = MODEL_INDEX_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != MODEL_INDEX_CONTRACT:
            raise ValueError("Invalid qualified model index contract")
        by_model = {record.model_id: record for record in self.records}
        if not by_model or len(by_model) != len(self.records):
            raise ValueError("Qualified model IDs must be nonempty and unique")
        symbols: set[str] = set()
        for mapping in self.mappings:
            if mapping.symbol_id in symbols:
                raise ValueError("KiCad symbol mappings must be unique")
            symbols.add(mapping.symbol_id)
            record = by_model.get(mapping.model_id)
            if record is None or record.content_sha256 != mapping.model_content_sha256:
                raise ValueError("KiCad mapping must target the exact indexed model digest")
            if set(mapping.pin_map.values()) != set(record.pins):
                raise ValueError("KiCad mapping must bind every model pin exactly once")

    def resolve_kicad(self, symbol_id: str) -> tuple[QualifiedModelRecord, KiCadModelMapping]:
        mapping = next((item for item in self.mappings if item.symbol_id == symbol_id), None)
        if mapping is None:
            raise KeyError(f"No qualified model mapping exists for {symbol_id}")
        record = next(item for item in self.records if item.model_id == mapping.model_id)
        return record, mapping

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "records": [item.to_dict() for item in sorted(self.records, key=lambda item: item.model_id)],
            "kicad_mappings": [item.to_dict() for item in sorted(self.mappings, key=lambda item: item.symbol_id)],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "QualifiedModelLibrary":
        return cls(
            records=tuple(QualifiedModelRecord.from_dict(item) for item in value.get("records", ())),
            mappings=tuple(KiCadModelMapping.from_dict(item) for item in value.get("kicad_mappings", ())),
            contract=str(value.get("contract", "")),
        )


__all__ = [
    "KICAD_MAPPING_CONTRACT", "MODEL_INDEX_CONTRACT", "MODEL_RECORD_CONTRACT",
    "REDISTRIBUTION_CONTRACT", "KiCadModelMapping", "QualifiedModelLibrary",
    "QualifiedModelRecord", "RedistributionApproval",
]
