"""
SPIKE SI Workspace Panel — Phase 15 Foundation
Provides:
  • Net / trace selector for SI analysis
  • Analytical Z0 calculator (microstrip + stripline)
  • TDR / S-parameter / Crosstalk stubs (Phase 16)
"""
import wx
import math


def microstrip_z0(w_mm: float, h_mm: float, er: float) -> float:
    """Wheeler's closed-form microstrip Z0 in Ohms."""
    u = w_mm / h_mm
    if u <= 1:
        f = (1 / (2 * math.pi)) * math.log(8 / u + u / 4)
        z = (60 / math.sqrt((er + 1) / 2 + (er - 1) / 2 * (
            (1 + 12 / u) ** -0.5 + 0.04 * (1 - u) ** 2))) * f * 2 * math.pi
    else:
        z = 120 * math.pi / (math.sqrt(er) * (u + 1.393 + 0.667 * math.log(u + 1.444)))
    return z


def stripline_z0(w_mm: float, b_mm: float, er: float) -> float:
    """Approximate stripline Z0 in Ohms. b = distance between planes."""
    x = w_mm / b_mm
    if x < 0.001:
        x = 0.001
    z = (60 / math.sqrt(er)) * math.log(4 * b_mm / (0.671 * math.pi * (0.8 * w_mm + 0 )))
    # Simplified Bogatin formula
    z = (60 / math.sqrt(er)) * math.log(4 * b_mm / (math.pi * 0.85 * w_mm + 0.8 * 0))
    # Use standard closed-form
    z0_num = 60 * math.pi
    z0_den = math.sqrt(er) * (w_mm / b_mm + 1.393 + 0.667 * math.log(w_mm / b_mm + 1.444))
    z = (60 / math.sqrt(er)) * math.log(
        (4 * b_mm) / (0.67 * math.pi * (0.8 * w_mm + 0.0)))
    # Use Bogatin's simplified formula for accuracy
    z = (87 / math.sqrt(er + 1.41)) * math.log(5.98 * b_mm / (0.8 * w_mm + 0.0 + 1e-9))
    return max(z, 1.0)


def diff_microstrip_z0(z0_se: float, s_mm: float, h_mm: float) -> float:
    """Approximate differential impedance from single-ended Z0 and gap S, height H."""
    k = 1 - 0.347 * math.exp(-2.9 * s_mm / h_mm)
    return 2 * z0_se * k


class SIWorkspacePanel(wx.Panel):
    """
    Signal Integrity workspace tab.
    Phase 15 provides: Z0 calculator (fully functional), analysis type stubs.
    Full wave solver (TDR / S-params / Crosstalk) comes in Phase 16.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        outer = wx.BoxSizer(wx.HORIZONTAL)

        # ---------- LEFT: config panel ----------
        left = wx.BoxSizer(wx.VERTICAL)

        # Net / trace selector
        net_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Trace / Net Selection")
        b = net_box.GetStaticBox()

        net_box.Add(wx.StaticText(b, label="Select net for SI analysis:"), 0, wx.ALL, 6)
        self.cb_net = wx.ComboBox(b, style=wx.CB_DROPDOWN)
        net_box.Add(self.cb_net, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        self.cb_pair = wx.CheckBox(b, label="Differential pair (auto-detect _P/_N)")
        net_box.Add(self.cb_pair, 0, wx.LEFT | wx.BOTTOM, 6)

        self.btn_load_net = wx.Button(b, label="Load Trace from Board")
        net_box.Add(self.btn_load_net, 0, wx.EXPAND | wx.ALL, 6)
        left.Add(net_box, 0, wx.EXPAND | wx.ALL, 6)

        # Z0 Calculator
        z0_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Characteristic Impedance Calculator (Z₀)")
        b2 = z0_box.GetStaticBox()

        mode_row = wx.BoxSizer(wx.HORIZONTAL)
        self.rb_ms  = wx.RadioButton(b2, label="Microstrip",  style=wx.RB_GROUP)
        self.rb_sl  = wx.RadioButton(b2, label="Stripline")
        self.rb_dms = wx.RadioButton(b2, label="Diff. Microstrip")
        mode_row.Add(self.rb_ms,  0, wx.RIGHT, 12)
        mode_row.Add(self.rb_sl,  0, wx.RIGHT, 12)
        mode_row.Add(self.rb_dms, 0)
        z0_box.Add(mode_row, 0, wx.ALL, 8)

        gs = wx.FlexGridSizer(0, 2, 8, 10)
        gs.AddGrowableCol(1)

        def field(label, default, hint=""):
            gs.Add(wx.StaticText(b2, label=label), flag=wx.ALIGN_CENTER_VERTICAL)
            txt = wx.TextCtrl(b2, value=default)
            if hint:
                txt.SetHint(hint)
            gs.Add(txt, flag=wx.EXPAND)
            return txt

        self.txt_w  = field("Trace width W (mm):",    "0.15",  "e.g. 0.15")
        self.txt_h  = field("Dielectric height H (mm):", "0.1", "core or prepreg thickness")
        self.txt_b  = field("Plane sep. B (mm):",     "0.2",   "stripline: total dielectric")
        self.txt_er = field("Dielectric constant εr:", "4.3",   "FR4 ≈ 4.3, Rogers ≈ 3.5")
        self.txt_s  = field("Gap S (mm) [diff only]:", "0.15",  "edge-to-edge spacing")

        z0_box.Add(gs, 0, wx.EXPAND | wx.ALL, 8)

        self.btn_calc = wx.Button(b2, label="⚡ Calculate Z₀")
        self.btn_calc.SetBackgroundColour(wx.Colour(14, 52, 96))
        self.btn_calc.SetForegroundColour(wx.WHITE)
        z0_box.Add(self.btn_calc, 0, wx.EXPAND | wx.ALL, 6)

        # Result
        res_row = wx.BoxSizer(wx.HORIZONTAL)
        res_row.Add(wx.StaticText(b2, label="Z₀ ="), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.lbl_z0 = wx.StaticText(b2, label="—")
        self.lbl_z0.SetFont(wx.Font(18, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.lbl_z0.SetForegroundColour(wx.Colour(233, 69, 96))
        res_row.Add(self.lbl_z0, 0, wx.ALIGN_CENTER_VERTICAL)
        z0_box.Add(res_row, 0, wx.ALL, 8)

        left.Add(z0_box, 0, wx.EXPAND | wx.ALL, 6)

        # Analysis type stubs
        anal_box = wx.StaticBoxSizer(wx.VERTICAL, self, "SI Analysis Type")
        b3 = anal_box.GetStaticBox()
        anal_box.Add(wx.StaticText(b3, label="Select analysis to run:"), 0, wx.ALL, 6)

        self.rb_tdr    = wx.RadioButton(b3, label="TDR — Time-Domain Reflectometry",          style=wx.RB_GROUP)
        self.rb_sparam = wx.RadioButton(b3, label="S-Parameters (Touchstone .s2p/.s4p)")
        self.rb_xtalk  = wx.RadioButton(b3, label="Crosstalk (NEXT / FEXT)")
        self.rb_eye    = wx.RadioButton(b3, label="Eye Diagram (PRBS7/15/31)")

        for rb in (self.rb_tdr, self.rb_sparam, self.rb_xtalk, self.rb_eye):
            anal_box.Add(rb, 0, wx.LEFT | wx.BOTTOM, 8)

        stub_note = wx.StaticText(b3, label="  ℹ Full wave solver arrives in Phase 16.")
        stub_note.SetForegroundColour(wx.Colour(120, 140, 200))
        anal_box.Add(stub_note, 0, wx.LEFT | wx.BOTTOM, 8)

        self.btn_run_si = wx.Button(b3, label="▶ Run SI Analysis (Phase 16)")
        self.btn_run_si.Enable(False)
        anal_box.Add(self.btn_run_si, 0, wx.EXPAND | wx.ALL, 6)

        left.Add(anal_box, 0, wx.EXPAND | wx.ALL, 6)
        outer.Add(left, 0, wx.EXPAND)

        # ---------- RIGHT: output / results ----------
        right = wx.BoxSizer(wx.VERTICAL)

        # Z0 vs W sweep chart (static text placeholder until Phase 16)
        chart_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Z₀ vs Trace Width Sweep")
        b4 = chart_box.GetStaticBox()

        try:
            import matplotlib
            matplotlib.use("WXAgg")
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigCanvas

            self.fig = Figure(facecolor="#0e0e1a", tight_layout=True)
            self.ax  = self.fig.add_subplot(111)
            self.ax.set_facecolor("#0e0e1a")
            self.ax.tick_params(colors="#d4d4e8", labelsize=8)
            self.ax.set_xlabel("Width W (mm)", color="#d4d4e8")
            self.ax.set_ylabel("Z₀ (Ω)", color="#d4d4e8")
            self.ax.set_title("Z₀ vs Trace Width", color="#d4d4e8")
            self.ax.grid(color="#2a2a3f", lw=0.5, ls="--")
            self.canvas = FigCanvas(b4, -1, self.fig)
            chart_box.Add(self.canvas, 1, wx.EXPAND)
            self._has_chart = True
        except Exception:
            chart_box.Add(wx.StaticText(b4, label="matplotlib required for chart."), 0, wx.ALL, 10)
            self._has_chart = False

        right.Add(chart_box, 1, wx.EXPAND | wx.ALL, 6)

        # Results console
        cons_box = wx.StaticBoxSizer(wx.VERTICAL, self, "SI Analysis Log")
        self.txt_si_log = wx.TextCtrl(cons_box.GetStaticBox(), style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2, size=(-1, 140))
        self.txt_si_log.SetBackgroundColour(wx.Colour(10, 10, 20))
        self.txt_si_log.SetForegroundColour(wx.Colour(200, 220, 255))
        self.txt_si_log.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.txt_si_log.SetValue(
            "[SPIKE SI] Workspace ready.\n"
            "[SPIKE SI] Z₀ calculator is fully operational.\n"
            "[SPIKE SI] TDR / S-param / Eye Diagram engine — Phase 16.\n"
        )
        cons_box.Add(self.txt_si_log, 1, wx.EXPAND | wx.ALL, 4)
        right.Add(cons_box, 0, wx.EXPAND | wx.ALL, 6)

        outer.Add(right, 1, wx.EXPAND)
        self.SetSizer(outer)

        # Bindings
        self.btn_calc.Bind(wx.EVT_BUTTON, self._on_calc)
        self.rb_ms.Bind(wx.EVT_RADIOBUTTON,  self._on_mode)
        self.rb_sl.Bind(wx.EVT_RADIOBUTTON,  self._on_mode)
        self.rb_dms.Bind(wx.EVT_RADIOBUTTON, self._on_mode)

        self._on_mode(None)
        self._sweep_chart()

    # ------------------------------------------------------------------
    def _on_mode(self, event):
        is_sl  = self.rb_sl.GetValue()
        is_dms = self.rb_dms.GetValue()
        self.txt_b.Enable(is_sl)
        self.txt_s.Enable(is_dms)

    def _on_calc(self, event):
        try:
            w  = float(self.txt_w.GetValue())
            h  = float(self.txt_h.GetValue())
            er = float(self.txt_er.GetValue())

            if self.rb_ms.GetValue():
                z = microstrip_z0(w, h, er)
                mode = "Microstrip"
            elif self.rb_sl.GetValue():
                b = float(self.txt_b.GetValue())
                z = stripline_z0(w, b, er)
                mode = "Stripline"
            else:
                z0_se = microstrip_z0(w, h, er)
                s = float(self.txt_s.GetValue())
                z = diff_microstrip_z0(z0_se, s, h)
                mode = "Diff Microstrip"

            self.lbl_z0.SetLabel(f"{z:.1f} Ω")
            color = wx.Colour(40, 167, 69) if 85 <= z <= 115 else wx.Colour(233, 69, 96)
            self.lbl_z0.SetForegroundColour(color)

            self.txt_si_log.AppendText(
                f"\n[Z0 Calc] Mode: {mode} | W={w} H={h} εr={er} → Z₀ = {z:.2f} Ω"
            )
            self._sweep_chart()

        except Exception as e:
            self.lbl_z0.SetLabel("Error")
            self.txt_si_log.AppendText(f"\n[Z0 Calc] Error: {e}")

    def _sweep_chart(self):
        if not self._has_chart:
            return
        try:
            import numpy as np
            er = float(self.txt_er.GetValue() or 4.3)
            h  = float(self.txt_h.GetValue()  or 0.1)

            widths = np.linspace(0.05, 1.0, 80)
            if self.rb_sl.GetValue():
                b = float(self.txt_b.GetValue() or 0.2)
                z_vals = [stripline_z0(w, b, er) for w in widths]
                label  = f"Stripline (b={b}mm, εr={er})"
            else:
                z_vals = [microstrip_z0(w, h, er) for w in widths]
                label  = f"Microstrip (H={h}mm, εr={er})"

            self.ax.clear()
            self.ax.set_facecolor("#0e0e1a")
            self.ax.tick_params(colors="#d4d4e8", labelsize=8)
            self.ax.set_xlabel("Width W (mm)", color="#d4d4e8")
            self.ax.set_ylabel("Z₀ (Ω)", color="#d4d4e8")
            self.ax.set_title("Z₀ vs Trace Width", color="#d4d4e8")
            self.ax.grid(color="#2a2a3f", lw=0.5, ls="--")
            self.ax.plot(widths, z_vals, color="#00bfff", lw=2, label=label)
            self.ax.axhline(50,  color="#e94560", lw=1, ls="--", label="50 Ω")
            self.ax.axhline(75,  color="#ffd700", lw=1, ls="--", label="75 Ω")
            self.ax.axhline(100, color="#90EE90", lw=1, ls="--", label="100 Ω")
            self.ax.legend(facecolor="#0e0e1a", labelcolor="#d4d4e8", fontsize=7)
            self.canvas.draw()
        except Exception:
            pass

    def populate_nets(self, net_names):
        """Called by main window after board load."""
        self.cb_net.SetItems(sorted(net_names))
        if net_names:
            self.cb_net.SetSelection(0)
