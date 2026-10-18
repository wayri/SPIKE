# SPDX-License-Identifier: Apache-2.0
"""Labeled component and equation-bench value fields for the wx Studio."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

import wx


@dataclass(frozen=True)
class FieldSpec:
    label: str
    unit: str = "1"
    quantity: str = "scalar"
    sequence: bool = False
    integer: bool = False


_SPECS = {
    "r": FieldSpec("Resistance", "ohm", "resistor"),
    "c": FieldSpec("Capacitance", "F", "capacitor"),
    "l": FieldSpec("Inductance", "H", "inductor"),
    "is": FieldSpec("Saturation current", "A", "current_source"),
    "voltage": FieldSpec("Voltage", "V", "voltage_source"),
    "frequency": FieldSpec("Frequency", "Hz"),
    "frequency_hz": FieldSpec("Frequency", "Hz"),
    "delay": FieldSpec("Delay", "s", "time"),
    "period": FieldSpec("Period", "s", "time"),
    "time_s": FieldSpec("Time", "s", "time"),
    "temperature_k": FieldSpec("Temperature", "K"),
    "temperature_c": FieldSpec("Model temperature", "degC"),
    "reference_temperature_c": FieldSpec("Reference temperature", "degC"),
    "series_resistance_ohm": FieldSpec("Series R / ESR / DCR", "ohm", "resistor"),
    "series_inductance_h": FieldSpec("Series L / ESL", "H", "inductor"),
    "parallel_capacitance_f": FieldSpec("Parallel capacitance", "F", "capacitor"),
    "leakage_resistance_ohm": FieldSpec("Leakage R (0 omits)", "ohm", "resistor"),
    "contact_resistance_ohm": FieldSpec("Each force contact R", "ohm", "resistor"),
    "tolerance_percent": FieldSpec("Tolerance", "%"),
    "corner": FieldSpec("Tolerance corner (-1 to +1)"),
    "tc1_per_k": FieldSpec("Linear temperature coefficient", "1/K"),
    "tc2_per_k2": FieldSpec("Quadratic temperature coefficient", "1/K^2"),
    "threshold_voltage_v": FieldSpec("Threshold voltage", "V", "voltage_source"),
    "transconductance_a_per_v2": FieldSpec("Transconductance parameter", "A/V^2"),
    "channel_length_modulation_per_v": FieldSpec("Channel-length modulation", "1/V"),
    "body_effect_sqrt_v": FieldSpec("Body-effect coefficient", "V^0.5"),
    "surface_potential_v": FieldSpec("Surface potential", "V", "voltage_source"),
    "width_over_length": FieldSpec("Width / length ratio"),
    "junction_saturation_current_a": FieldSpec("Junction saturation current", "A", "current_source"),
    "junction_emission_coefficient": FieldSpec("Junction emission coefficient"),
    "cgs_f": FieldSpec("Gate-source capacitance", "F", "capacitor"),
    "cgd_f": FieldSpec("Gate-drain capacitance", "F", "capacitor"),
    "cds_f": FieldSpec("Drain-source capacitance", "F", "capacitor"),
    "cgb_f": FieldSpec("Gate-bulk capacitance", "F", "capacitor"),
    "cbd_f": FieldSpec("Bulk-drain capacitance", "F", "capacitor"),
    "cbs_f": FieldSpec("Bulk-source capacitance", "F", "capacitor"),
    "saturation_current_a": FieldSpec("Core saturation current", "A", "current_source"),
    "forward_beta": FieldSpec("Forward beta"),
    "reverse_beta": FieldSpec("Reverse beta"),
    "emission_coefficient": FieldSpec("Emission coefficient"),
    "cbe_f": FieldSpec("Base-emitter capacitance", "F", "capacitor"),
    "cbc_f": FieldSpec("Base-collector capacitance", "F", "capacitor"),
    "csub_f": FieldSpec("Collector-substrate capacitance", "F", "capacitor"),
    "forward_transit_time_s": FieldSpec("Forward transit time", "s", "time"),
    "reverse_transit_time_s": FieldSpec("Reverse transit time", "s", "time"),
    "resistance_ohm": FieldSpec("Resistance", "ohm", "resistor"),
    "substrate_capacitance_f": FieldSpec("Substrate capacitance", "F", "capacitor"),
    "substrate_leakage_resistance_ohm": FieldSpec("Substrate leakage resistance", "ohm", "resistor"),
    "capacitance_f": FieldSpec("Capacitance", "F", "capacitor"),
    "bits": FieldSpec("Resolution", "bit", integer=True),
    "modulus": FieldSpec("Counter modulus", "count", integer=True),
    "vref": FieldSpec("Reference voltage", "V", "voltage_source"),
    "vdd": FieldSpec("Supply voltage", "V", "voltage_source"),
    "rating": FieldSpec("Rating", "A", "current_source"),
    "capacity_ah": FieldSpec("Capacity", "Ah"),
    "soc_initial": FieldSpec("Initial state of charge"),
    "loss_db": FieldSpec("Attenuation", "dB"),
    "x": FieldSpec("Lookup x coordinates", "1", sequence=True),
    "y": FieldSpec("Lookup y coordinates", "1", sequence=True),
    "current": FieldSpec("Current", "A", "current_source"),
    "optical_w": FieldSpec("Optical power", "W"),
    "base_current": FieldSpec("Base current", "A", "current_source"),
    "vgs": FieldSpec("Gate-source voltage", "V", "voltage_source"),
    "a": FieldSpec("Input A", "V", "voltage_source"),
    "b": FieldSpec("Input B", "V", "voltage_source"),
    "clock": FieldSpec("Clock", "V", "voltage_source"),
    "select": FieldSpec("Select", "V", "voltage_source"),
    "duty": FieldSpec("Duty cycle"),
    "irradiance": FieldSpec("Irradiance", "W/m^2"),
    "speed": FieldSpec("Speed", "rad/s"),
    "head": FieldSpec("Head", "m"),
    "flow": FieldSpec("Flow", "m^3/s"),
    "angle": FieldSpec("Angle", "rad"),
    "force": FieldSpec("Force", "N"),
    "pressure": FieldSpec("Pressure", "Pa"),
}


BENCH_DEFAULTS = {
    "x": 0.1,
    "voltage": 0.1,
    "current": 0.01,
    "temperature_k": 298.15,
    "frequency_hz": 1000.0,
    "time_s": 0.0,
    "optical_w": 0.0,
    "base_current": 0.0,
    "vgs": 0.0,
    "gate": 0.0,
    "a": 0.0,
    "b": 0.0,
    "clock": 0.0,
    "select": 0.0,
    "duty": 0.5,
    "irradiance": 1000.0,
    "speed": 0.0,
    "head": 0.0,
    "flow": 0.0,
    "angle": 0.0,
    "force": 0.0,
    "pressure": 0.0,
}


def field_spec(name: str, primary_unit: str | None = None, value=None) -> FieldSpec:
    if name in _SPECS:
        spec = _SPECS[name]
        if spec.sequence != isinstance(value, list):
            return FieldSpec(spec.label, spec.unit, spec.quantity, isinstance(value, list), spec.integer)
        return spec
    label = name.replace("_", " ").strip().capitalize()
    return FieldSpec(label, primary_unit or "1", sequence=isinstance(value, list))


def format_value(value) -> str:
    if isinstance(value, list):
        return ", ".join(f"{item:.12g}" for item in value)
    return f"{value:.12g}" if type(value) in (int, float) else str(value)


def parse_value(text: str, spec: FieldSpec):
    from python.spikes.netlist import parse_spice_number

    def scalar(token: str):
        value = parse_spice_number(token.strip(), spec.quantity)
        if not math.isfinite(value):
            raise ValueError("Value must be finite")
        if spec.integer:
            if value != int(value):
                raise ValueError(f"{spec.label} must be an integer")
            return int(value)
        return value

    if spec.sequence:
        tokens = [token for token in text.replace(";", ",").split(",") if token.strip()]
        if not tokens:
            raise ValueError(f"{spec.label} requires one or more comma-separated values")
        return [scalar(token) for token in tokens]
    if not text.strip():
        raise ValueError(f"{spec.label} is required")
    return scalar(text)


class ComponentParameterForm(wx.Panel):
    """Dynamic, labeled fields with a legacy string adapter for internal callers."""

    def __init__(self, parent, values=None, *, primary_unit=None, empty_message="No editable values"):
        super().__init__(parent)
        self.primary_unit = primary_unit
        self.empty_message = empty_message
        self.fields = {}
        self._specs = {}
        self._callbacks = []
        self._loading = False
        self._box = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(self._box)
        self.load(values or {}, primary_unit=primary_unit)

    def bind_changed(self, callback):
        self._callbacks.append(callback)

    def _changed(self, event):
        if not self._loading:
            for callback in tuple(self._callbacks):
                callback()
        event.Skip()

    def load(self, values, *, primary_unit=None, draft=None, notify=False):
        if not isinstance(values, dict):
            raise ValueError("Component values must be a mapping")
        self._loading = True
        try:
            self.primary_unit = primary_unit
            self._box.Clear(delete_windows=True)
            self.fields = {}
            self._specs = {}
            if not values:
                self._box.Add(wx.StaticText(self, label=self.empty_message), 0, wx.ALL, 6)
            else:
                grid = wx.FlexGridSizer(cols=3, hgap=8, vgap=7)
                grid.AddGrowableCol(1)
                first = True
                for name, value in values.items():
                    spec = field_spec(name, primary_unit if first else None, value)
                    first = False
                    raw = (draft or {}).get(name, format_value(value))
                    grid.Add(wx.StaticText(self, label=spec.label), 0, wx.ALIGN_CENTER_VERTICAL)
                    control = wx.TextCtrl(self, value=str(raw))
                    control.SetName("Component value " + name)
                    control.SetToolTip(f"{spec.label} [{spec.unit}]. Engineering suffixes such as k, m, u, n and p are accepted.")
                    control.Bind(wx.EVT_TEXT, self._changed)
                    grid.Add(control, 1, wx.EXPAND)
                    grid.Add(wx.StaticText(self, label=spec.unit), 0, wx.ALIGN_CENTER_VERTICAL)
                    self.fields[name] = control
                    self._specs[name] = spec
                self._box.Add(grid, 0, wx.EXPAND | wx.ALL, 4)
            self.Layout()
            parent = self.GetParent()
            if hasattr(parent, "FitInside"):
                parent.FitInside()
        finally:
            self._loading = False
        if notify:
            for callback in tuple(self._callbacks):
                callback()

    def clear(self):
        self.load({}, primary_unit=self.primary_unit)

    def raw_values(self):
        return {name: control.GetValue() for name, control in self.fields.items()}

    def values(self):
        result = {}
        for name, control in self.fields.items():
            try:
                result[name] = parse_value(control.GetValue(), self._specs[name])
            except ValueError as error:
                raise ValueError(f"{self._specs[name].label}: {error}") from error
        return result

    # Transitional adapter for evidence scripts and existing callers. JSON is
    # never rendered: it is decoded immediately into the labeled controls.
    def SetValue(self, value):
        supplied = json.loads(value) if isinstance(value, str) else dict(value)
        if not set(supplied).issubset(self.fields):
            base = {name: 0.0 for name in supplied}
            self.load(base, primary_unit=self.primary_unit, draft={name: format_value(item) for name, item in supplied.items()}, notify=True)
            return
        self._loading = True
        try:
            for name, item in supplied.items():
                self.fields[name].SetValue(format_value(item))
        finally:
            self._loading = False
        for callback in tuple(self._callbacks):
            callback()

    def ChangeValue(self, value):
        supplied = json.loads(value) if isinstance(value, str) else dict(value)
        self.load(supplied, primary_unit=self.primary_unit)

    def GetValue(self):
        return json.dumps(self.values(), separators=(",", ":"))


def format_evaluation(result: dict) -> str:
    lines = []
    for name, item in result.get("outputs", {}).items():
        lines.append(f"{name.replace('_', ' ').title()}: {item['value']:.8g} {item['unit']}")
    if result.get("state"):
        lines.append("State: " + ", ".join(f"{key}={value:.8g}" for key, value in result["state"].items()))
    for alert in result.get("alerts", []):
        lines.append("ALERT: " + alert)
    lines.append("Equation bench only; not circuit-coupled." if result.get("not_circuit_coupled") else "")
    return "\n".join(line for line in lines if line)
