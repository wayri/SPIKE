# SPDX-License-Identifier: Apache-2.0
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "standalone" / "spikes_project" / "studio" / "python"))

from spikes_studio.controller_boards import catalog, get_record, lookup, records


class ControllerBoardCatalogTests(unittest.TestCase):
    def test_catalog_identity_is_unique_and_lookup_is_exact(self):
        boards = catalog()
        self.assertGreaterEqual(len(boards), 17)
        self.assertEqual(len({board.id for board in boards}), len(boards))
        for board in boards:
            self.assertIs(lookup(board.id), board)
        with self.assertRaises(KeyError):
            lookup("generic-unknown-board")

    def test_every_physical_position_is_unique_and_metadata_is_bounded(self):
        for board in catalog():
            positions = [(pin.header, pin.position) for pin in board.pins]
            self.assertEqual(len(positions), len(set(positions)), board.id)
            self.assertEqual(len({pin.id for pin in board.pins}), len(board.pins))
            self.assertTrue(all(pin.position > 0 and pin.label for pin in board.pins))
            self.assertEqual(board.execution_status, "pinout_template_only")
            self.assertIn("No binary", board.emulation_scope)
            self.assertTrue(all(url.startswith("https://") for url in board.source_urls))

    def test_representative_complete_header_boundaries(self):
        uno = lookup("arduino-uno-r3-a000066")
        self.assertIn(("POWER", 8, "VIN"), [(p.header, p.position, p.label) for p in uno.pins])
        mega = lookup("arduino-mega-2560-r3-a000067")
        self.assertIn("D53", {p.label for p in mega.pins})
        self.assertIn("A15", {p.label for p in mega.pins})
        pico = lookup("raspberry-pi-pico-rp2040")
        self.assertEqual(next(p.label for p in pico.pins if p.header == "J1/J2" and p.position == 40), "VBUS")
        nucleo = lookup("st-nucleo-f401re-mb1136")
        self.assertIn("D15/PB8", {p.label for p in nucleo.pins})
        self.assertEqual(next(p.label for p in nucleo.pins if p.header == "CN7" and p.position == 21), "PB7")
        self.assertEqual(next(p.label for p in nucleo.pins if p.header == "CN10" and p.position == 17), "PB6")
        self.assertIn("ST Morpho CN7/CN10", nucleo.connector_scope)
        esp32 = lookup("esp32-devkitc-v4-esp-wroom-32e")
        self.assertEqual(next(p.capabilities for p in esp32.pins if p.label == "IO34"), ("digital_input",))
        esp32s3 = lookup("esp32-s3-devkitc-1-v1-1")
        self.assertEqual(next(p.label for p in esp32s3.pins if p.header == "J3" and p.position == 2),
                         "TX/GPIO43")
        nordic = lookup("nordic-nrf52840-dk-pca10056-r3-0-2")
        self.assertEqual(next(p.label for p in nordic.pins if p.header == "P4" and p.position == 10),
                         "SCL/P0.27")
        self.assertEqual(next(p.role for p in nordic.pins if p.header == "P2" and p.position == 1), "analog")
        self.assertEqual(next(p.role for p in nordic.pins if p.header == "P4" and p.position == 8), "reference")
        self.assertIn("auxiliary headers excluded", nordic.connector_scope)

    def test_expanded_exact_board_header_positions(self):
        leonardo = lookup("arduino-leonardo-a000057")
        self.assertEqual(next(p.label for p in leonardo.pins
                              if p.header == "DIGITAL-8-13" and p.position == 5), "D12/A11")
        micro = lookup("arduino-micro-a000053")
        self.assertEqual(next(p.label for p in micro.pins
                              if p.header == "RIGHT" and p.position == 10), "SS/D17")
        nano_ble = lookup("arduino-nano-33-ble-abx00030")
        self.assertEqual(next(p.label for p in nano_ble.pins
                              if p.header == "LEFT" and p.position == 8), "A4/SDA/P0.31")
        self.assertEqual(next(p.label for p in nano_ble.pins
                              if p.header == "RIGHT" and p.position == 15), "D1/TX/P1.03")
        discovery = lookup("st-stm32f407g-disc1-mb997")
        self.assertEqual(next(p.label for p in discovery.pins
                              if p.header == "P1" and p.position == 14), "PA2")
        self.assertEqual(next(p.label for p in discovery.pins
                              if p.header == "P2" and p.position == 39), "PA14")
        esp32c3 = lookup("esp32-c3-devkitm-1")
        self.assertEqual(next(p.label for p in esp32c3.pins
                              if p.header == "J1" and p.position == 14), "5V")
        self.assertEqual(next(p.label for p in esp32c3.pins
                              if p.header == "J3" and p.position == 13), "IO18/USB_D-")
        esp32c6 = lookup("esp32-c6-devkitc-1-v1-2")
        self.assertEqual(next(p.label for p in esp32c6.pins
                              if p.header == "J3" and p.position == 13), "GPIO13/USB_D+")
        nrf5340 = lookup("nordic-nrf5340-dk-pca10095")
        self.assertEqual(next(p.label for p in nrf5340.pins
                              if p.header == "P24" and p.position == 18), "P0.31/LED4")
        self.assertEqual(next(p.label for p in nrf5340.pins
                              if p.header == "P24" and p.position == 20), "GND")

    def test_non_io_and_input_only_pins_do_not_claim_output_capability(self):
        io_capabilities = {"digital_io", "digital_input", "analog_input"}
        for board in catalog():
            for pin in board.pins:
                if pin.role in {"power", "ground", "reset", "reference", "reserved", "debug"}:
                    self.assertTrue(io_capabilities.isdisjoint(pin.capabilities),
                                    f"{board.id} {pin.id} exposes {pin.capabilities}")
                if "digital_input" in pin.capabilities:
                    self.assertNotIn("digital_io", pin.capabilities,
                                     f"{board.id} {pin.id} incorrectly claims output capability")
        for label in ("VP/GPIO36", "VN/GPIO39", "IO34", "IO35"):
            pin = next(p for p in lookup("esp32-devkitc-v4-esp-wroom-32e").pins
                       if p.label == label)
            self.assertEqual(pin.capabilities, ("digital_input",))

    def test_new_templates_state_connector_exclusions(self):
        board_ids = {
            "arduino-leonardo-a000057", "arduino-micro-a000053",
            "arduino-nano-33-ble-abx00030", "st-stm32f407g-disc1-mb997",
            "esp32-c3-devkitm-1", "esp32-c6-devkitc-1-v1-2",
            "nordic-nrf5340-dk-pca10095",
        }
        for board_id in board_ids:
            self.assertIn("excluded", lookup(board_id).connector_scope)

    def test_representative_manufacturers_are_present(self):
        manufacturers = {board.manufacturer for board in catalog()}
        self.assertTrue({"Arduino", "Raspberry Pi", "STMicroelectronics", "Espressif",
                         "Nordic Semiconductor"}.issubset(manufacturers))

    def test_dictionary_adapters_are_deep_independent_snapshots(self):
        first = get_record("arduino-uno-r3-a000066")
        first["pins"][0]["label"] = "changed"
        first["source_urls"].append("changed")
        fresh = get_record("arduino-uno-r3-a000066")
        self.assertEqual(fresh["pins"][0]["label"], "NC")
        self.assertNotIn("changed", fresh["source_urls"])
        self.assertEqual(len(records()), len(catalog()))


if __name__ == "__main__":
    unittest.main()
