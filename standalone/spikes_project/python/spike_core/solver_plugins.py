"""Minimal solver manifest used by the standalone ngspice comparison adapter."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PLUGIN_CONTRACT = "spike/solver-plugin/v1"
PLUGIN_API_VERSION = 1


@dataclass(frozen=True)
class SolverPluginManifest:
    id: str
    name: str
    version: str
    provider: str
    analyses: list[str]
    formulations: list[str]
    capabilities: list[str]
    geometry_contracts: list[str] = field(default_factory=lambda: ["spike/v1"])
    result_contract: str = "spike/v1"
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
    limits: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.contract != PLUGIN_CONTRACT or self.api_version != PLUGIN_API_VERSION:
            raise ValueError("Unsupported solver manifest contract")
        if not self.id or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in self.id):
            raise ValueError("Invalid solver plugin ID")
        if self.state not in {"available", "experimental", "integration_pending", "unavailable"}:
            raise ValueError("Invalid solver plugin state")
        if not self.analyses or not self.formulations:
            raise ValueError("Solver manifest requires analyses and formulations")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["PLUGIN_API_VERSION", "PLUGIN_CONTRACT", "SolverPluginManifest"]
