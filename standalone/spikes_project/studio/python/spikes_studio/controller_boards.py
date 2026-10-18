# SPDX-License-Identifier: Apache-2.0
"""Authoritative, data-only controller-board pinout templates.

The catalog describes physical connector positions.  It deliberately provides
no firmware, peripheral, binary, timing, or RF emulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict


EXECUTION_STATUS = "pinout_template_only"
NO_EMULATION = "No binary, peripheral, timing, electrical, or RF emulation."


@dataclass(frozen=True)
class BoardPin:
    id: str
    label: str
    header: str
    position: int
    role: str
    aliases: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class ControllerBoard:
    id: str
    name: str
    manufacturer: str
    family: str
    revision: str
    mcu: str
    source_urls: tuple[str, ...]
    logic_voltage_v: float | None
    pins: tuple[BoardPin, ...]
    connector_scope: str = "all documented external pin headers"
    execution_status: str = EXECUTION_STATUS
    emulation_scope: str = NO_EMULATION


def _traits(label: str) -> tuple[tuple[str, ...], str]:
    upper = label.upper()
    parts = tuple(part.strip() for part in upper.split("/"))
    if upper in {"GND", "AGND", "G"}:
        return (("ground",), "ground")
    if upper in {"NC", "N/C"}:
        return ((), "reserved")
    if any(token in upper for token in ("VCC", "VDD", "VIN", "VBUS", "VSYS", "VBAT", "E5V", "U5V",
                                              "+5V", "+3V3", "5V", "3V", "3V3", "IOREF")):
        return (("power",), "power")
    if (upper in {"RESET", "RST", "NRST", "RUN", "EN", "3V3_EN", "AREF", "ADC_VREF"}
            or upper.startswith(("RST/", "RESET/", "NRST/", "AREF/"))):
        is_reset = upper in {"RESET", "RST", "NRST", "RUN", "EN", "3V3_EN"} or upper.startswith(("RST/", "RESET/", "NRST/"))
        return (("system",), "reset" if is_reset else "reference")
    if upper.startswith("SWD") or upper == "SWCLK":
        return (("debug",), "debug")
    if upper == "BOOT0":
        return (("system",), "reserved")
    caps = []
    if any((part.startswith(("A", "ADC", "AIN")) and any(c.isdigit() for c in part)) for part in parts):
        caps.append("analog_input")
    if any(part.startswith(("D", "GP", "GPIO", "IO", "PA", "PB", "PC", "PD", "PE", "PF", "PG", "PK", "PJ", "PH", "P0.", "P1."))
           for part in parts):
        caps.append("digital_io")
    return (tuple(caps or ("digital_io",)), "analog" if "analog_input" in caps else "gpio")


def _pin_id(header: str, position: int) -> str:
    stem = "".join(character if character.isalnum() else "_" for character in header).strip("_")
    return f"{stem}_{position}"


def _header(header_id: str, labels: tuple[str, ...], aliases: dict[str, tuple[str, ...]] | None = None,
            input_only: frozenset[str] = frozenset()) -> tuple[BoardPin, ...]:
    result = []
    for position, label in enumerate(labels, 1):
        capabilities, role = _traits(label)
        if label in input_only:
            capabilities = ("digital_input",)
        inferred_aliases = tuple(part for part in label.split("/") if part != label)
        result.append(BoardPin(_pin_id(header_id, position), label, header_id, position, role,
                               (aliases or {}).get(label, inferred_aliases), capabilities))
    return tuple(result)


def _numbered(header_id: str, labels_by_position: dict[int, str], aliases: dict[str, tuple[str, ...]] | None = None) -> tuple[BoardPin, ...]:
    result = []
    for position, label in sorted(labels_by_position.items()):
        capabilities, role = _traits(label)
        inferred_aliases = tuple(part for part in label.split("/") if part != label)
        result.append(BoardPin(_pin_id(header_id, position), label, header_id, position, role,
                               (aliases or {}).get(label, inferred_aliases), capabilities))
    return tuple(result)


_ARDUINO_UNO = ControllerBoard(
    "arduino-uno-r3-a000066", "Arduino UNO R3", "Arduino", "UNO", "Rev3 / A000066", "ATmega328P",
    ("https://docs.arduino.cc/hardware/uno-rev3/",
     "https://docs.arduino.cc/resources/pinouts/A000066-full-pinout.pdf"), 5.0,
    _header("POWER", ("NC", "IOREF", "RESET", "+3V3", "+5V", "GND", "GND", "VIN"))
    + _header("ANALOG", ("A0", "A1", "A2", "A3", "A4/SDA", "A5/SCL"))
    + _header("DIGITAL-0-7", tuple(f"D{i}" for i in range(8)))
    + _header("DIGITAL-8-13", ("D8", "D9", "D10/SS", "D11/COPI", "D12/CIPO", "D13/SCK", "GND", "AREF"))
    + _header("I2C", ("SDA", "SCL"))
    + _header("ICSP", ("CIPO", "+5V", "SCK", "COPI", "RESET", "GND")),
)


_ARDUINO_NANO = ControllerBoard(
    "arduino-nano-classic-a000005", "Arduino Nano", "Arduino", "Nano", "Classic / A000005", "ATmega328P",
    ("https://docs.arduino.cc/hardware/nano/",
     "https://docs.arduino.cc/resources/pinouts/A000005-full-pinout.pdf"), 5.0,
    _header("LEFT", ("D1/TX", "D0/RX", "RESET", "GND", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12"))
    + _header("RIGHT", ("D13", "+3V3", "AREF", "A0", "A1", "A2", "A3", "A4/SDA", "A5/SCL", "A6", "A7", "+5V", "RESET", "GND", "VIN"))
    + _header("ICSP", ("CIPO", "+5V", "SCK", "COPI", "RESET", "GND")),
)


_ARDUINO_MEGA = ControllerBoard(
    "arduino-mega-2560-r3-a000067", "Arduino Mega 2560 Rev3", "Arduino", "Mega", "Rev3 / A000067", "ATmega2560",
    ("https://docs.arduino.cc/hardware/mega-2560/",
     "https://docs.arduino.cc/resources/pinouts/A000067-full-pinout.pdf"), 5.0,
    _header("POWER", ("NC", "IOREF", "RESET", "+3V3", "+5V", "GND", "GND", "VIN"))
    + _header("ANALOG", tuple(f"A{i}" for i in range(16)))
    + _header("DIGITAL-0-7", tuple(f"D{i}" for i in range(8)))
    + _header("DIGITAL-8-13", tuple(f"D{i}" for i in range(8, 14)) + ("GND", "AREF"))
    + _header("DIGITAL-14-21", ("D14/TX3", "D15/RX3", "D16/TX2", "D17/RX2", "D18/TX1", "D19/RX1", "D20/SDA", "D21/SCL"))
    + _header("DIGITAL-22-53", tuple(f"D{i}" for i in range(22, 54)))
    + _header("I2C", ("SDA", "SCL"))
    + _header("ICSP", ("CIPO", "+5V", "SCK", "COPI", "RESET", "GND")),
)


_ARDUINO_LEONARDO = ControllerBoard(
    "arduino-leonardo-a000057", "Arduino Leonardo", "Arduino", "Leonardo",
    "A000057", "ATmega32U4",
    ("https://docs.arduino.cc/hardware/leonardo/",
     "https://docs.arduino.cc/resources/pinouts/A000057-full-pinout.pdf"), 5.0,
    _header("POWER", ("NC", "IOREF", "RESET", "+3V3", "+5V", "GND", "GND", "VIN"))
    + _header("ANALOG", ("A0/D14", "A1/D15", "A2/D16", "A3/D17", "A4/D18", "A5/D19"))
    + _header("DIGITAL-0-7", ("D0/RX", "D1/TX", "D2/SDA", "D3/SCL", "D4/A6", "D5", "D6/A7", "D7"))
    + _header("DIGITAL-8-13", ("D8/A8", "D9/A9", "D10/A10", "D11", "D12/A11", "D13", "GND", "AREF"))
    + _header("I2C", ("SDA/D2", "SCL/D3"))
    + _header("ICSP", ("CIPO", "+5V", "SCK", "COPI", "RESET", "GND")),
    connector_scope="POWER, ANALOG, DIGITAL, I2C, and ICSP headers; USB and onboard test pads excluded",
)


_ARDUINO_MICRO = ControllerBoard(
    "arduino-micro-a000053", "Arduino Micro", "Arduino", "Micro", "A000053", "ATmega32U4",
    ("https://docs.arduino.cc/hardware/micro/",
     "https://docs.arduino.cc/resources/pinouts/A000053-full-pinout.pdf"), 5.0,
    _header("LEFT", ("D13", "+3V3", "AREF", "A0/D18", "A1/D19", "A2/D20", "A3/D21",
                     "A4/D22", "A5/D23", "D4/A6", "D6/A7", "D8/A8", "D9/A9", "D10/A10",
                     "D12/A11", "D11", "D5"))
    + _header("RIGHT", ("VIN", "GND", "RESET", "+5V", "NC", "NC", "CIPO/D14", "SCK/D15",
                      "COPI/D16", "SS/D17", "D1/TX", "D0/RX", "RESET", "GND", "D2/SDA",
                      "D3/SCL", "D7"))
    + _header("ICSP", ("CIPO", "+5V", "SCK", "COPI", "RESET", "GND")),
    connector_scope="two 17-position side headers and ICSP header; USB contacts and test pads excluded",
)


_ARDUINO_NANO_33_BLE = ControllerBoard(
    "arduino-nano-33-ble-abx00030", "Arduino Nano 33 BLE", "Arduino", "Nano 33 BLE",
    "ABX00030", "nRF52840 (NINA-B306)",
    ("https://docs.arduino.cc/hardware/nano-33-ble/",
     "https://docs.arduino.cc/resources/pinouts/ABX00030-full-pinout.pdf",
     "https://docs.arduino.cc/resources/datasheets/ABX00030-datasheet.pdf"),
    3.3,
    _header("LEFT", ("D13/P0.13", "+3V3", "AREF", "A0/P0.04", "A1/P0.05", "A2/P0.30",
                     "A3/P0.29", "A4/SDA/P0.31", "A5/SCL/P0.02", "A6/P0.28", "A7/P0.03",
                     "+5V", "RESET", "GND", "VIN"))
    + _header("RIGHT", ("D12/CIPO/P1.08", "D11/COPI/P1.01", "D10/P1.02", "D9/P0.27",
                      "D8/P0.21", "D7/P0.23", "D6/P1.14", "D5/P1.13", "D4/P1.15",
                      "D3/P1.12", "D2/P1.11", "GND", "RESET", "D0/RX/P1.10",
                      "D1/TX/P1.03")),
    connector_scope="two 15-position castellated side headers; USB contacts, SWD pads, and onboard IMU/LED signals excluded",
)


_PICO_LABELS = {
    1:"GP0", 2:"GP1", 3:"GND", 4:"GP2", 5:"GP3", 6:"GP4", 7:"GP5", 8:"GND", 9:"GP6", 10:"GP7",
    11:"GP8", 12:"GP9", 13:"GND", 14:"GP10", 15:"GP11", 16:"GP12", 17:"GP13", 18:"GND", 19:"GP14", 20:"GP15",
    21:"GP16", 22:"GP17", 23:"GND", 24:"GP18", 25:"GP19", 26:"GP20", 27:"GP21", 28:"GND", 29:"GP22", 30:"RUN",
    31:"GP26/ADC0", 32:"GP27/ADC1", 33:"AGND", 34:"GP28/ADC2", 35:"ADC_VREF", 36:"3V3(OUT)", 37:"3V3_EN", 38:"GND", 39:"VSYS", 40:"VBUS",
}


def _pico(board_id: str, name: str, revision: str, source_url: str) -> ControllerBoard:
    return ControllerBoard(board_id, name, "Raspberry Pi", "Pico", revision, "RP2040",
        ("https://www.raspberrypi.com/documentation/microcontrollers/raspberry-pi-pico.html",
         source_url), 3.3, _numbered("J1/J2", _PICO_LABELS) + _header("SWD", ("SWCLK", "GND", "SWDIO")))


_PICO = _pico("raspberry-pi-pico-rp2040", "Raspberry Pi Pico", "Pico 1 / RP2040",
                   "https://datasheets.raspberrypi.com/pico/Pico-R3-A4-Pinout.pdf")
_PICO_W = _pico("raspberry-pi-pico-w-rp2040", "Raspberry Pi Pico W", "Pico W / RP2040",
                     "https://datasheets.raspberrypi.com/picow/PicoW-A4-Pinout.pdf")


_NUCLEO_ARDUINO = (
    _header("CN6-POWER", ("NC", "IOREF", "RESET", "+3V3", "+5V", "GND", "GND", "VIN"))
    + _header("CN8-ANALOG", ("A0/PA0", "A1/PA1", "A2/PA4", "A3/PB0", "A4/PC1", "A5/PC0"))
    + _header("CN9-DIGITAL", ("D0/PA3", "D1/PA2", "D2/PA10", "D3/PB3", "D4/PB5", "D5/PB4", "D6/PB10", "D7/PA8"))
    + _header("CN5-DIGITAL", ("D8/PA9", "D9/PC7", "D10/PB6", "D11/PA7", "D12/PA6", "D13/PA5", "GND", "AREF", "D14/PB9", "D15/PB8"))
)


_NUCLEO_F401RE = ControllerBoard(
    "st-nucleo-f401re-mb1136", "NUCLEO-F401RE", "STMicroelectronics", "Nucleo-64", "MB1136 (UM1724 Rev 17)", "STM32F401RET6",
    ("https://www.st.com/en/evaluation-tools/nucleo-f401re.html", "https://www.st.com/resource/en/user_manual/um1724-.pdf"), 3.3,
    _NUCLEO_ARDUINO
    + _numbered("CN7", {
        **dict(zip(range(1, 38, 2), ("PC10", "PC12", "VDD", "BOOT0", "NC", "NC", "PA13", "PA14", "PA15",
                                      "GND", "PB7", "PC13", "PC14", "PC15", "PH0", "PH1", "VBAT", "PC2", "PC3"))),
        **dict(zip(range(2, 39, 2), ("PC11", "PD2", "E5V", "GND", "NC", "IOREF", "RESET", "+3V3", "+5V",
                                      "GND", "GND", "VIN", "NC", "PA0", "PA1", "PA4", "PB0", "PC1", "PC0"))),
    })
    + _numbered("CN10", {
        **dict(zip(range(1, 38, 2), ("PC9", "PB8", "PB9", "AVDD", "GND", "PA5", "PA6", "PA7", "PB6",
                                      "PC7", "PA9", "PA8", "PB10", "PB4", "PB5", "PB3", "PA10", "PA2", "PA3"))),
        **dict(zip(range(2, 39, 2), ("PC8", "PC6", "PC5", "U5V", "NC", "PA12", "PA11", "PB12", "NC",
                                      "GND", "PB2", "PB1", "PB15", "PB14", "PB13", "AGND", "PC4", "NC", "NC"))),
    }),
    connector_scope="Arduino CN5/CN6/CN8/CN9 and ST Morpho CN7/CN10; onboard debugger and jumper headers excluded",
)
_NUCLEO_F446RE = ControllerBoard(
    "st-nucleo-f446re-mb1136", "NUCLEO-F446RE", "STMicroelectronics", "Nucleo-64", "MB1136 (UM1724 Rev 17)", "STM32F446RET6",
    ("https://www.st.com/en/evaluation-tools/nucleo-f446re.html", "https://www.st.com/resource/en/user_manual/um1724-.pdf"), 3.3,
    _NUCLEO_ARDUINO, connector_scope="Arduino shield headers CN5, CN6, CN8, and CN9 only; Morpho headers excluded",
)


_STM32F407G_DISC1 = ControllerBoard(
    "st-stm32f407g-disc1-mb997", "STM32F407G-DISC1", "STMicroelectronics", "STM32 Discovery",
    "MB997 / UM1472 Rev 9", "STM32F407VGT6",
    ("https://www.st.com/en/evaluation-tools/stm32f4discovery.html",
     "https://www.st.com/resource/en/user_manual/um1472-stm32f4-discovery-stmicroelectronics.pdf"),
    3.0,
    _numbered("P1", {
        1: "GND", 2: "GND", 3: "VDD", 4: "VDD", 5: "NRST", 6: "PB3", 7: "PC1", 8: "PC0",
        9: "PC3", 10: "PC2", 11: "PA1", 12: "PA0", 13: "PA3", 14: "PA2", 15: "PA5", 16: "PA4",
        17: "PA7", 18: "PA6", 19: "PC5", 20: "PC4", 21: "PB1", 22: "VDD", 23: "GND", 24: "PB2",
        25: "PE7", 26: "PE8", 27: "PE9", 28: "PE10", 29: "PE11", 30: "PE12", 31: "PE13",
        32: "PE14", 33: "PE15", 34: "PB10", 35: "PB11", 36: "PB12", 37: "PB13", 38: "PB14",
        39: "PB15", 40: "PD8", 41: "PD9", 42: "PD10", 43: "PD11", 44: "PD12", 45: "PD13",
        46: "PD14", 47: "PD15", 48: "PC6", 49: "GND", 50: "GND",
    })
    + _numbered("P2", {
        1: "GND", 2: "GND", 3: "5V", 4: "5V", 5: "3V", 6: "3V", 7: "PH0", 8: "PH1",
        9: "PC14", 10: "PC15", 11: "PE6", 12: "PC13", 13: "PE4", 14: "PE5", 15: "PE2",
        16: "PE3", 17: "PE0", 18: "PE1", 19: "PB8", 20: "PB9", 21: "BOOT0", 22: "VDD",
        23: "PB6", 24: "PB7", 25: "PB4", 26: "PB5", 27: "PD7", 28: "PB3", 29: "PD5",
        30: "PD6", 31: "PD3", 32: "PD4", 33: "PD1", 34: "PD2", 35: "PC12", 36: "PD0",
        37: "PC10", 38: "PC11", 39: "PA14", 40: "PA15", 41: "PA10", 42: "PA13", 43: "PA8",
        44: "PA9", 45: "PC8", 46: "PC9", 47: "PC6", 48: "PC7", 49: "GND", 50: "GND",
    }),
    connector_scope="target expansion headers P1 and P2; ST-LINK CN2/CN3, power jumper, USB, and onboard peripherals excluded",
)


_ESP32_DEVKITC = ControllerBoard(
    "esp32-devkitc-v4-esp-wroom-32e", "ESP32-DevKitC V4 (ESP32-WROOM-32E)", "Espressif",
    "ESP32-DevKitC", "V4 / ESP32-WROOM-32E", "ESP32-D0WD-V3",
    ("https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html",),
    3.3,
    _header("J2", ("3V3", "EN", "VP/GPIO36", "VN/GPIO39", "IO34", "IO35", "IO32", "IO33", "IO25",
                   "IO26", "IO27", "IO14", "IO12", "GND", "IO13", "D2/GPIO9", "D3/GPIO10", "CMD/GPIO11", "5V"),
            input_only=frozenset({"VP/GPIO36", "VN/GPIO39", "IO34", "IO35"}))
    + _header("J3", ("GND", "IO23", "IO22", "TX/GPIO1", "RX/GPIO3", "IO21", "GND", "IO19", "IO18",
                     "IO5", "IO17", "IO16", "IO4", "IO0", "IO2", "IO15", "D1/GPIO8", "D0/GPIO7", "CLK/GPIO6")),
)


_ESP32_S3_DEVKITC = ControllerBoard(
    "esp32-s3-devkitc-1-v1-1", "ESP32-S3-DevKitC-1", "Espressif", "ESP32-S3-DevKitC-1",
    "v1.1 / ESP32-S3-WROOM-1, -1U, or -2", "ESP32-S3",
    ("https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html",),
    3.3,
    _header("J1", ("3V3", "3V3", "RST/EN", "GPIO4", "GPIO5", "GPIO6", "GPIO7", "GPIO15", "GPIO16",
                   "GPIO17", "GPIO18", "GPIO8", "GPIO3", "GPIO46", "GPIO9", "GPIO10", "GPIO11", "GPIO12",
                   "GPIO13", "GPIO14", "5V", "GND"))
    + _header("J3", ("GND", "TX/GPIO43", "RX/GPIO44", "GPIO1", "GPIO2", "GPIO42", "GPIO41", "GPIO40",
                     "GPIO39", "GPIO38", "GPIO37", "GPIO36", "GPIO35", "GPIO0", "GPIO45", "GPIO48", "GPIO47",
                     "GPIO21", "GPIO20", "GPIO19", "GND", "GND")),
)


_ESP32_C3_DEVKITM = ControllerBoard(
    "esp32-c3-devkitm-1", "ESP32-C3-DevKitM-1", "Espressif", "ESP32-C3-DevKitM-1",
    "ESP32-C3-MINI-1 module", "ESP32-C3",
    ("https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c3/"
     "esp32-c3-devkitm-1/user_guide.html",),
    3.3,
    _header("J1", ("GND", "3V3", "3V3", "IO2/ADC1_CH2", "IO3/ADC1_CH3", "GND", "RST",
                   "GND", "IO0/ADC1_CH0", "IO1/ADC1_CH1", "IO10", "GND", "5V", "5V", "GND"))
    + _header("J3", ("GND", "TX/GPIO21", "RX/GPIO20", "GND", "IO9", "IO8", "GND", "IO7",
                     "IO6", "IO5/ADC2_CH0", "IO4/ADC1_CH4", "GND", "IO18/USB_D-",
                     "IO19/USB_D+", "GND")),
    connector_scope="all pins on J1 and J3; Micro-USB connector, buttons, and onboard RGB LED excluded",
)


_ESP32_C6_DEVKITC = ControllerBoard(
    "esp32-c6-devkitc-1-v1-2", "ESP32-C6-DevKitC-1", "Espressif", "ESP32-C6-DevKitC-1",
    "v1.2", "ESP32-C6",
    ("https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/"
     "esp32-c6-devkitc-1/user_guide.html",),
    3.3,
    _header("J1", ("3V3", "RST", "GPIO4/ADC1_CH4", "GPIO5/ADC1_CH5", "GPIO6/ADC1_CH6",
                   "GPIO7", "GPIO0/ADC1_CH0", "GPIO1/ADC1_CH1", "GPIO8", "GPIO10", "GPIO11",
                   "GPIO2/ADC1_CH2", "GPIO3/ADC1_CH3", "5V", "GND", "NC"))
    + _header("J3", ("GND", "TX/GPIO16", "RX/GPIO17", "GPIO15", "GPIO23", "GPIO22", "GPIO21",
                     "GPIO20", "GPIO19", "GPIO18", "GPIO9", "GND", "GPIO13/USB_D+",
                     "GPIO12/USB_D-", "GND", "NC")),
    connector_scope="all pins on J1 and J3; USB connectors, J5, buttons, and onboard RGB LED excluded",
)


_NRF52840_DK = ControllerBoard(
    "nordic-nrf52840-dk-pca10056-r3-0-2", "nRF52840 DK", "Nordic Semiconductor", "nRF52 DK",
    "PCA10056 schematic revision 3.0.2 (2023-02-07)", "nRF52840-QIAA",
    ("https://docs.nordicsemi.com/r/bundle/ug_nrf52840_dk/page/ug/dk/connector_if.html",
     "https://devzone.nordicsemi.com/cfs-file/__key/communityserver-discussions-components-files/4/"
     "nRF52840DK_5F00_3_5F00_0_5F00_2_5F00_pca10056_5F00_schematic.pdf"),
    3.3,
    _header("P2", ("A0/P0.03/AIN1", "A1/P0.04/AIN2", "A2/P0.28/AIN4",
                   "A3/P0.29/AIN5", "A4/P0.30/AIN6", "A5/P0.31/AIN7"))
    + _header("P3", ("D0/P0.02/AIN0", "D1/P1.01", "D2/P1.02", "D3/P1.04",
                     "D4/P1.05", "D5/P1.06", "D6/P1.07", "D7/P1.08"))
    + _header("P4", ("D8/P1.03", "D9/P1.10", "D10/P1.11", "D11/P1.12", "D12/P1.13",
                     "D13/P1.14", "GND", "AREF/P1.15", "SDA/P0.26", "SCL/P0.27")),
    connector_scope="mounted Arduino signal headers P2, P3, and P4 only; power and auxiliary headers excluded",
)


_NRF5340_DK = ControllerBoard(
    "nordic-nrf5340-dk-pca10095", "nRF5340 DK", "Nordic Semiconductor", "nRF53 DK",
    "PCA10095 / user guide v2.0.0", "nRF5340-QKAA",
    ("https://docs.nordicsemi.com/r/bundle/ug_nrf5340_dk/",
     "https://docs-be.nordicsemi.com/bundle/nRF5340_DK/raw/resource/enus/"
     "nRF5340_DK_User_Guide_v2.0.0.pdf"),
    3.0,
    _header("P24", ("P0.11/TRACEDATA0", "P0.12/TRACECLK", "P0.13/QSPI_IO0",
                    "P0.14/QSPI_IO1", "P0.15/QSPI_IO2", "P0.16/QSPI_IO3",
                    "P0.17/QSPI_CLK", "P0.18/QSPI_CS", "P0.19/nRF53_RTS",
                    "P0.20/nRF53_TXD", "P0.21/nRF53_CTS", "P0.22/nRF53_RXD",
                    "P0.23/BUTTON1", "P0.24/BUTTON2", "P0.28/LED1", "P0.29/LED2",
                    "P0.30/LED3", "P0.31/LED4", "GND", "GND")),
    connector_scope="GPIO expansion header P24 only; P1-P6, P19-P23, debug, NFC, power, and auxiliary connectors excluded",
)


_CATALOG = (_ARDUINO_UNO, _ARDUINO_MEGA, _ARDUINO_NANO, _ARDUINO_LEONARDO,
            _ARDUINO_MICRO, _ARDUINO_NANO_33_BLE, _PICO, _PICO_W, _NUCLEO_F401RE, _NUCLEO_F446RE,
            _STM32F407G_DISC1, _ESP32_DEVKITC, _ESP32_S3_DEVKITC, _ESP32_C3_DEVKITM,
            _ESP32_C6_DEVKITC, _NRF52840_DK, _NRF5340_DK)
_BY_ID = {board.id: board for board in _CATALOG}
if len(_BY_ID) != len(_CATALOG):
    raise RuntimeError("controller-board IDs must be unique")


def catalog() -> tuple[ControllerBoard, ...]:
    """Return the immutable catalog in stable display order."""
    return _CATALOG


def lookup(board_id: str) -> ControllerBoard:
    """Return a board by stable ID; raise KeyError for unknown IDs."""
    return _BY_ID[board_id]


def records() -> list[dict[str, object]]:
    """Return independent, JSON-compatible catalog snapshots."""
    return [_record(board) for board in _CATALOG]


def get_record(board_id: str) -> dict[str, object]:
    """Return an independent JSON-compatible snapshot for one board."""
    return _record(lookup(board_id))


def _record(board: ControllerBoard) -> dict[str, object]:
    record = asdict(board)
    record["source_urls"] = list(board.source_urls)
    record["pins"] = [
        {**asdict(pin), "aliases": list(pin.aliases), "capabilities": list(pin.capabilities)}
        for pin in board.pins
    ]
    return record

