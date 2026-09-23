"""
SPIKE Analysis Dashboard — Phase 15 rewrite
Embedded matplotlib canvas for interactive plots:
  • Probe Table (live, logged)
  • Impedance Sweep  Z(f) vs frequency
  • Transient Waveform  V(t)
"""
import wx
import wx.grid
import datetime

try:
    import numpy as np
    import matplotlib
    matplotlib.use("WXAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigCanvas
    from matplotlib.backends.backend_wxagg import NavigationToolbar2WxAgg as NavToolbar
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# Dark plot style colors
PLOT_BG    = "#0e0e1a"
PLOT_FG    = "#d4d4e8"
PLOT_GRID  = "#2a2a3f"
PLOT_ACC1  = "#e94560"   # red accent
PLOT_ACC2  = "#00bfff"   # cyan
PLOT_ACC3  = "#ffd700"   # yellow / Z-target line


class PlotPanel(wx.Panel):
    """Single matplotlib canvas with a nav toolbar + optional Z-target line."""

    def __init__(self, parent):
        super().__init__(parent)
        self.fig = None
        self.canvas = None
        self._build_placeholder()

    def _build_placeholder(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        if HAS_MPL:
            self.fig = Figure(facecolor=PLOT_BG, tight_layout=True)
            self.ax  = self.fig.add_subplot(111)
            self._style_axes(self.ax)
            self.ax.text(0.5, 0.5, "Run a simulation to\ngenerate plots",
                         ha="center", va="center",
                         color=PLOT_FG, fontsize=13,
                         transform=self.ax.transAxes)
            self.canvas  = FigCanvas(self, -1, self.fig)
            self.toolbar = NavToolbar(self.canvas)
            self.toolbar.Realize()
            sizer.Add(self.toolbar, 0, wx.EXPAND)
            sizer.Add(self.canvas,  1, wx.EXPAND)
        else:
            lbl = wx.StaticText(self, label="matplotlib not found — install via pip install matplotlib")
            lbl.SetForegroundColour(wx.Colour(233, 69, 96))
            sizer.Add(lbl, 0, wx.ALL, 20)
        self.SetSizer(sizer)

    def _style_axes(self, ax):
        ax.set_facecolor(PLOT_BG)
        ax.tick_params(colors=PLOT_FG, labelsize=8)
        ax.xaxis.label.set_color(PLOT_FG)
        ax.yaxis.label.set_color(PLOT_FG)
        ax.title.set_color(PLOT_FG)
        for spine in ax.spines.values():
            spine.set_edgecolor(PLOT_GRID)
        ax.grid(True, color=PLOT_GRID, linewidth=0.5, linestyle="--")

    # ------------------------------------------------------------------
    def plot_impedance(self, freqs, z_vals, z_target=None, label="Z(f)"):
        """Plot impedance vs frequency (log-log)."""
        if not HAS_MPL:
            return
        self.ax.clear()
        self._style_axes(self.ax)
        self.ax.loglog(freqs, z_vals, color=PLOT_ACC1, lw=1.8, label=label)
        if z_target is not None:
            self.ax.axhline(z_target, color=PLOT_ACC3, lw=1.2, ls="--", label=f"Z_target = {z_target} mΩ")
            # Fill region above Z_target
            self.ax.fill_between(freqs, z_vals, z_target,
                                 where=[z > z_target for z in z_vals],
                                 alpha=0.2, color=PLOT_ACC1, label="Exceeds target")
        self.ax.set_xlabel("Frequency (Hz)", color=PLOT_FG)
        self.ax.set_ylabel("Impedance (mΩ)", color=PLOT_FG)
        self.ax.set_title("PDN Impedance vs Frequency", color=PLOT_FG)
        self.ax.legend(facecolor=PLOT_BG, labelcolor=PLOT_FG, fontsize=8)
        self.canvas.draw()

    def plot_transient(self, time_ns, voltages_dict):
        """Plot transient voltage droop. voltages_dict = {label: [V(t)]}."""
        if not HAS_MPL:
            return
        self.ax.clear()
        self._style_axes(self.ax)
        colors = [PLOT_ACC1, PLOT_ACC2, PLOT_ACC3, "#90EE90", "#FF69B4"]
        for i, (label, vlist) in enumerate(voltages_dict.items()):
            self.ax.plot(time_ns, vlist, color=colors[i % len(colors)], lw=1.6, label=label)
        self.ax.set_xlabel("Time (ns)", color=PLOT_FG)
        self.ax.set_ylabel("Voltage (V)", color=PLOT_FG)
        self.ax.set_title("Transient Load-Step Response", color=PLOT_FG)
        self.ax.legend(facecolor=PLOT_BG, labelcolor=PLOT_FG, fontsize=8)
        self.canvas.draw()

    def clear(self):
        if not HAS_MPL:
            return
        self.ax.clear()
        self._style_axes(self.ax)
        self.ax.text(0.5, 0.5, "No data", ha="center", va="center",
                     color=PLOT_FG, fontsize=12, transform=self.ax.transAxes)
        self.canvas.draw()


# ---------------------------------------------------------------------------

class AnalysisDashboardPanel(wx.Panel):
    """
    Main Analysis Dashboard.
    Three sub-tabs:  Probe Table | Impedance Plot | Transient Waveform
    Plus bottom Observations / Insights text area.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._probes = []     # list of probe dicts
        self._probe_ctr = 0
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = wx.BoxSizer(wx.VERTICAL)

        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE)

        # ---- TOP: sub-tab notebook ----
        top_panel = wx.Panel(splitter)
        top_sz    = wx.BoxSizer(wx.VERTICAL)

        self.plot_nb = wx.Notebook(top_panel)
        self.plot_nb.AddPage(self._make_probe_page(self.plot_nb),     "🔬 Probe Table")
        self.plot_nb.AddPage(self._make_impedance_page(self.plot_nb), "📈 Impedance Z(f)")
        self.plot_nb.AddPage(self._make_transient_page(self.plot_nb), "⚡ Transient V(t)")

        top_sz.Add(self.plot_nb, 1, wx.EXPAND | wx.ALL, 4)
        top_panel.SetSizer(top_sz)

        # ---- BOTTOM: observations ----
        bot_panel = wx.Panel(splitter)
        bot_sz    = wx.BoxSizer(wx.VERTICAL)

        obs_box = wx.StaticBoxSizer(wx.VERTICAL, bot_panel, "Analytical Observations & Insights")

        tb_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_auto_analyze = wx.Button(obs_box.GetStaticBox(), label="🔍 Auto-Analyze")
        self.btn_export_obs   = wx.Button(obs_box.GetStaticBox(), label="📄 Export")
        self.btn_clear_obs    = wx.Button(obs_box.GetStaticBox(), label="Clear")
        tb_row.Add(self.btn_auto_analyze, 0, wx.RIGHT, 6)
        tb_row.Add(self.btn_export_obs,   0, wx.RIGHT, 6)
        tb_row.Add(self.btn_clear_obs,    0)
        obs_box.Add(tb_row, 0, wx.ALL, 6)

        self.txt_obs = wx.TextCtrl(obs_box.GetStaticBox(),
                                   style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self.txt_obs.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.txt_obs.SetBackgroundColour(wx.Colour(12, 12, 22))
        self.txt_obs.SetForegroundColour(wx.Colour(200, 210, 255))
        obs_box.Add(self.txt_obs, 1, wx.EXPAND | wx.ALL, 4)
        bot_sz.Add(obs_box, 1, wx.EXPAND | wx.ALL, 6)
        bot_panel.SetSizer(bot_sz)

        splitter.SplitHorizontally(top_panel, bot_panel)
        splitter.SetSashPosition(340)
        splitter.SetMinimumPaneSize(120)

        outer.Add(splitter, 1, wx.EXPAND)
        self.SetSizer(outer)

        # Bindings
        self.btn_clear_probes.Bind(wx.EVT_BUTTON, lambda e: self.clear_probes())
        self.btn_export_probes.Bind(wx.EVT_BUTTON, self._export_probe_csv)
        self.btn_auto_analyze.Bind(wx.EVT_BUTTON, self._on_auto_analyze)
        self.btn_export_obs.Bind(wx.EVT_BUTTON,   self._on_export_obs)
        self.btn_clear_obs.Bind(wx.EVT_BUTTON,    lambda e: self.txt_obs.Clear())

        self._init_obs_text()

    # ------------------------------------------------------------------
    def _make_probe_page(self, parent):
        p  = wx.Panel(parent)
        sz = wx.BoxSizer(wx.VERTICAL)

        # Probe controls toolbar
        ctrl_row = wx.BoxSizer(wx.HORIZONTAL)

        ctrl_row.Add(wx.StaticText(p, label="Probe mode:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.cb_probe_mode = wx.Choice(p, choices=["Voltage", "Current Density", "Impedance", "All Fields"])
        self.cb_probe_mode.SetSelection(0)
        ctrl_row.Add(self.cb_probe_mode, 0, wx.RIGHT, 12)

        self.chk_hover = wx.CheckBox(p, label="Hover probe")
        self.chk_hover.SetValue(True)
        ctrl_row.Add(self.chk_hover, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)

        self.btn_clear_probes  = wx.Button(p, label="Clear All")
        self.btn_export_probes = wx.Button(p, label="📥 Export CSV")
        ctrl_row.Add(self.btn_clear_probes,  0, wx.RIGHT, 4)
        ctrl_row.Add(self.btn_export_probes, 0)
        sz.Add(ctrl_row, 0, wx.ALL, 6)

        # Grid
        self.probe_grid = wx.grid.Grid(p)
        self.probe_grid.CreateGrid(0, 9)
        for i, h in enumerate(["ID", "Net", "Layer", "X (mm)", "Y (mm)",
                                "V (V)", "J (A/mm²)", "Z (mΩ)", "Notes"]):
            self.probe_grid.SetColLabelValue(i, h)
        widths = [40, 110, 65, 65, 65, 75, 85, 75, 160]
        for i, w in enumerate(widths):
            self.probe_grid.SetColSize(i, w)
        self.probe_grid.SetRowLabelSize(32)
        self.probe_grid.EnableEditing(False)
        sz.Add(self.probe_grid, 1, wx.EXPAND | wx.ALL, 4)
        p.SetSizer(sz)
        return p

    def _make_impedance_page(self, parent):
        p  = wx.Panel(parent)
        sz = wx.BoxSizer(wx.VERTICAL)
        self.impedance_plot = PlotPanel(p)
        sz.Add(self.impedance_plot, 1, wx.EXPAND)
        p.SetSizer(sz)
        return p

    def _make_transient_page(self, parent):
        p  = wx.Panel(parent)
        sz = wx.BoxSizer(wx.VERTICAL)
        self.transient_plot = PlotPanel(p)
        sz.Add(self.transient_plot, 1, wx.EXPAND)
        p.SetSizer(sz)
        return p

    # ------------------------------------------------------------------
    def _init_obs_text(self):
        self.txt_obs.SetValue(
            "═══════════════════════════════════════════════════════\n"
            "  SPIKE Analysis Dashboard — Ready\n"
            "═══════════════════════════════════════════════════════\n\n"
            "  Load a board and run a simulation to see results.\n"
            "  Use the Probe Table tab to inspect point values.\n"
            "  Use Impedance Z(f) tab after a frequency sweep.\n"
            "  Use Transient V(t) tab after a transient run.\n"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_probe(self, net, layer, x, y, voltage=None,
                  current_density=None, impedance=None, notes=""):
        self._probe_ctr += 1
        pid = self._probe_ctr
        probe = dict(id=pid, net=net, layer=layer, x=x, y=y,
                     v=voltage, j=current_density, z=impedance, notes=notes)
        self._probes.append(probe)

        row = self.probe_grid.GetNumberRows()
        self.probe_grid.AppendRows(1)
        self.probe_grid.SetCellValue(row, 0, str(pid))
        self.probe_grid.SetCellValue(row, 1, str(net))
        self.probe_grid.SetCellValue(row, 2, str(layer))
        self.probe_grid.SetCellValue(row, 3, f"{x:.3f}")
        self.probe_grid.SetCellValue(row, 4, f"{y:.3f}")
        if voltage is not None:
            self.probe_grid.SetCellValue(row, 5, f"{voltage:.5f}")
        if current_density is not None:
            self.probe_grid.SetCellValue(row, 6, f"{current_density:.3f}")
        if impedance is not None:
            self.probe_grid.SetCellValue(row, 7, f"{impedance:.4f}")
        self.probe_grid.SetCellValue(row, 8, notes)
        self.probe_grid.SetReadOnly(row, 0)
        self.probe_grid.MakeCellVisible(row, 0)

    def clear_probes(self):
        self._probes.clear()
        self._probe_ctr = 0
        if self.probe_grid.GetNumberRows() > 0:
            self.probe_grid.DeleteRows(0, self.probe_grid.GetNumberRows())

    def update_impedance_plot(self, freqs, z_vals, z_target=None):
        """Called from main thread (wx.CallAfter) after a sweep run."""
        self.impedance_plot.plot_impedance(freqs, z_vals, z_target)
        self.plot_nb.SetSelection(1)   # switch to impedance tab

    def update_transient_plot(self, time_ns, voltages_dict):
        """Called from main thread (wx.CallAfter) after a transient run."""
        self.transient_plot.plot_transient(time_ns, voltages_dict)
        self.plot_nb.SetSelection(2)

    def append_observation(self, text, level="INFO"):
        prefix = {"INFO": "[INFO]", "WARNING": "⚠ ", "CRITICAL": "🔴", "SUCCESS": "✓ "}.get(level, "[INFO]")
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt_obs.AppendText(f"\n[{ts}] {prefix} {text}")
        self.txt_obs.SetInsertionPointEnd()

    def set_observations(self, text):
        self.txt_obs.SetValue(text)

    # ------------------------------------------------------------------
    # Internal events
    def _on_auto_analyze(self, event):
        self.append_observation("Auto-analysis requested — connect to post-simulation data to populate.", "INFO")

    def _on_export_obs(self, event):
        dlg = wx.FileDialog(self, "Export Observations", wildcard="Text files (*.txt)|*.txt",
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                with open(dlg.GetPath(), "w", encoding="utf-8") as f:
                    f.write(self.txt_obs.GetValue())
                wx.MessageBox("Observations exported.", "Done", wx.OK | wx.ICON_INFORMATION)
            except Exception as e:
                wx.MessageBox(f"Export failed: {e}", "Error", wx.ICON_ERROR)
        dlg.Destroy()

    def _export_probe_csv(self, event):
        if not self._probes:
            wx.MessageBox("No probes logged.", "Nothing to Export")
            return
        dlg = wx.FileDialog(self, "Export Probe CSV", wildcard="CSV files (*.csv)|*.csv",
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            try:
                import csv
                with open(dlg.GetPath(), "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["id", "net", "layer", "x", "y",
                                                            "v", "j", "z", "notes"])
                    writer.writeheader()
                    writer.writerows(self._probes)
                wx.MessageBox("Probe data exported.", "Done", wx.OK | wx.ICON_INFORMATION)
            except Exception as e:
                wx.MessageBox(f"Export failed: {e}", "Error", wx.ICON_ERROR)
        dlg.Destroy()
