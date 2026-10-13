# SPDX-License-Identifier: Apache-2.0
"""Fail-closed admission metadata for prospective MCU emulation adapters.

This module validates identities and loading assumptions.  It does not invoke
an emulator, decode UF2, or couple digital events to an electrical solver.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


FIRMWARE_TARGET_CONTRACT = "spikes/firmware-target-manifest/v1"
FIRMWARE_ADMISSION_CONTRACT = "spikes/firmware-target-admission/v1"

_SHA256 = re.compile(r"[0-9a-f]{64}")
_TARGETS = MappingProxyType({
    "arduino-uno-r3-atmega328p": ("avr-atmega328p", "simavr", frozenset({"elf"})),
    "arduino-nano-33-ble": ("arm-cortex-m4", "renode", frozenset({"elf", "raw-bin"})),
    "raspberry-pi-pico-rp2040": ("arm-cortex-m0plus", None, frozenset({"elf", "uf2", "raw-bin"})),
    "esp32": ("xtensa-lx6", "esp-idf-qemu", frozenset({"esp32-flash-bin"})),
    "stm32f103-blue-pill": ("arm-cortex-m3", "renode", frozenset({"elf", "raw-bin"})),
    "stm32f4-discovery": ("arm-cortex-m4", "renode", frozenset({"elf", "raw-bin"})),
})


class FirmwareTargetError(ValueError):
    """The target manifest is ambiguous or violates the loading contract."""


@dataclass(frozen=True, slots=True)
class FirmwareTargetManifest:
    target_id: str
    cpu_architecture: str
    artifact_kind: str
    artifact_sha256: str
    load_address: int | None = None
    flash_size_bytes: int | None = None
    includes_bootloader: bool = False
    includes_partition_table: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.target_id, str):
            raise FirmwareTargetError("target_id must be a string")
        if not isinstance(self.cpu_architecture, str):
            raise FirmwareTargetError("cpu_architecture must be a string")
        if not isinstance(self.artifact_kind, str):
            raise FirmwareTargetError("artifact_kind must be a string")
        if not isinstance(self.artifact_sha256, str):
            raise FirmwareTargetError("artifact_sha256 must be a string")
        if not isinstance(self.includes_bootloader, bool):
            raise FirmwareTargetError("includes_bootloader must be boolean")
        if not isinstance(self.includes_partition_table, bool):
            raise FirmwareTargetError("includes_partition_table must be boolean")
        target = _TARGETS.get(self.target_id)
        if target is None:
            raise FirmwareTargetError("unknown target_id; a board-level target is required")
        architecture, _backend, formats = target
        if self.cpu_architecture != architecture:
            raise FirmwareTargetError("cpu_architecture does not match target_id")
        if self.artifact_kind not in formats:
            raise FirmwareTargetError("artifact_kind is not admitted for target_id")
        if _SHA256.fullmatch(self.artifact_sha256) is None:
            raise FirmwareTargetError("artifact_sha256 must be a lowercase SHA-256 digest")
        if self.artifact_kind == "raw-bin":
            if (not isinstance(self.load_address, int) or isinstance(self.load_address, bool)
                    or self.load_address < 0 or self.load_address > 0xFFFFFFFFFFFFFFFF):
                raise FirmwareTargetError("raw-bin requires a load_address in the unsigned 64-bit range")
        elif self.load_address is not None:
            raise FirmwareTargetError("load_address is only valid for raw-bin")
        if self.artifact_kind == "esp32-flash-bin":
            if (not isinstance(self.flash_size_bytes, int) or isinstance(self.flash_size_bytes, bool)
                    or self.flash_size_bytes <= 0 or self.flash_size_bytes > 0xFFFFFFFFFFFFFFFF):
                raise FirmwareTargetError(
                    "esp32-flash-bin requires its configured flash size in the unsigned 64-bit range"
                )
            if not self.includes_bootloader or not self.includes_partition_table:
                raise FirmwareTargetError(
                    "esp32-flash-bin must include bootloader and partition table at their build offsets"
                )
        elif self.flash_size_bytes is not None or self.includes_bootloader or self.includes_partition_table:
            raise FirmwareTargetError("flash-layout fields are only valid for esp32-flash-bin")

    @property
    def contract(self) -> str:
        return FIRMWARE_TARGET_CONTRACT


@dataclass(frozen=True, slots=True)
class FirmwareAdmission:
    target_id: str
    status: str
    backend: str | None
    code: str
    instruction_emulation: bool
    peripheral_emulation: bool
    electrical_cosimulation: bool

    @property
    def contract(self) -> str:
        return FIRMWARE_ADMISSION_CONTRACT


def admit_firmware(
    manifest: FirmwareTargetManifest,
    *,
    available_backends: Mapping[str, str] | None = None,
) -> FirmwareAdmission:
    """Classify an artifact without executing it.

    ``available_backends`` maps backend name to a reviewed adapter version.  No
    such adapter ships in SPIKE today, so omission always fails closed.
    """
    _architecture, backend, _formats = _TARGETS[manifest.target_id]
    if manifest.artifact_kind == "uf2":
        return FirmwareAdmission(
            manifest.target_id, "rejected", backend, "UF2_EXTRACTION_NOT_IMPLEMENTED",
            False, False, False,
        )
    if backend is None:
        return FirmwareAdmission(
            manifest.target_id, "rejected", None, "TARGET_RUNTIME_NOT_ESTABLISHED",
            False, False, False,
        )
    if available_backends is not None and not isinstance(available_backends, Mapping):
        raise FirmwareTargetError("available_backends must be a mapping")
    version = (available_backends or {}).get(backend)
    if not version or not isinstance(version, str):
        return FirmwareAdmission(
            manifest.target_id, "rejected", backend, "EMULATOR_ADAPTER_UNAVAILABLE",
            False, False, False,
        )
    # Admission only establishes an instruction/peripheral execution candidate.
    # A future adapter must separately prove the target peripherals it exposes.
    return FirmwareAdmission(
        manifest.target_id, "backend-candidate", backend, "EXECUTION_EVIDENCE_REQUIRED",
        False, False, False,
    )


__all__ = [
    "FIRMWARE_ADMISSION_CONTRACT", "FIRMWARE_TARGET_CONTRACT", "FirmwareAdmission",
    "FirmwareTargetError", "FirmwareTargetManifest", "admit_firmware",
]
