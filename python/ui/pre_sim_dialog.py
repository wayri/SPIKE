"""
SPIKE Pre-Simulation Validation Dialog
Full blocking modal that runs a checklist before any simulation starts.
Reports pass / warning / fail per item, estimates nodes, memory and runtime.
"""
import wx
import wx.grid
import time

# Check icons
ICON_PASS = "✅"
ICON_WARN = "⚠️"
ICON_FAIL = "❌"
ICON_SKIP = "⏭️"

LEVEL_COLORS = {
    "PASS":    wx.Colour(40, 167, 69),
    "WARN":    wx.Colour(255, 193, 7),
    "FAIL":    wx.Colour(220, 53, 69),
    "SKIP":    wx.Colour(120, 120, 120),
}


class PreSimDialog(wx.Dialog):
    """
    Blocking pre-simulation checklist.
    Returns wx.ID_OK if user clicks 'Proceed', wx.ID_CANCEL otherwise.
    Always run BEFORE launching the solver thread.
    """

    def __init__(self, parent, analysis_panel, parser=None):
        super().__init__(parent,
                         title="Pre-Simulation Validation",
                         size=(700, 540),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.analysis_panel = analysis_panel
        self.parser = parser
        self._results = []   # list of (name, level, detail)
        self._has_fail = False

        self._build_ui()
        self._run_checks()
        self.CentreOnParent()

    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = wx.BoxSizer(wx.VERTICAL)

        # Title bar
        hdr = wx.Panel(self, style=wx.BORDER_NONE)
        hdr.SetBackgroundColour(wx.Colour(30, 50, 100))
        hdr_sz = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(hdr, label="  🔍  Pre-Simulation Validation Checklist")
        lbl.SetForegroundColour(wx.WHITE)
        lbl.SetFont(wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        hdr_sz.Add(lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        hdr.SetSizer(hdr_sz)
        outer.Add(hdr, 0, wx.EXPAND)

        # Check table
        self.grid = wx.grid.Grid(self)
        self.grid.CreateGrid(0, 3)
        self.grid.SetColLabelValue(0, "Check")
        self.grid.SetColLabelValue(1, "Status")
        self.grid.SetColLabelValue(2, "Detail")
        self.grid.SetColSize(0, 220)
        self.grid.SetColSize(1, 80)
        self.grid.SetColSize(2, 340)
        self.grid.SetRowLabelSize(0)
        self.grid.EnableEditing(False)
        outer.Add(self.grid, 1, wx.EXPAND | wx.ALL, 8)

        # Estimates section
        est_box = wx.StaticBoxSizer(wx.HORIZONTAL, self, "Resource Estimates")
        self.lbl_nodes  = wx.StaticText(self, label="Nodes:  --")
        self.lbl_mem    = wx.StaticText(self, label="Memory: -- MB")
        self.lbl_time   = wx.StaticText(self, label="Est. Time: -- s")
        for w in (self.lbl_nodes, self.lbl_mem, self.lbl_time):
            w.SetFont(wx.Font(10, wx.DEFAULT, wx.NORMAL, wx.BOLD))
            est_box.Add(w, 1, wx.ALIGN_CENTER | wx.ALL, 8)
        outer.Add(est_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        # Status summary
        self.lbl_summary = wx.StaticText(self, label="Running checks…")
        self.lbl_summary.SetFont(wx.Font(10, wx.DEFAULT, wx.ITALIC, wx.NORMAL))
        outer.Add(self.lbl_summary, 0, wx.LEFT | wx.BOTTOM, 12)

        # Buttons
        btn_sz = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_proceed = wx.Button(self, wx.ID_OK,     "▶  Proceed Anyway")
        self.btn_cancel  = wx.Button(self, wx.ID_CANCEL, "✖  Cancel")
        self.btn_proceed.SetBackgroundColour(wx.Colour(40, 167, 69))
        self.btn_proceed.SetForegroundColour(wx.WHITE)
        btn_sz.AddStretchSpacer()
        btn_sz.Add(self.btn_proceed, 0, wx.RIGHT, 8)
        btn_sz.Add(self.btn_cancel, 0, wx.RIGHT, 8)
        outer.Add(btn_sz, 0, wx.EXPAND | wx.BOTTOM, 10)

        self.SetSizer(outer)
        self.btn_proceed.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_OK))
        self.btn_cancel.Bind(wx.EVT_BUTTON,  lambda e: self.EndModal(wx.ID_CANCEL))

    # ------------------------------------------------------------------
    def _add_row(self, name, level, detail):
        icon = {"PASS": ICON_PASS, "WARN": ICON_WARN, "FAIL": ICON_FAIL, "SKIP": ICON_SKIP}.get(level, "")
        row = self.grid.GetNumberRows()
        self.grid.AppendRows(1)
        self.grid.SetCellValue(row, 0, name)
        self.grid.SetCellValue(row, 1, f"{icon} {level}")
        self.grid.SetCellValue(row, 2, detail)
        color = LEVEL_COLORS.get(level, wx.Colour(200, 200, 200))
        for col in range(3):
            self.grid.SetCellBackgroundColour(row, col, wx.Colour(color.Red()//6, color.Green()//6, color.Blue()//6))
            self.grid.SetCellTextColour(row, col, color)
        if level == "FAIL":
            self._has_fail = True

    # ------------------------------------------------------------------
    def _run_checks(self):
        ss = self.analysis_panel.sources_sinks

        # 1 — Board loaded
        if self.parser:
            self._add_row("Board Loaded", "PASS", f"{len(getattr(self.parser,'tracks',[])):,} tracks, "
                          f"{len(getattr(self.parser,'vias',[])):,} vias, "
                          f"{len(getattr(self.parser,'pads',[])):,} pads")
        else:
            self._add_row("Board Loaded", "FAIL", "No board is loaded. Open a .kicad_pcb or .spk file first.")

        # 2 — At least one source
        sources = [s for s in ss if "Source" in s.get("type", "")]
        if sources:
            self._add_row("Source Defined", "PASS", f"{len(sources)} source(s) configured")
        else:
            self._add_row("Source Defined", "FAIL", "No VRM / current source defined. Add at least one source.")

        # 3 — At least one sink
        sinks = [s for s in ss if "Sink" in s.get("type", "")]
        if sinks:
            self._add_row("Sink Defined", "PASS", f"{len(sinks)} sink(s) configured")
        else:
            self._add_row("Sink Defined", "WARN", "No load sink defined — simulation will solve for open-circuit conditions.")

        # 4 — Pad resolution
        if self.parser:
            pad_ids = {f"{p['component']}:{p['component_pad']}" for p in getattr(self.parser, 'pads', [])}
            unresolved = [s for s in ss if s.get("pad") and s["pad"] not in pad_ids and s.get("type") != "Pass-Through"]
            if unresolved:
                self._add_row("Pad Resolution", "WARN",
                              f"{len(unresolved)} pad(s) not found in netlist — they will be skipped.")
            else:
                self._add_row("Pad Resolution", "PASS", "All configured pads found in board netlist.")
        else:
            self._add_row("Pad Resolution", "SKIP", "No board loaded.")

        # 5 — Diode direction sanity
        diodes = [s for s in ss if s.get("pt_type") == "Diode / Bridge"]
        if diodes:
            self._add_row("Diode Direction", "WARN",
                          f"{len(diodes)} diode(s) found — iterative non-linear solver will be used (slower).")
        else:
            self._add_row("Diode Direction", "PASS", "No non-linear elements — standard linear solver active.")

        # 6 — Grid resolution
        try:
            grid_mm = float(self.analysis_panel.txt_grid_mm.GetValue())
            if grid_mm < 0.005:
                self._add_row("Mesh Resolution", "WARN", f"{grid_mm} mm is extremely fine — expect very long runtime.")
            elif grid_mm > 1.0:
                self._add_row("Mesh Resolution", "WARN", f"{grid_mm} mm is coarse — results may lose accuracy.")
            else:
                self._add_row("Mesh Resolution", "PASS", f"{grid_mm} mm mesh resolution is reasonable.")
        except Exception:
            self._add_row("Mesh Resolution", "WARN", "Could not parse mesh resolution value.")

        # Resource estimates
        self._estimate_resources()

        # Summary
        fails  = sum(1 for _, l, _ in self._results if l == "FAIL")
        warns  = sum(1 for _, l, _ in self._results if l == "WARN")
        passes = sum(1 for _, l, _ in self._results if l == "PASS")
        if self._has_fail:
            self.lbl_summary.SetLabel(f"❌  {fails} critical issue(s) detected. Fix before running or proceed at own risk.")
            self.lbl_summary.SetForegroundColour(LEVEL_COLORS["FAIL"])
            self.btn_proceed.SetLabel("⚠  Proceed Anyway (Issues Present)")
            self.btn_proceed.SetBackgroundColour(wx.Colour(180, 80, 20))
        elif warns > 0:
            self.lbl_summary.SetLabel(f"⚠️  {warns} warning(s). {passes} checks passed. Review before proceeding.")
            self.lbl_summary.SetForegroundColour(LEVEL_COLORS["WARN"])
        else:
            self.lbl_summary.SetLabel(f"✅  All {passes} checks passed. Ready to simulate.")
            self.lbl_summary.SetForegroundColour(LEVEL_COLORS["PASS"])
            self.btn_proceed.SetLabel("▶  Run Simulation")

        self.grid.AutoSizeRows()

    # ------------------------------------------------------------------
    def _estimate_resources(self):
        if not self.parser:
            return
        try:
            grid_mm = float(self.analysis_panel.txt_grid_mm.GetValue())
            b = getattr(self.parser, "board_bbox", None)
            if b:
                area = (b["max_x"] - b["min_x"]) * (b["max_y"] - b["min_y"])
            else:
                area = 100 * 100
            zone_nodes = int(area / (grid_mm ** 2))
            track_nodes = len(getattr(self.parser, "tracks", [])) * 2
            via_nodes   = len(getattr(self.parser, "vias", [])) * 2
            total_nodes = track_nodes + via_nodes + zone_nodes

            # Memory: sparse LIL ~ 120 bytes/node
            mem_mb = (total_nodes * 120) / 1024 / 1024

            # Time: rough heuristic 0.5 ms per 1000 nodes for iterative solver
            est_sec = max(0.1, (total_nodes / 1000) * 0.5)

            self.lbl_nodes.SetLabel(f"Nodes:  ~{total_nodes:,}")
            self.lbl_mem.SetLabel(f"Memory: ~{mem_mb:.0f} MB")
            self.lbl_time.SetLabel(f"Est. Time: ~{est_sec:.1f} s")

            if mem_mb > 2000:
                self._add_row("Memory Warning", "WARN",
                              f"Estimated {mem_mb:.0f} MB — close other apps if system RAM is limited.")
            elif mem_mb > 8000:
                self._add_row("Memory Warning", "FAIL",
                              f"Estimated {mem_mb:.0f} MB exceeds typical system RAM — coarsen the mesh!")
        except Exception as e:
            self.lbl_nodes.SetLabel("Nodes:  (error)")
            print(f"[PreSim] Estimate error: {e}")
