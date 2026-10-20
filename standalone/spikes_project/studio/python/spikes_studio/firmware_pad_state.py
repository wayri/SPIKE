# SPDX-License-Identifier: Apache-2.0
"""Pure MCU GPIO-register to generic electrical-pad state decoding.

The register encodings come from the manufacturer references below.  This
module only translates documented digital GPIO configuration; it does not
assign resistance, current, timing, or slew-rate values.

References reviewed 2026-10-19:

* ST RM0090 Rev 22, sections 8.3.3-8.3.5 and 8.4.1-8.4.6:
  https://www.st.com/resource/en/reference_manual/rm0090-stm32f407-advanced-armbased-32bit-mcus-stmicroelectronics.pdf
* Nordic nRF52840 Product Specification v1.8, sections 6.9.2.1 and 6.9.2.10
  (GPIO ``OUT`` and ``PIN_CNF[n]``):
  https://docs-be.nordicsemi.com/bundle/nRF52840_PS_v1.8/raw/resource/enus/nRF52840_PS_v1.8.pdf

``OSPEEDR`` is retained as exact categorical metadata.  It is not converted
to resistance or treated as a Nordic-style drive-strength selection.  The
generic STM32 drive level therefore remains the native pad model's default
profile (``strong``); a characterized profile must interpret the speed field
separately if appropriate.
"""

from __future__ import annotations


class UnsupportedPadConfiguration(ValueError):
    """Raised when documented register state has no admitted pad mapping."""


_PULL = {0: "none", 1: "up", 2: "down"}
_STM_SPEED = {0: "low", 1: "medium", 2: "fast", 3: "high"}

# name, generic mode, low-side level, high-side level.  ``None`` is a
# disconnected side.  Nordic calls S "standard" and H "high drive".
_NRF_DRIVE = {
    0: ("S0S1", "push_pull", "weak", "weak"),
    1: ("H0S1", "push_pull", "strong", "weak"),
    2: ("S0H1", "push_pull", "weak", "strong"),
    3: ("H0H1", "push_pull", "strong", "strong"),
    4: ("D0S1", "open_source", None, "weak"),
    5: ("D0H1", "open_source", None, "strong"),
    6: ("S0D1", "open_drain", "weak", None),
    7: ("H0D1", "open_drain", "strong", None),
}

_NRF_PIN_CNF_MASK = 0x0003_070F


def _u32(value: int, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 0xFFFF_FFFF
    ):
        raise ValueError(f"{name} must be an unsigned 32-bit integer")
    return value


def _pin(value: int, maximum: int, family: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= maximum
    ):
        raise ValueError(f"{family} GPIO pin must be in [0, {maximum}]")
    return value


def decode_stm32(
    mode: int,
    otype: int,
    pupdr: int,
    ospeed: int,
    odr: int,
    pin: int,
) -> dict[str, object]:
    """Decode STM32F407 GPIO port registers for one pin.

    ``mode``, ``otype``, ``pupdr``, ``ospeed`` and ``odr`` are the complete
    GPIOx register values.  Alternate-function and analog modes are rejected:
    the available registers do not identify the peripheral output's present
    electrical state, and analog mode is outside the digital pad contract.
    """

    mode = _u32(mode, "mode")
    otype = _u32(otype, "otype")
    pupdr = _u32(pupdr, "pupdr")
    ospeed = _u32(ospeed, "ospeed")
    odr = _u32(odr, "odr")
    pin = _pin(pin, 15, "STM32F407")
    if otype & 0xFFFF_0000:
        raise ValueError("otype sets reserved bits [31:16]")
    if odr & 0xFFFF_0000:
        raise ValueError("odr sets reserved bits [31:16]")

    shift = pin * 2
    mode_field = (mode >> shift) & 0b11
    type_field = (otype >> pin) & 1
    pull_field = (pupdr >> shift) & 0b11
    speed_field = (ospeed >> shift) & 0b11
    output_latch = (odr >> pin) & 1

    if mode_field == 2:
        raise UnsupportedPadConfiguration(
            "STM32F407 alternate-function mode requires peripheral routing and output state"
        )
    if mode_field == 3:
        raise UnsupportedPadConfiguration(
            "STM32F407 analog mode is outside the digital electrical-pad contract"
        )
    if pull_field == 3:
        raise UnsupportedPadConfiguration("STM32F407 PUPDR value 3 is reserved")

    pull = _PULL[pull_field]
    if mode_field == 0:
        pad_mode = "input"
        output = "released"
    elif type_field == 0:
        pad_mode = "push_pull"
        output = "high" if output_latch else "low"
    else:
        pad_mode = "open_drain"
        output = "released" if output_latch else "low"

    return {
        "input_enabled": True,
        "state": {
            "mode": pad_mode,
            "output": output,
            "drive_level": "strong",
            "pull": pull,
        },
        "family": "STM32F407",
        "pin": pin,
        "moder": mode_field,
        "otype": type_field,
        "pupdr": pull_field,
        "ospeedr": speed_field,
        "output_speed": _STM_SPEED[speed_field],
        "output_latch": output_latch,
        "drive_level_source": "generic_profile_default",
    }


def decode_nrf(pin_cnf: int, out: int, pin: int) -> dict[str, object]:
    """Decode one nRF52840 ``PIN_CNF[n]`` value and the port ``OUT`` value."""

    pin_cnf = _u32(pin_cnf, "pin_cnf")
    out = _u32(out, "out")
    pin = _pin(pin, 31, "nRF52840")
    reserved = pin_cnf & ~_NRF_PIN_CNF_MASK
    if reserved:
        raise UnsupportedPadConfiguration(
            f"nRF52840 PIN_CNF sets reserved bits: 0x{reserved:08x}"
        )

    direction = pin_cnf & 1
    input_disconnected = bool((pin_cnf >> 1) & 1)
    pull_field = (pin_cnf >> 2) & 0b11
    drive_field = (pin_cnf >> 8) & 0b111
    sense_field = (pin_cnf >> 16) & 0b11
    output_latch = (out >> pin) & 1

    if pull_field == 2:
        raise UnsupportedPadConfiguration("nRF52840 PIN_CNF.PULL value 2 is reserved")
    if sense_field == 1:
        raise UnsupportedPadConfiguration("nRF52840 PIN_CNF.SENSE value 1 is reserved")

    pull = {0: "none", 1: "down", 3: "up"}[pull_field]
    drive_name, drive_mode, low_level, high_level = _NRF_DRIVE[drive_field]
    if drive_mode == "open_source":
        # The high side is the only driven side, so its strength remains the
        # applicable profile even while OUT selects the disconnected low side.
        drive_level = high_level
    elif drive_mode == "open_drain":
        drive_level = low_level
    else:
        drive_level = high_level if output_latch else low_level
    assert drive_level is not None

    if not direction:
        pad_mode = "input"
        output = "released"
    elif drive_mode == "push_pull":
        pad_mode = drive_mode
        output = "high" if output_latch else "low"
    elif drive_mode == "open_source":
        pad_mode = drive_mode
        output = "high" if output_latch else "released"
    else:
        pad_mode = drive_mode
        output = "released" if output_latch else "low"

    sense = {0: "disabled", 2: "high", 3: "low"}[sense_field]
    return {
        "input_enabled": not input_disconnected,
        "state": {
            "mode": pad_mode,
            "output": output,
            "drive_level": drive_level,
            "pull": pull,
        },
        "family": "nRF52840",
        "pin": pin,
        "direction": "output" if direction else "input",
        "input_buffer": "disconnected" if input_disconnected else "connected",
        "pull_field": pull_field,
        "drive": drive_field,
        "drive_name": drive_name,
        "sense": sense_field,
        "sense_name": sense,
        "output_latch": output_latch,
    }
