# SPDX-License-Identifier: Apache-2.0
"""Inert admission inspection for narrowly supported Cortex-M firmware images.

This module parses bytes and reports artifact metadata only.  It does not load,
execute, translate, emulate, or attach firmware to a simulator.

Memory bounds come from the nRF52840 Product Specification (1 MiB flash,
256 KiB RAM) and the STM32F405/407 datasheet memory map (flash at 0x08000000,
128 KiB system SRAM at 0x20000000; CCM at 0x10000000 is deliberately excluded):

* https://docs.nordicsemi.com/r/bundle/ps_nrf52840/
* https://www.st.com/resource/en/datasheet/stm32f407zg.pdf
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import struct


MAX_IMAGE_SIZE = 16 * 1024 * 1024

TARGETS: dict[str, dict[str, object]] = {
    "nordic-nrf52840-dk-pca10056-r3-0-2": {
        "mcu": "nRF52840",
        "flash": (0x00000000, 0x00100000),
        "sram": (0x20000000, 0x20040000),
        "renode_platform": "platforms/boards/nrf52840dk_nrf52840.repl",
    },
    "arduino-nano-33-ble-abx00030": {
        "mcu": "nRF52840 (NINA-B306)",
        "flash": (0x00000000, 0x00100000),
        "sram": (0x20000000, 0x20040000),
        "renode_platform": "platforms/boards/arduino_nano_33_ble.repl",
    },
    "st-stm32f407g-disc1-mb997": {
        "mcu": "STM32F407VGT6",
        "flash": (0x08000000, 0x08100000),
        "sram": (0x20000000, 0x20020000),
        "renode_platform": "platforms/boards/stm32f4_discovery.repl",
    },
}


def inspect_image(path: str | os.PathLike[str], target_id: str,
                  kind: str = "auto") -> dict[str, object]:
    """Validate an inert firmware artifact and return bounded metadata.

    ``kind`` is ``"auto"``, ``"elf"``, or ``"bin"``.  Auto detection only
    recognizes the ELF magic; every other artifact must satisfy the Cortex-M
    raw-vector contract before it is admitted as a binary.
    """
    if target_id not in TARGETS:
        raise ValueError(f"unsupported firmware target: {target_id}")
    if kind not in {"auto", "elf", "bin"}:
        raise ValueError("kind must be 'auto', 'elf', or 'bin'")

    input_path = os.fspath(path)
    data = _read_bounded_regular_file(Path(input_path))
    detected_kind = "elf" if data.startswith(b"\x7fELF") else "bin"
    if kind != "auto" and kind != detected_kind:
        raise ValueError(f"firmware content is not {kind}")

    target = TARGETS[target_id]
    segments, initial_sp, reset_pc = _inspect_payload(data, target, detected_kind)

    return {
        "path": input_path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "kind": detected_kind,
        "load_address": min(segment["address"] for segment in segments),
        "reset_pc": reset_pc,
        "initial_sp": initial_sp,
        "target_id": target_id,
    }


def image_segments(payload: bytes, target_id: str,
                   kind: str = "auto") -> list[dict[str, object]]:
    """Return validated physical file-load segments without loading them.

    ELF segment ``address`` is ``p_paddr`` when nonzero, otherwise ``p_vaddr``.
    ``vaddr`` separately preserves the runtime-memory destination used to
    validate VMA overlap and zero-initialized extent.  Callers must not treat
    this artifact inspection as execution evidence.
    """
    if target_id not in TARGETS:
        raise ValueError(f"unsupported firmware target: {target_id}")
    if kind not in {"auto", "elf", "bin"}:
        raise ValueError("kind must be 'auto', 'elf', or 'bin'")
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if not payload:
        raise ValueError("firmware image is empty")
    if len(payload) > MAX_IMAGE_SIZE:
        raise ValueError("firmware image exceeds the 16 MiB inspection limit")
    detected_kind = "elf" if payload.startswith(b"\x7fELF") else "bin"
    if kind != "auto" and kind != detected_kind:
        raise ValueError(f"firmware content is not {kind}")
    segments, _initial_sp, _reset_pc = _inspect_payload(
        payload, TARGETS[target_id], detected_kind)
    return [dict(segment) for segment in segments]


def _inspect_payload(data: bytes, target: dict[str, object],
                     detected_kind: str) -> tuple[list[dict[str, object]], int, int]:
    if detected_kind == "elf":
        return _inspect_elf(data, target)
    return _inspect_bin(data, target)


def _read_bounded_regular_file(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError("firmware image must not be a symbolic link")
    try:
        before = path.stat()
    except OSError as exc:
        raise ValueError(f"cannot stat firmware image: {exc}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("firmware image must be a regular file")
    if before.st_size <= 0:
        raise ValueError("firmware image is empty")
    if before.st_size > MAX_IMAGE_SIZE:
        raise ValueError("firmware image exceeds the 16 MiB inspection limit")
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_IMAGE_SIZE + 1)
            after = os.fstat(stream.fileno())
    except OSError as exc:
        raise ValueError(f"cannot read firmware image: {exc}") from exc
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise ValueError("firmware image changed while opening")
    if len(data) != before.st_size:
        raise ValueError("firmware image changed while reading")
    if len(data) > MAX_IMAGE_SIZE:
        raise ValueError("firmware image exceeds the 16 MiB inspection limit")
    return data


def _inspect_bin(data: bytes, target: dict[str, object]) -> tuple[list[dict[str, object]], int, int]:
    if len(data) < 8:
        raise ValueError("raw Cortex-M image is shorter than its vector table")
    flash_start, flash_end = target["flash"]
    if len(data) > flash_end - flash_start:
        raise ValueError("raw image does not fit target flash")
    initial_sp, reset_pc = struct.unpack_from("<II", data)
    _validate_boot_vectors(initial_sp, reset_pc, target,
                           ((flash_start, flash_start + len(data), True),))
    return ([{
        "address": flash_start,
        "offset": 0,
        "file_size": len(data),
        "memory_size": len(data),
        "vaddr": flash_start,
        "executable": True,
    }], initial_sp, reset_pc)


def _inspect_elf(data: bytes, target: dict[str, object]) -> tuple[list[dict[str, object]], int, int]:
    if len(data) < 52:
        raise ValueError("truncated ELF32 header")
    ident = data[:16]
    if ident[:4] != b"\x7fELF" or ident[4] != 1 or ident[5] != 1 or ident[6] != 1:
        raise ValueError("firmware must be ELF32 little-endian version 1")
    fields = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    (elf_type, machine, version, entry, phoff, _shoff, _flags, ehsize,
     phentsize, phnum, _shentsize, _shnum, _shstrndx) = fields
    if elf_type != 2 or machine != 40 or version != 1:
        raise ValueError("firmware must be an ARM ELF32 executable")
    if ehsize != 52 or phentsize != 32 or phnum == 0:
        raise ValueError("unsupported or missing ELF32 program-header table")
    if phoff > len(data) or phnum > (len(data) - phoff) // phentsize:
        raise ValueError("ELF32 program-header table is out of bounds")

    segments: list[dict[str, object]] = []
    for index in range(phnum):
        offset = phoff + index * phentsize
        (segment_type, file_offset, vaddr, paddr, file_size, memory_size,
         flags, alignment) = struct.unpack_from("<IIIIIIII", data, offset)
        if segment_type != 1:
            continue
        if memory_size == 0:
            continue
        if file_size > memory_size or file_offset > len(data) or file_size > len(data) - file_offset:
            raise ValueError("ELF32 PT_LOAD file extent is out of bounds")
        if alignment not in {0, 1}:
            if alignment & (alignment - 1):
                raise ValueError("ELF32 PT_LOAD alignment is not a power of two")
            if file_offset % alignment != vaddr % alignment:
                raise ValueError("ELF32 PT_LOAD offset/address alignment is inconsistent")
        load_address = paddr or vaddr
        _validate_memory_extent(vaddr, memory_size, target, "virtual")
        if file_size:
            _validate_memory_extent(load_address, file_size, target, "physical file")
        segments.append({
            "address": load_address,
            "offset": file_offset,
            "file_size": file_size,
            "memory_size": memory_size,
            "vaddr": vaddr,
            "executable": bool(flags & 1),
        })

    if not segments:
        raise ValueError("ELF32 image contains no nonempty PT_LOAD segment")
    virtual_order = sorted(segments, key=lambda segment: segment["vaddr"])
    for previous, current in zip(virtual_order, virtual_order[1:]):
        if current["vaddr"] < previous["vaddr"] + previous["memory_size"]:
            raise ValueError("ELF32 PT_LOAD virtual ranges overlap")
    physical_order = sorted(
        (segment for segment in segments if segment["file_size"]),
        key=lambda segment: segment["address"])
    for previous, current in zip(physical_order, physical_order[1:]):
        if current["address"] < previous["address"] + previous["file_size"]:
            raise ValueError("ELF32 PT_LOAD physical file ranges overlap")

    if not entry & 1:
        raise ValueError("ELF32 entry point is not a Thumb address")
    if not _address_in_executable_file(entry & ~1, segments):
        raise ValueError("ELF32 entry point is outside executable PT_LOAD file bytes")

    flash_start, _flash_end = target["flash"]
    vectors = _read_physical_file(data, segments, flash_start, 8)
    initial_sp, reset_pc = struct.unpack("<II", vectors)
    executable_ranges = tuple(
        (segment["address"], segment["address"] + segment["file_size"], segment["executable"])
        for segment in segments if segment["file_size"])
    _validate_boot_vectors(initial_sp, reset_pc, target, executable_ranges)
    return segments, initial_sp, reset_pc


def _validate_memory_extent(address: int, size: int, target: dict[str, object],
                            address_kind: str) -> None:
    end = address + size
    if end > 0x100000000:
        raise ValueError(f"ELF32 PT_LOAD {address_kind} address wraps 32-bit space")
    if not any(start <= address and end <= limit
               for start, limit in (target["flash"], target["sram"])):
        raise ValueError(f"ELF32 PT_LOAD {address_kind} range is outside admitted flash/SRAM")


def _read_physical_file(data: bytes, segments: list[dict[str, object]],
                        address: int, size: int) -> bytes:
    result = bytearray()
    for current in range(address, address + size):
        for segment in segments:
            if segment["address"] <= current < segment["address"] + segment["file_size"]:
                relative = current - segment["address"]
                result.append(data[segment["offset"] + relative])
                break
        else:
            raise ValueError("ELF32 vector table is not present in physical file bytes at target flash base")
    return bytes(result)


def _address_in_executable_file(address: int, segments: list[dict[str, object]]) -> bool:
    return any(segment["executable"]
               and segment["address"] <= address < segment["address"] + segment["file_size"]
               for segment in segments)


def _validate_boot_vectors(initial_sp: int, reset_pc: int, target: dict[str, object],
                           executable_ranges: tuple[tuple[int, int, bool], ...]) -> None:
    sram_start, sram_end = target["sram"]
    if initial_sp & 7 or not sram_start <= initial_sp <= sram_end:
        raise ValueError("initial stack pointer is not 8-byte aligned in admitted SRAM")
    if not reset_pc & 1:
        raise ValueError("reset vector is not a Thumb address")
    reset_address = reset_pc & ~1
    flash_start, flash_end = target["flash"]
    if not flash_start <= reset_address < flash_end:
        raise ValueError("reset vector is outside target flash")
    if not any(executable and start <= reset_address < end
               for start, end, executable in executable_ranges):
        raise ValueError("reset vector is outside executable loaded memory")
