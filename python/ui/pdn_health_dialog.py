"""
SPIKE PDN Health Score Dialog
Post-simulation modal showing an A–F letter grade across 4 PDN metrics,
rendered as a matplotlib polar (radar) chart.
"""
import wx
import math

try:
    import numpy as np
    import matplotlib
    matplotlib.use("WXAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigCanvas
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

PLOT_BG   = "#0e0e1a"
PLOT_FG   = "#d4d4e8"
GRADES    = ["A", "B", "C", "D", "F"]

# Color bands per grade (green → red)
GRADE_COLORS = {
    "A": ("#28a745", "Excellent"),
    "B": ("#8bc34a", "Good"),
    "C": ("#ffc107", "Marginal"),
    "D": ("#ff7043", "Poor"),
    "F": ("#dc3545", "Critical"),
}


def _score_drop(drop_mv) -> float:
    """Score 0–1 based on IR drop in mV. 100% = ≤10 mV, 0% = ≥200 mV."""
    if drop_mv <= 10:  return 1.0
    if drop_mv >= 200: return 0.0
    return 1.0 - (drop_mv - 10) / 190


def _score_j(j_amm2) -> float:
    """Score 0–1 based on max current density A/mm². 100% = ≤50, 0% = ≥250."""
    if j_amm2 <= 50:  return 1.0
    if j_amm2 >= 250: return 0.0
    return 1.0 - (j_amm2 - 50) / 200


def _score_efficiency(eff_pct) -> float:
    """Score 0–1 based on efficiency %. 100% = ≥99%, 0% = ≤90%."""
    eff = max(0, min(100, eff_pct))
    if eff >= 99: return 1.0
    if eff <= 90: return 0.0
    return (eff - 90) / 9


def _score_fusing(fusing_risk_count) -> float:
    """Score 0–1 based on fusing risk segment count."""
    if fusing_risk_count == 0: return 1.0
    if fusing_risk_count >= 10: return 0.0
    return 1.0 - fusing_risk_count / 10


def _to_grade(score_0to1) -> str:
    if score_0to1 >= 0.90: return "A"
    if score_0to1 >= 0.75: return "B"
    if score_0to1 >= 0.55: return "C"
    if score_0to1 >= 0.35: return "D"
    return "F"


class PDNHealthDialog(wx.Dialog):
    """
    Displays a radar chart + letter grades for the four PDN health metrics.
    Instantiate after a simulation run with metrics dict.
    """

    def __init__(self, parent, metrics: dict):
        super().__init__(parent, title="PDN Health Score",
                         size=(700, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.metrics = metrics
        self._compute()
        self._build_ui()
        self.CentreOnParent()

    # ------------------------------------------------------------------
    def _compute(self):
        m = self.metrics
        s1 = _score_drop(m.get("drop_mv", 0))
        s2 = _score_j(m.get("max_j", 0))
        s3 = _score_efficiency(m.get("efficiency", 100))
        s4 = _score_fusing(len(m.get("fusing_risks", [])))

        self.scores  = [s1, s2, s3, s4]
        self.labels  = ["IR Drop\nMargin", "Current\nDensity", "Efficiency", "Fusing\nRisk"]
        self.grades  = [_to_grade(s) for s in self.scores]
        overall_raw  = sum(self.scores) / len(self.scores)
        self.overall = _to_grade(overall_raw)

    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = wx.BoxSizer(wx.VERTICAL)

        # Header
        hdr = wx.Panel(self)
        hdr.SetBackgroundColour(wx.Colour(15, 20, 50))
        hdr_sz = wx.BoxSizer(wx.HORIZONTAL)
        grade_txt = wx.StaticText(hdr, label=f"  Overall PDN Health: {self.overall}")
        gc, gdesc = GRADE_COLORS.get(self.overall, ("#888", "Unknown"))
        grade_txt.SetForegroundColour(wx.Colour(*_hex(gc)))
        grade_txt.SetFont(wx.Font(15, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        hdr_sz.Add(grade_txt, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 12)
        hdr_sz.AddStretchSpacer()
        desc = wx.StaticText(hdr, label=f"{gdesc}  ")
        desc.SetForegroundColour(wx.Colour(180, 180, 220))
        desc.SetFont(wx.Font(11, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        hdr_sz.Add(desc, 0, wx.ALIGN_CENTER_VERTICAL)
        hdr.SetSizer(hdr_sz)
        outer.Add(hdr, 0, wx.EXPAND)

        # Main content: radar chart + metric tiles
        content = wx.BoxSizer(wx.HORIZONTAL)

        # Radar chart
        if HAS_MPL:
            import numpy as np
            fig = Figure(figsize=(4, 4), facecolor=PLOT_BG, tight_layout=True)
            ax  = fig.add_subplot(111, polar=True)
            ax.set_facecolor(PLOT_BG)
            ax.tick_params(colors=PLOT_FG, labelsize=8)
            ax.spines["polar"].set_color("#2a2a4a")

            angles = np.linspace(0, 2 * np.pi, len(self.scores), endpoint=False).tolist()
            vals   = self.scores + self.scores[:1]
            angs   = angles + angles[:1]
            ax.fill(angs, vals, alpha=0.3, color="#e94560")
            ax.plot(angs, vals, color="#e94560", lw=2)
            ax.set_thetagrids(np.degrees(angles), self.labels, color=PLOT_FG, fontsize=9)
            ax.set_ylim(0, 1)
            ax.set_yticks([0.25, 0.5, 0.75, 1.0])
            ax.set_yticklabels(["D", "C", "B", "A"], color="#8080a0", fontsize=7)
            ax.grid(color="#2a2a4a", linewidth=0.8)

            canvas = FigCanvas(self, -1, fig)
            content.Add(canvas, 1, wx.EXPAND | wx.ALL, 10)
        else:
            content.Add(wx.StaticText(self, label="matplotlib not found"), 1, wx.ALL, 20)

        # Metric tiles
        tiles = wx.BoxSizer(wx.VERTICAL)
        raw_vals = [
            f"{self.metrics.get('drop_mv', 0):.1f} mV",
            f"{self.metrics.get('max_j', 0):.1f} A/mm²",
            f"{self.metrics.get('efficiency', 0):.1f}%",
            f"{len(self.metrics.get('fusing_risks', []))} segments",
        ]
        for label, grade, raw in zip(self.labels, self.grades, raw_vals):
            tile = wx.Panel(self, style=wx.BORDER_SIMPLE)
            gc, _ = GRADE_COLORS.get(grade, ("#888", ""))
            tile.SetBackgroundColour(wx.Colour(20, 20, 38))
            tsz = wx.BoxSizer(wx.VERTICAL)
            lbl_name  = wx.StaticText(tile, label=label.replace("\n", " "))
            lbl_name.SetForegroundColour(wx.Colour(160, 160, 220))
            lbl_grade = wx.StaticText(tile, label=grade)
            lbl_grade.SetFont(wx.Font(22, wx.DEFAULT, wx.NORMAL, wx.BOLD))
            lbl_grade.SetForegroundColour(wx.Colour(*_hex(gc)))
            lbl_raw   = wx.StaticText(tile, label=raw)
            lbl_raw.SetForegroundColour(wx.Colour(200, 200, 230))
            tsz.Add(lbl_name,  0, wx.ALL, 6)
            tsz.Add(lbl_grade, 0, wx.LEFT | wx.BOTTOM, 6)
            tsz.Add(lbl_raw,   0, wx.LEFT | wx.BOTTOM, 6)
            tile.SetSizer(tsz)
            tiles.Add(tile, 0, wx.EXPAND | wx.ALL, 6)

        content.Add(tiles, 0, wx.EXPAND | wx.ALL, 6)
        outer.Add(content, 1, wx.EXPAND)

        # Recommendations
        recs_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Recommendations")
        self.txt_recs = wx.TextCtrl(recs_box.GetStaticBox(), style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=(-1, 100))
        self.txt_recs.SetBackgroundColour(wx.Colour(14, 14, 28))
        self.txt_recs.SetForegroundColour(wx.Colour(200, 210, 255))
        recs_box.Add(self.txt_recs, 1, wx.EXPAND | wx.ALL, 6)
        self._populate_recs()
        outer.Add(recs_box, 0, wx.EXPAND | wx.ALL, 8)

        btn = wx.Button(self, wx.ID_OK, "Close")
        btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_OK))
        outer.Add(btn, 0, wx.ALIGN_RIGHT | wx.BOTTOM | wx.RIGHT, 12)

        self.SetSizer(outer)

    def _populate_recs(self):
        lines = []
        g = dict(zip(self.labels, self.grades))
        if "F" in self.grades or "D" in self.grades:
            if g.get("IR Drop\nMargin") in ("D", "F"):
                lines.append("• IR Drop critical — widen power traces or add copper pours.")
            if g.get("Current\nDensity") in ("D", "F"):
                lines.append("• Fusing risk high — increase trace width on high-current segments immediately.")
            if g.get("Efficiency") in ("D", "F"):
                lines.append("• Efficiency low — review resistive losses in the power path.")
            if g.get("Fusing\nRisk") in ("D", "F"):
                lines.append("• Multiple fusing-risk segments — add parallel copper paths.")
        if not lines:
            lines.append("✓  PDN health is good. Consider AC impedance sweep for full frequency-domain verification.")
        self.txt_recs.SetValue("\n".join(lines))


def _hex(h):
    h = h.lstrip("#")
    return int(h[:2], 16), int(h[2:4], 16), int(h[4:6], 16)
