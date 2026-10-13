# SPDX-License-Identifier: Apache-2.0
"""Native reusable HDL diagnostics, synthesis and digital timing suite."""
from __future__ import annotations

from pathlib import Path

import wx
import wx.grid
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg, NavigationToolbar2WxAgg
from matplotlib.figure import Figure
from matplotlib.ticker import EngFormatter

from .hdl_analysis import (MAX_DISPLAY_TRANSITIONS, bounded_transitions, capability_inventory,
                           serialize_measurements, summarize_netlist,
                           timing_measurements)
from .ide import find_tool
from .fuzzy_search import ranked


TOOLS = ("yosys", "iverilog", "vvp", "verilator", "ghdl", "sta")
MAX_VISIBLE_SIGNALS = 128
MAX_ANNOTATIONS_PER_SIGNAL = 256


class TimingPlotter:
    """Own a bounded waveform figure and draggable shared-time cursors."""
    def __init__(self, parent, changed):
        self.figure = Figure(figsize=(8, 4), layout="constrained")
        self.canvas = FigureCanvasWxAgg(parent, -1, self.figure)
        self.canvas.SetMinSize((120,100))
        self.toolbar = NavigationToolbar2WxAgg(self.canvas)
        self.changed, self.data, self.names = changed, None, []
        self.cursor_times = [0.0, 0.0]; self.cursor_lines = []
        self.drag_index = None
        self.canvas.mpl_connect("button_press_event", self._press)
        self.canvas.mpl_connect("motion_notify_event", self._motion)
        self.canvas.mpl_connect("button_release_event", self._release)

    def draw(self, data, names):
        same_capture = self.data is data
        self.data, self.names = data, list(names)[:MAX_VISIBLE_SIGNALS]
        end = float(data.get("end_time_s", 0.0))
        if not same_capture: self.cursor_times = [0.0, end]
        self.figure.clear(); ax = self.figure.add_subplot()
        labels = []
        for row, name in enumerate(self.names):
            signal = data["signals"][name]; transitions = bounded_transitions(signal.get("transitions", []))
            labels.append(name)
            if not transitions: continue
            xs = [t for t, _ in transitions] + [end]
            ys = []
            annotation_count = 0
            for time_s, value in transitions:
                known = "x" not in value and "z" not in value
                high = known and int(value, 2) != 0
                ys.append(row + (0.72 if high else 0.12))
                if (signal.get("width", 1) > 1 or not known) and annotation_count < MAX_ANNOTATIONS_PER_SIGNAL:
                    ax.text(time_s, row + .40, value, fontsize=8, clip_on=True)
                    annotation_count += 1
            ax.step(xs, ys + [ys[-1]], where="post", label=name)
        ax.set_yticks(range(len(labels)), labels); ax.set_xlabel("Time")
        ax.xaxis.set_major_formatter(EngFormatter(unit="s")); ax.grid(axis="x", alpha=.25)
        self.cursor_lines = [ax.axvline(value, color=color, linestyle="--", picker=6,
                                        label=f"Cursor {letter}")
                             for value, color, letter in zip(self.cursor_times, ("#d04a4a", "#4a78d0"), "AB")]
        suffix = f"; first {MAX_VISIBLE_SIGNALS} selected signals" if len(names) > MAX_VISIBLE_SIGNALS else ""
        ax.set_title(f"VCD timing (at most {MAX_DISPLAY_TRANSITIONS:,} transitions/signal{suffix})")
        self.canvas.draw_idle(); self.changed()

    def _press(self, event):
        if self.toolbar.mode: return
        if event.inaxes and event.xdata is not None and self.cursor_lines:
            distances = [abs(event.x - line.axes.transData.transform((line.get_xdata()[0], 0))[0])
                         for line in self.cursor_lines]
            closest = min(range(2), key=distances.__getitem__)
            if distances[closest] <= 10: self.drag_index = closest

    def _motion(self, event):
        if self.drag_index is None or event.xdata is None or not self.data: return
        end = float(self.data.get("end_time_s", 0.0))
        value = min(end, max(0.0, float(event.xdata)))
        self.cursor_times[self.drag_index] = value
        self.cursor_lines[self.drag_index].set_xdata([value, value])
        self.canvas.draw_idle(); self.changed()

    def _release(self, _event): self.drag_index = None


class HDLSuitePanel(wx.Panel):
    """Reusable bottom IDE panel. The owner supplies ``build_code(mode)``."""
    def __init__(self, parent, owner):
        super().__init__(parent); self.owner = owner; self.report = None; self.timing = None
        root = wx.BoxSizer(wx.VERTICAL); commands = wx.WrapSizer(wx.HORIZONTAL)
        self.tool_text = wx.StaticText(self); commands.Add(self.tool_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        root.Add(commands, 0, wx.EXPAND)
        self.book = wx.Notebook(self); root.Add(self.book, 1, wx.EXPAND); self.SetSizer(root)
        self._make_diagnostics(); self._make_synthesis(); self._make_timing(); self.refresh_tools()

    def _make_diagnostics(self):
        page = wx.Panel(self.book); box = wx.BoxSizer(wx.VERTICAL)
        self.diagnostics = wx.TextCtrl(page, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.build_log = self.diagnostics
        box.Add(self.diagnostics, 1, wx.EXPAND | wx.ALL, 4); page.SetSizer(box); self.book.AddPage(page, "Diagnostics")

    def _make_synthesis(self):
        page = wx.Panel(self.book); box = wx.BoxSizer(wx.HORIZONTAL)
        self.modules = wx.TreeCtrl(page, style=wx.TR_HAS_BUTTONS | wx.TR_LINES_AT_ROOT)
        self.cells = wx.ListCtrl(page, style=wx.LC_REPORT); self.cells.AppendColumn("Cell type", width=220); self.cells.AppendColumn("Count", width=80)
        box.Add(self.modules, 1, wx.EXPAND | wx.ALL, 4); box.Add(self.cells, 1, wx.EXPAND | wx.ALL, 4)
        page.SetSizer(box); self.book.AddPage(page, "Synthesis")

    def _make_timing(self):
        page = wx.Panel(self.book); outer = wx.BoxSizer(wx.VERTICAL); filters = wx.BoxSizer(wx.HORIZONTAL)
        self.search = wx.SearchCtrl(page); self.search.ShowCancelButton(True); filters.Add(self.search, 1, wx.EXPAND | wx.ALL, 3)
        export_json = wx.Button(page, label="Export JSON"); export_csv = wx.Button(page, label="Export CSV")
        export_json.Bind(wx.EVT_BUTTON, lambda e: self._export("json")); export_csv.Bind(wx.EVT_BUTTON, lambda e: self._export("csv"))
        filters.Add(export_json, 0, wx.ALL, 3); filters.Add(export_csv, 0, wx.ALL, 3); outer.Add(filters, 0, wx.EXPAND)
        split = wx.BoxSizer(wx.HORIZONTAL); self.signal_list = wx.CheckListBox(page); split.Add(self.signal_list, 0, wx.EXPAND | wx.ALL, 3)
        plot_box = wx.BoxSizer(wx.VERTICAL); self.plotter = TimingPlotter(page, self._refresh_readings)
        self.timing_figure = self.plotter.figure; self.timing_canvas = self.plotter.canvas
        plot_box.Add(self.plotter.toolbar, 0, wx.EXPAND); plot_box.Add(self.plotter.canvas, 1, wx.EXPAND); split.Add(plot_box, 1, wx.EXPAND)
        outer.Add(split, 1, wx.EXPAND); self.readings = wx.grid.Grid(page); self.readings.CreateGrid(0, 9)
        self.cursor_summary=wx.StaticText(page,label='A/B cursors: load a VCD capture')
        outer.Add(self.cursor_summary,0,wx.EXPAND|wx.ALL,3)
        for col, name in enumerate(("Signal", "A", "B", "Delta (s)", "Transitions", "Rise", "Fall", "Period (s)", "Duty")): self.readings.SetColLabelValue(col, name)
        self.readings.SetMinSize((-1, 125)); outer.Add(self.readings, 0, wx.EXPAND | wx.ALL, 3)
        page.SetSizer(outer); self.book.AddPage(page, "Timing")
        self.search.Bind(wx.EVT_TEXT, self._filter_signals); self.signal_list.Bind(wx.EVT_CHECKLISTBOX, self._selection_changed)

    def refresh_tools(self):
        paths = {name: find_tool(name) for name in TOOLS}
        availability = [f"{name}: {path or 'unavailable'}" for name, path in paths.items()]
        capabilities = capability_inventory(paths)
        supported = [f"{item['language']} {item['operation']}: " +
                     ("available" if item["available"] else "unsupported") + f" ({item['detail']})"
                     for item in capabilities]
        self.tool_text.SetLabel('Local toolchains - hover for paths and supported workflows')
        self.tool_text.SetToolTip("\n".join(availability + supported))
        if not self.diagnostics.GetValue(): self.diagnostics.SetValue("Toolchain inventory\n" + "\n".join(availability + supported))

    def accept_report(self, report):
        self.report = report; self.diagnostics.SetValue(f"Tool: {report.get('tool', 'unknown')}\nExit: {report.get('exit_code', 'unknown')}\n{report.get('output', '')}")
        self.modules.DeleteAllItems(); self.cells.DeleteAllItems()
        if "netlist" in report:
            summary = summarize_netlist(report["netlist"]); root = self.modules.AddRoot(f"Modules ({summary['module_count']})")
            for name, module in summary["modules"].items():
                item = self.modules.AppendItem(root, f"{name} ({module['cell_count']} cells)")
                ports = self.modules.AppendItem(item, "Ports")
                for port in module["ports"]: self.modules.AppendItem(ports, f"{port['direction']} [{port['width']}] {port['name']}")
                hierarchy = self.modules.AppendItem(item, "Hierarchy")
                for child in module["children"]: self.modules.AppendItem(hierarchy, f"{child['instance']}: {child['module']}")
            self.modules.Expand(root)
            for kind, count in summary["cell_type_totals"].items(): index = self.cells.InsertItem(self.cells.GetItemCount(), kind); self.cells.SetItem(index, 1, str(count))
        if "timing" in report: self.load_timing(report["timing"])

    def load_timing(self, data):
        if not isinstance(data, dict) or not isinstance(data.get("signals"), dict): raise ValueError("Invalid parsed VCD timing data")
        self.timing = data; self._filter_signals()

    def _filter_signals(self, _event=None):
        if not self.timing: return
        old = {self.signal_list.GetString(i) for i in range(self.signal_list.GetCount()) if self.signal_list.IsChecked(i)}
        names = ranked(self.timing["signals"], self.search.GetValue())
        self.signal_list.Set(names)
        for index, name in enumerate(names): self.signal_list.Check(index, name in old or not old)
        self._selection_changed()

    def _selected(self): return [self.signal_list.GetString(i) for i in range(self.signal_list.GetCount()) if self.signal_list.IsChecked(i)]
    def _selection_changed(self, _event=None):
        if self.timing: self.plotter.draw(self.timing, self._selected())

    def _refresh_readings(self):
        if not self.timing: return
        a,b=self.plotter.cursor_times
        self.cursor_summary.SetLabel(f'A: {a:.6g} s    B: {b:.6g} s    B - A: {b-a:.6g} s')
        rows = timing_measurements(self.timing, self._selected(), *self.plotter.cursor_times)
        current = self.readings.GetNumberRows()
        if current: self.readings.DeleteRows(0, current)
        if rows: self.readings.AppendRows(len(rows))
        for row_index, row in enumerate(rows):
            values = (row["signal"], row["value_a"], row["value_b"], row["delta_s"], row["transition_count"], row["rising_edges"], row["falling_edges"], row["period_s"], row["duty_cycle"])
            for col, value in enumerate(values):
                rendered='' if value is None else f'{value:.6g}' if isinstance(value,float) else str(value)
                self.readings.SetCellValue(row_index,col,rendered)
                self.readings.SetReadOnly(row_index,col)

    def _export(self, format_name):
        if not self.timing: return
        wildcard = "JSON (*.json)|*.json" if format_name == "json" else "CSV (*.csv)|*.csv"
        with wx.FileDialog(self, "Export selected timing measurements", wildcard=wildcard,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() != wx.ID_OK: return
            rows = timing_measurements(self.timing, self._selected(), *self.plotter.cursor_times)
            Path(dialog.GetPath()).write_text(serialize_measurements(rows, format_name), encoding="utf-8")
