# SPDX-License-Identifier: Apache-2.0
"""Native editor for inert owned electrical-pad settings."""
from __future__ import annotations

from copy import deepcopy
import wx
import wx.grid

from .firmware_pad_settings import (
    BOOL_PROFILE_FIELDS, GENERIC_WARNING, PROFILE_FIELDS, default_settings,
    gpio_pins, validate_settings,
)


_FIELD_GROUPS = (
    ("Drive", (
        ("high_strong_resistance_ohm", "High strong resistance", "ohm"),
        ("high_weak_resistance_ohm", "High weak resistance", "ohm"),
        ("low_strong_resistance_ohm", "Low strong resistance", "ohm"),
        ("low_weak_resistance_ohm", "Low weak resistance", "ohm"),
        ("off_resistance_ohm", "Off resistance", "ohm"),
    )),
    ("Pulls", (
        ("pull_up_resistance_ohm", "Pull-up resistance", "ohm"),
        ("pull_down_resistance_ohm", "Pull-down resistance", "ohm"),
    )),
    ("Parasitics", (
        ("package_resistance_ohm", "Package resistance", "ohm"),
        ("package_inductance_h", "Package inductance", "H"),
        ("capacitance_to_vss_f", "Capacitance to VSS", "F"),
        ("capacitance_to_vdd_f", "Capacitance to VDD", "F"),
    )),
    ("Receiver", (
        ("vil_ratio", "VIL / supply", "ratio"),
        ("vih_ratio", "VIH / supply", "ratio"),
    )),
    ("Clamps", (
        ("clamp_saturation_current_a", "Saturation current", "A"),
        ("clamp_emission_coefficient", "Emission coefficient", "ratio"),
        ("clamp_temperature_k", "Temperature", "K"),
    )),
)


def _text(value):
    return format(value, ".12g")


class FirmwarePadPropertiesDialog(wx.Dialog):
    """Edit enabled pins, circuit nets, generic profiles and state sources."""

    def __init__(self, owner, board, settings=None, net_names=()):
        super().__init__(owner, title="Firmware electrical-pin properties",
                         size=(1120, 780),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.board = deepcopy(board)
        self.pin_rows = list(gpio_pins(self.board))
        if not self.pin_rows:
            self.Destroy()
            raise ValueError("This board has no unambiguous admitted MCU GPIO pins")
        initial = default_settings(board) if settings is None else settings
        self.draft = validate_settings(initial, board)
        self.result = None
        self.current_row = 0
        self._loading = False
        self._net_names = tuple(sorted({str(name) for name in net_names if str(name).strip()}))
        self._field_drafts = {
            pin["id"]: self._field_values(self.draft["pins"][pin["id"]])
            for pin, _port, _index in self.pin_rows
        }
        self._build()
        self._load_fields(0)
        if hasattr(owner, "palette"):
            from .themes import apply_window
            apply_window(self, owner.palette)

    @staticmethod
    def _field_values(value):
        state = value["static_state"]
        fields = {name: _text(value["profile"][name])
                  for name in PROFILE_FIELDS if name not in BOOL_PROFILE_FIELDS}
        fields.update({name: value["profile"][name] for name in BOOL_PROFILE_FIELDS})
        fields.update({"vil_ratio": _text(value["vil_ratio"]),
                       "vih_ratio": _text(value["vih_ratio"]),
                       "output_source": value["output_source"],
                       "pull_source": value["pull_source"],
                       "mode": state["mode"], "output": state["output"],
                       "drive_level": state["drive_level"], "pull": state["pull"]})
        return fields

    def _build(self):
        outer = wx.BoxSizer(wx.VERTICAL)
        warning = wx.StaticText(self, label=GENERIC_WARNING)
        warning.Wrap(1060)
        outer.Add(warning, 0, wx.EXPAND | wx.ALL, 8)
        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        splitter.SetMinimumPaneSize(330)
        self._build_pin_grid(splitter)
        self._build_profile_panel(splitter)
        splitter.SplitVertically(self.grid, self.profile_panel, 585)
        splitter.SetSashGravity(.53)
        outer.Add(splitter, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        self.error = wx.StaticText(self, label="")
        outer.Add(self.error, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        actions = wx.StdDialogButtonSizer()
        self.apply_button = wx.Button(self, wx.ID_OK, "Apply")
        self.cancel_button = wx.Button(self, wx.ID_CANCEL, "Cancel")
        actions.AddButton(self.apply_button); actions.AddButton(self.cancel_button); actions.Realize()
        outer.Add(actions, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(outer); self.SetMinSize((860, 620))
        self.apply_button.Bind(wx.EVT_BUTTON, self.accept)
        self.grid.Bind(wx.grid.EVT_GRID_SELECT_CELL, self._selected)

    def _build_pin_grid(self, parent):
        self.grid = wx.grid.Grid(parent)
        self.grid.CreateGrid(len(self.pin_rows), 6)
        self.grid.SetRowLabelSize(0)
        columns = (("Use", 48), ("Board pin", 185), ("MCU GPIO", 78),
                   ("Signal node", 105), ("VDD node", 88), ("VSS node", 75))
        for col, (label, width) in enumerate(columns):
            self.grid.SetColLabelValue(col, label); self.grid.SetColSize(col, width)
        for row, (pin, port, index) in enumerate(self.pin_rows):
            value = self.draft["pins"][pin["id"]]
            cells = ("1" if value["enabled"] else "",
                     f"{pin['header']}.{pin['position']}  {pin['label']}",
                     f"P{port}.{index}", value["signal_node"],
                     value["vdd_node"], value["vss_node"])
            for col, cell in enumerate(cells): self.grid.SetCellValue(row, col, cell)
            self.grid.SetCellRenderer(row, 0, wx.grid.GridCellBoolRenderer())
            self.grid.SetCellEditor(row, 0, wx.grid.GridCellBoolEditor())
            self.grid.SetReadOnly(row, 1); self.grid.SetReadOnly(row, 2)
            for col in (3, 4, 5):
                self.grid.SetCellEditor(row, col,
                    wx.grid.GridCellChoiceEditor(list(self._net_names), True))
        self.grid.SetToolTip("Only pins with an unambiguous board-label to MCU-GPIO mapping are listed.")

    def _build_profile_panel(self, parent):
        panel = wx.ScrolledWindow(parent)
        panel.SetScrollRate(10, 10)
        self.profile_panel = panel
        outer = wx.BoxSizer(wx.VERTICAL); panel.SetSizer(outer)
        self.selected_label = wx.StaticText(panel, label="")
        outer.Add(self.selected_label, 0, wx.EXPAND | wx.ALL, 7)
        sources = wx.StaticBoxSizer(wx.VERTICAL, panel, "Pad-state source")
        source_grid = wx.FlexGridSizer(cols=2, hgap=7, vgap=6); source_grid.AddGrowableCol(1, 1)
        self.output_source = wx.Choice(panel, choices=["firmware", "static"])
        self.pull_source = wx.Choice(panel, choices=["firmware", "static"])
        self.static_mode = wx.Choice(panel, choices=["input", "push_pull", "open_drain", "open_source"])
        self.static_output = wx.Choice(panel, choices=["released", "low", "high"])
        self.static_drive = wx.Choice(panel, choices=["strong", "weak"])
        self.static_pull = wx.Choice(panel, choices=["none", "up", "down"])
        for label, control in (("Output drive", self.output_source), ("Pulls", self.pull_source),
                               ("Static mode", self.static_mode), ("Static output", self.static_output),
                               ("Static drive level", self.static_drive), ("Static pull", self.static_pull)):
            source_grid.Add(wx.StaticText(panel, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            source_grid.Add(control, 1, wx.EXPAND)
        sources.Add(source_grid, 0, wx.EXPAND | wx.ALL, 6)
        note = wx.StaticText(panel, label="Firmware uses decoded GPIO state. Static is an explicit circuit-only override; it does not alter or emulate registers.")
        note.Wrap(450); sources.Add(note, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        outer.Add(sources, 0, wx.EXPAND | wx.ALL, 5)
        self.fields = {}
        for title, descriptions in _FIELD_GROUPS:
            box = wx.StaticBoxSizer(wx.VERTICAL, panel, title)
            form = wx.FlexGridSizer(cols=3, hgap=6, vgap=5); form.AddGrowableCol(1, 1)
            for name, label, unit in descriptions:
                control = wx.TextCtrl(panel)
                self.fields[name] = control
                form.Add(wx.StaticText(panel, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
                form.Add(control, 1, wx.EXPAND)
                form.Add(wx.StaticText(panel, label=unit), 0, wx.ALIGN_CENTER_VERTICAL)
            if title == "Clamps":
                self.fields["enable_clamp_to_vdd"] = wx.CheckBox(panel, label="Enable clamp to VDD")
                self.fields["enable_clamp_to_vss"] = wx.CheckBox(panel, label="Enable clamp to VSS")
                form.Add(self.fields["enable_clamp_to_vdd"], 0, wx.EXPAND); form.Add((1, 1)); form.Add((1, 1))
                form.Add(self.fields["enable_clamp_to_vss"], 0, wx.EXPAND); form.Add((1, 1)); form.Add((1, 1))
            box.Add(form, 0, wx.EXPAND | wx.ALL, 6)
            outer.Add(box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        for choice in (self.output_source, self.pull_source):
            choice.Bind(wx.EVT_CHOICE, self._source_changed)

    @staticmethod
    def _set_choice(control, value):
        index = control.FindString(value)
        if index == wx.NOT_FOUND: raise ValueError("Unknown saved pad-state choice: " + value)
        control.SetSelection(index)

    def _save_fields(self, row=None):
        if self._loading: return
        row = self.current_row if row is None else row
        pin_id = self.pin_rows[row][0]["id"]
        value = {name: (control.GetValue() if name in BOOL_PROFILE_FIELDS else control.GetValue().strip())
                 for name, control in self.fields.items()}
        value.update({"output_source": self.output_source.GetStringSelection(),
                      "pull_source": self.pull_source.GetStringSelection(),
                      "mode": self.static_mode.GetStringSelection(),
                      "output": self.static_output.GetStringSelection(),
                      "drive_level": self.static_drive.GetStringSelection(),
                      "pull": self.static_pull.GetStringSelection()})
        self._field_drafts[pin_id] = value

    def _load_fields(self, row):
        self._loading = True
        try:
            self.current_row = row
            pin, port, index = self.pin_rows[row]
            self.selected_label.SetLabel(f"{pin['header']}.{pin['position']}  {pin['label']}  -  P{port}.{index}")
            value = self._field_drafts[pin["id"]]
            for name, control in self.fields.items():
                if name in BOOL_PROFILE_FIELDS: control.SetValue(value[name])
                else: control.SetValue(value[name])
            for control, name in ((self.output_source, "output_source"),
                                  (self.pull_source, "pull_source"),
                                  (self.static_mode, "mode"), (self.static_output, "output"),
                                  (self.static_drive, "drive_level"), (self.static_pull, "pull")):
                self._set_choice(control, value[name])
        finally:
            self._loading = False
        self._reflect_sources()

    def _selected(self, event):
        row = event.GetRow()
        if row != self.current_row:
            self._save_fields(); self._load_fields(row)
        event.Skip()

    def select_pin(self, row):
        """Select a pin and preserve the previous pin's unsaved field edits."""
        if not 0 <= row < len(self.pin_rows): raise IndexError("pin row out of range")
        if row != self.current_row:
            self._save_fields(); self._load_fields(row)
        self.grid.SetGridCursor(row, 0); self.grid.MakeCellVisible(row, 0)

    def _source_changed(self, event=None):
        self._reflect_sources()
        if event: event.Skip()

    def _reflect_sources(self):
        static_output = self.output_source.GetStringSelection() == "static"
        for control in (self.static_mode, self.static_output, self.static_drive): control.Enable(static_output)
        self.static_pull.Enable(self.pull_source.GetStringSelection() == "static")

    @staticmethod
    def _number(text, label):
        from python.spikes.netlist import parse_spice_number
        try: return parse_spice_number(text, "scalar")
        except (TypeError, ValueError) as exc: raise ValueError(label + ": " + str(exc)) from exc

    def configuration(self):
        """Return a validated detached contract; the dialog remains inert."""
        self.grid.SaveEditControlValue(); self.grid.DisableCellEditControl(); self._save_fields()
        result = deepcopy(self.draft)
        for row, (pin, _port, _index) in enumerate(self.pin_rows):
            value = result["pins"][pin["id"]]
            value["enabled"] = self.grid.GetCellValue(row, 0).strip().lower() in ("1", "true")
            value["signal_node"] = self.grid.GetCellValue(row, 3).strip()
            value["vdd_node"] = self.grid.GetCellValue(row, 4).strip()
            value["vss_node"] = self.grid.GetCellValue(row, 5).strip()
            raw = self._field_drafts[pin["id"]]
            value["output_source"] = raw["output_source"]
            value["pull_source"] = raw["pull_source"]
            value["static_state"] = {name: raw[name] for name in ("mode", "output", "drive_level", "pull")}
            for name in PROFILE_FIELDS:
                value["profile"][name] = raw[name] if name in BOOL_PROFILE_FIELDS else self._number(raw[name], pin["label"] + " " + name)
            value["vil_ratio"] = self._number(raw["vil_ratio"], pin["label"] + " VIL ratio")
            value["vih_ratio"] = self._number(raw["vih_ratio"], pin["label"] + " VIH ratio")
        return validate_settings(result, self.board)

    def accept(self, event=None):
        try:
            self.result = self.configuration()
            self.error.SetLabel("")
            if self.IsModal(): self.EndModal(wx.ID_OK)
            else: self.SetReturnCode(wx.ID_OK)
        except ValueError as exc:
            self.result = None; self.error.SetLabel(str(exc)); self.Layout()


PadPropertiesDialog = FirmwarePadPropertiesDialog


def show(owner, board, settings=None, net_names=()):
    """Show the editor and return accepted settings, or None on cancel."""
    with FirmwarePadPropertiesDialog(owner, board, settings, net_names) as dialog:
        return dialog.result if dialog.ShowModal() == wx.ID_OK else None
