# SPDX-License-Identifier: Apache-2.0
"""Bounded, theme-aware glyphs for symbol library and palette rows.

The icons are drawn with wx primitives so SPIKES does not acquire a packaged
icon or font dependency.  Part names are normalized to a fixed family table;
arbitrary library records therefore cannot grow an image cache.
"""
from __future__ import annotations

import re
from typing import Mapping


CANONICAL_KEYS = (
    "generic", "resistor", "capacitor", "inductor", "diode", "led",
    "mosfet", "bjt", "opamp", "comparator", "ic", "ground_reference",
    "ground_signal", "ground_chassis", "ground_earth", "power_flag",
    "battery", "voltage_source", "current_source", "transformer", "fuse",
    "thermal", "motor", "operating_point", "transient", "ac", "parameter",
    "measurement", "library_folder", "note", "rectangle", "ellipse",
    "logic_and", "logic_nand", "logic_or", "logic_nor", "logic_xor",
    "logic_xnor", "logic_not", "logic_buffer", "logic_schmitt",
    "sensor_optical", "filter_lowpass", "filter_highpass", "filter_bandpass",
    "filter_notch", "source_wave", "analog_gain", "analog_converter",
    "control", "switch", "energy_solar", "energy_turbine", "energy_converter",
    "attenuator", "transmission_line",
)

_ALIASES = {
    "logic_ic": "ic", "instrumentation_amplifier": "opamp", "bipolar_transistor": "bjt",
    "r": "resistor", "resistance": "resistor", "c": "capacitor",
    "capacitance": "capacitor", "l": "inductor", "inductance": "inductor",
    "rectifier": "diode", "zener": "diode", "schottky": "diode",
    "light_emitting_diode": "led", "nmos": "mosfet", "pmos": "mosfet",
    "nmos_enhancement": "mosfet", "pmos_enhancement": "mosfet",
    "nmos_depletion": "mosfet", "pmos_depletion": "mosfet",
    "jfet": "mosfet", "igbt": "mosfet", "npn": "bjt", "pnp": "bjt",
    "transistor": "bjt", "operational_amplifier": "opamp",
    "operational_amp": "opamp", "op_amp": "opamp", "integrated_circuit": "ic",
    "chip": "ic", "reference_ground": "ground_reference", "ground": "ground_reference",
    "gnd": "ground_reference", "signal_ground": "ground_signal",
    "chassis_ground": "ground_chassis", "earth_ground": "ground_earth",
    "power": "power_flag", "supply": "power_flag", "cell": "battery",
    "source": "voltage_source", "vsource": "voltage_source",
    "current_source": "current_source", "isource": "current_source",
    "dc_source": "voltage_source", "sin_source": "source_wave", "sine_source": "source_wave",
    "pulse_source": "source_wave", "pwl_source": "source_wave",
    "ptc_resettable_fuse": "fuse", "resettable_fuse": "fuse",
    "ntc_thermistor": "thermal", "ptc_thermistor": "thermal",
    "thermistor": "thermal", "temperature": "thermal", "machine": "motor",
    "dc_operating_point": "operating_point", "operatingpoint": "operating_point",
    "tran": "transient", "transient_analysis": "transient", "ac_analysis": "ac",
    "parameter_sweep": "parameter", "sweep": "parameter", "measure": "measurement",
    "folder": "library_folder", "library": "library_folder", "annotation": "note",
    "op": "operating_point", "param": "parameter", "meas": "measurement", "rect": "rectangle",
    "box": "rectangle", "circle": "ellipse", "component": "generic",
    "generic_component": "generic", "genericcomponent": "generic",
    # Established explicit-terminal model builders use their electrical family.
    'nmos4': 'mosfet', 'npn4': 'bjt', 'resistor3': 'resistor',
    'feedthrough_capacitor3': 'capacitor', 'kelvin_shunt4': 'resistor',
    # Catalog families share bounded glyphs by recognizable circuit role.
    "and": "logic_and", "nand": "logic_nand", "or": "logic_or", "nor": "logic_nor",
    "xor": "logic_xor", "xnor": "logic_xnor", "not": "logic_not", "buffer": "logic_buffer",
    "schmitt": "logic_schmitt", "photodiode": "sensor_optical", "optocoupler": "sensor_optical",
    "rc_lowpass": "filter_lowpass", "rlc_lowpass": "filter_lowpass",
    "rc_highpass": "filter_highpass", "rlc_highpass": "filter_highpass",
    "bandpass": "filter_bandpass", "notch": "filter_notch",
    "oscillator": "source_wave", "generator": "source_wave",
    "gain": "analog_gain", "transconductance": "analog_gain",
    "isolation_amplifier": "analog_gain", "adc": "analog_converter", "dac": "analog_converter",
    "integrator": "control", "differentiator": "control", "limiter": "control",
    "envelope_detector": "control", "precision_rectifier": "control", "lookup_table": "control",
    "sample_hold": "control", "pwm_controller": "control", "soft_start": "control",
    "uvlo": "control", "voltage_supervisor": "control", "current_limiter": "control",
    "analog_switch": "switch", "load_switch": "switch", "mux2": "switch",
    "solar_cell": "energy_solar", "wind_turbine": "energy_turbine",
    "hydro_turbine": "energy_turbine", "battery_charger_cccv": "energy_converter",
    "buck_averaged": "energy_converter", "boost_averaged": "energy_converter",
    "buck_boost_averaged": "energy_converter", "linear_regulator": "energy_converter",
    "voltage_reference": "voltage_source",
    "battery_alkaline": "battery", "battery_leadacid": "battery", "battery_lifepo4": "battery",
    "battery_liion": "battery", "battery_nicd": "battery", "battery_nimh": "battery",
    "bldc_averaged": "motor", "stepper_torque": "motor", "fan": "energy_turbine",
    "pump": "motor", "solenoid": "inductor", "ntc": "thermal", "ptc": "thermal",
    "counter": "ic", "d_flipflop": "ic", "level_translator": "ic", "timer_astable": "control",
    "crystal_equivalent": "source_wave", "diac": "diode", "thyristor": "diode", "triac": "diode",
    "gan_channel": "mosfet", "igbt_channel": "mosfet", "sic_channel": "mosfet", "mesfet": "mosfet",
    "cable": "transmission_line", "line_lumped_section": "transmission_line", "termination": "resistor",
}


def _normalized(value: object) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", text)).strip("_")


def key_for(value: object) -> str:
    """Return a stable canonical glyph key; unknown inputs use ``generic``."""
    key = _normalized(value)
    if key in CANONICAL_KEYS:
        return key
    if key in _ALIASES:
        return _ALIASES[key]
    # Recipe families often append polarity, construction, or package detail.
    for token, canonical in (
        ("mosfet", "mosfet"), ("nmos", "mosfet"), ("pmos", "mosfet"),
        ("opamp", "opamp"), ("amplifier", "opamp"), ("comparator", "comparator"),
        ("resistor", "resistor"), ("capacitor", "capacitor"), ("inductor", "inductor"),
        ("diode", "diode"), ("transistor", "bjt"), ("therm", "thermal"),
        ("fuse", "fuse"), ("transformer", "transformer"), ("motor", "motor"),
        ("sensor", "measurement"), ("lowpass", "filter_lowpass"),
        ("highpass", "filter_highpass"), ("bandpass", "filter_bandpass"),
        ("notch", "filter_notch"), ("oscillator", "source_wave"),
        ("turbine", "energy_turbine"), ("solar", "energy_solar"), ("battery", "battery"),
    ):
        if token in key:
            return canonical
    return "generic"


def _colour(palette: Mapping[str, str], name: str, fallback: str) -> str:
    return str(palette.get(name, fallback))


def bitmap(key: object, palette: Mapping[str, str], size: int = 20):
    """Draw one square wx bitmap for a canonical key or alias."""
    import wx

    size = max(12, min(int(size), 64))
    k = key_for(key)
    bg = wx.Colour(_colour(palette, "field", _colour(palette, "panel", "#ffffff")))
    fg = wx.Colour(_colour(palette, "fg", "#27313d"))
    accent = wx.Colour(_colour(palette, "accent", "#2863a2"))
    danger = wx.Colour(_colour(palette, "danger", "#b44040"))
    muted = wx.Colour(_colour(palette, "muted", "#606b79"))
    bmp = wx.Bitmap(size, size, 32)
    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(bg)); dc.Clear()
    dc.SetPen(wx.Pen(fg, max(1, size // 12))); dc.SetBrush(wx.TRANSPARENT_BRUSH)
    s = size / 20.0
    p = lambda x, y: wx.Point(round(x * s), round(y * s))
    line = lambda a, b, c, d: dc.DrawLine(round(a*s), round(b*s), round(c*s), round(d*s))

    if k == "resistor":
        dc.SetPen(wx.Pen(danger, max(1, size//10))); dc.DrawLines([p(1,10),p(4,10),p(5,6),p(7,14),p(9,6),p(11,14),p(13,6),p(15,10),p(19,10)])
    elif k == "capacitor":
        dc.SetPen(wx.Pen(accent, max(1, size//9))); line(1,10,7,10); line(7,4,7,16); line(12,4,12,16); line(12,10,19,10)
    elif k == "inductor":
        dc.SetPen(wx.Pen(wx.Colour("#5aa469"), max(1, size//10))); line(1,10,4,10)
        for x in (6,9,12,15): dc.DrawArc(p(x-2,10),p(x+2,10),p(x,10))
        line(17,10,19,10)
    elif k in ("diode", "led"):
        line(1,10,6,10); line(14,10,19,10); dc.DrawPolygon([p(6,4),p(6,16),p(14,10)]); line(14,4,14,16)
        if k == "led": line(12,5,17,1); line(15,7,19,3)
    elif k in ("mosfet", "bjt"):
        line(2,10,7,10); line(7,4,7,16); line(10,5,10,15); line(10,7,18,3); line(10,13,18,17)
        if k == "bjt": dc.DrawPolygon([p(14,13),p(18,17),p(13,17)])
    elif k in ("opamp", "comparator"):
        dc.DrawPolygon([p(3,3),p(3,17),p(17,10)]); line(0,6,3,6); line(0,14,3,14); line(17,10,20,10)
        dc.DrawText("+", round(4*s), round(2*s)); dc.DrawText("-", round(4*s), round(10*s))
        if k == "comparator": line(15,6,18,6)
    elif k == "ic":
        dc.DrawRoundedRectangle(round(4*s),round(3*s),round(12*s),round(14*s),round(2*s)); dc.DrawText("IC",round(6*s),round(5*s))
        for y in (6,10,14): line(1,y,4,y); line(16,y,19,y)
    elif k.startswith("ground_"):
        line(10,1,10,10)
        if k == "ground_signal": dc.DrawPolygon([p(4,10),p(16,10),p(10,18)])
        elif k == "ground_chassis": line(4,10,16,10); line(6,10,3,16); line(11,10,8,16); line(16,10,13,16)
        elif k == "ground_earth": line(4,10,16,10); dc.DrawArc(p(5,14),p(15,14),p(10,10)); dc.DrawArc(p(7,17),p(13,17),p(10,13))
        else: line(4,10,16,10); line(6,13,14,13); line(8,16,12,16)
    elif k == "power_flag":
        line(10,18,10,3); dc.SetBrush(wx.Brush(accent)); dc.DrawPolygon([p(10,3),p(18,7),p(10,11)])
    elif k == "battery":
        line(1,10,6,10); line(6,4,6,16); line(10,7,10,13); line(10,10,19,10)
    elif k in ("voltage_source", "current_source"):
        line(0,10,3,10); dc.DrawCircle(round(10*s),round(10*s),round(7*s)); line(17,10,20,10)
        if k == "current_source": line(10,15,10,5); dc.DrawPolygon([p(7,8),p(10,4),p(13,8)])
        else: dc.DrawText("+",round(7*s),round(2*s)); dc.DrawText("-",round(8*s),round(10*s))
    elif k == "transformer":
        for x in (5,8,12,15): dc.DrawArc(p(x-2,4),p(x+2,4),p(x,8))
        line(10,2,10,18)
        for x in (5,8,12,15): dc.DrawArc(p(x+2,16),p(x-2,16),p(x,12))
    elif k == "fuse":
        line(1,10,4,10); dc.DrawRoundedRectangle(round(4*s),round(7*s),round(12*s),round(6*s),round(2*s)); line(16,10,19,10)
    elif k == "thermal":
        dc.SetPen(wx.Pen(danger,max(1,size//10))); dc.DrawCircle(round(10*s),round(15*s),round(3*s)); dc.DrawRoundedRectangle(round(8*s),round(2*s),round(4*s),round(14*s),round(2*s)); line(10,6,10,15)
    elif k == "motor":
        dc.DrawCircle(round(10*s),round(10*s),round(7*s)); dc.DrawText("M",round(5*s),round(4*s)); line(0,10,3,10); line(17,10,20,10)
    elif k.startswith("logic_"):
        inverted = k in ("logic_nand", "logic_nor", "logic_xnor", "logic_not")
        if k in ("logic_not", "logic_buffer", "logic_schmitt"): line(0,10,4,10)
        else: line(0,6,4,6); line(0,14,4,14)
        line(16,10,16 if inverted else 20,10)
        if k in ("logic_and", "logic_nand"):
            line(4,3,9,3); line(4,17,9,17); line(4,3,4,17)
            dc.DrawEllipticArc(round(2*s),round(3*s),round(14*s),round(14*s),270,90)
        elif k in ("logic_or", "logic_nor", "logic_xor", "logic_xnor"):
            dc.DrawSpline([p(4,3),p(10,4),p(16,10),p(10,16),p(4,17)])
            dc.DrawSpline([p(4,3),p(7,10),p(4,17)])
            if k in ("logic_xor", "logic_xnor"): dc.DrawSpline([p(2,3),p(5,10),p(2,17)])
        else:
            dc.DrawPolygon([p(4,3),p(4,17),p(15,10)])
            if k == "logic_schmitt": dc.DrawLines([p(7,7),p(10,7),p(10,13),p(13,13)])
        if inverted:
            dc.DrawCircle(round(18*s),round(10*s),max(1,round(2*s))); line(20,10,20,10)
    elif k == "sensor_optical":
        line(1,10,6,10); line(14,10,19,10); dc.DrawPolygon([p(6,4),p(6,16),p(14,10)]); line(14,4,14,16)
        line(4,1,8,5); line(8,0,11,3)
    elif k.startswith("filter_"):
        line(1,10,4,10); line(16,10,19,10); dc.DrawRoundedRectangle(round(4*s),round(3*s),round(12*s),round(14*s),round(2*s))
        if k == "filter_lowpass": dc.DrawLines([p(6,6),p(9,6),p(11,13),p(14,13)])
        elif k == "filter_highpass": dc.DrawLines([p(6,13),p(9,13),p(11,6),p(14,6)])
        elif k == "filter_bandpass": dc.DrawLines([p(6,13),p(8,13),p(9,6),p(11,6),p(12,13),p(14,13)])
        else: dc.DrawLines([p(6,6),p(8,6),p(9,13),p(11,13),p(12,6),p(14,6)])
    elif k == "attenuator":
        line(1,10,4,10); line(16,10,19,10); dc.DrawRectangle(round(4*s),round(4*s),round(12*s),round(12*s))
        dc.DrawLines([p(6,7),p(9,13),p(12,7),p(14,7)])
    elif k == "transmission_line":
        line(1,7,19,7); line(1,13,19,13)
        line(3,5,3,15); line(17,5,17,15)
    elif k == "source_wave":
        line(0,10,3,10); dc.DrawCircle(round(10*s),round(10*s),round(7*s)); line(17,10,20,10)
        dc.DrawSpline([p(5,10),p(7,6),p(10,10),p(13,14),p(15,10)])
    elif k == "analog_gain":
        line(0,10,4,10); dc.DrawPolygon([p(4,3),p(4,17),p(16,10)]); line(16,10,20,10); dc.DrawText("G",round(6*s),round(5*s))
    elif k == "analog_converter":
        line(0,10,4,10); line(16,10,20,10); dc.DrawRectangle(round(4*s),round(3*s),round(12*s),round(14*s))
        dc.DrawLines([p(6,13),p(8,13),p(8,10),p(10,10),p(10,7),p(14,7)])
    elif k == "control":
        line(0,10,4,10); line(16,10,20,10); dc.DrawRoundedRectangle(round(4*s),round(3*s),round(12*s),round(14*s),round(2*s))
        dc.DrawLines([p(6,13),p(8,13),p(8,7),p(11,7),p(11,11),p(14,11)])
    elif k == "switch":
        line(1,10,6,10); line(14,10,19,10); dc.DrawCircle(round(6*s),round(10*s),max(1,round(s))); dc.DrawCircle(round(14*s),round(10*s),max(1,round(s))); line(6,10,13,5)
    elif k == "energy_solar":
        dc.SetBrush(wx.Brush(accent)); dc.DrawCircle(round(4*s),round(4*s),round(2*s)); dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawPolygon([p(5,8),p(17,8),p(15,17),p(3,17)]); line(9,8,8,17); line(13,8,12,17); line(4,12,16,12)
    elif k == "energy_turbine":
        dc.DrawCircle(round(10*s),round(10*s),round(2*s))
        dc.DrawPolygon([p(10,8),p(8,1),p(13,6)]); dc.DrawPolygon([p(12,10),p(19,8),p(14,13)]); dc.DrawPolygon([p(9,12),p(7,19),p(5,13)])
    elif k == "energy_converter":
        line(0,10,3,10); line(17,10,20,10); dc.DrawRoundedRectangle(round(3*s),round(3*s),round(14*s),round(14*s),round(2*s))
        line(6,7,14,7); dc.DrawPolygon([p(11,4),p(15,7),p(11,10)]); line(14,13,6,13); dc.DrawPolygon([p(9,10),p(5,13),p(9,16)])
    elif k in ("operating_point", "transient", "ac", "parameter", "measurement"):
        line(2,17,2,3); line(2,17,19,17)
        if k == "operating_point": dc.SetBrush(wx.Brush(accent)); dc.DrawCircle(round(11*s),round(9*s),round(3*s))
        elif k == "transient": dc.DrawLines([p(3,14),p(7,14),p(7,5),p(12,5),p(12,12),p(18,12)])
        elif k == "ac": dc.DrawSpline([p(3,10),p(6,5),p(10,10),p(14,15),p(18,10)])
        elif k == "parameter": dc.DrawLines([p(3,14),p(8,7),p(13,11),p(18,4)])
        else: dc.DrawLines([p(3,13),p(7,9),p(10,12),p(17,5)]); dc.DrawCircle(round(10*s),round(12*s),round(2*s))
    elif k == "library_folder":
        dc.SetBrush(wx.Brush(accent)); dc.SetPen(wx.Pen(accent)); dc.DrawPolygon([p(2,6),p(8,6),p(10,8),p(18,8),p(17,17),p(2,17)])
    elif k == "note":
        dc.DrawRectangle(round(4*s),round(2*s),round(12*s),round(16*s)); line(7,7,14,7); line(7,11,14,11); line(7,15,11,15)
    elif k == "rectangle": dc.DrawRectangle(round(3*s),round(4*s),round(14*s),round(12*s))
    elif k == "ellipse": dc.DrawEllipse(round(3*s),round(4*s),round(14*s),round(12*s))
    else:
        dc.SetPen(wx.Pen(muted,max(1,size//12))); dc.DrawRectangle(round(5*s),round(5*s),round(10*s),round(10*s)); line(1,10,5,10); line(15,10,19,10)

    dc.SelectObject(wx.NullBitmap)
    # A mask keeps row backgrounds native while preserving deterministic RGB
    # clearing on ports where drawing directly into fully transparent pixels fails.
    try: bmp.SetMask(wx.Mask(bmp, bg))
    except (AttributeError, TypeError): pass
    return bmp


class SymbolImages:
    """One fixed image list shared by a symbol tree or report-style list."""

    def __init__(self, window, palette: Mapping[str, str], size: int = 20):
        import wx
        self.size = max(12, min(int(size), 64))
        self.keys = CANONICAL_KEYS
        self._indices = {key: index for index, key in enumerate(self.keys)}
        self.image_list = wx.ImageList(self.size, self.size, True, len(self.keys))
        for key in self.keys:
            self.image_list.Add(bitmap(key, palette, self.size))
        if window is not None:
            self.install(window)

    @staticmethod
    def key_for(value: object) -> str:
        return key_for(value)

    def index(self, family_or_category: object) -> int:
        return self._indices[key_for(family_or_category)]

    def install(self, window) -> None:
        """Assign the list using the ownership-taking wx control API."""
        import wx
        if isinstance(window, wx.TreeCtrl):
            window.AssignImageList(self.image_list)
        else:
            window.AssignImageList(self.image_list, wx.IMAGE_LIST_SMALL)
