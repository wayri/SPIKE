# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from dataclasses import replace

from python.spikes.firmware_targets import (
    FirmwareTargetError,
    FirmwareTargetManifest,
    admit_firmware,
)


DIGEST = "a" * 64


def manifest(target="stm32f4-discovery", architecture="arm-cortex-m4", kind="elf", **fields):
    return FirmwareTargetManifest(target, architecture, kind, DIGEST, **fields)


class FirmwareTargetTests(unittest.TestCase):
    def test_known_elf_target_is_still_rejected_without_runtime(self):
        admission = admit_firmware(manifest())
        self.assertEqual(admission.status, "rejected")
        self.assertEqual(admission.code, "EMULATOR_ADAPTER_UNAVAILABLE")
        self.assertFalse(admission.instruction_emulation)
        self.assertFalse(admission.electrical_cosimulation)

    def test_reviewed_backend_only_creates_candidate_not_cosimulation_claim(self):
        admission = admit_firmware(manifest(), available_backends={"renode": "reviewed-1"})
        self.assertEqual(admission.status, "backend-candidate")
        self.assertFalse(admission.instruction_emulation)
        self.assertFalse(admission.peripheral_emulation)
        self.assertFalse(admission.electrical_cosimulation)
        self.assertEqual(admission.code, "EXECUTION_EVIDENCE_REQUIRED")

    def test_raw_binary_requires_load_address_and_elf_forbids_it(self):
        with self.assertRaisesRegex(FirmwareTargetError, "load_address"):
            manifest(kind="raw-bin")
        raw = manifest(kind="raw-bin", load_address=0x08000000)
        self.assertEqual(raw.load_address, 0x08000000)
        with self.assertRaisesRegex(FirmwareTargetError, "only valid"):
            replace(manifest(), load_address=0x08000000)

    def test_uf2_is_packaging_not_an_execution_claim(self):
        pico = manifest("raspberry-pi-pico-rp2040", "arm-cortex-m0plus", "uf2")
        self.assertEqual(admit_firmware(pico).code, "UF2_EXTRACTION_NOT_IMPLEMENTED")

    def test_esp32_requires_complete_flash_image_metadata(self):
        with self.assertRaisesRegex(FirmwareTargetError, "flash size"):
            manifest("esp32", "xtensa-lx6", "esp32-flash-bin")
        image = manifest(
            "esp32", "xtensa-lx6", "esp32-flash-bin", flash_size_bytes=4 * 1024 * 1024,
            includes_bootloader=True, includes_partition_table=True,
        )
        result = admit_firmware(image, available_backends={"esp-idf-qemu": "reviewed-1"})
        self.assertEqual(result.status, "backend-candidate")

    def test_uno_is_explicit_atmega328p_candidate_without_execution_claim(self):
        uno = manifest("arduino-uno-r3-atmega328p", "avr-atmega328p", "elf")
        result = admit_firmware(uno, available_backends={"simavr": "reviewed-1"})
        self.assertEqual(result.backend, "simavr")
        self.assertEqual(result.status, "backend-candidate")
        self.assertFalse(result.instruction_emulation)

    def test_unknown_board_architecture_format_and_digest_fail_closed(self):
        cases = (
            lambda: manifest("arduino-unknown"),
            lambda: manifest(architecture="arm-cortex-m3"),
            lambda: manifest(kind="uf2"),
            lambda: replace(manifest(), artifact_sha256="ABC"),
        )
        for case in cases:
            with self.subTest(case=case), self.assertRaises(FirmwareTargetError):
                case()

    def test_wrong_types_boolean_flags_and_integer_bounds_fail_cleanly(self):
        cases = (
            lambda: manifest(target=["stm32f4-discovery"]),
            lambda: manifest(architecture=None),
            lambda: manifest(kind=[]),
            lambda: replace(manifest(), artifact_sha256=None),
            lambda: manifest(kind="raw-bin", load_address=True),
            lambda: manifest(kind="raw-bin", load_address=1 << 64),
            lambda: manifest(
                "esp32", "xtensa-lx6", "esp32-flash-bin", flash_size_bytes=1,
                includes_bootloader=1, includes_partition_table=True,
            ),
            lambda: manifest(
                "esp32", "xtensa-lx6", "esp32-flash-bin", flash_size_bytes=1 << 64,
                includes_bootloader=True, includes_partition_table=True,
            ),
        )
        for case in cases:
            with self.subTest(case=case), self.assertRaises(FirmwareTargetError):
                case()
        with self.assertRaises(FirmwareTargetError):
            admit_firmware(manifest(), available_backends=[])


if __name__ == "__main__":
    unittest.main()
