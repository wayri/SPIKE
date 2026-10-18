# SPDX-License-Identifier: Apache-2.0
"""Labeled, source-preserving editor for imported SPICE model library entries.

The form edits text tokens only.  It neither interprets compact-model physics
nor establishes that a model is executable by a native SPIKE backend.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

import wx

from .model_import import ModelImportError, _PARAMETER_RE, _split_fields, parse_model_statement
from .themes import apply_window


_META = {
    "IS": ("Saturation current", "A", "Electrical"),
    "BF": ("Forward current gain", "", "Electrical"),
    "BR": ("Reverse current gain", "", "Electrical"),
    "VTO": ("Threshold voltage", "V", "Electrical"),
    "VT0": ("Threshold voltage", "V", "Electrical"),
    "KP": ("Transconductance parameter", "A/V^2", "Electrical"),
    "RD": ("Drain/series resistance", "ohm", "Electrical"),
    "RS": ("Source/series resistance", "ohm", "Electrical"),
    "RB": ("Base resistance", "ohm", "Electrical"),
    "RC": ("Collector resistance", "ohm", "Electrical"),
    "RE": ("Emitter resistance", "ohm", "Electrical"),
    "RON": ("On resistance", "ohm", "Electrical"),
    "ROFF": ("Off resistance", "ohm", "Electrical"),
    "CJO": ("Zero-bias junction capacitance", "F", "Charge & parasitics"),
    "CJ0": ("Zero-bias junction capacitance", "F", "Charge & parasitics"),
    "CJE": ("Base-emitter depletion capacitance", "F", "Charge & parasitics"),
    "CJC": ("Base-collector depletion capacitance", "F", "Charge & parasitics"),
    "CGSO": ("Gate-source overlap capacitance", "F/m", "Charge & parasitics"),
    "CGDO": ("Gate-drain overlap capacitance", "F/m", "Charge & parasitics"),
    "QG": ("Gate charge", "C", "Charge & parasitics"),
    "TT": ("Transit time", "s", "Charge & parasitics"),
    "TF": ("Forward transit time", "s", "Charge & parasitics"),
    "TR": ("Reverse transit time", "s", "Charge & parasitics"),
    "TNOM": ("Nominal model temperature", "degC", "Thermal"),
    "TEMP": ("Model temperature", "degC", "Thermal"),
    "XTI": ("Saturation-current temperature exponent", "", "Thermal"),
    "EG": ("Activation energy", "eV", "Thermal"),
    "RTH": ("Thermal resistance", "K/W", "Thermal"),
    "CTH": ("Thermal capacitance", "J/K", "Thermal"),
    "GAIN": ("Open-loop gain", "V/V", "Electrical"),
    "AOL": ("Open-loop gain", "V/V", "Electrical"),
    "GBW": ("Gain-bandwidth product", "Hz", "Electrical"),
    "ROUT": ("Output resistance", "ohm", "Electrical"),
    "RIN": ("Input resistance", "ohm", "Electrical"),
    "SLEW": ("Slew rate", "V/s", "Electrical"),
    "SR": ("Slew rate", "V/s", "Electrical"),
    "VOFF": ("Input offset voltage", "V", "Electrical"),
    "VOS": ("Input offset voltage", "V", "Electrical"),
    "IBIAS": ("Input bias current", "A", "Electrical"),
    "IOS": ("Input offset current", "A", "Electrical"),
}
_CATEGORIES = ("Electrical", "Charge & parasitics", "Thermal", "Other")
_SUBCKT_RE = re.compile(r"(?im)^[ \t]*\.subckt\b")
_END_RE = re.compile(r"(?im)^[ \t]*\.ends\b")


@dataclass(frozen=True)
class ParameterField:
    name: str
    value: str
    label: str
    unit: str
    category: str


def parameter_field(name: str, value: str) -> ParameterField:
    key = name.upper()
    metadata = _META.get(key)
    if metadata is None:
        # Common wide-bandgap vendor-card suffixes retain their full identity;
        # these labels describe syntax only and do not imply a device model.
        suffixes = (
            (("CISS", "COSS", "CRSS", "CGD", "CGS", "CDS"), "Capacitance", "F", "Charge & parasitics"),
            (("QG", "QGD", "QGS", "QRR"), "Charge", "C", "Charge & parasitics"),
            (("RTH", "RTHJC", "RTHJA"), "Thermal resistance", "K/W", "Thermal"),
            (("CTH", "CTHJC", "CTHJA"), "Thermal capacitance", "J/K", "Thermal"),
            (("RDSON", "RDS", "RG", "RGATE"), "Resistance", "ohm", "Electrical"),
        )
        metadata = next(((f"{title} ({key})", unit, category)
                         for endings, title, unit, category in suffixes
                         if any(key.endswith(ending) for ending in endings)), None)
    label, unit, category = metadata or (key.replace("_", " ").title(), "", "Other")
    return ParameterField(key, value, label, unit, category)


def _safe_token(value: str, description: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{description} must be text")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{description} cannot contain line breaks or control characters")
    return value.strip()


def _subckt_header(source: str) -> tuple[str, str, str, list[tuple[str, str]]]:
    """Return name, prefix before PARAMS, untouched suffix/body, parameters."""
    lines = source.splitlines(keepends=True)
    header = next((index for index, line in enumerate(lines)
                   if line.strip() and not line.lstrip().startswith("*")), -1)
    if header < 0 or not re.match(r"^[ \t]*\.subckt\b", lines[header], re.I):
        raise ValueError("Expected comments followed by a .SUBCKT declaration")
    count = header + 1
    while count < len(lines) and re.match(r"^[ \t]*\+", lines[count]):
        count += 1
    leading = "".join(lines[:header])
    header_source = "".join(lines[header:count])
    logical = re.sub(r"\r?\n[ \t]*\+[ \t]*", " ", header_source).strip()
    match = re.match(r"(?is)^\.subckt\s+([A-Za-z_][\w.$+-]*)\s+(.*)$", logical)
    if not match:
        raise ValueError("Malformed .SUBCKT header")
    name, tail = match.group(1), match.group(2)
    marker = re.search(r"(?i)(?:^|\s)params\s*:\s*", tail)
    if marker is None:
        return name, leading + logical, "".join(lines[count:]), []
    prefix = leading + ".SUBCKT " + name + " " + tail[:marker.start()].rstrip()
    raw_fields = _split_fields(tail[marker.end():])
    params: list[tuple[str, str]] = []
    for token in raw_fields:
        if "=" not in token:
            raise ValueError("SUBCKT PARAMS entries must use NAME=VALUE; source is read-only")
        key, value = (part.strip() for part in token.split("=", 1))
        key = key.upper()
        if _PARAMETER_RE.fullmatch(key) is None or not value:
            raise ValueError("Malformed SUBCKT PARAMS entry; source is read-only")
        params.append((key, value))
    if len({key for key, _ in params}) != len(params):
        raise ValueError("Duplicate SUBCKT PARAMS entries; source is read-only")
    return name, prefix, "".join(lines[count:]), params


class ModelLibraryDocument:
    """Editable token view which returns the original source until modified."""

    def __init__(self, source: str):
        if (not isinstance(source, str) or not source.strip() or "\x00" in source
                or len(source.encode("utf-8")) > 1024 * 1024):
            raise ValueError("Model source must be non-empty text")
        self.original = source
        first = re.search(r"(?im)^[ \t]*\.(model|subckt)\b", source)
        self.kind = "model" if first and first.group(1).lower() == "model" else "subckt"
        self.read_only_reason = ""
        self._changed = False
        self._added: list[tuple[str, str]] = []
        if self.kind == "model":
            parsed = parse_model_statement(source)
            self.name = parsed["name"]
            self.model_type = parsed["model_type"]
            self._prefix = ""
            self._suffix = ""
            lines = source.splitlines(keepends=True)
            self._model_line_indexes = {
                index for index, line in enumerate(lines)
                if re.match(r"^[ \t]*(?:\.model\b|\+)", line, re.I)
            }
            first_model = next(index for index in sorted(self._model_line_indexes)
                               if re.match(r"^[ \t]*\.model\b", lines[index], re.I))
            self._model_lines = lines
            self._model_indent = re.match(r"^[ \t]*", lines[first_model]).group(0)
            ending = re.search(r"(?:\r\n|\n|\r)$", lines[first_model])
            self._model_ending = ending.group(0) if ending else ""
            self._model_first = first_model
            values = [(item["name"], item["value_text"]) for item in parsed["parameters"]]
        else:
            if not _SUBCKT_RE.search(source) or not _END_RE.search(source):
                raise ValueError("Expected one complete .MODEL or .SUBCKT source block")
            try:
                self.name, self._prefix, self._suffix, values = _subckt_header(source)
            except (ValueError, ModelImportError) as exc:
                self.name = "SUBCKT"
                self.model_type = "SUBCKT"
                self._prefix, self._suffix, values = "", source, []
                self.read_only_reason = str(exc)
            else:
                self.model_type = "SUBCKT"
        self._values = dict(values)
        self._order = [name for name, _ in values]

    @property
    def fields(self) -> tuple[ParameterField, ...]:
        return tuple(parameter_field(name, self._values[name]) for name in self._order)

    def set_value(self, name: str, value: str) -> None:
        key = _safe_token(name, "Parameter name").upper()
        raw = _safe_token(value, "Parameter value")
        if self.read_only_reason:
            raise ValueError(self.read_only_reason)
        if key not in self._values or not raw:
            raise ValueError("Parameter and non-empty value are required")
        if self._values[key] != raw:
            self._values[key] = raw
            self._changed = True

    def add_parameter(self, name: str, value: str = "true") -> None:
        key = _safe_token(name, "Parameter name").upper()
        raw = _safe_token(value, "Parameter value")
        if self.read_only_reason:
            raise ValueError(self.read_only_reason)
        if _PARAMETER_RE.fullmatch(key) is None or not raw:
            raise ValueError("Enter a valid parameter name and non-empty SPICE value")
        if key in self._values:
            raise ValueError("That parameter already exists")
        self._values[key] = raw
        self._order.append(key)
        self._added.append((key, raw))
        self._changed = True

    def source_text(self) -> str:
        if not self._changed:
            return self.original
        tokens = [name if self._values[name].lower() == "true" else f"{name}={self._values[name]}"
                  for name in self._order]
        if self.kind == "model":
            result = f".MODEL {self.name} {self.model_type}"
            if tokens:
                result += " (" + " ".join(tokens) + ")"
            parse_model_statement(result)
            # Replace only MODEL/continuation records.  Standalone vendor,
            # licensing and provenance comments plus blank lines remain exact.
            records: list[str] = []
            for index, line in enumerate(self._model_lines):
                if index == self._model_first:
                    records.append(self._model_indent + result + self._model_ending)
                elif index not in self._model_line_indexes:
                    records.append(line)
            return "".join(records)
        result = self._prefix.rstrip()
        if tokens:
            result += " PARAMS: " + " ".join(tokens)
        result += "\n" + self._suffix
        # Reparse the edited header before returning it; body bytes are retained.
        _subckt_header(result)
        return result


class ModelLibraryEditor(wx.Dialog):
    """Dialog for a single imported .MODEL statement or .SUBCKT block."""

    def __init__(self, owner, source):
        super().__init__(owner, title="SPICE model library editor", size=(820, 700),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetName("SPICE model library editor")
        self._palette = getattr(owner, "palette", None)
        self.document = ModelLibraryDocument(source)
        self.controls: dict[str, wx.TextCtrl] = {}
        self.pages = {}
        self.grids = {}
        outer = wx.BoxSizer(wx.VERTICAL)
        summary = wx.StaticText(self, label=f"{self.document.name}  ·  {self.document.model_type}")
        outer.Add(summary, 0, wx.EXPAND | wx.ALL, 10)
        self.tabs = wx.Notebook(self)
        self.tabs.SetName("SPICE parameter categories and source preview")
        outer.Add(self.tabs, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        for category in _CATEGORIES:
            page = wx.ScrolledWindow(self.tabs)
            page.SetName(category + " model parameters")
            page.SetScrollRate(0, 10)
            grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
            grid.AddGrowableCol(1)
            self.pages[category], self.grids[category] = page, grid
            for field in (item for item in self.document.fields if item.category == category):
                self._render_field(field)
            page.SetSizer(grid)
            page.FitInside()
            self.tabs.AddPage(page, category)
        preview = wx.Panel(self.tabs)
        preview_box = wx.BoxSizer(wx.VERTICAL)
        self.preview = wx.TextCtrl(preview, value=source, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.preview.SetName("Read-only SPICE source preview")
        preview_box.Add(self.preview, 1, wx.EXPAND)
        preview.SetSizer(preview_box)
        self.tabs.AddPage(preview, "Source preview")

        add_row = wx.BoxSizer(wx.HORIZONTAL)
        self.new_name = wx.TextCtrl(self, size=(150, -1))
        self.new_name.SetName("New SPICE parameter name")
        self.new_value = wx.TextCtrl(self, value="true")
        self.new_value.SetName("New SPICE parameter value or expression")
        add = wx.Button(self, label="Add named parameter")
        add.SetName("Add named SPICE parameter")
        add.Bind(wx.EVT_BUTTON, self._add)
        add_row.Add(wx.StaticText(self, label="Name"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        add_row.Add(self.new_name, 0, wx.RIGHT, 8)
        add_row.Add(wx.StaticText(self, label="Value / expression"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        add_row.Add(self.new_value, 1, wx.RIGHT, 8)
        add_row.Add(add)
        outer.Add(add_row, 0, wx.EXPAND | wx.ALL, 10)
        status = self.document.read_only_reason or (
            "Text editing does not validate native executability; validate the selected backend separately."
        )
        self.status = wx.StaticText(self, label=status)
        self.status.SetName("SPICE model editor status")
        self.status.Wrap(780)
        outer.Add(self.status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        actions = wx.BoxSizer(wx.HORIZONTAL)
        buttons = wx.StdDialogButtonSizer()
        export = wx.Button(self, label="Export .lib...")
        self.export_button=export
        export.SetName("Export SPICE library")
        export.Bind(wx.EVT_BUTTON, self._export)
        actions.Add(export,0,wx.RIGHT,10)
        actions.AddStretchSpacer()
        ok = wx.Button(self, wx.ID_OK)
        ok.SetName("Apply SPICE model edits")
        ok.Bind(wx.EVT_BUTTON, self._accept)
        buttons.AddButton(ok)
        buttons.AddButton(wx.Button(self, wx.ID_CANCEL))
        buttons.Realize()
        actions.Add(buttons,0)
        outer.Add(actions, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(outer)
        self.SetMinSize((620, 520))
        if self.document.read_only_reason:
            add.Disable()
            ok.SetToolTip("Source is preserved but its header cannot be edited safely.")
        if self._palette is not None:
            apply_window(self, self._palette)

    def _render_field(self, field):
        page, grid = self.pages[field.category], self.grids[field.category]
        title = field.label + (f" [{field.unit}]" if field.unit else "")
        label = wx.StaticText(page, label=title)
        label.SetToolTip("SPICE parameter " + field.name)
        control = wx.TextCtrl(page, value=field.value)
        control.SetName(f"SPICE parameter {field.name}: {title}")
        control.SetToolTip("Expression text is preserved; no units or defaults are inferred.")
        self.controls[field.name] = control
        grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(control, 1, wx.EXPAND)

    def _apply_controls(self):
        for name, control in self.controls.items():
            self.document.set_value(name, control.GetValue())
        self.preview.SetValue(self.document.source_text())

    def _add(self, _event):
        try:
            self._apply_controls()
            raw_name = self.new_name.GetValue()
            self.document.add_parameter(raw_name, self.new_value.GetValue())
            name = raw_name.strip().upper()
            field = next(field for field in self.document.fields if field.name == name)
            self._render_field(field)
            page = self.pages[field.category]
            page.FitInside()
            page.Layout()
            if self._palette is not None:
                apply_window(page, self._palette)
            self.tabs.SetSelection(next(index for index in range(self.tabs.GetPageCount())
                                        if self.tabs.GetPage(index) is page))
            self.preview.SetValue(self.document.source_text())
            self.new_name.SetValue("")
            self.status.SetLabel("Parameter added to the categorized form.")
        except ValueError as exc:
            wx.MessageBox(str(exc), "SPICE model editor", wx.OK | wx.ICON_ERROR, self)

    def _export(self, _event):
        try:
            value = self.source_text()
        except ValueError as exc:
            wx.MessageBox(str(exc), "SPICE model editor", wx.OK | wx.ICON_ERROR, self)
            return
        with wx.FileDialog(self, "Export SPICE library", defaultFile=f"{self.document.name}.lib",
                           wildcard="SPICE libraries (*.lib)|*.lib|All files (*.*)|*.*",
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                with open(dialog.GetPath(), "w", encoding="utf-8", newline="") as stream:
                    stream.write(value)

    def _accept(self, _event):
        try:
            self._apply_controls()
        except ValueError as exc:
            wx.MessageBox(str(exc), "SPICE model editor", wx.OK | wx.ICON_ERROR, self)
            return
        self.EndModal(wx.ID_OK)

    def source_text(self) -> str:
        self._apply_controls()
        return self.document.source_text()
