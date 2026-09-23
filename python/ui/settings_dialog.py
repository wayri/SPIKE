"""
SPIKE Settings Dialog
Tabbed settings covering General, Solver, Console, Display, and Units.
"""
import wx
import json
import os
from pathlib import Path

# Default settings
DEFAULTS = {
    # General
    "default_project_path": str(Path.home() / "Documents"),
    "auto_save_interval": 5,
    "recent_files_max": 10,
    # Solver
    "default_mesh_mm": "0.05",
    "default_cu_mm": "0.035",
    "max_threads": 8,
    "gmres_tolerance": "1e-6",
    "preconditioner": "ILU",
    "solver_engine": "Auto",
    # Console
    "log_verbosity": "INFO",
    "log_to_file": False,
    "log_file_path": "",
    "max_log_lines": 5000,
    # Display
    "theme": "Dark",
    "heatmap_colormap": "Inferno",
    "font_scale": 1.0,
    # Units
    "unit_length": "mm",
    "unit_current_density": "A/mm²",
    "unit_impedance": "mΩ",
    "unit_frequency": "Hz",
}

# Global settings dict (loaded once)
_settings = dict(DEFAULTS)
_settings_path = Path(__file__).parent.parent.parent / "spike_settings.json"


def load_settings():
    global _settings
    if _settings_path.exists():
        try:
            with open(_settings_path) as f:
                loaded = json.load(f)
            _settings.update(loaded)
        except Exception:
            pass
    return _settings


def save_settings():
    try:
        with open(_settings_path, "w") as f:
            json.dump(_settings, f, indent=2)
    except Exception as e:
        print(f"[SPIKE] Warning: Could not save settings: {e}")


def get(key, default=None):
    return _settings.get(key, DEFAULTS.get(key, default))


def set_val(key, value):
    _settings[key] = value


# Load on import
load_settings()


# ---------------------------------------------------------------------------
# Theme palette helpers
# ---------------------------------------------------------------------------

DARK_BG  = wx.Colour(22, 22, 38)
DARK_PANEL = wx.Colour(30, 30, 50)
DARK_ACCENT = wx.Colour(233, 69, 96)     # #E94560
DARK_TEXT = wx.Colour(220, 220, 235)
DARK_BORDER = wx.Colour(60, 60, 85)

LIGHT_BG = wx.Colour(245, 245, 250)
LIGHT_PANEL = wx.Colour(255, 255, 255)
LIGHT_ACCENT = wx.Colour(70, 70, 200)
LIGHT_TEXT = wx.Colour(20, 20, 30)
LIGHT_BORDER = wx.Colour(200, 200, 210)


def apply_theme(window, theme="Dark"):
    """Recursively apply colour theme to a window and all children."""
    bg  = DARK_BG    if theme == "Dark" else LIGHT_BG
    fg  = DARK_TEXT  if theme == "Dark" else LIGHT_TEXT
    _apply_recursive(window, bg, fg)


def _apply_recursive(win, bg, fg):
    try:
        win.SetBackgroundColour(bg)
        win.SetForegroundColour(fg)
    except Exception:
        pass
    for child in win.GetChildren():
        _apply_recursive(child, bg, fg)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class SettingsDialog(wx.Dialog):
    """Full-featured application settings dialog."""

    def __init__(self, parent):
        super().__init__(parent, title="SPIKE Settings",
                         size=(760, 600),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetMinSize((700, 540))
        self._build_ui()
        self._load_current()
        self.CentreOnParent()
        self.Layout()
        self.Fit()

    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = wx.BoxSizer(wx.VERTICAL)

        # Tab book
        self.nb = wx.Notebook(self)
        self.nb.AddPage(self._make_general(),  "General")
        self.nb.AddPage(self._make_solver(),   "Solver")
        self.nb.AddPage(self._make_console(),  "Console")
        self.nb.AddPage(self._make_display(),  "Display")
        self.nb.AddPage(self._make_units(),    "Units")
        outer.Add(self.nb, 1, wx.EXPAND | wx.ALL, 8)

        # Buttons
        btn_sizer = wx.StdDialogButtonSizer()
        ok  = wx.Button(self, wx.ID_OK,     "Apply & Close")
        rst = wx.Button(self, wx.ID_RESET,  "Reset to Defaults")
        can = wx.Button(self, wx.ID_CANCEL, "Cancel")
        ok.SetDefault()
        btn_sizer.AddButton(ok)
        btn_sizer.AddButton(rst)
        btn_sizer.AddButton(can)
        btn_sizer.Realize()
        outer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizer(outer)

        ok.Bind(wx.EVT_BUTTON,  self._on_ok)
        rst.Bind(wx.EVT_BUTTON, self._on_reset)

    # ------------------------------------------------------------------
    # Page builders
    def _make_general(self):
        p = wx.Panel(self.nb)
        gs = wx.FlexGridSizer(0, 2, 10, 12)
        gs.AddGrowableCol(1)

        gs.Add(wx.StaticText(p, label="Default project folder:"), flag=wx.ALIGN_CENTER_VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_proj_path = wx.TextCtrl(p, size=(300, -1))
        btn_browse = wx.Button(p, label="…", size=(30, -1))
        btn_browse.Bind(wx.EVT_BUTTON, self._browse_proj_path)
        row.Add(self.txt_proj_path, 1, wx.EXPAND | wx.RIGHT, 4)
        row.Add(btn_browse)
        gs.Add(row, flag=wx.EXPAND)

        gs.Add(wx.StaticText(p, label="Auto-save interval (min):"), flag=wx.ALIGN_CENTER_VERTICAL)
        self.sp_autosave = wx.SpinCtrl(p, min=0, max=60, initial=5)
        gs.Add(self.sp_autosave)

        gs.Add(wx.StaticText(p, label="Recent files limit:"), flag=wx.ALIGN_CENTER_VERTICAL)
        self.sp_recent = wx.SpinCtrl(p, min=1, max=50, initial=10)
        gs.Add(self.sp_recent)

        wrap = wx.BoxSizer(wx.VERTICAL)
        wrap.Add(gs, 0, wx.ALL, 15)
        p.SetSizer(wrap)
        return p

    def _make_solver(self):
        p = wx.Panel(self.nb)
        gs = wx.FlexGridSizer(0, 2, 10, 12)
        gs.AddGrowableCol(1)

        def row(label, widget):
            gs.Add(wx.StaticText(p, label=label), flag=wx.ALIGN_CENTER_VERTICAL)
            gs.Add(widget, flag=wx.EXPAND)

        self.txt_mesh   = wx.TextCtrl(p, value="0.05")
        self.txt_cu     = wx.TextCtrl(p, value="0.035")
        self.sp_threads = wx.SpinCtrl(p, min=1, max=64, initial=8)
        self.txt_tol    = wx.TextCtrl(p, value="1e-6")
        self.cb_precond = wx.Choice(p, choices=["ILU", "Jacobi", "None"])
        self.cb_engine  = wx.Choice(p, choices=["Auto", "Dense Direct (<2k nodes)", "Sparse Iterative (>10k nodes)"])

        row("Default mesh resolution (mm):", self.txt_mesh)
        row("Default copper thickness (mm):", self.txt_cu)
        row("Max CPU threads:",  self.sp_threads)
        row("GMRES tolerance:",  self.txt_tol)
        row("Preconditioner:",   self.cb_precond)
        row("Default engine:",   self.cb_engine)

        wrap = wx.BoxSizer(wx.VERTICAL)
        wrap.Add(gs, 0, wx.ALL, 15)
        p.SetSizer(wrap)
        return p

    def _make_console(self):
        p = wx.Panel(self.nb)
        gs = wx.FlexGridSizer(0, 2, 10, 12)
        gs.AddGrowableCol(1)

        self.cb_verbosity = wx.Choice(p, choices=["DEBUG", "INFO", "WARNING", "ERROR"])
        gs.Add(wx.StaticText(p, label="Log verbosity:"), flag=wx.ALIGN_CENTER_VERTICAL)
        gs.Add(self.cb_verbosity, flag=wx.EXPAND)

        self.chk_log_file = wx.CheckBox(p, label="Log to file")
        gs.Add(self.chk_log_file, flag=wx.ALIGN_CENTER_VERTICAL)
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_log_path = wx.TextCtrl(p, size=(250, -1))
        btn_log = wx.Button(p, label="…", size=(30, -1))
        btn_log.Bind(wx.EVT_BUTTON, self._browse_log_path)
        row.Add(self.txt_log_path, 1, wx.EXPAND | wx.RIGHT, 4)
        row.Add(btn_log)
        gs.Add(row, flag=wx.EXPAND)

        self.sp_maxlines = wx.SpinCtrl(p, min=500, max=100000, initial=5000)
        gs.Add(wx.StaticText(p, label="Max console lines:"), flag=wx.ALIGN_CENTER_VERTICAL)
        gs.Add(self.sp_maxlines, flag=wx.EXPAND)

        wrap = wx.BoxSizer(wx.VERTICAL)
        wrap.Add(gs, 0, wx.ALL, 15)
        p.SetSizer(wrap)
        return p

    def _make_display(self):
        p = wx.Panel(self.nb)
        gs = wx.FlexGridSizer(0, 2, 10, 12)
        gs.AddGrowableCol(1)

        self.cb_theme    = wx.Choice(p, choices=["Dark", "Light"])
        self.cb_colormap = wx.Choice(p, choices=["Inferno", "Plasma", "Viridis", "Magma", "Jet", "Hot"])
        self.sl_font     = wx.Slider(p, value=100, minValue=75, maxValue=150)
        self.lbl_font_val = wx.StaticText(p, label="100%")
        self.sl_font.Bind(wx.EVT_SLIDER, lambda e: self.lbl_font_val.SetLabel(f"{self.sl_font.GetValue()}%"))

        def row(label, widget):
            gs.Add(wx.StaticText(p, label=label), flag=wx.ALIGN_CENTER_VERTICAL)
            gs.Add(widget, flag=wx.EXPAND)

        row("Color theme:",          self.cb_theme)
        row("Heatmap colormap:",     self.cb_colormap)
        gs.Add(wx.StaticText(p, label="Font scale:"),  flag=wx.ALIGN_CENTER_VERTICAL)
        font_row = wx.BoxSizer(wx.HORIZONTAL)
        font_row.Add(self.sl_font, 1, wx.EXPAND | wx.RIGHT, 8)
        font_row.Add(self.lbl_font_val, 0, wx.ALIGN_CENTER_VERTICAL)
        gs.Add(font_row, flag=wx.EXPAND)

        wrap = wx.BoxSizer(wx.VERTICAL)
        wrap.Add(gs, 0, wx.ALL, 15)
        p.SetSizer(wrap)
        return p

    def _make_units(self):
        p = wx.Panel(self.nb)
        gs = wx.FlexGridSizer(0, 2, 10, 12)
        gs.AddGrowableCol(1)

        self.cb_unit_len  = wx.Choice(p, choices=["mm", "mil", "μm", "m"])
        self.cb_unit_jden = wx.Choice(p, choices=["A/mm²", "A/mil²", "mA/mm²", "A/m²", "kA/m²"])
        self.cb_unit_imp  = wx.Choice(p, choices=["mΩ", "Ω", "kΩ", "μΩ"])
        self.cb_unit_freq = wx.Choice(p, choices=["Hz", "kHz", "MHz", "GHz"])

        def row(label, widget):
            gs.Add(wx.StaticText(p, label=label), flag=wx.ALIGN_CENTER_VERTICAL)
            gs.Add(widget, flag=wx.EXPAND)

        row("Length unit:",           self.cb_unit_len)
        row("Current density unit:",  self.cb_unit_jden)
        row("Impedance unit:",        self.cb_unit_imp)
        row("Frequency unit:",        self.cb_unit_freq)

        wrap = wx.BoxSizer(wx.VERTICAL)
        wrap.Add(gs, 0, wx.ALL, 15)
        p.SetSizer(wrap)
        return p

    # ------------------------------------------------------------------
    # Populate controls from stored settings
    def _load_current(self):
        self.txt_proj_path.SetValue(get("default_project_path"))
        self.sp_autosave.SetValue(get("auto_save_interval"))
        self.sp_recent.SetValue(get("recent_files_max"))

        self.txt_mesh.SetValue(get("default_mesh_mm"))
        self.txt_cu.SetValue(get("default_cu_mm"))
        self.sp_threads.SetValue(get("max_threads"))
        self.txt_tol.SetValue(get("gmres_tolerance"))
        _sel(self.cb_precond, get("preconditioner"))
        _sel(self.cb_engine,  get("solver_engine"))

        _sel(self.cb_verbosity, get("log_verbosity"))
        self.chk_log_file.SetValue(get("log_to_file"))
        self.txt_log_path.SetValue(get("log_file_path"))
        self.sp_maxlines.SetValue(get("max_log_lines"))

        _sel(self.cb_theme,    get("theme"))
        _sel(self.cb_colormap, get("heatmap_colormap"))
        self.sl_font.SetValue(int(get("font_scale") * 100))
        self.lbl_font_val.SetLabel(f"{self.sl_font.GetValue()}%")

        _sel(self.cb_unit_len,  get("unit_length"))
        _sel(self.cb_unit_jden, get("unit_current_density"))
        _sel(self.cb_unit_imp,  get("unit_impedance"))
        _sel(self.cb_unit_freq, get("unit_frequency"))

    # ------------------------------------------------------------------
    # Write controls back to global settings
    def _save_to_settings(self):
        set_val("default_project_path", self.txt_proj_path.GetValue())
        set_val("auto_save_interval",   self.sp_autosave.GetValue())
        set_val("recent_files_max",     self.sp_recent.GetValue())

        set_val("default_mesh_mm",  self.txt_mesh.GetValue())
        set_val("default_cu_mm",    self.txt_cu.GetValue())
        set_val("max_threads",      self.sp_threads.GetValue())
        set_val("gmres_tolerance",  self.txt_tol.GetValue())
        set_val("preconditioner",   self.cb_precond.GetString(self.cb_precond.GetSelection()))
        set_val("solver_engine",    self.cb_engine.GetString(self.cb_engine.GetSelection()))

        set_val("log_verbosity",  self.cb_verbosity.GetString(self.cb_verbosity.GetSelection()))
        set_val("log_to_file",    self.chk_log_file.GetValue())
        set_val("log_file_path",  self.txt_log_path.GetValue())
        set_val("max_log_lines",  self.sp_maxlines.GetValue())

        set_val("theme",           self.cb_theme.GetString(self.cb_theme.GetSelection()))
        set_val("heatmap_colormap",self.cb_colormap.GetString(self.cb_colormap.GetSelection()))
        set_val("font_scale",      self.sl_font.GetValue() / 100.0)

        set_val("unit_length",           self.cb_unit_len.GetString(self.cb_unit_len.GetSelection()))
        set_val("unit_current_density",  self.cb_unit_jden.GetString(self.cb_unit_jden.GetSelection()))
        set_val("unit_impedance",        self.cb_unit_imp.GetString(self.cb_unit_imp.GetSelection()))
        set_val("unit_frequency",        self.cb_unit_freq.GetString(self.cb_unit_freq.GetSelection()))

        save_settings()

    # ------------------------------------------------------------------
    def _on_ok(self, event):
        self._save_to_settings()
        self.EndModal(wx.ID_OK)

    def _on_reset(self, event):
        global _settings
        _settings = dict(DEFAULTS)
        self._load_current()

    def _browse_proj_path(self, event):
        dlg = wx.DirDialog(self, "Select default project folder",
                           defaultPath=self.txt_proj_path.GetValue())
        if dlg.ShowModal() == wx.ID_OK:
            self.txt_proj_path.SetValue(dlg.GetPath())
        dlg.Destroy()

    def _browse_log_path(self, event):
        dlg = wx.FileDialog(self, "Select log file", wildcard="Log files (*.log)|*.log",
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            self.txt_log_path.SetValue(dlg.GetPath())
        dlg.Destroy()


def _sel(choice_ctrl, value):
    """Helper: select a choice item by string value."""
    idx = choice_ctrl.FindString(str(value))
    if idx != wx.NOT_FOUND:
        choice_ctrl.SetSelection(idx)
    else:
        choice_ctrl.SetSelection(0)
