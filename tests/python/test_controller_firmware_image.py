# SPDX-License-Identifier: Apache-2.0
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "standalone" / "spikes_project" / "studio" / "python"))

from spikes_studio.firmware_image import MAX_IMAGE_SIZE, TARGETS, image_segments, inspect_image


def make_raw(flash_start, initial_sp, size=32):
    image = bytearray(size)
    struct.pack_into("<II", image, 0, initial_sp, flash_start + 9)
    return bytes(image)


def make_elf(flash_start, initial_sp, *, machine=40, segment_size=32,
             file_size=None, extra_headers=()):
    file_size = segment_size if file_size is None else file_size
    segment_offset = 0x100
    headers = [(segment_offset, flash_start, flash_start, file_size,
                segment_size, 5, 0x100), *extra_headers]
    image_size = max([segment_offset + file_size]
                     + [offset + filesz for offset, _vaddr, _paddr, filesz,
                        _memsz, _flags, _align in extra_headers])
    image = bytearray(image_size)
    ident = b"\x7fELF" + bytes((1, 1, 1)) + bytes(9)
    image[:16] = ident
    struct.pack_into("<HHIIIIIHHHHHH", image, 16,
                     2, machine, 1, flash_start + 9, 52, 0, 0,
                     52, 32, len(headers), 0, 0, 0)
    for index, (offset, vaddr, paddr, filesz, memsz, flags, align) in enumerate(headers):
        struct.pack_into("<IIIIIIII", image, 52 + 32 * index,
                         1, offset, vaddr, paddr, filesz, memsz, flags, align)
    if file_size >= 4:
        struct.pack_into("<I", image, segment_offset, initial_sp)
    if file_size >= 8:
        struct.pack_into("<I", image, segment_offset + 4, flash_start + 9)
    return bytes(image)


def make_elf_with_initialized_data(flash_start, initial_sp, *, data_lma=None):
    data_lma = flash_start + 32 if data_lma is None else data_lma
    data_vma = 0x20000000
    image = bytearray(0x128)
    ident = b"\x7fELF" + bytes((1, 1, 1)) + bytes(9)
    image[:16] = ident
    struct.pack_into("<HHIIIIIHHHHHH", image, 16,
                     2, 40, 1, flash_start + 9, 52, 0, 0, 52, 32, 2, 0, 0, 0)
    struct.pack_into("<IIIIIIII", image, 52,
                     1, 0x100, flash_start, flash_start, 32, 32, 5, 0x20)
    struct.pack_into("<IIIIIIII", image, 84,
                     1, 0x120, data_vma, data_lma, 8, 16, 6, 0x20)
    struct.pack_into("<II", image, 0x100, initial_sp, flash_start + 9)
    image[0x120:0x128] = b"DATAINIT"
    return bytes(image)


class ControllerFirmwareImageTests(unittest.TestCase):
    def write_image(self, directory, name, content):
        path = Path(directory) / name
        path.write_bytes(content)
        return path

    def test_supported_targets_are_exact_and_describe_runtime_resources(self):
        self.assertEqual(set(TARGETS), {
            "nordic-nrf52840-dk-pca10056-r3-0-2",
            "arduino-nano-33-ble-abx00030",
            "st-stm32f407g-disc1-mb997",
        })
        self.assertEqual(TARGETS["nordic-nrf52840-dk-pca10056-r3-0-2"]["renode_platform"],
                         "platforms/boards/nrf52840dk_nrf52840.repl")
        self.assertEqual(TARGETS["arduino-nano-33-ble-abx00030"]["renode_platform"],
                         "platforms/boards/arduino_nano_33_ble.repl")
        self.assertEqual(TARGETS["st-stm32f407g-disc1-mb997"]["renode_platform"],
                         "platforms/boards/stm32f4_discovery.repl")

    def test_raw_images_report_exact_artifact_metadata_for_each_target(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            for target_id, descriptor in TARGETS.items():
                flash_start, _flash_end = descriptor["flash"]
                _sram_start, sram_end = descriptor["sram"]
                content = make_raw(flash_start, sram_end)
                path = self.write_image(directory, f"{target_id}.bin", content)
                result = inspect_image(path, target_id)
                self.assertEqual(result, {
                    "path": str(path),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                    "kind": "bin",
                    "load_address": flash_start,
                    "reset_pc": flash_start + 9,
                    "initial_sp": sram_end,
                    "target_id": target_id,
                })

    def test_arm_elf32_little_endian_is_admitted_without_loading(self):
        target_id = "st-stm32f407g-disc1-mb997"
        flash_start, _flash_end = TARGETS[target_id]["flash"]
        _sram_start, sram_end = TARGETS[target_id]["sram"]
        content = make_elf(flash_start, sram_end)
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = self.write_image(directory, "firmware.elf", content)
            result = inspect_image(str(path), target_id, kind="elf")
        self.assertEqual(result["kind"], "elf")
        self.assertEqual(result["load_address"], flash_start)
        self.assertEqual(result["initial_sp"], sram_end)
        self.assertEqual(result["reset_pc"], flash_start + 9)

    def test_divergent_data_vma_and_flash_lma_expose_physical_file_loads(self):
        target_id = "st-stm32f407g-disc1-mb997"
        flash_start, _flash_end = TARGETS[target_id]["flash"]
        _sram_start, sram_end = TARGETS[target_id]["sram"]
        content = make_elf_with_initialized_data(flash_start, sram_end)
        self.assertEqual(image_segments(content, target_id), [
            {
                "address": flash_start,
                "offset": 0x100,
                "file_size": 32,
                "memory_size": 32,
                "vaddr": flash_start,
                "executable": True,
            },
            {
                "address": flash_start + 32,
                "offset": 0x120,
                "file_size": 8,
                "memory_size": 16,
                "vaddr": 0x20000000,
                "executable": False,
            },
        ])
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = self.write_image(directory, "split.elf", content)
            result = inspect_image(path, target_id)
        self.assertEqual(result["load_address"], flash_start)
        self.assertEqual(set(result), {"path", "sha256", "size", "kind", "load_address",
                                       "reset_pc", "initial_sp", "target_id"})

    def test_raw_image_segments_are_one_validated_physical_load(self):
        target_id = "arduino-nano-33-ble-abx00030"
        content = make_raw(0, 0x20040000)
        self.assertEqual(image_segments(content, target_id, kind="bin"), [{
            "address": 0,
            "offset": 0,
            "file_size": len(content),
            "memory_size": len(content),
            "vaddr": 0,
            "executable": True,
        }])

    def test_foreign_truncated_and_mislabeled_formats_are_rejected(self):
        target_id = "arduino-nano-33-ble-abx00030"
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            foreign = self.write_image(directory, "foreign.elf",
                                       make_elf(0, 0x20040000, machine=3))
            with self.assertRaisesRegex(ValueError, "ARM ELF32"):
                inspect_image(foreign, target_id)
            short = self.write_image(directory, "short.bin", b"UF2\n")
            with self.assertRaisesRegex(ValueError, "vector table"):
                inspect_image(short, target_id)
            raw = self.write_image(directory, "raw.elf", make_raw(0, 0x20040000))
            with self.assertRaisesRegex(ValueError, "not elf"):
                inspect_image(raw, target_id, kind="elf")

    def test_vectors_must_be_aligned_thumb_and_in_admitted_memory(self):
        target_id = "st-stm32f407g-disc1-mb997"
        flash_start, _flash_end = TARGETS[target_id]["flash"]
        cases = {
            "ccm-stack": (0x10010000, flash_start + 9, "stack pointer"),
            "unaligned-stack": (0x20020004, flash_start + 9, "stack pointer"),
            "arm-reset": (0x20020000, flash_start + 8, "Thumb"),
            "outside-image": (0x20020000, flash_start + 0x101, "executable loaded"),
        }
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            for name, (stack, reset, message) in cases.items():
                content = bytearray(32)
                struct.pack_into("<II", content, 0, stack, reset)
                path = self.write_image(directory, f"{name}.bin", content)
                with self.assertRaisesRegex(ValueError, message):
                    inspect_image(path, target_id)

    def test_elf_load_ranges_file_bounds_overlap_and_zero_fill_are_checked(self):
        target_id = "st-stm32f407g-disc1-mb997"
        flash_start, _flash_end = TARGETS[target_id]["flash"]
        _sram_start, sram_end = TARGETS[target_id]["sram"]
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            zero_reset = self.write_image(
                directory, "zero-reset.elf",
                make_elf(flash_start, sram_end, segment_size=32, file_size=4))
            with self.assertRaisesRegex(ValueError, "entry point|vector table"):
                inspect_image(zero_reset, target_id)

            outside = bytearray(make_elf(flash_start, sram_end))
            struct.pack_into("<I", outside, 52 + 8, 0x60000000)
            outside_path = self.write_image(directory, "outside.elf", outside)
            with self.assertRaisesRegex(ValueError, "outside admitted"):
                inspect_image(outside_path, target_id)

            overlap_header = (0x120, flash_start + 16, flash_start + 16, 16, 32, 5, 0x10)
            overlap = self.write_image(
                directory, "overlap.elf",
                make_elf(flash_start, sram_end, extra_headers=(overlap_header,)))
            with self.assertRaisesRegex(ValueError, "overlap"):
                inspect_image(overlap, target_id)

            physical_overlap = self.write_image(
                directory, "physical-overlap.elf",
                make_elf_with_initialized_data(flash_start, sram_end,
                                               data_lma=flash_start + 16))
            with self.assertRaisesRegex(ValueError, "physical file ranges overlap"):
                inspect_image(physical_overlap, target_id)

            truncated = bytearray(make_elf(flash_start, sram_end))
            struct.pack_into("<I", truncated, 52 + 16, 0x1000)
            truncated_path = self.write_image(directory, "truncated.elf", truncated)
            with self.assertRaisesRegex(ValueError, "out of bounds"):
                inspect_image(truncated_path, target_id)

            wrapped = bytearray(make_elf(flash_start, sram_end))
            struct.pack_into("<II", wrapped, 52 + 8, 0xFFFFFFF0, 0xFFFFFFF0)
            struct.pack_into("<I", wrapped, 52 + 28, 1)
            wrapped_path = self.write_image(directory, "wrapped.elf", wrapped)
            with self.assertRaisesRegex(ValueError, "wraps 32-bit"):
                inspect_image(wrapped_path, target_id)

    def test_unknown_target_empty_directory_symlink_and_size_limit_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            valid = self.write_image(directory, "valid.bin", make_raw(0, 0x20040000))
            with self.assertRaisesRegex(ValueError, "unsupported firmware target"):
                inspect_image(valid, "unknown-target")
            with self.assertRaisesRegex(ValueError, "regular file"):
                inspect_image(directory, "arduino-nano-33-ble-abx00030")
            empty = self.write_image(directory, "empty.bin", b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                inspect_image(empty, "arduino-nano-33-ble-abx00030")
            oversized = Path(directory) / "oversized.bin"
            with oversized.open("wb") as stream:
                stream.truncate(MAX_IMAGE_SIZE + 1)
            with self.assertRaisesRegex(ValueError, "16 MiB"):
                inspect_image(oversized, "arduino-nano-33-ble-abx00030")
            link = Path(directory) / "link.bin"
            try:
                link.symlink_to(valid)
            except OSError:
                pass
            else:
                with self.assertRaisesRegex(ValueError, "symbolic link"):
                    inspect_image(link, "arduino-nano-33-ble-abx00030")


if __name__ == "__main__":
    unittest.main()
