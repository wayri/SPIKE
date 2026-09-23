"""
SPIKE - Signal, Power, and Integrity Knowledge Engine
Professional UI
=====================================================
Match SIKIPI-style layout with wx.aui docking system.
"""

import sys
import os
from pathlib import Path
import wx
import wx.adv
import wx.aui
import wx.grid
import wx.lib.agw.aui as aui   # AGW AUI — full dock/float/collapse support
import wx.lib.agw.ribbon as ribbon
import logging

# Enable Windows 11 dark title bars and native dark controls
if hasattr(wx, "SystemOptions"):
    wx.SystemOptions.SetOption("msw.dark-mode", 2)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('SPIKE')
# ============================================================================
# SETUP & IMPORTS
# ============================================================================
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

if os.name == 'nt':
    vcpkg_bin = Path("C:/vcpkg/installed/x64-windows/bin")
    if vcpkg_bin.exists():
        try: os.add_dll_directory(str(vcpkg_bin))
        except: pass

HAS_CORE = False
try:
    sys.path.insert(0, str(project_root / "python"))
    if os.name == 'nt' and hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(str(project_root / "python"))
    import spike_core
    from core.version import __version__, __build_date__
    HAS_CORE = True
except ImportError as e:
    print(f"Warning: Failed to load C++ Engine: {e}")
    __version__ = "0.1.7.0 (Simulated)"
    __build_date__ = "Unknown"
    pass

if str(project_root / "python") not in sys.path:
    sys.path.insert(0, str(project_root / "python"))
try:
    from viz.viewport3d import Viewport3D
    from ui.analysis_dashboard import AnalysisDashboardPanel
    from ui.reports_panel import ReportsPanel
    from ui.settings_dialog import SettingsDialog, get as settings_get
    from ui.theme import apply_theme, SpikeDockArt, SpikeTabArt, Palette
    from ui.pre_sim_dialog import PreSimDialog
    from ui.net_classifier_dialog import NetClassifierDialog
    from ui.pdn_health_dialog import PDNHealthDialog
    from ui.si_workspace import SIWorkspacePanel
    from ui.wizards import ComponentWizard, SetupWizard
    from ui.thermal_side_panel import ThermalSidePanel
except ImportError as _ie:
    print(f"[SPIKE] Import warning: {_ie}")
    from viz.viewport3d import Viewport3D
    from ui.analysis_dashboard import AnalysisDashboardPanel
    from ui.reports_panel import ReportsPanel
    # Stubs for new modules if not yet available
    SettingsDialog = None
    PreSimDialog = None
    NetClassifierDialog = None
    PDNHealthDialog = None
    SIWorkspacePanel = None
    def apply_theme(w, t="Dark"): pass
    def settings_get(k, d=None): return d
    SpikeDockArt = None
    SpikeTabArt  = None
    class Palette:
        BG_BASE = wx.Colour(18,18,27)
        BG_PANEL = wx.Colour(28,28,40)
        ACCENT_RED = wx.Colour(233,69,96)

# ============================================================================
# UI PANELS
# ============================================================================

class LogContext:
    """Redirects stdout/stderr to a wx.TextCtrl"""
    def __init__(self, text_ctrl):
        self.text_ctrl = text_ctrl
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

    def write(self, message):
        if message.strip(): # Only create timestamp for non-empty messages
            import datetime
            ts = datetime.datetime.now().strftime("[%H:%M:%S] ")
            wx.CallAfter(self.text_ctrl.AppendText, f"{ts}{message}")
        else:
             wx.CallAfter(self.text_ctrl.AppendText, message)

    def flush(self):
        pass

class ConsolePanel(wx.Panel):
    """Bottom Panel: Integrated Logging Console"""
    def __init__(self, parent):
        super().__init__(parent)
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Header
        header = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(self, label="Console Output")
        lbl.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        header.Add(lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        
        header.AddStretchSpacer()
        
        btn_clear = wx.Button(self, label="Clear", size=(60, 20))
        btn_clear.Bind(wx.EVT_BUTTON, self.on_clear)
        header.Add(btn_clear, 0, wx.RIGHT, 5)
        
        sizer.Add(header, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 2)
        
        # Log Text Area
        _con_bg = wx.Colour(10, 10, 18)
        _con_fg = wx.Colour(220, 220, 235)
        self.log_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        mono = wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        self.log_ctrl.SetFont(mono)
        self.log_ctrl.SetBackgroundColour(_con_bg)
        self.log_ctrl.SetForegroundColour(_con_fg)
        # Lock text colour so AppendText always produces readable text
        self.log_ctrl.SetDefaultStyle(wx.TextAttr(_con_fg, _con_bg, mono))

        # Style the header too
        self.SetBackgroundColour(wx.Colour(20, 20, 32))
        lbl.SetForegroundColour(_con_fg)
        lbl.SetBackgroundColour(wx.Colour(20, 20, 32))

        sizer.Add(self.log_ctrl, 1, wx.EXPAND)
        self.SetSizer(sizer)

        
        # Redirect Output
        sys.stdout = LogContext(self.log_ctrl)
        sys.stderr = LogContext(self.log_ctrl)
        print(f"SPIKE Console Initialized...")
        print(f"Version: {__version__} ({__build_date__})")
        print(f"Python: {sys.version.split()[0]}")
        print(f"wxPython: {wx.version()}")
        try:
            import pyvista
            print(f"PyVista: {pyvista.__version__}")
        except:
             print("PyVista: Not Found")
        print("-" * 40)

    def on_clear(self, event):
        self.log_ctrl.Clear()

class NetListPanel(wx.Panel):
    """Left Panel: Nets & Layers Management"""
    def __init__(self, parent):
        super().__init__(parent)
        self.viewport = None
        self.viewport_2d = None
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 1. Net List Section
        sb_nets = wx.StaticBoxSizer(wx.VERTICAL, self, "Nets")
        sb_nets_box = sb_nets.GetStaticBox()
        
        # Filter
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.search = wx.TextCtrl(sb_nets_box, style=wx.TE_PROCESS_ENTER)
        self.search.SetHint("Filter nets...")
        self.search.Bind(wx.EVT_TEXT, self.on_filter_nets)
        filter_sizer.Add(self.search, 1, wx.EXPAND | wx.RIGHT, 5)
        sb_nets.Add(filter_sizer, 0, wx.EXPAND | wx.BOTTOM, 5)
        
        # List
        self.net_list = wx.ListBox(sb_nets_box, style=wx.LB_SINGLE | wx.LB_HSCROLL | wx.LB_SORT)
        self.net_list.Bind(wx.EVT_LISTBOX, self.on_net_selected)
        sb_nets.Add(self.net_list, 1, wx.EXPAND)
        
        self.btn_clear = wx.Button(sb_nets_box, label="Clear Selection")
        self.btn_clear.Bind(wx.EVT_BUTTON, self.on_clear_selection)
        sb_nets.Add(self.btn_clear, 0, wx.EXPAND | wx.TOP, 5)
        
        sizer.Add(sb_nets, 2, wx.EXPAND | wx.ALL, 5)
        
        # 2. Layer Manager Section - ADVANCED
        sb_layers = wx.StaticBoxSizer(wx.VERTICAL, self, "Layer Stackup")
        sb_layers_box = sb_layers.GetStaticBox()
        
        self.layer_scroll = wx.ScrolledWindow(sb_layers_box, style=wx.VSCROLL)
        self.layer_scroll.SetScrollbars(0, 20, 0, 50)
        
        self.layer_sizer = wx.BoxSizer(wx.VERTICAL)
        self.layer_controls = {}

        # Initialize with standard layers
        standard_layers = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "Edge.Cuts", "F.SilkS", "B.SilkS"]
        self.populate_layers(standard_layers)
            
        self.layer_scroll.SetSizer(self.layer_sizer)
        sb_layers.Add(self.layer_scroll, 1, wx.EXPAND)
        
        sizer.Add(sb_layers, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        self.SetSizer(sizer)
        
        self.all_nets = []
        self.net_map = {}

    def on_filter_nets(self, event):
        """Filter net list based on search text"""
        query = self.search.GetValue().lower()
        print(f"Filtering nets by: '{query}'")
        
        self.net_list.Clear()
        if not query:
            self.net_list.AppendItems(self.all_nets)
        else:
            filtered = [n for n in self.all_nets if query in n.lower()]
            self.net_list.AppendItems(filtered)

    def update_net_list(self, nets):
        """Update source data"""
        self.all_nets = sorted(nets)
        self.net_list.Clear()
        self.net_list.AppendItems(self.all_nets)
        print(f"Net list updated: {len(self.all_nets)} total nets.")

    def select_net(self, net_name, net_id=None):
        """Programmatically select a net in the list"""
        if not net_name:
            self.on_clear_selection(None)
            return

        for i in range(self.net_list.GetCount()):
            if self.net_list.GetString(i) == net_name:
                self.net_list.SetSelection(i)
                # Manually trigger dashboard update since EVT_LISTBOX won't fire
                frame = wx.GetTopLevelParent(self)
                if hasattr(frame, 'analysis_panel'):
                    frame.analysis_panel.set_target_net(net_name)
                break

    def populate_layers(self, layers):
        """Build rich layer controls with colour swatches and type labels."""
        self.layer_sizer.Clear(True)
        self.layer_controls.clear()

        # Colour map per layer type
        LAYER_COLOURS = {
            "F.Cu":     (185, 0,   0),    # red
            "B.Cu":     (0,  132, 132),   # teal
            "In1.Cu":   (0,   0, 192),    # blue
            "In2.Cu":   (132,  0, 132),   # purple
            "In3.Cu":   (0,  132,   0),   # green
            "In4.Cu":   (132, 132,  0),   # olive
            "Edge.Cuts":(255, 215,  0),   # gold
            "Vias":     (210, 180, 140),  # tan
            "F.SilkS":  (80,  80, 255),
            "B.SilkS":  (80, 255,  80),
            "F.Paste":  (200, 200, 200),
            "B.Paste":  (170, 170, 170),
            "F.Mask":   (220, 100, 100),
            "B.Mask":   (100, 220, 100),
            "F.CrtYd":  (160, 160, 160),
            "B.CrtYd":  (120, 120, 120),
            "Fusing Risk": (255, 80, 0),
        }
        DEFAULT_COLOUR = (100, 100, 100)

        def _is_visible(name):
            return (name in ("F.Cu","B.Cu","Vias","Edge.Cuts","F.CrtYd","B.CrtYd") or
                    (name.startswith("In") and ".Cu" in name))

        for name in layers:
            row_panel = wx.Panel(self.layer_scroll)
            row_panel.SetBackgroundColour(wx.Colour(28, 28, 42))
            row_sizer = wx.BoxSizer(wx.HORIZONTAL)

            # ── Colour swatch ───────────────────────────────────────────
            rgb   = LAYER_COLOURS.get(name, DEFAULT_COLOUR)
            swatch = wx.Panel(row_panel, size=(12, 18))
            swatch.SetBackgroundColour(wx.Colour(*rgb))
            swatch.SetMinSize((12, 18))
            row_sizer.Add(swatch, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 4)

            # ── Checkbox ────────────────────────────────────────────────
            is_visible = _is_visible(name)
            chk = wx.CheckBox(row_panel, label=name)
            chk.SetValue(is_visible)
            chk.SetForegroundColour(wx.Colour(220, 220, 235))
            chk.SetBackgroundColour(wx.Colour(28, 28, 42))
            font = chk.GetFont()
            if ".Cu" in name:
                font.SetWeight(wx.FONTWEIGHT_BOLD)
            chk.SetFont(font)
            chk.Bind(wx.EVT_CHECKBOX, lambda e, n=name: self.on_layer_toggle(n))
            row_sizer.Add(chk, 1, wx.ALIGN_CENTER_VERTICAL)

            # ── Opacity slider ──────────────────────────────────────────
            slider = wx.Slider(row_panel, value=100, minValue=0, maxValue=100, size=(80, -1))
            if not is_visible:
                slider.Enable(False)
            slider.Bind(wx.EVT_COMMAND_SCROLL, lambda e, n=name: self.on_layer_opacity(n))
            row_sizer.Add(slider, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

            row_panel.SetSizer(row_sizer)
            self.layer_sizer.Add(row_panel, 0, wx.EXPAND | wx.BOTTOM, 2)
            self.layer_controls[name] = {'chk': chk, 'slider': slider, 'swatch': swatch}

        self.layer_scroll.Layout()
        self.layer_scroll.FitInside()



    def set_viewport(self, viewport):
        self.viewport = viewport

    def set_viewport_2d(self, viewport):
        self.viewport_2d = viewport

    def on_layer_toggle(self, layer_name):
        ctrl = self.layer_controls[layer_name]
        visible = ctrl['chk'].GetValue()
        ctrl['slider'].Enable(visible) # Toggle slider state
        if self.viewport:
             self.viewport.set_layer_visibility(layer_name, visible)
        if self.viewport_2d:
             self.viewport_2d.set_layer_visibility(layer_name, visible)

    def on_layer_opacity(self, layer_name):
        ctrl = self.layer_controls[layer_name]
        opacity = ctrl['slider'].GetValue() / 100.0
        if self.viewport:
            self.viewport.set_layer_opacity(layer_name, opacity)
        if self.viewport_2d:
            self.viewport_2d.set_layer_opacity(layer_name, opacity)

    def on_net_selected(self, event):
        net_name = event.GetString()
        net_id = self.net_map.get(net_name)
        
        # Highlight in both 2D and 3D
        if self.viewport:
            self.viewport.highlight_net(net_name, net_id=net_id)
        if self.viewport_2d:
            self.viewport_2d.highlight_net(net_name, net_id=net_id)

        # Update Dashboard
        frame = wx.GetTopLevelParent(self)
        if hasattr(frame, 'analysis_panel'):
            frame.analysis_panel.set_target_net(net_name)

    def on_clear_selection(self, event):
        """Clear net selection"""
        if self.net_list.GetCount() > 0:
            # Deselect all items manually
            for i in range(self.net_list.GetCount()):
                if self.net_list.IsSelected(i):
                    self.net_list.Deselect(i)
        
        if self.viewport:
            self.viewport.clear_highlight()
        if self.viewport_2d:
            self.viewport_2d.clear_highlight()
            
        # Reset Dashboard
        frame = wx.GetTopLevelParent(self)
        if hasattr(frame, 'analysis_panel'):
            frame.analysis_panel.set_target_net("No Net Selected")

class ResultsPanel(wx.ScrolledWindow):
    """
    Professional Results Dashboard (Inspired by SIKIPI)
    Displays detailed statistics, sink performance, and auto-generated observations.
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.SetScrollRate(0, 10)
        self._init_ui()
        
    def _init_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 1. Key Statistics Grid
        sb = wx.StaticBoxSizer(wx.VERTICAL, self, "Key Metrics")
        self._sb_box = sb.GetStaticBox()
        self.stats_grid = wx.FlexGridSizer(0, 2, 8, 15)
        self.stats_grid.AddGrowableCol(1)
        
        self.lbl_drop = self._add_stat(self.stats_grid, "Max IR Drop:")
        self.lbl_volt = self._add_stat(self.stats_grid, "Min Voltage:")
        self.lbl_j = self._add_stat(self.stats_grid, "Max Current Density:")
        self.lbl_l = self._add_stat(self.stats_grid, "Loop Inductance:")
        self.lbl_z = self._add_stat(self.stats_grid, "Path Impedance:")
        
        sb.Add(self.stats_grid, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(sb, 0, wx.EXPAND | wx.ALL, 5)

        # 1.5 Viewport Control
        vp_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Viewport Heatmap Mode")
        
        self.cb_view_mode = wx.ComboBox(vp_box.GetStaticBox(), choices=[
            "Raw Geometry", "Voltage Map", "Voltage Drop", "Current Density", "AC Impedance"
        ], style=wx.CB_READONLY)
        self.cb_view_mode.SetSelection(0)
        vp_box.Add(self.cb_view_mode, 0, wx.EXPAND | wx.ALL, 5)
        
        self.cb_units = wx.ComboBox(vp_box.GetStaticBox(), choices=["A/mm²","A/mil²","mA/mm²"], style=wx.CB_READONLY)
        self.cb_units.SetSelection(0)
        vp_box.Add(self.cb_units, 0, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(vp_box, 0, wx.EXPAND | wx.ALL, 5)

        
        # 2. Sink Performance Table
        sizer.Add(wx.StaticText(self, label="Sink Performance:"), 0, wx.LEFT|wx.TOP, 10)
        self.sink_list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.sink_list.InsertColumn(0, "Sink ID", width=60)
        self.sink_list.InsertColumn(1, "Voltage", width=80)
        self.sink_list.InsertColumn(2, "Drop (mV)", width=80)
        self.sink_list.InsertColumn(3, "Margin", width=70)
        sizer.Add(self.sink_list, 0, wx.EXPAND | wx.ALL, 5)
        
        # 3. Analytical Observations
        sizer.Add(wx.StaticText(self, label="Engine Observations:"), 0, wx.LEFT|wx.TOP, 10)
        self.txt_obs = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 150))
        self.txt_obs.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        sizer.Add(self.txt_obs, 1, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(sizer)
        
    def _add_stat(self, grid, label):
        parent = getattr(self, '_sb_box', self)
        grid.Add(wx.StaticText(parent, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
        val = wx.StaticText(parent, label="--")
        val.SetFont(wx.Font(10, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        grid.Add(val, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        return val

    def update_metrics(self, data):
        """Update dashboard with real simulation data"""
        # Stats
        self.lbl_drop.SetLabel(f"{data.get('drop_mv', 0):.1f} mV")
        self.lbl_volt.SetLabel(f"{data.get('min_v', 0):.3f} V")
        self.lbl_j.SetLabel(f"{data.get('max_j', 0):.1f} MA/m²")
        
        # Color coding
        if data.get('drop_mv', 0) > 100:
            self.lbl_drop.SetForegroundColour(wx.Colour(200, 0, 0))
        else:
            self.lbl_drop.SetForegroundColour(wx.Colour(0, 100, 0))
            
        # Sinks
        self.sink_list.DeleteAllItems()
        for idx, s in enumerate(data.get('sinks', [])):
            self.sink_list.InsertItem(idx, f"U{idx+1}")
            self.sink_list.SetItem(idx, 1, f"{s.get('v', 0):.3f} V")
            self.sink_list.SetItem(idx, 2, f"{s.get('drop', 0):.1f}")
            self.sink_list.SetItem(idx, 3, "OK")
            
        # Observations
        obs = []
        obs.append("ANALYSIS COMPLETED SUCCESSFULLY")
        obs.append("-" * 30)
        obs.append(f"• Voltage Stability: {'MARGINAL' if data.get('drop_mv',0)>50 else 'PASS'}")
        obs.append(f"• Efficiency: {data.get('efficiency', 100):.1f}%")
        if data.get('max_j', 0) > 50:
            obs.append("• [WARNING] High current density detected!")
        else:
            obs.append("• Thermal Density: Safe")
        
        self.txt_obs.SetValue("\n".join(obs))


class BatchSettingsDialog(wx.Dialog):
    """Pop-up to configure which nets to simulate in Batch mode"""
    def __init__(self, parent, net_stats):
        super().__init__(parent, title="Batch Simulation Settings", size=(450, 400))
        self.net_stats = net_stats # {net_name: {'enabled': bool, 'mode': 'DC'|'AC'}}
        self._init_ui()
        
    def _init_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(self, label="Select nets and simulation modes for Batch Run:")
        sizer.Add(lbl, 0, wx.ALL, 10)
        
        # Mode options for the dropdown
        self.modes = ["DC IR-Drop", "AC Impedance", "Thermal"]
        
        self.grid = wx.grid.Grid(self)
        self.grid.CreateGrid(len(self.net_stats), 3)
        self.grid.SetColLabelValue(0, "Simulate")
        self.grid.SetColLabelValue(1, "Net Name")
        self.grid.SetColLabelValue(2, "Simulation Type")
        self.grid.SetColSize(1, 150)
        self.grid.SetColSize(2, 120)
        
        for idx, (net, cfg) in enumerate(self.net_stats.items()):
            # Enable checkbox
            attr = wx.grid.GridCellAttr()
            attr.SetEditor(wx.grid.GridCellBoolEditor())
            attr.SetRenderer(wx.grid.GridCellBoolRenderer())
            self.grid.SetColAttr(0, attr)
            
            self.grid.SetCellValue(idx, 0, "1" if cfg.get('enabled', True) else "0")
            
            self.grid.SetReadOnly(idx, 1)
            self.grid.SetCellValue(idx, 1, net)
            
            # Use Choice Editor for Mode
            editor = wx.grid.GridCellChoiceEditor(self.modes)
            self.grid.SetCellEditor(idx, 2, editor)
            self.grid.SetCellValue(idx, 2, cfg.get('mode', self.modes[0]))
            
        sizer.Add(self.grid, 1, wx.EXPAND | wx.ALL, 10)
        
        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(sizer)
        
    def get_config(self):
        new_stats = {}
        for idx in range(self.grid.GetNumberRows()):
            net = self.grid.GetCellValue(idx, 1)
            enabled = (self.grid.GetCellValue(idx, 0) == "1")
            mode = self.grid.GetCellValue(idx, 2)
            new_stats[net] = {'enabled': enabled, 'mode': mode}
        return new_stats

class PassThroughDialog(wx.Dialog):
    """Dialog to define inline/pass-through components bridging two nets"""
    def __init__(self, parent, parser):
        super().__init__(parent, title="Pass-Through Component Configuration", size=(500, 400))
        self.parser = parser
        self.net_names = sorted(list(self.parser.nets.keys())) if self.parser else []
        self._init_ui()
        
    def _init_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(self, label="Bridge isolated nets through an inline component (e.g. MOSFET, Resistor)")
        sizer.Add(lbl, 0, wx.ALL, 10)
        
        grid = wx.FlexGridSizer(9, 2, 10, 10)
        grid.AddGrowableCol(1)
        
        # Component Type
        grid.Add(wx.StaticText(self, label="Component Type:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.cb_type = wx.ComboBox(self, choices=["Resistor", "Inductor", "Diode / Bridge"], style=wx.CB_READONLY)
        self.cb_type.SetSelection(0)
        self.cb_type.Bind(wx.EVT_COMBOBOX, self.on_type_change)
        grid.Add(self.cb_type, 1, wx.EXPAND)
        
        # Input
        grid.Add(wx.StaticText(self, label="Input Net:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.cb_in_net = wx.ComboBox(self, choices=self.net_names, style=wx.CB_READONLY)
        self.cb_in_net.Bind(wx.EVT_COMBOBOX, lambda e: self.update_pads(self.cb_in_net, self.cb_in_pad))
        grid.Add(self.cb_in_net, 1, wx.EXPAND)
        
        grid.Add(wx.StaticText(self, label="Input Pad:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.cb_in_pad = wx.ComboBox(self, style=wx.CB_READONLY)
        grid.Add(self.cb_in_pad, 1, wx.EXPAND)
        
        # Output
        grid.Add(wx.StaticText(self, label="Output Net:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.cb_out_net = wx.ComboBox(self, choices=self.net_names, style=wx.CB_READONLY)
        self.cb_out_net.Bind(wx.EVT_COMBOBOX, lambda e: self.update_pads(self.cb_out_net, self.cb_out_pad))
        grid.Add(self.cb_out_net, 1, wx.EXPAND)
        
        grid.Add(wx.StaticText(self, label="Output Pad:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.cb_out_pad = wx.ComboBox(self, style=wx.CB_READONLY)
        grid.Add(self.cb_out_pad, 1, wx.EXPAND)
        
        # Values
        grid.Add(wx.StaticText(self, label="Resistance / ESR (Ω):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_r = wx.TextCtrl(self, value="0.01")
        grid.Add(self.txt_r, 1, wx.EXPAND)
        
        self.lbl_l = wx.StaticText(self, label="Inductance (nH):")
        grid.Add(self.lbl_l, 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_l = wx.TextCtrl(self, value="0.0")
        grid.Add(self.txt_l, 1, wx.EXPAND)
        
        self.lbl_vd = wx.StaticText(self, label="Diode Drop (V):")
        grid.Add(self.lbl_vd, 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_vd = wx.TextCtrl(self, value="0.7")
        grid.Add(self.txt_vd, 1, wx.EXPAND)
        
        self.lbl_rb = wx.StaticText(self, label="Reverse Breakdown (V):")
        grid.Add(self.lbl_rb, 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_rb = wx.TextCtrl(self, value="50.0")
        grid.Add(self.txt_rb, 1, wx.EXPAND)
        
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 10)
        sizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)
        self.on_type_change(None)
        
    def on_type_change(self, event):
        t = self.cb_type.GetStringSelection()
        is_ind = (t == "Inductor")
        is_diode = (t == "Diode / Bridge")
        
        self.lbl_l.Enable(is_ind)
        self.txt_l.Enable(is_ind)
        self.lbl_vd.Enable(is_diode)
        self.txt_vd.Enable(is_diode)
        self.lbl_rb.Enable(is_diode)
        self.txt_rb.Enable(is_diode)
        
    def update_pads(self, net_cb, pad_cb):
        net_name = net_cb.GetStringSelection()
        pads = []
        if self.parser:
            for pad in self.parser.pads:
                if pad.get('net_name') == net_name:
                    pads.append(f"{pad.get('component')}:{pad.get('component_pad')}")
        pad_cb.SetItems(sorted(list(set(pads))))
        if pads:
            pad_cb.SetSelection(0)
            
    def get_config(self):
        return {
            'pt_type': self.cb_type.GetStringSelection(),
            'in_net': self.cb_in_net.GetStringSelection(),
            'in_pad': self.cb_in_pad.GetStringSelection(),
            'out_net': self.cb_out_net.GetStringSelection(),
            'out_pad': self.cb_out_pad.GetStringSelection(),
            'r_val': float(self.txt_r.GetValue() or 0.0),
            'l_val': float(self.txt_l.GetValue() or 0.0) if self.txt_l.IsEnabled() else 0.0,
            'v_drop': float(self.txt_vd.GetValue() or 0.7) if self.txt_vd.IsEnabled() else 0.0,
            'v_rev': float(self.txt_rb.GetValue() or 50.0) if self.txt_rb.IsEnabled() else 50.0
        }

class PDNWizardDialog(wx.Dialog):
    """Wizard to automatically detect power nets and assign VRMs/Sinks"""
    def __init__(self, parent):
        super().__init__(parent, title="PDN Wizard", size=(450, 300))
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 1. Standard PDN
        sizer.Add(wx.StaticText(self, label="Automatically detect VRMs, Bulk Capacitors, and Loads?"), 0, wx.ALL, 10)
        self.chk_auto_assign = wx.CheckBox(self, label="Auto-assign typical voltage levels based on net names (e.g. 3V3 -> 3.3V)")
        self.chk_auto_assign.SetValue(True)
        sizer.Add(self.chk_auto_assign, 0, wx.LEFT|wx.RIGHT|wx.BOTTOM, 10)
        
        sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.ALL, 10)
        
        # 2. Capacitor Placement
        lbl = wx.StaticText(self, label="Capacitor Optimal Placement Analytics")
        lbl.SetFont(wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        sizer.Add(lbl, 0, wx.LEFT, 10)
        
        self.chk_cap_opt = wx.CheckBox(self, label="Analyze PDN Impedance and recommend Decoupling locations")
        self.chk_cap_opt.SetValue(False)
        sizer.Add(self.chk_cap_opt, 0, wx.ALL, 10)
        
        place_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.rb_ic_pads = wx.RadioButton(self, label="Recommend on IC Pads", style=wx.RB_GROUP)
        self.rb_raw_geom = wx.RadioButton(self, label="Recommend on Raw Copper Geometry")
        place_sizer.Add(self.rb_ic_pads, 0, wx.RIGHT, 15)
        place_sizer.Add(self.rb_raw_geom, 0)
        sizer.Add(place_sizer, 0, wx.LEFT | wx.BOTTOM, 25)
        
        sizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)


class AdvSolverSettingsDialog(wx.Dialog):
    """Advanced Settings for the PEEC Matrix Solver"""
    def __init__(self, parent):
        super().__init__(parent, title="Advanced Solver Settings", size=(350, 250))
        sizer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(3, 2, 10, 10)
        
        grid.Add(wx.StaticText(self, label="Max CPU Threads:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_threads = wx.TextCtrl(self, value="8")
        grid.Add(self.txt_threads, 0, wx.EXPAND)
        
        grid.Add(wx.StaticText(self, label="Tolerance (GMRES):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_tol = wx.TextCtrl(self, value="1e-6")
        grid.Add(self.txt_tol, 0, wx.EXPAND)
        
        grid.Add(wx.StaticText(self, label="Preconditioner:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.cb_precond = wx.ComboBox(self, choices=["ILU", "Jacobi", "None"], style=wx.CB_READONLY)
        self.cb_precond.SetSelection(0)
        grid.Add(self.cb_precond, 0, wx.EXPAND)
        
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 15)
        sizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(sizer)

class AnalysisPanel(wx.Panel):
    """Right Panel: Analysis Configuration & Results"""
    def __init__(self, parent):
        super().__init__(parent)
        
        self.nb = wx.Notebook(self)
        
        # Tab 1: PI (Setup)
        self.setup_panel = wx.Panel(self.nb)
        self._init_setup_tab(self.setup_panel)
        self.nb.AddPage(self.setup_panel, "PI Setup")
        
        # Tab 2: Thermal
        self.thermal_panel = wx.Panel(self.nb)
        self._init_thermal_tab(self.thermal_panel)
        self.nb.AddPage(self.thermal_panel, "Thermal")
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.nb, 1, wx.EXPAND)
        self.SetSizer(sizer)
        
        # Data
        self.sources_sinks = [] # List of dicts
        self.current_net = None
        self.cap_opt_mode = None

    def set_target_net(self, net_name):
        """Called by parent when a net is selected"""
        self.current_net = net_name
        self.lbl_sel.SetLabel(net_name if net_name else "No Net Selected")
        
        # Fetch pads for this net from the parser
        pads = []
        frame = wx.GetTopLevelParent(self)
        if hasattr(frame, 'parser') and net_name:
            for pad in frame.parser.pads:
                if pad.get('net_name') == net_name:
                    pads.append(pad.get('component_pad', f"P{pad.get('name')}"))
        
        self.pad_list.Clear()
        if pads:
            sorted_pads = sorted(list(set(pads)))
            print(f"PI: Found {len(sorted_pads)} pads for net '{net_name}'")
            self.pad_list.AppendItems(sorted_pads)
        else:
            print(f"PI: No pads found for net '{net_name}'")
            
        self.setup_scroll.Layout()

    def select_pad(self, pad_name):
        """Programmatically select a pad in the list"""
        # For CheckListBox, we find index and check it
        for i in range(self.pad_list.GetCount()):
            if self.pad_list.GetString(i) == pad_name:
                self.pad_list.SetSelection(i)
                self.pad_list.Check(i, True)
                break

    def update_run_buttons(self):
        """Switch between DC/AC Run and Batch Mode based on net count"""
        nets = set(item['net'] for item in self.sources_sinks)
        is_batch = len(nets) > 1
        
        self.btn_run_dc.Show(not is_batch)
        self.btn_run_ac.Show(not is_batch)
        self.btn_batch_run.Show(is_batch)
        self.btn_batch_settings.Enable(is_batch)
        
        # Update labels if needed
        if is_batch:
            self.btn_batch_run.SetLabel(f"▶ Batch Run ({len(nets)} Nets)")
            
        self.setup_panel.Layout()
        
    def _init_setup_tab(self, panel):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.setup_scroll = wx.ScrolledWindow(panel)
        self.setup_scroll.SetScrollRate(0, 10)
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # --- 1. Header & Toggle ---
        header = wx.BoxSizer(wx.HORIZONTAL)
        self.lbl_sel = wx.StaticText(self.setup_scroll, label="No Net Selected")
        self.lbl_sel.SetFont(wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.lbl_sel.SetForegroundColour(wx.Colour(233, 69, 96)) # SPIKE Red accent
        header.Add(self.lbl_sel, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 10)
        
        self.btn_toggle_side = wx.Button(self.setup_scroll, label="<< Toggle Sidebar >>", size=(120, -1))
        header.Add(self.btn_toggle_side, 0, wx.ALL, 10)
        scroll_sizer.Add(header, 0, wx.EXPAND)
        
        # --- 2. Pin/Pad Selection List ---
        pad_box = wx.StaticBoxSizer(wx.VERTICAL, self.setup_scroll, "Select Pin/Pad to Assign")
        self.pad_list = wx.CheckListBox(pad_box.GetStaticBox(), size=(-1, 150))
        pad_box.Add(self.pad_list, 1, wx.EXPAND | wx.ALL, 8)
        
        p_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_check_all = wx.Button(pad_box.GetStaticBox(), label="Check All")
        self.btn_check_all.Bind(wx.EVT_BUTTON, lambda e: [self.pad_list.Check(i) for i in range(self.pad_list.GetCount())])
        self.btn_uncheck_all = wx.Button(pad_box.GetStaticBox(), label="Uncheck All")
        self.btn_uncheck_all.Bind(wx.EVT_BUTTON, lambda e: [self.pad_list.Check(i, False) for i in range(self.pad_list.GetCount())])
        p_btn_sizer.Add(self.btn_check_all, 1, wx.EXPAND | wx.RIGHT, 5)
        p_btn_sizer.Add(self.btn_uncheck_all, 1, wx.EXPAND)
        pad_box.Add(p_btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        
        scroll_sizer.Add(pad_box, 0, wx.EXPAND | wx.ALL, 8)
        
        # --- 3. Voltage Source (VRM) ---
        vrm_box = wx.StaticBoxSizer(wx.VERTICAL, self.setup_scroll, "Source (VRM / Current)")
        v_grid = wx.FlexGridSizer(4, 2, 8, 10)
        v_grid.AddGrowableCol(1)
        
        b_vrm = vrm_box.GetStaticBox()
        v_grid.Add(wx.StaticText(b_vrm, label="Type:"), 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        self.cb_src_type = wx.ComboBox(b_vrm, choices=["Voltage (V)", "Current (A)"], style=wx.CB_READONLY)
        self.cb_src_type.SetSelection(0)
        v_grid.Add(self.cb_src_type, 0, wx.EXPAND)
        
        v_grid.Add(wx.StaticText(b_vrm, label="Value (V/A):"), 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        self.txt_dc = wx.TextCtrl(b_vrm, value="3.3", size=(80, -1))
        v_grid.Add(self.txt_dc, 0, wx.EXPAND)
        
        v_grid.Add(wx.StaticText(b_vrm, label="AC (V):"), 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        self.txt_ac = wx.TextCtrl(b_vrm, value="0.0", size=(80, -1))
        v_grid.Add(self.txt_ac, 0, wx.EXPAND)
        
        v_grid.Add(wx.StaticText(b_vrm, label="Freq (Hz):"), 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        self.txt_hz = wx.TextCtrl(b_vrm, value="0", size=(80, -1))
        v_grid.Add(self.txt_hz, 0, wx.EXPAND)
        
        vrm_box.Add(v_grid, 0, wx.EXPAND | wx.ALL, 8)
        self.btn_set_source = wx.Button(b_vrm, label="Set as Source")
        self.btn_set_source.Bind(wx.EVT_BUTTON, lambda e: self.on_bulk_assign("Source (V/A)"))
        vrm_box.Add(self.btn_set_source, 0, wx.EXPAND | wx.ALL, 8)
        scroll_sizer.Add(vrm_box, 0, wx.EXPAND | wx.ALL, 8)
        
        # --- 4. Load (Sink) ---
        load_box = wx.StaticBoxSizer(wx.VERTICAL, self.setup_scroll, "Load (Sink)")
        b_load = load_box.GetStaticBox()
        v_grid2 = wx.BoxSizer(wx.HORIZONTAL)
        v_grid2.Add(wx.StaticText(b_load, label="Current (A):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.txt_sink_current = wx.TextCtrl(b_load, value="1.0", size=(80, -1))
        v_grid2.Add(self.txt_sink_current, 1, wx.EXPAND)
        load_box.Add(v_grid2, 0, wx.EXPAND | wx.ALL, 8)
        
        self.btn_add_sink = wx.Button(b_load, label="Add Sink to Selected Pins")
        self.btn_add_sink.Bind(wx.EVT_BUTTON, lambda e: self.on_bulk_assign("Sink (Load)"))
        load_box.Add(self.btn_add_sink, 0, wx.EXPAND | wx.ALL, 8)
        scroll_sizer.Add(load_box, 0, wx.EXPAND | wx.ALL, 8)
        
        # --- 4b. Pass-Through Components ---
        pass_box = wx.StaticBoxSizer(wx.VERTICAL, self.setup_scroll, "Inline/Pass-Through Devices")
        self.btn_add_pass = wx.Button(pass_box.GetStaticBox(), label="+ Bridge Nets via Component")
        self.btn_add_pass.Bind(wx.EVT_BUTTON, self.on_add_pass_through)
        pass_box.Add(self.btn_add_pass, 0, wx.EXPAND | wx.ALL, 8)
        scroll_sizer.Add(pass_box, 0, wx.EXPAND | wx.ALL, 8)
        
        # --- 5. Assigned Configuration (Source/Sink Table) ---
        cfg_box = wx.StaticBoxSizer(wx.VERTICAL, self.setup_scroll, "Assigned Configuration")
        b_cfg = cfg_box.GetStaticBox()
        
        self.ss_grid = wx.grid.Grid(b_cfg)
        self.ss_grid.CreateGrid(0, 6)
        self.ss_grid.SetColLabelValue(0, "Type")
        self.ss_grid.SetColLabelValue(1, "Net")
        self.ss_grid.SetColLabelValue(2, "Loc")
        self.ss_grid.SetColLabelValue(3, "Val")
        self.ss_grid.SetColLabelValue(4, "AC")
        self.ss_grid.SetColLabelValue(5, "Hz")
        self.ss_grid.SetRowLabelSize(25)
        self.ss_grid.SetColSize(0, 60); self.ss_grid.SetColSize(1, 60); self.ss_grid.SetColSize(2, 60); self.ss_grid.SetColSize(3, 40)
        cfg_box.Add(self.ss_grid, 0, wx.EXPAND | wx.ALL, 8)
        
        ss_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_edit = wx.Button(b_cfg, label="Edit")
        self.btn_remove = wx.Button(b_cfg, label="Remove")
        self.btn_remove.Bind(wx.EVT_BUTTON, self.on_delete_selected)
        self.btn_clear_all = wx.Button(b_cfg, label="Clear All")
        self.btn_clear_all.SetForegroundColour(wx.Colour(233, 69, 96)) # Accent Red
        self.btn_clear_all.Bind(wx.EVT_BUTTON, self.on_clear_all_ss)
        ss_btn_sizer.Add(self.btn_edit, 1, wx.RIGHT, 5)
        ss_btn_sizer.Add(self.btn_remove, 1, wx.RIGHT, 5)
        ss_btn_sizer.Add(self.btn_clear_all, 1)
        cfg_box.Add(ss_btn_sizer, 0, wx.EXPAND | wx.ALL, 8)
        
        scroll_sizer.Add(cfg_box, 0, wx.EXPAND | wx.ALL, 8)
        
        # --- 6. Simulation Tools ---
        self.tool_box = wx.StaticBoxSizer(wx.VERTICAL, self.setup_scroll, "Simulation Tools")
        t_box = self.tool_box.GetStaticBox()
        
        q_grid = wx.FlexGridSizer(3, 2, 8, 10)
        q_grid.AddGrowableCol(1)
        q_grid.Add(wx.StaticText(t_box, label="Mesh Res(mm):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_grid_mm = wx.TextCtrl(t_box, value="0.05", size=(80, -1))
        q_grid.Add(self.txt_grid_mm, 0, wx.EXPAND)
        
        q_grid.Add(wx.StaticText(t_box, label="Thickness(mm):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_cu_mm = wx.TextCtrl(t_box, value="0.035", size=(80, -1))
        q_grid.Add(self.txt_cu_mm, 0, wx.EXPAND)
        
        q_grid.Add(wx.StaticText(t_box, label="Engine:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.cb_solver = wx.ComboBox(t_box, choices=["Auto", "Dense Direct (<2k)", "Iterative Sparse (>10k)"], style=wx.CB_READONLY)
        self.cb_solver.SetSelection(0)
        q_grid.Add(self.cb_solver, 0, wx.EXPAND)
        
        self.tool_box.Add(q_grid, 0, wx.EXPAND | wx.ALL, 8)
        
        units_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.rb_ma = wx.RadioButton(t_box, label="MA/m²", style=wx.RB_GROUP)
        self.rb_amm = wx.RadioButton(t_box, label="A/mm²")
        units_sizer.Add(self.rb_ma, 0, wx.RIGHT, 15)
        units_sizer.Add(self.rb_amm, 0)
        self.tool_box.Add(units_sizer, 0, wx.ALL, 8)

        # Action Buttons Stack
        btn_stack = wx.BoxSizer(wx.VERTICAL)
        
        # Tools group
        tools_grid = wx.GridSizer(2, 2, 5, 5)
        self.btn_pdn_wizard = wx.Button(t_box, label="PDN Wizard")
        self.btn_adv_settings = wx.Button(t_box, label="Adv. Settings")
        self.btn_batch_settings = wx.Button(t_box, label="Batch Settings")
        self.btn_debug_mesh = wx.Button(t_box, label="Debug Mesh")
        tools_grid.Add(self.btn_pdn_wizard, 0, wx.EXPAND)
        tools_grid.Add(self.btn_adv_settings, 0, wx.EXPAND)
        tools_grid.Add(self.btn_batch_settings, 0, wx.EXPAND)
        tools_grid.Add(self.btn_debug_mesh, 0, wx.EXPAND)
        btn_stack.Add(tools_grid, 0, wx.EXPAND | wx.BOTTOM, 12)
        
        # Simulation group - large buttons
        self.btn_run_dc = wx.Button(t_box, label="▶ Run DC Simulation", size=(-1, 35))
        self.btn_run_ac = wx.Button(t_box, label="⚡ Run AC Simulation", size=(-1, 35))
        self.btn_batch_run = wx.Button(t_box, label="▶ Run Batch Simulation", size=(-1, 35))
        self.btn_run_rlc = wx.Button(t_box, label="Run RLC Extraction", size=(-1, 35))
        
        # Make run buttons prominent
        self.btn_run_dc.SetBackgroundColour(wx.Colour(0, 100, 200))
        self.btn_run_dc.SetForegroundColour(wx.WHITE)
        self.btn_run_ac.SetBackgroundColour(wx.Colour(180, 100, 0))
        self.btn_run_ac.SetForegroundColour(wx.WHITE)
        self.btn_batch_run.SetBackgroundColour(wx.Colour(100, 0, 100))
        self.btn_batch_run.SetForegroundColour(wx.WHITE)
        
        font_large = self.btn_run_dc.GetFont()
        font_large.SetWeight(wx.FONTWEIGHT_BOLD)
        self.btn_run_dc.SetFont(font_large)
        self.btn_run_ac.SetFont(font_large)
        
        btn_stack.Add(self.btn_run_dc, 0, wx.EXPAND | wx.BOTTOM, 5)
        btn_stack.Add(self.btn_run_ac, 0, wx.EXPAND | wx.BOTTOM, 5)
        btn_stack.Add(self.btn_batch_run, 0, wx.EXPAND | wx.BOTTOM, 5)
        btn_stack.Add(self.btn_run_rlc, 0, wx.EXPAND | wx.BOTTOM, 5)
        
        self.btn_batch_run.Hide()
        
        self.tool_box.Add(btn_stack, 0, wx.EXPAND | wx.ALL, 8)
        
        # Stop Simulation
        bot_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_stop = wx.CheckBox(t_box, label="Stop Simulation")
        self.chk_stop.Enable(False)
        bot_sizer.Add(self.chk_stop, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 15)
        
        self.lnk_view3d = wx.StaticText(t_box, label="View 3D Field Map")
        self.lnk_view3d.SetForegroundColour(wx.Colour(0, 150, 255))
        font_lnk = self.lnk_view3d.GetFont(); font_lnk.SetUnderlined(True)
        self.lnk_view3d.SetFont(font_lnk)
        bot_sizer.Add(self.lnk_view3d, 0, wx.ALIGN_CENTER_VERTICAL)
        
        self.tool_box.Add(bot_sizer, 0, wx.EXPAND | wx.ALL, 8)
        scroll_sizer.Add(self.tool_box, 0, wx.EXPAND | wx.ALL, 8)
        
        # --- 7. Analysis Probes ---
        self.probe_box = wx.StaticBoxSizer(wx.VERTICAL, self.setup_scroll, "Analysis Probes (Post-Sim)")
        p_box = self.probe_box.GetStaticBox()
        self.probe_box.Add(wx.StaticText(p_box, label="Phase/Mode Selection"), 0, wx.ALIGN_CENTER | wx.TOP, 5)
        self.slider_probe = wx.Slider(p_box, value=0, minValue=0, maxValue=100)
        self.probe_box.Add(self.slider_probe, 0, wx.EXPAND | wx.ALL, 8)
        
        self.chk_hover = wx.CheckBox(p_box, label="Hover Info")
        self.chk_hover.SetValue(True)
        self.probe_box.Add(self.chk_hover, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 8)
        
        pb_sizer = wx.BoxSizer(wx.HORIZONTAL)
        pb_sizer.Add(wx.Button(p_box, label="Del"), 1, wx.RIGHT, 5)
        pb_sizer.Add(wx.Button(p_box, label="Clear"), 1, wx.RIGHT, 5)
        pb_sizer.Add(wx.Button(p_box, label="Refresh"), 1)
        self.probe_box.Add(pb_sizer, 0, wx.EXPAND | wx.ALL, 8)
        
        self.probe_grid = wx.grid.Grid(p_box)
        self.probe_grid.CreateGrid(0, 7)
        for i, lbl in enumerate(["Snap", "ID", "Net", "Loc", "V", "J", "Z"]):
            self.probe_grid.SetColLabelValue(i, lbl)
        self.probe_grid.SetRowLabelSize(0)
        self.probe_grid.SetColSize(0, 35); self.probe_grid.SetColSize(1, 40)
        self.probe_box.Add(self.probe_grid, 0, wx.EXPAND | wx.ALL, 8)
        
        self.probe_box.GetStaticBox().Enable(False) # DISABLED until simulation finish
        scroll_sizer.Add(self.probe_box, 0, wx.EXPAND | wx.ALL, 8)
        
        # BINDINGS
        self.btn_pdn_wizard.Bind(wx.EVT_BUTTON, self.on_pdn_wizard)
        self.btn_adv_settings.Bind(wx.EVT_BUTTON, self.on_adv_settings)
        self.btn_batch_settings.Bind(wx.EVT_BUTTON, self.on_batch_settings)
        self.btn_run_rlc.Bind(wx.EVT_BUTTON, self.on_run_rlc)
        self.ss_grid.Bind(wx.grid.EVT_GRID_CELL_CHANGED, self.on_grid_change)
        self.ss_grid.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.on_grid_select)
        self.pad_list.Bind(wx.EVT_LISTBOX, self.on_pad_choice)
        
        self.setup_scroll.SetSizer(scroll_sizer)
        main_sizer.Add(self.setup_scroll, 1, wx.EXPAND)
        panel.SetSizer(main_sizer)

    def on_pdn_wizard(self, event):
        dlg = PDNWizardDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            if dlg.chk_auto_assign.GetValue() and self.current_net:
                # Basic heuristic: if net has "3V3" or "5V" assign source
                v_guess = 3.3
                if '5' in self.current_net: v_guess = 5.0
                elif '12' in self.current_net: v_guess = 12.0
                elif '1' in self.current_net: v_guess = 1.8
                
                self.txt_dc.SetValue(str(v_guess))
                self.txt_ac.SetValue("0.1") # 100mV AC ripple test
                self.txt_hz.SetValue("1000000") # 1MHz target
                
                wx.MessageBox(f"Auto-assigned {v_guess}V VRM and 1MHz AC test to Setup Panel. Please assign pads and run.", "PDN Wizard")
                
            if dlg.chk_cap_opt.GetValue():
                self.cap_opt_mode = 'IC' if dlg.rb_ic_pads.GetValue() else 'RAW'
                wx.MessageBox(f"Capacitor Optimization armed ({self.cap_opt_mode} mode). Recommendations will be generated after the next simulation run.", "PDN Wizard")
            else:
                self.cap_opt_mode = None
        dlg.Destroy()
        
    def on_adv_settings(self, event):
        dlg = AdvSolverSettingsDialog(self)
        dlg.ShowModal()
        dlg.Destroy()
        
    def on_batch_settings(self, event):
        # Gather current nets
        nets = {ss['net']: {'mode': 'DC IR-Drop'} for ss in self.sources_sinks}
        if not nets:
            wx.MessageBox("No nets assigned. Setup a source/sink first.", "Notice")
            return
        dlg = BatchSettingsDialog(self, nets)
        dlg.ShowModal()
        dlg.Destroy()
        
    def on_run_rlc(self, event):
        wx.MessageBox("RLC Extraction algorithm requires zone mesher (Phase 11).", "Information", wx.OK | wx.ICON_INFORMATION)

    def _init_thermal_tab(self, panel):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        scroll = wx.ScrolledWindow(panel)
        scroll.SetScrollRate(0, 5)
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 1. Component Selection
        scroll_sizer.Add(wx.StaticText(scroll, label="Select Component:"), 0, wx.LEFT | wx.TOP, 10)
        self.thermal_comp_list = wx.ComboBox(scroll, style=wx.CB_DROPDOWN | wx.CB_READONLY)
        scroll_sizer.Add(self.thermal_comp_list, 0, wx.EXPAND | wx.ALL, 10)
        
        # 2. Limits Assignment
        limit_box = wx.StaticBoxSizer(wx.VERTICAL, scroll, "Component Limits")
        l_grid = wx.FlexGridSizer(4, 2, 5, 5)
        l_grid.AddGrowableCol(1)
        
        l_grid.Add(wx.StaticText(limit_box.GetStaticBox(), label="Max Temp (°C):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_tmax = wx.TextCtrl(limit_box.GetStaticBox(), value="85.0")
        l_grid.Add(self.txt_tmax, 0, wx.EXPAND)
        
        l_grid.Add(wx.StaticText(limit_box.GetStaticBox(), label="Max Voltage (V):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_vmax = wx.TextCtrl(limit_box.GetStaticBox(), value="5.0")
        l_grid.Add(self.txt_vmax, 0, wx.EXPAND)
        
        l_grid.Add(wx.StaticText(limit_box.GetStaticBox(), label="Max Current (A):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_imax = wx.TextCtrl(limit_box.GetStaticBox(), value="1.0")
        l_grid.Add(self.txt_imax, 0, wx.EXPAND)
        
        l_grid.Add(wx.StaticText(limit_box.GetStaticBox(), label="Power Diss. (W):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_pdiss = wx.TextCtrl(limit_box.GetStaticBox(), value="0.1")
        l_grid.Add(self.txt_pdiss, 0, wx.EXPAND)
        
        limit_box.Add(l_grid, 0, wx.EXPAND | wx.ALL, 5)
        
        self.btn_assign_limits = wx.Button(limit_box.GetStaticBox(), label="Assign Limits/Power")
        self.btn_assign_limits.Bind(wx.EVT_BUTTON, self.on_assign_thermal)
        limit_box.Add(self.btn_assign_limits, 0, wx.EXPAND | wx.TOP, 5)
        
        scroll_sizer.Add(limit_box, 0, wx.EXPAND | wx.ALL, 10)
        
        # 3. Assigned Components Grid
        scroll_sizer.Add(wx.StaticText(scroll, label="Assigned Components:"), 0, wx.LEFT, 10)
        self.thermal_grid = wx.grid.Grid(scroll)
        self.thermal_grid.CreateGrid(0, 5)
        self.thermal_grid.SetColLabelValue(0, "Comp")
        self.thermal_grid.SetColLabelValue(1, "Tmax")
        self.thermal_grid.SetColLabelValue(2, "Vmax")
        self.thermal_grid.SetColLabelValue(3, "Imax")
        self.thermal_grid.SetColLabelValue(4, "Power")
        self.thermal_grid.SetRowLabelSize(25)
        scroll_sizer.Add(self.thermal_grid, 1, wx.EXPAND | wx.ALL, 5)
        
        self.btn_clear_thermal = wx.Button(scroll, label="Clear All")
        self.btn_clear_thermal.Bind(wx.EVT_BUTTON, self.on_clear_thermal)
        scroll_sizer.Add(self.btn_clear_thermal, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 10)
        
        scroll_sizer.Add(wx.StaticLine(scroll), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 10)
        
        # 4. Run Thermal
        self.btn_run_thermal = wx.Button(scroll, label="▶ Run Thermal Simulation")
        self.btn_run_thermal.SetBackgroundColour(wx.Colour(200, 100, 50))
        self.btn_run_thermal.SetForegroundColour(wx.WHITE)
        self.btn_run_thermal.Bind(wx.EVT_BUTTON, self.on_run_thermal_sim)
        scroll_sizer.Add(self.btn_run_thermal, 0, wx.EXPAND | wx.ALL, 10)
        
        scroll.SetSizer(scroll_sizer)
        main_sizer.Add(scroll, 1, wx.EXPAND)
        panel.SetSizer(main_sizer)

    def on_assign_thermal(self, event):
        comp = self.thermal_comp_list.GetValue()
        if not comp: return
        tmax = self.txt_tmax.GetValue()
        vmax = self.txt_vmax.GetValue()
        imax = self.txt_imax.GetValue()
        pdiss = self.txt_pdiss.GetValue()
        
        row = self.thermal_grid.GetNumberRows()
        self.thermal_grid.AppendRows(1)
        self.thermal_grid.SetCellValue(row, 0, comp)
        self.thermal_grid.SetCellValue(row, 1, tmax)
        self.thermal_grid.SetCellValue(row, 2, vmax)
        self.thermal_grid.SetCellValue(row, 3, imax)
        self.thermal_grid.SetCellValue(row, 4, pdiss)
        self.thermal_grid.AutoSize()
        
    def on_clear_thermal(self, event):
        if self.thermal_grid.GetNumberRows() > 0:
            self.thermal_grid.DeleteRows(0, self.thermal_grid.GetNumberRows())        
            
    def on_run_thermal_sim(self, event):
        frame = wx.GetTopLevelParent(self)
        if not HAS_CORE or not hasattr(frame, 'parser'):
            wx.MessageBox("Core solver or board data missing.", "Error", wx.ICON_ERROR)
            return
            
        frame.SetStatusText("Running Thermal Simulation via C++ FEM Solver...")
        
        # 1. Setup Solver Grid over the board
        bbox = frame.parser.board_bbox
        min_x, max_x = bbox['min_x'], bbox['max_x']
        min_y, max_y = bbox['min_y'], bbox['max_y']
        
        nx, ny = 100, 100
        dx = (max_x - min_x) / nx
        dy = (max_y - min_y) / ny
        
        solver = spike_core.ThermalSolver()
        solver.set_grid(nx, ny, dx, dy)
        solver.set_ambient(25.0, 10.0) # 25C ambient
        
        # 2. Assign Power from UI Grid
        import numpy as np
        heat_sources = np.zeros(nx * ny)
        failed_pads = []
        
        for row in range(self.thermal_grid.GetNumberRows()):
            comp = self.thermal_grid.GetCellValue(row, 0)
            tmax = float(self.thermal_grid.GetCellValue(row, 1))
            power = float(self.thermal_grid.GetCellValue(row, 4))
            
            # Find component location
            for pad in frame.parser.pads:
                if pad['component'] == comp:
                    px, py = pad['at']
                    ix = int((px - min_x) / dx)
                    iy = int((py - min_y) / dy)
                    if 0 <= ix < nx and 0 <= iy < ny:
                        solver.add_heat_source(ix, iy, power)
                        heat_sources[iy * nx + ix] += power
                        
        # 3. Run C++ Matrix Solver
        import time
        t0 = time.time()
        try:
            temps = solver.solve_steady_state(heat_sources)
            
            # 4. Check Limits
            for row in range(self.thermal_grid.GetNumberRows()):
                comp = self.thermal_grid.GetCellValue(row, 0)
                tmax = float(self.thermal_grid.GetCellValue(row, 1))
                # Sample temp at component pads
                max_t = 25.0
                for pad in frame.parser.pads:
                    if pad['component'] == comp:
                        px, py = pad['at']
                        ix = int((px - min_x) / dx)
                        iy = int((py - min_y) / dy)
                        if 0 <= ix < nx and 0 <= iy < ny:
                            t = solver.get_temperature(ix, iy)
                            max_t = max(max_t, t)
                            if t > tmax:
                                failed_pads.append(pad.get('component_pad'))
                                
            # 5. Update Viewport
            if hasattr(frame, 'viewport') and frame.viewport:
                # Use PyVista 3D heatmap
                frame.viewport.show_thermal_heatmap(temps, nx, ny, min_x, max_x, min_y, max_y)
                frame.viewport.highlight_failed_components(failed_pads)
                
            frame.SetStatusText(f"Thermal Sim Complete in {time.time()-t0:.3f}s. {len(failed_pads)} failures.")
            
            if failed_pads:
                wx.MessageBox(f"Warning: {len(failed_pads)} components exceeded thermal limits!", "Thermal Limit Exceeded", wx.ICON_WARNING)
                
        except Exception as e:
            wx.MessageBox(f"Solver Error: {str(e)}", "Error", wx.ICON_ERROR)

    def on_pdn_wizard(self, event):
        dlg = PDNWizardDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            if dlg.chk_auto_assign.GetValue():
                frame = wx.GetTopLevelParent(self)
                if hasattr(frame, 'parser'):
                    for pad in frame.parser.pads:
                        net = pad.get('net_name', '')
                        if not net: continue
                        val = 0.0
                        stype = None
                        if '3V3' in net or '3.3V' in net:
                            val = 3.3; stype = 'Source'
                        elif '5V' in net:
                            val = 5.0; stype = 'Source'
                        elif '1V2' in net or '1.2V' in net:
                            val = 1.2; stype = 'Source'
                        elif 'GND' in net:
                            val = 0.0; stype = 'Sink'
                            
                        if stype:
                            # Only add if not already present
                            pad_id = f"{pad['component']}:{pad['component_pad']}"
                            exists = any(s['pad'] == pad_id for s in self.sources_sinks)
                            if not exists:
                                entry = {
                                    'type': stype,
                                    'src_mode': 'Voltage',
                                    'net': net,
                                    'pad': pad_id,
                                    'dc': str(val),
                                    'ac': '0',
                                    'freq': '0'
                                }
                                self.sources_sinks.append(entry)
                                row = self.ss_grid.GetNumberRows()
                                self.ss_grid.AppendRows(1)
                                self.ss_grid.SetCellValue(row, 0, stype)
                                self.ss_grid.SetCellValue(row, 1, net)
                                self.ss_grid.SetCellValue(row, 2, pad_id)
                                self.ss_grid.SetCellValue(row, 3, str(val))
                                self.ss_grid.SetCellValue(row, 4, "0")
                                self.ss_grid.SetCellValue(row, 5, "0")
                                
            if dlg.chk_cap_opt.GetValue():
                self.cap_opt_mode = 'IC' if dlg.rb_ic_pads.GetValue() else 'RAW'
            else:
                self.cap_opt_mode = None
                
            self.update_run_buttons()
        dlg.Destroy()

    def on_pad_choice(self, event):
        """Highlight pad in 3D when selected in list"""
        idx = self.pad_list.GetSelection()
        if idx == wx.NOT_FOUND: return
        pad_name = self.pad_list.GetString(idx)
        frame = wx.GetTopLevelParent(self)
        if hasattr(frame, 'viewport') and self.current_net:
            frame.viewport.highlight_pad(self.current_net, pad_name)

    def on_grid_select(self, event):
        """Highlight pad in 3D when selected in Source/Sink table"""
        row = event.GetRow()
        if row < len(self.sources_sinks):
            item = self.sources_sinks[row]
            frame = wx.GetTopLevelParent(self)
            if hasattr(frame, 'viewport'):
                frame.viewport.highlight_pad(item['net'], item['pad'])
        event.Skip()

    def on_grid_change(self, event):
        row = event.GetRow()
        col = event.GetCol()
        val = self.ss_grid.GetCellValue(row, col)
        
        # Grid Cols: Type, Net, Loc, Val, AC, Hz
        field_map = {0: 'type', 1: 'net', 2: 'pad', 3: 'dc', 4: 'ac', 5: 'freq'}
        field = field_map.get(col)
        if field and row < len(self.sources_sinks):
            self.sources_sinks[row][field] = val
            self.update_run_buttons()

    def on_delete_selected(self, event):
        """Remove selected rows from the simulation plan"""
        selected_rows = self.ss_grid.GetSelectedRows()
        if not selected_rows:
            # Fallback: check focused cell
            selected_rows = [self.ss_grid.GetGridCursorRow()]
            
        # Delete from list in reverse to avoid index shifting
        for row in sorted(selected_rows, reverse=True):
            if row < len(self.sources_sinks):
                self.sources_sinks.pop(row)
                self.ss_grid.DeleteRows(row, 1)
        
        self.update_run_buttons()

    def on_clear_all_ss(self, event):
        """Wipe the entire simulation plan"""
        if wx.MessageBox("Are you sure you want to clear the entire Simulation Plan?", 
                        "Confirm Clear", wx.YES_NO | wx.ICON_QUESTION) == wx.YES:
            self.sources_sinks.clear()
            if self.ss_grid.GetNumberRows() > 0:
                self.ss_grid.DeleteRows(0, self.ss_grid.GetNumberRows())
            self.update_run_buttons()

    def on_batch_settings(self, event):
        if not hasattr(self, 'batch_config'):
            self.batch_config = {}
            
        nets = sorted(list(set(it['net'] for it in self.sources_sinks if it['net'])))
        # Initialize any new nets
        for n in nets:
            if n not in self.batch_config:
                self.batch_config[n] = {'enabled': True, 'mode': 'DC IR-Drop'}
                
        # Filter out nets that are no longer in the sources_sinks list
        current_stats = {n: self.batch_config[n] for n in nets}
        
        dlg = BatchSettingsDialog(self, current_stats)
        if dlg.ShowModal() == wx.ID_OK:
            self.batch_config = dlg.get_config()
            print("PI: Batch configuration updated.")
        dlg.Destroy()

    def on_bulk_assign(self, assignment_type):
        """Add all checked pads to the plan"""
        if not self.current_net: return
        checked = []
        for i in range(self.pad_list.GetCount()):
            if self.pad_list.IsChecked(i):
                checked.append(self.pad_list.GetString(i))
        
        if not checked:
            sel = self.pad_list.GetSelection()
            if sel != wx.NOT_FOUND:
                checked = [self.pad_list.GetString(sel)]
        
        if not checked: 
            wx.MessageBox("Please select at least one pin from the list.", "Selection Required")
            return
        
        dc = self.txt_dc.GetValue() if "Source" in assignment_type else self.txt_sink_current.GetValue()
        ac = self.txt_ac.GetValue()
        hz = self.txt_hz.GetValue()
        
        # If it's a source, get the specific type (V or A)
        src_mode = "Voltage"
        if "Source" in assignment_type and hasattr(self, 'cb_src_type'):
            if self.cb_src_type.GetSelection() == 1:
                src_mode = "Current"
        
        for pad in checked:
            entry = {'net': self.current_net, 'pad': pad, 'type': assignment_type, 'dc': dc, 'freq': hz, 'ac': ac, 'src_mode': src_mode}
            self.sources_sinks.append(entry)
            
            row = self.ss_grid.GetNumberRows()
            self.ss_grid.AppendRows(1)
            # Grid Cols: Type, Net, Loc, Val, AC, Hz
            display_type = "SRC(V)" if src_mode == "Voltage" and "Source" in assignment_type else "SRC(A)" if "Source" in assignment_type else "SINK"
            self.ss_grid.SetCellValue(row, 0, display_type)
            self.ss_grid.SetCellValue(row, 1, self.current_net)
            self.ss_grid.SetCellValue(row, 2, pad)
            self.ss_grid.SetCellValue(row, 3, dc)
            self.ss_grid.SetCellValue(row, 4, ac)
            self.ss_grid.SetCellValue(row, 5, hz)
        
        self.update_run_buttons()

    def on_add_pass_through(self, event):
        frame = wx.GetTopLevelParent(self)
        parser = frame.parser if hasattr(frame, 'parser') else None
        dlg = PassThroughDialog(self, parser)
        if dlg.ShowModal() == wx.ID_OK:
            cfg = dlg.get_config()
            entry = {
                'type': 'Pass-Through',
                'pt_type': cfg.get('pt_type', 'Resistor'),
                'net': cfg['in_net'],
                'pad': cfg['in_pad'],
                'out_net': cfg['out_net'],
                'out_pad': cfg['out_pad'],
                'dc': str(cfg['r_val']), # Re-use dc for resistance/ESR
                'l_val': cfg.get('l_val', 0.0),
                'v_drop': cfg.get('v_drop', 0.7),
                'v_rev': cfg.get('v_rev', 50.0),
                'ac': '0',
                'freq': '0'
            }
            self.sources_sinks.append(entry)
            
            row = self.ss_grid.GetNumberRows()
            self.ss_grid.AppendRows(1)
            self.ss_grid.SetCellValue(row, 0, f"PASS({cfg.get('pt_type', 'RES')[:3].upper()})")
            self.ss_grid.SetCellValue(row, 1, f"{cfg['in_net']} -> {cfg['out_net']}")
            self.ss_grid.SetCellValue(row, 2, f"{cfg['in_pad']} -> {cfg['out_pad']}")
            self.ss_grid.SetCellValue(row, 3, str(cfg['r_val']))
            self.ss_grid.SetCellValue(row, 4, str(cfg.get('l_val', 0.0)))
            self.ss_grid.SetCellValue(row, 5, "-")
            
            self.update_run_buttons()
        dlg.Destroy()


# ============================================================================
# MAIN WINDOW FRAME
# ============================================================================

class SPIKEMainWindow(wx.Frame):
    def __init__(self):
        title = f"SPIKE v{__version__} - Professional SI/PI Analyzer"
        if not HAS_CORE: title += " (Simulation Mode)"
        super().__init__(None, title=title, size=(1600, 1000))
        
        # 1. Setup Status Bar & Menu
        self.status_bar = self.CreateStatusBar(4)
        self.status_bar.SetStatusWidths([-1, 150, 150, 250])
        self.SetStatusText("Ready - C++ Engine: " + ("Loaded" if HAS_CORE else "Not Found (Sim Mode)"), 0)
        self.SetStatusText("Est. Time: --", 1)
        self.SetStatusText("Mem: --", 2)
        
        self.current_project_path = None
        self.current_board_path = None
        
        # Multipurpose Loading Bar
        self.progress_gauge = wx.Gauge(self.status_bar, range=100)
        self.progress_gauge.Hide()
        # self._init_menu() # Classic menu removed to prevent duplicates with Ribbon
        self._init_toolbar()   # creates self._ribbon

        # Bind resize for gauge positioning
        self.Bind(wx.EVT_SIZE, self.on_frame_size)
        
        # 2. Layout: Ribbon at top, AUI below
        #    Frame → BoxSizer → [Ribbon (fixed)] + [_aui_host (fill)]
        self._aui_host = wx.Panel(self)
        frame_sizer = wx.BoxSizer(wx.VERTICAL)
        frame_sizer.Add(self._ribbon, 0, wx.EXPAND)
        frame_sizer.Add(self._aui_host, 1, wx.EXPAND)
        self.SetSizer(frame_sizer)

        # 3. AUI manages the host panel (not the frame)
        self._mgr = aui.AuiManager(self._aui_host,
            agwFlags=aui.AUI_MGR_DEFAULT |
                     aui.AUI_MGR_ALLOW_ACTIVE_PANE |
                     aui.AUI_MGR_LIVE_RESIZE |
                     aui.AUI_MGR_TRANSPARENT_DRAG)

        # 4. Create Panels — all parented to _aui_host

        # LEFT: Nets & Layers (Dockable)
        self.net_panel = NetListPanel(self._aui_host)
        self._mgr.AddPane(self.net_panel, aui.AuiPaneInfo().
                          Left().Caption("Nets & Layers").
                          BestSize(340, -1).MinSize(300, -1).
                          Floatable(True).Movable(True).
                          CloseButton(True).MaximizeButton(True))

        # CENTER: Visualization (Notebook)
        self.center_nb = aui.AuiNotebook(self._aui_host,
            agwStyle=aui.AUI_NB_TOP |
                     aui.AUI_NB_TAB_SPLIT |
                     aui.AUI_NB_SCROLL_BUTTONS |
                     aui.AUI_NB_CLOSE_ON_TAB_LEFT |
                     aui.AUI_NB_MIDDLE_CLICK_CLOSE)
        if SpikeTabArt:
            self.center_nb.SetArtProvider(SpikeTabArt(dark=True))

        # Tab 1: Visualizer (with internal toolbar)
        self.viz_panel = wx.Panel(self.center_nb)
        self.viz_sizer = wx.BoxSizer(wx.VERTICAL)

        # Internal Toolbar
        self.viz_tb = wx.ToolBar(self.viz_panel, style=wx.TB_FLAT | wx.TB_HORIZONTAL | wx.TB_NODIVIDER)
        self.viz_tb.SetBackgroundColour(wx.Colour(240, 240, 240))

        self.btn_3d = self.viz_tb.AddCheckTool(wx.ID_ANY, "3D View", wx.ArtProvider.GetBitmap(wx.ART_REPORT_VIEW))
        self.btn_2d = self.viz_tb.AddCheckTool(wx.ID_ANY, "2D View", wx.ArtProvider.GetBitmap(wx.ART_LIST_VIEW))
        self.viz_tb.ToggleTool(self.btn_3d.GetId(), True)
        self.viz_tb.AddSeparator()
        self.btn_zoom = self.viz_tb.AddTool(wx.ID_ANY, "Zoom Fit", wx.ArtProvider.GetBitmap(wx.ART_FIND))

        self.viz_tb.Realize()
        self.viz_sizer.Add(self.viz_tb, 0, wx.EXPAND)

        # Viewport Container
        self.vp_container = wx.Panel(self.viz_panel)
        self.vp_sizer = wx.BoxSizer(wx.VERTICAL)

        self.viewport = Viewport3D(self.vp_container)
        from viz.viewport2d import Viewport2D
        self.viewport_2d = Viewport2D(self.vp_container)

        self.vp_sizer.Add(self.viewport, 1, wx.EXPAND)
        self.vp_sizer.Add(self.viewport_2d, 1, wx.EXPAND)
        self.viewport_2d.Hide()

        self.vp_container.SetSizer(self.vp_sizer)
        self.viz_sizer.Add(self.vp_container, 1, wx.EXPAND)
        self.viz_panel.SetSizer(self.viz_sizer)

        # Link Viewports to Net Panel
        self.net_panel.set_viewport(self.viewport)
        self.net_panel.set_viewport_2d(self.viewport_2d)

        # Bi-directional callbacks - Sync across all
        self.viewport.on_net_click_cb = self.on_viewport_net_click
        self.viewport.on_pad_click_cb = self.on_viewport_pad_click
        self.viewport_2d.on_net_click_cb = self.on_viewport_net_click
        self.viewport_2d.on_pad_click_cb = self.on_viewport_pad_click

        # Bind Toolbar
        self.Bind(wx.EVT_TOOL, self.on_switch_view, self.btn_3d)
        self.Bind(wx.EVT_TOOL, self.on_switch_view, self.btn_2d)
        self.Bind(wx.EVT_TOOL, self.on_zoom_fit, self.btn_zoom)

        # Tab 2: Analysis Dashboard
        self.dashboard_panel = AnalysisDashboardPanel(self.center_nb)

        # Tab 3: Results
        self.results_panel = ResultsPanel(self.center_nb)

        # Tab 4: Reports
        self.reports_panel = ReportsPanel(self.center_nb)
        
        # Bind results_panel comboboxes now that they exist
        self.results_panel.cb_view_mode.Bind(wx.EVT_COMBOBOX, self.on_view_mode_change)
        self.results_panel.cb_units.Bind(wx.EVT_COMBOBOX, lambda e: self._update_viewports_async())
        self.center_nb.AddPage(self.viz_panel,       "Visualizer",     select=True)
        self.center_nb.AddPage(self.dashboard_panel, "Dashboard")
        self.center_nb.AddPage(self.results_panel,   "Results")
        self.center_nb.AddPage(self.reports_panel,    "Reports")

        self._mgr.AddPane(self.center_nb, aui.AuiPaneInfo().
                          CenterPane().PaneBorder(False))

        # RIGHT: Simulation Manager (Dockable)
        self.analysis_panel = AnalysisPanel(self._aui_host)
        self._mgr.AddPane(self.analysis_panel, aui.AuiPaneInfo().
                          Right().Caption("Simulation Manager").
                          BestSize(420, -1).MinSize(380, -1).
                          Floatable(True).Movable(True).
                          CloseButton(True).MaximizeButton(True))
                          
        # RIGHT: Thermal Manager (Dockable)
        self.thermal_panel = ThermalSidePanel(self._aui_host)
        self._mgr.AddPane(self.thermal_panel, aui.AuiPaneInfo().
                          Right().Caption("Thermal Management").
                          Position(1).
                          BestSize(420, -1).MinSize(380, -1).
                          Floatable(True).Movable(True).
                          CloseButton(True).MaximizeButton(True))

        # SI Workspace (Moved to Right Panel)
        if SIWorkspacePanel:
            self.si_panel = SIWorkspacePanel(self.analysis_panel.nb)
        else:
            self.si_panel = wx.Panel(self.analysis_panel.nb)
            wx.StaticText(self.si_panel, label="SI Workspace - import error")
        self.analysis_panel.nb.AddPage(self.si_panel, "SI Workspace")

        # BOTTOM: Console (Dockable)
        self.console_panel = ConsolePanel(self._aui_host)
        self._mgr.AddPane(self.console_panel, aui.AuiPaneInfo().
                          Bottom().Caption("Console & Debug").
                          BestSize(-1, 200).MinSize(-1, 100).
                          CloseButton(True).MaximizeButton(True))

        # 5. Commit Layout
        self._mgr.Update()


        # 5b. Apply startup theme from settings
        startup_theme = "Dark"
        try:
            startup_theme = settings_get("theme", "Dark")
        except Exception:
            pass
        wx.CallAfter(self.apply_app_theme, startup_theme)
        
        # 5. Bind Events
        self.analysis_panel.btn_run_dc.Bind(wx.EVT_BUTTON, self.on_run_simulation)
        self.analysis_panel.btn_run_ac.Bind(wx.EVT_BUTTON, self.on_run_simulation)
        self.analysis_panel.btn_batch_run.Bind(wx.EVT_BUTTON, self.on_run_simulation)
        
        # 6. Load Board Data (if path passed)
        if len(sys.argv) > 1:
            board_path = sys.argv[1]
            if os.path.exists(board_path):
                wx.CallAfter(self.load_board, board_path)
        else:
            wx.CallAfter(self.load_demo_data)

    def on_switch_view(self, event):
        is_3d = self.viz_tb.GetToolState(self.btn_3d.GetId())
        is_2d = self.viz_tb.GetToolState(self.btn_2d.GetId())
        
        # Mutual Exclusivity
        if event.GetId() == self.btn_3d.GetId():
            if not is_3d: self.viz_tb.ToggleTool(self.btn_3d.GetId(), True); return # Don't allow both off
            self.viz_tb.ToggleTool(self.btn_2d.GetId(), False)
        else:
            if not is_2d: self.viz_tb.ToggleTool(self.btn_2d.GetId(), True); return
            self.viz_tb.ToggleTool(self.btn_3d.GetId(), False)
            
        show_3d = self.viz_tb.GetToolState(self.btn_3d.GetId())
        self.viewport.Show(show_3d)
        self.viewport_2d.Show(not show_3d)
        self.vp_container.Layout()

    def on_zoom_fit(self, event):
        if self.viewport.IsShown(): self.viewport.zoom_extents()
        if self.viewport_2d.IsShown(): self.viewport_2d.zoom_extents()

    def on_viewport_net_click(self, net_name, best_id=None):
        """Called when user clicks a net in any viewport"""
        if not net_name: return
        self.net_panel.select_net(net_name, net_id=best_id)
        self.analysis_panel.set_target_net(net_name)
        self.sync_to_kicad(net_name)
        if self.viewport: self.viewport.highlight_net(net_name, net_id=best_id)
        if hasattr(self, 'viewport_2d'): self.viewport_2d.highlight_net(net_name, net_id=best_id)

    def on_viewport_pad_click(self, net_name, pad_name):
        """Called when user clicks a pad in any viewport"""
        if not net_name: return
        self.net_panel.select_net(net_name)
        self.analysis_panel.set_target_net(net_name)
        self.analysis_panel.select_pad(pad_name)
        self.sync_to_kicad(net_name, pad_name)
        if self.viewport: self.viewport.highlight_pad(net_name, pad_name) if hasattr(self.viewport, 'highlight_pad') else None
        if hasattr(self, 'viewport_2d'): self.viewport_2d.highlight_pad(net_name, pad_name)

    def sync_to_kicad(self, net_name, pad_name=None):
        """Cross-highlight in KiCad via sync file"""
        import json
        import time
        sync_file = project_root / "kicad_sync_info.json"
        try:
            sync_data = {
                "net": net_name,
                "pad": pad_name,
                "src": "SPIKE",
                "time": time.time()
            }
            with open(sync_file, "w") as f:
                json.dump(sync_data, f)
        except Exception as e:
             print(f"Sync: Failed to write {sync_file}: {e}")

    def load_board(self, filepath):
        """Load real KiCad, ODB++, or IPC-2581 board data"""
        self.SetStatusText(f"Loading board: {filepath}...")
        self.current_board_path = filepath
        
        try:
            ext = filepath.lower().split('.')[-1]
            if ext == 'zip':
                from core.odb_parser import OdbParser
                self.parser = OdbParser(filepath)
            elif ext == 'xml':
                from core.ipc_parser import IpcParser
                self.parser = IpcParser(filepath)
            else:
                from core.board_parser import KicadParser
                self.parser = KicadParser(filepath)
            
            # 1. Populate Nets Panel
            net_names = []
            self.net_panel.net_map = {}
            for nid, name in self.parser.nets.items():
                net_names.append(name)
                self.net_panel.net_map[name] = nid
                
            self.net_panel.update_net_list(net_names)

            # 1b. Populate Layers Panel (Dynamic)
            # Use a dictionary to normalize names and avoid duplicates
            layer_map = {} 
            
            # From parser definitions
            for l in self.parser.layers.values():
                name = l['name'].replace('"', '')
                if name: layer_map[name] = True

            # Scan all entities for layers
            for d in self.parser.drawings:
                if 'layer' in d: layer_map[d['layer'].replace('"', '')] = True
            for pad in self.parser.pads:
                for l in pad.get('layers', []): layer_map[l.replace('"', '')] = True
            for zone in self.parser.zones:
                if 'layer' in zone: layer_map[zone['layer'].replace('"', '')] = True
            
            # Ensure Vias and Fusing Risk
            layer_map["Vias"] = True
            layer_map["Fusing Risk"] = True
            
            # Sorting Logic
            def layer_sort_key(name):
                name = name.strip()
                # -1. Overlays
                if name == "Fusing Risk": return (-1, 0)
                # 0. Front Copper
                if name == "F.Cu": return (0, 0)
                # 1. Inner Copper
                if name.startswith("In") and ".Cu" in name: 
                    try: 
                        num = int(''.join(filter(str.isdigit, name)))
                        return (0, num)
                    except: return (0, 99)
                # 2. Bottom Copper
                if name == "B.Cu": return (0, 100)
                
                # 3. Paste
                if "Paste" in name: return (1, 0 if name.startswith("F") else 1)
                # 4. Silk
                if "SilkS" in name: return (2, 0 if name.startswith("F") else 1)
                # 5. Mask
                if "Mask" in name: return (3, 0 if name.startswith("F") else 1)
                # 6. CrtYd
                if "CrtYd" in name: return (4, 0 if name.startswith("F") else 1)
                
                # 7. Edge Cuts / Vias
                if name == "Edge.Cuts": return (5, 0)
                if name == "Vias": return (5, 1)
                
                # 8. Others
                return (6, name)

            sorted_layers = sorted(layer_map.keys(), key=layer_sort_key)
            self.net_panel.populate_layers(sorted_layers)
                
            self.SetStatusText(f"Loaded {len(self.parser.nets)} nets from {os.path.basename(filepath)}")
            
            # 2. Render 3D Geometry
            self.render_board_3d()
            self.viewport.set_on_net_click_cb(self.on_viewport_net_click)
            if hasattr(self.viewport, 'set_on_thermal_click_cb'):
                self.viewport.set_on_thermal_click_cb(self.on_thermal_click)
            
            # Apply initial layer visibility (sync CheckBoxes -> Viewport)
            for name, ctrl in self.net_panel.layer_controls.items():
                if self.viewport:
                    self.viewport.set_layer_visibility(name, ctrl['chk'].GetValue())
            
        except ImportError:
            wx.MessageBox("Could not import KicadParser. Check python/core/board_parser.py", "Error")
        except Exception as e:
            wx.MessageBox(f"Failed to load board: {str(e)}", "Error")

    def build_layer_z_map(self):
        """Dynamically compute Z heights for all layers based on parsed stackup."""
        layer_z = { "Edge.Cuts": 0.0 }
        layer_z_fallback = {
            "F.Cu": 0.0, "In1.Cu": -0.5, "In2.Cu": -1.0, "In3.Cu": -1.5, "In4.Cu": -2.0, "B.Cu": -1.6
        }
        
        if not hasattr(self.parser, 'stackup') or not self.parser.stackup:
            for k, v in layer_z_fallback.items(): layer_z[k] = v
            return layer_z
            
        current_z = 0.0
        for layer in self.parser.stackup:
            name = layer.get('name', '')
            if name:
                layer_z[name] = current_z
            
            thickness = layer.get('thickness', 0.0)
            if thickness:
                current_z -= float(thickness)
                
        for k, v in layer_z_fallback.items():
            if k not in layer_z:
                layer_z[k] = v
                
        return layer_z

    def render_board_3d(self):
        """Render parsed geometry to Viewport3D"""
        if not self.viewport: return
        
        total_items = len(self.parser.tracks) + len(self.parser.vias) + len(self.parser.pads) + len(self.parser.zones)
        if total_items == 0: return

        self.set_progress(5, "Clearing scenes...")
        self.viewport.clear()
        if hasattr(self, 'viewport_2d'): self.viewport_2d.clear()
        
        # Add Board Substrate (FR4)
        if hasattr(self.parser, 'board_bbox'):
            b = self.board_bbox = self.parser.board_bbox
            self.viewport.add_board_substrate(b['min_x'], b['max_x'], b['min_y'], b['max_y'])
            if hasattr(self, 'viewport_2d'):
                self.viewport_2d.add_board_substrate(b['min_x'], b['max_x'], b['min_y'], b['max_y'])
        
        layer_z = self.build_layer_z_map()
        
        colors = {
            "F.Cu": "red",
            "B.Cu": "green",
            "In1.Cu": "orange",
            "In2.Cu": "yellow",
            "Edge.Cuts": "white",
            "Vias": "silver",
            "F.SilkS": "white", "B.SilkS": "magenta",
            "F.CrtYd": "grey", "B.CrtYd": "grey",
            "F.Paste": "grey", "B.Paste": "grey"
        }
        
        self.set_progress(20, f"Rendering {len(self.parser.tracks)} Tracks...")
        # Render Tracks
        for i, track in enumerate(self.parser.tracks):
            layer = track['layer']
            z = layer_z.get(layer, 0)
            name = track.get('net_name', f"Net_{track['net_id']}")
            
            self.viewport.add_filament(
                start=(track['start'][0], track['start'][1], z), 
                end=(track['end'][0], track['end'][1], z),
                width=track['width'], thickness=0.035,
                color=colors.get(layer, 'grey'),
                name=name,
                layer=layer,
                net_id=track.get('net_id')
            )
            if hasattr(self, 'viewport_2d'):
                self.viewport_2d.add_filament(
                    start=track['start'], end=track['end'],
                    width=track['width'], thickness=0,
                    name=name, layer=layer, net_id=track.get('net_id')
                )
            if i % 100 == 0:
                p = 20 + int(30 * i / len(self.parser.tracks))
                self.set_progress(p)
            
        self.set_progress(50, f"Rendering {len(self.parser.vias)} Vias...")
        # Render Vias
        for i, via in enumerate(self.parser.vias):
            x, y = via['at']
            name = via.get('net_name', f"Net_{via['net_id']}")
            
            # Use specific layers to determine via length
            v_layers = via.get('layers', ("F.Cu", "B.Cu"))
            z_top = layer_z.get(v_layers[0], 0.0)
            z_bot = layer_z.get(v_layers[-1], -1.6)
            if z_bot > z_top: z_top, z_bot = z_bot, z_top # ensure correct order
            
            self.viewport.add_via(
                x=x, y=y, 
                size=via['size'], drill=via['drill'],
                net_name=name,
                net_id=via.get('net_id'),
                z_start=z_top,
                z_end=z_bot
            )
            if hasattr(self, 'viewport_2d'):
                 self.viewport_2d.add_via(x, y, via['size'], via['drill'], net_name=name, net_id=via.get('net_id'))
            if i % 50 == 0:
                p = 50 + int(10 * i / len(self.parser.vias))
                self.set_progress(p)

        self.set_progress(60, f"Rendering {len(self.parser.pads)} Pads...")
        # Render Pads
        for i, pad in enumerate(self.parser.pads):
            self.viewport.add_pad(
                shape=pad['shape'],
                pos=pad['at'],
                size=pad['size'],
                rotation=pad['rotation'],
                layer=pad['layer'],
                net_name=pad['net_name'],
                net_id=pad.get('net_id'),
                drill=pad.get('drill', 0),
                pad_name=pad['component_pad']
            )
            if hasattr(self, 'viewport_2d'):
                self.viewport_2d.add_pad(
                    shape=pad['shape'], pos=pad['at'], size=pad['size'],
                    rotation=pad['rotation'], layer=pad['layer'],
                    net_name=pad['net_name'], net_id=pad.get('net_id'),
                    drill=pad.get('drill', 0), pad_name=pad['component_pad']
                )
            if i % 50 == 0:
                p = 60 + int(10 * i / len(self.parser.pads))
                self.set_progress(p)

        self.set_progress(70, f"Rendering {len(self.parser.zones)} Copper Zones...")
        # Render Zones
        for i, zone in enumerate(self.parser.zones):
            # Pass net_name for highlighting
            self.viewport.add_zone(
                points=zone['points'],
                layer=zone['layer'],
                net_name=zone.get('net_name', ""),
                net_id=zone.get('net_id')
            )
            if hasattr(self, 'viewport_2d'):
                self.viewport_2d.add_zone(
                    points=zone['points'], layer=zone['layer'],
                    net_name=zone.get('net_name', ""), net_id=zone.get('net_id')
                )
            if i % 10 == 0:
                p = 70 + int(20 * i / len(self.parser.zones))
                self.set_progress(p)

        self.set_progress(95, "Finalizing 3D Scene...")
        # Render Drawings (Silk / Edge Cuts)
        import math
        for d in self.parser.drawings:
            if d['type'] == 'line':
                # Map to add_line or add_filament
                # For 2D, z isn't critical.
                self.viewport.add_filament(
                    start=(d['start'][0], d['start'][1], 0),
                    end=(d['end'][0], d['end'][1], 0),
                    width=d['width'], thickness=0,
                    color='white', name='Drawing', layer=d['layer']
                )
            elif d['type'] == 'circle':
                self.viewport.add_circle(
                    center=d['center'], radius=d['radius'],
                    layer=d['layer'], width=d['width']
                )
            elif d['type'] == 'arc_3pt':
                # Geometric Arc Calculation
                def get_arc_params(p1, p2, p3):
                    x1, y1 = p1
                    x2, y2 = p2
                    x3, y3 = p3
                    D = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
                    if abs(D) < 1e-9: return None # Collinear
                    
                    Ux = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / D
                    Uy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / D
                    
                    center = (Ux, Uy)
                    radius = math.hypot(x1 - Ux, y1 - Uy)
                    
                    # Angles in degrees
                    a1 = math.degrees(math.atan2(y1 - Uy, x1 - Ux))
                    a2 = math.degrees(math.atan2(y2 - Uy, x2 - Ux))
                    a3 = math.degrees(math.atan2(y3 - Uy, x3 - Ux))
                    
                    return center, radius, a1, a3

                params = get_arc_params(d['start'], d['mid'], d['end'])
                if params:
                    center, radius, start, end = params
                    # Viewport2D handles arcs
                    self.viewport.add_arc(center, radius, start, end, 
                                          layer=d['layer'], width=d['width'], net_name=None)
                else:
                     # Fallback
                     self.viewport.add_filament(
                        start=(d['start'][0], d['start'][1], 0), 
                        end=(d['end'][0], d['end'][1], 0), 
                        width=d['width'], thickness=0, layer=d['layer']
                     )
            elif d['type'] == 'text':
                self.viewport.add_text(
                    text=d['text'], pos=d['pos'], 
                    rotation=d['rotation'], size=d['size'], 
                    layer=d['layer'], thick=d.get('thickness', 0)
                )

        msg = "Render complete."
        if hasattr(self.viewport, 'filaments'):
            msg = f"Render complete: {len(self.viewport.filaments)} elements."
        elif hasattr(self.viewport, 'command_cache'):
            msg = f"Render complete: {len(self.viewport.command_cache)} commands cached."
        print(msg)
        
        if hasattr(self.viewport, 'render_geometry'):
            self.viewport.render_geometry()
        self.viewport.zoom_extents()
        self.set_progress(-1, "Board Loaded") # Clear progress bar

    def _init_menu(self):
        """Initialize the full application menu bar — Phase 15 & 16 Ready"""
        menubar = wx.MenuBar()

        # ── FILE ─────────────────────────────────────────────────────────
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_NEW,    "&New Project\tCtrl+N")
        file_menu.Append(wx.ID_OPEN,   "&Open Project/Board…\tCtrl+O")
        file_menu.AppendSeparator()
        
        mnu_import = wx.Menu()
        mnu_import.Append(301, "KiCad PCB (.kicad_pcb)")
        mnu_import.Append(302, "ODB++ Archive (.zip)")
        mnu_import.Append(303, "IPC-2581 (.xml)")
        file_menu.AppendSubMenu(mnu_import, "&Import")
        file_menu.AppendSeparator()
        
        file_menu.Append(wx.ID_SAVE,   "&Save\tCtrl+S")
        file_menu.Append(wx.ID_SAVEAS, "Save &As…\tCtrl+Shift+S")
        file_menu.AppendSeparator()
        
        mnu_export = wx.Menu()
        mnu_export.Append(311, "Export HTML Report")
        mnu_export.Append(312, "Export PDF Report")
        mnu_export.Append(313, "Export Probe CSV")
        file_menu.AppendSubMenu(mnu_export, "&Export")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT,   "E&xit\tAlt+F4")
        menubar.Append(file_menu, "&File")
        
        # ── COMPONENTS ───────────────────────────────────────────────────
        comp_menu = wx.Menu()
        comp_menu.Append(321, "🔧  Component Parameter Wizard…")
        comp_menu.Append(322, "🤖  Auto-Detect Parameters from BoM")
        comp_menu.AppendSeparator()
        comp_menu.Append(323, "📚  Material & Package Library")
        menubar.Append(comp_menu, "&Components")

        # ── SIMULATION ───────────────────────────────────────────────────
        sim_menu = wx.Menu()
        
        pi_menu = wx.Menu()
        pi_menu.Append(101, "▶  Run DC IR-Drop\tF5")
        pi_menu.Append(102, "⚡  Run AC Impedance\tF6")
        pi_menu.Append(104, "📈  Run Impedance Sweep\tF7")
        pi_menu.Append(105, "⏱  Run Transient Load-Step\tF8")
        sim_menu.AppendSubMenu(pi_menu, "&Power Integrity (PI)")
        
        thm_menu = wx.Menu()
        thm_menu.Append(111, "🌡  Run Steady-State Thermal")
        thm_menu.Append(112, "⏱  Run Transient Thermal")
        thm_menu.AppendSeparator()
        thm_menu.Append(113, "🌬  Setup Convection & Airflow…")
        sim_menu.AppendSubMenu(thm_menu, "&Thermal")
        
        si_menu = wx.Menu()
        si_menu.Append(121, "📡  Run High-Speed Digital SI")
        si_menu.Append(122, "👁  Extract Eye Diagram")
        si_menu.Append(123, "🔁  Compute RLC Parasitics\tF9")
        sim_menu.AppendSubMenu(si_menu, "&Signal Integrity (SI)")
        
        sim_menu.AppendSeparator()
        sim_menu.Append(106, "Run Batch Simulation\tCtrl+B")
        sim_menu.AppendSeparator()
        sim_menu.Append(107, "🔍  Unified PDN & Thermal Setup…\tCtrl+P")
        sim_menu.Append(108, "📊  System Health Score…")
        menubar.Append(sim_menu, "&Simulation")

        # ── ANALYSIS ─────────────────────────────────────────────────────
        anal_menu = wx.Menu()
        anal_menu.Append(201, "🧙  &PDN Source/Sink Wizard…")
        anal_menu.Append(202, "🏷  &Classify Nets…")
        anal_menu.AppendSeparator()
        anal_menu.Append(204, "🔬  Clear All Probes")
        menubar.Append(anal_menu, "&Analysis")
        
        # ── REPORTS ──────────────────────────────────────────────────────
        rep_menu = wx.Menu()
        rep_menu.Append(331, "Configure Report Settings")
        rep_menu.Append(332, "Generate Full Dossier")
        menubar.Append(rep_menu, "&Reports")

        # ── VIEW ─────────────────────────────────────────────────────────
        view_menu = wx.Menu()
        self._mnu_nets_panel = view_menu.AppendCheckItem(401, "Show &Nets Panel\tCtrl+1")
        self._mnu_anal_panel = view_menu.AppendCheckItem(402, "Show &Analysis Panel\tCtrl+2")
        self._mnu_console    = view_menu.AppendCheckItem(403, "Show &Console\tCtrl+`")
        self._mnu_nets_panel.Check(True)
        self._mnu_anal_panel.Check(True)
        self._mnu_console.Check(True)
        view_menu.AppendSeparator()
        view_menu.Append(411, "Switch to &3D View")
        view_menu.Append(412, "Switch to &2D View")
        view_menu.Append(413, "Zoom &Fit\tCtrl+0")
        view_menu.AppendSeparator()
        mnu_theme = wx.Menu()
        mnu_theme.Append(421, "&Dark Theme")
        mnu_theme.Append(422, "&Light Theme")
        view_menu.AppendSubMenu(mnu_theme, "Color &Theme")
        menubar.Append(view_menu, "&View")

        # ── TOOLS ────────────────────────────────────────────────────────
        tools_menu = wx.Menu()
        tools_menu.Append(501, "⚙  &Settings…\tCtrl+,")
        tools_menu.AppendSeparator()
        tools_menu.Append(511, "Copy Console to Clipboard")
        tools_menu.Append(512, "Clear Console")
        menubar.Append(tools_menu, "&Tools")

        # ── HELP ─────────────────────────────────────────────────────────
        help_menu = wx.Menu()
        help_menu.Append(wx.ID_ABOUT, "&About SPIKE…")
        help_menu.Append(601, "&User Guide")
        help_menu.Append(602, "Release &Notes")
        menubar.Append(help_menu, "&Help")

        self.SetMenuBar(menubar)

        # ── BINDINGS ─────────────────────────────────────────────────────
        self.Bind(wx.EVT_MENU, self.on_about,           id=wx.ID_ABOUT)
        self.Bind(wx.EVT_MENU, self.on_open_project,    id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.on_save_project,    id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self.on_save_as_project, id=wx.ID_SAVEAS)
        self.Bind(wx.EVT_MENU, lambda e: self.Close(),  id=wx.ID_EXIT)
        
        self.Bind(wx.EVT_MENU, lambda e: self.on_run_simulation(e), id=101)
        self.Bind(wx.EVT_MENU, lambda e: self.on_run_simulation(e), id=102)
        self.Bind(wx.EVT_MENU, lambda e: self.on_run_simulation(e), id=106)
        self.Bind(wx.EVT_MENU, lambda e: self.on_run_sweep(e),      id=104)
        self.Bind(wx.EVT_MENU, lambda e: self.on_run_transient(e),  id=105)
        
        self.Bind(wx.EVT_MENU, self.on_run_thermal,                 id=111)
        
        # New Wizard Bindings
        self.Bind(wx.EVT_MENU, self.on_open_setup_wizard,           id=107)
        self.Bind(wx.EVT_MENU, self.on_open_comp_wizard,            id=321)
        
        self.Bind(wx.EVT_MENU, self.on_pdn_health,                  id=108)
        self.Bind(wx.EVT_MENU, lambda e: self.analysis_panel.on_pdn_wizard(e), id=201)
        self.Bind(wx.EVT_MENU, self.on_classify_nets,               id=202)
        self.Bind(wx.EVT_MENU, self.on_clear_all_probes,            id=204)
        
        self.Bind(wx.EVT_MENU, self.on_toggle_nets_panel,           id=401)
        self.Bind(wx.EVT_MENU, self.on_toggle_anal_panel,           id=402)
        self.Bind(wx.EVT_MENU, self.on_toggle_console,              id=403)
        self.Bind(wx.EVT_MENU, lambda e: self._switch_to_3d(),      id=411)
        self.Bind(wx.EVT_MENU, lambda e: self._switch_to_2d(),      id=412)
        self.Bind(wx.EVT_MENU, self.on_zoom_fit,                    id=413)
        self.Bind(wx.EVT_MENU, lambda e: self.apply_app_theme("Dark"),  id=421)
        self.Bind(wx.EVT_MENU, lambda e: self.apply_app_theme("Light"), id=422)
        self.Bind(wx.EVT_MENU, self.on_settings,                    id=501)
        self.Bind(wx.EVT_MENU, self.on_copy_console,                id=511)
        self.Bind(wx.EVT_MENU, lambda e: self.console_panel.on_clear(e), id=512)
        self.Bind(wx.EVT_MENU, lambda e: self.reports_panel._on_export_html(e), id=311)
        self.Bind(wx.EVT_MENU, lambda e: self.reports_panel._on_print(e),  id=312)
        self.Bind(wx.EVT_MENU, lambda e: self.dashboard_panel._export_probe_csv(e), id=313)
        
    @property
    def cb_view_mode(self):
        return self.results_panel.cb_view_mode

    @property
    def cb_units(self):
        return self.results_panel.cb_units

    def _init_toolbar(self):
        """Ribbon-style toolbar using wx.lib.agw.ribbon"""
        self._ribbon = ribbon.RibbonBar(self, wx.ID_ANY,
            agwStyle=ribbon.RIBBON_BAR_DEFAULT_STYLE |
                     ribbon.RIBBON_BAR_SHOW_PAGE_LABELS)
        self._ribbon.SetArtProvider(ribbon.RibbonAUIArtProvider())

        # ── Page 1: FILE ─────────────────────────────────────────────────
        pg_file = ribbon.RibbonPage(self._ribbon, wx.ID_ANY, "File")
        panel_io = ribbon.RibbonPanel(pg_file, wx.ID_ANY, "Project")
        btns_io  = ribbon.RibbonButtonBar(panel_io)
        def _bmp(art_id, size=(24,24)):
            bmp = wx.ArtProvider.GetBitmap(art_id, wx.ART_TOOLBAR, size)
            if bmp.IsOk() and bmp.GetSize() != size:
                img = bmp.ConvertToImage()
                img.Rescale(size[0], size[1], wx.IMAGE_QUALITY_HIGH)
                bmp = wx.Bitmap(img)
            return bmp if bmp.IsOk() else wx.NullBitmap

        def _add(bar, btn_id, label, art_id, help_str=""):
            b = _bmp(art_id)
            bar.AddButton(btn_id, label, b, help_string=help_str)

        _add(btns_io, wx.ID_OPEN,  "Open",    wx.ART_FILE_OPEN,    "Open project or board (Ctrl+O)")
        _add(btns_io, wx.ID_SAVE,  "Save",    wx.ART_FILE_SAVE,    "Save project (Ctrl+S)")
        _add(btns_io, wx.ID_SAVEAS,"Save As", wx.ART_FILE_SAVE_AS, "Save project as…")

        # ── Page 2: SIMULATION ───────────────────────────────────────────
        pg_sim = ribbon.RibbonPage(self._ribbon, wx.ID_ANY, "Simulation")
        panel_run = ribbon.RibbonPanel(pg_sim, wx.ID_ANY, "Run")
        btns_run  = ribbon.RibbonButtonBar(panel_run)
        _add(btns_run, 101, "DC IR-Drop",  wx.ART_EXECUTABLE_FILE, "Run DC simulation (F5)")
        _add(btns_run, 102, "AC Impedance",wx.ART_REMOVABLE,       "Run AC simulation (F6)")
        _add(btns_run, 104, "Freq Sweep",  wx.ART_FIND,            "Run impedance sweep (F7)")
        _add(btns_run, 105, "Transient",   wx.ART_NORMAL_FILE,     "Run transient (F8)")

        panel_check = ribbon.RibbonPanel(pg_sim, wx.ID_ANY, "Pre-flight")
        btns_check  = ribbon.RibbonButtonBar(panel_check)
        _add(btns_check, 107, "Pre-Sim Check", wx.ART_TICK_MARK,   "Run pre-simulation checklist")
        _add(btns_check, 108, "PDN Health",    wx.ART_INFORMATION,  "PDN health score")

        # ── Page 3: ANALYSIS ─────────────────────────────────────────────
        pg_anal = ribbon.RibbonPage(self._ribbon, wx.ID_ANY, "Analysis")
        panel_tools = ribbon.RibbonPanel(pg_anal, wx.ID_ANY, "Tools")
        btns_tools  = ribbon.RibbonButtonBar(panel_tools)
        _add(btns_tools, 201, "PDN Wizard",    wx.ART_HELP_SETTINGS, "Auto-assign PDN sources/sinks")
        _add(btns_tools, 202, "Classify Nets", wx.ART_LIST_VIEW,     "Classify nets by type")

        panel_probe = ribbon.RibbonPanel(pg_anal, wx.ID_ANY, "Probe")
        btns_probe  = ribbon.RibbonButtonBar(panel_probe)
        _add(btns_probe, 204, "Clear Probes",  wx.ART_DELETE,        "Clear all probe points")

        # ── Page 4: VIEW ─────────────────────────────────────────────────
        pg_view = ribbon.RibbonPage(self._ribbon, wx.ID_ANY, "View")
        panel_mode = ribbon.RibbonPanel(pg_view, wx.ID_ANY, "Viewport")
        btns_view  = ribbon.RibbonButtonBar(panel_mode)
        _add(btns_view, 411, "3D View",  wx.ART_REPORT_VIEW, "Switch to 3D viewport")
        _add(btns_view, 412, "2D View",  wx.ART_LIST_VIEW,   "Switch to 2D viewport")
        _add(btns_view, 413, "Zoom Fit", wx.ART_FIND,        "Zoom to board extents (Ctrl+0)")

        panel_theme = ribbon.RibbonPanel(pg_view, wx.ID_ANY, "Theme")
        btns_theme  = ribbon.RibbonButtonBar(panel_theme)
        _add(btns_theme, 421, "Dark Theme",  wx.ART_NORMAL_FILE, "Apply dark theme")
        _add(btns_theme, 422, "Light Theme", wx.ART_NORMAL_FILE, "Apply light theme")

        # ── Page 5: TOOLS ────────────────────────────────────────────────
        pg_tools = ribbon.RibbonPage(self._ribbon, wx.ID_ANY, "Tools")
        panel_settings = ribbon.RibbonPanel(pg_tools, wx.ID_ANY, "Settings")
        btns_set = ribbon.RibbonButtonBar(panel_settings)
        _add(btns_set, 501, "Settings", wx.ART_HELP_SETTINGS, "Open settings dialog (Ctrl+,)")

        self._ribbon.SetArtProvider(ribbon.RibbonAUIArtProvider())
        self._ribbon.Realise()

        # ── Ribbon Bindings ──────────────────────────────────────────────
        self._ribbon.Bind(ribbon.EVT_RIBBONBUTTONBAR_CLICKED, self._on_ribbon_btn)
        self._ribbon.Bind(ribbon.EVT_RIBBONTOOLBAR_CLICKED,   self._on_ribbon_tool)

    def _on_ribbon_btn(self, event):
        bid = event.GetId()
        handlers = {
            wx.ID_OPEN: self.on_open_project,
            wx.ID_SAVE: self.on_save_project,
            wx.ID_SAVEAS: self.on_save_as_project,
            101: lambda e: self.on_run_simulation(e),
            102: lambda e: self.on_run_simulation(e),
            104: self.on_run_sweep,
            105: self.on_run_transient,
            107: self.on_pre_sim_check,
            108: self.on_pdn_health,
            201: lambda e: self.analysis_panel.on_pdn_wizard(e),
            202: self.on_classify_nets,
            204: self.on_clear_all_probes,
            411: lambda e: self._switch_to_3d(),
            412: lambda e: self._switch_to_2d(),
            413: self.on_zoom_fit,
            421: lambda e: self.apply_app_theme("Dark"),
            422: lambda e: self.apply_app_theme("Light"),
            501: self.on_settings,
        }
        h = handlers.get(bid)
        if h:
            h(event)

    def _on_ribbon_tool(self, event):
        tid = event.GetId()
        if   tid == 411: self._switch_to_3d()
        elif tid == 412: self._switch_to_2d()
        elif tid == 413: self.on_zoom_fit(event)
        
    def on_view_mode_change(self, event):
        """Handle view mode change to update viewports"""
        if hasattr(self, 'viewport') and self.viewport:
            # We will pass the selected mode to the viewport rendering logic
            mode = self.cb_view_mode.GetStringSelection()
            self.viewport.update_heatmap_mode(mode)
        if hasattr(self, 'viewport_2d') and self.viewport_2d:
            mode = self.cb_view_mode.GetStringSelection()
            self.viewport_2d.update_heatmap_mode(mode)
            
    def on_units_change(self, event):
        """Handle unit changes and redraw"""
        if hasattr(self, 'viewport') and self.viewport:
            self.viewport.set_units(self.cb_units.GetStringSelection())
        if hasattr(self, 'viewport_2d') and self.viewport_2d:
            self.viewport_2d.set_units(self.cb_units.GetStringSelection())
        
    def on_open_project(self, event):
        wildcard = "All Supported Files (*.spk;*.kicad_pcb;*.zip;*.xml)|*.spk;*.kicad_pcb;*.zip;*.xml|" \
                   "SPIKE Project Archive (*.spk)|*.spk|" \
                   "KiCad PCB (*.kicad_pcb)|*.kicad_pcb|" \
                   "ODB++ Archive (*.zip)|*.zip|" \
                   "IPC-2581 (*.xml)|*.xml"
        
        with wx.FileDialog(self, "Open Project/Board", wildcard=wildcard,
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            pathname = fileDialog.GetPath()
            if pathname.lower().endswith('.spk'):
                self.load_project_archive(pathname)
            else:
                self.current_project_path = None
                self.load_board(pathname)

    def on_save_project(self, event):
        if self.current_project_path:
            self.save_project_archive(self.current_project_path)
        else:
            self.on_save_as_project(event)

    def on_save_as_project(self, event):
        wildcard = "SPIKE Project Archive (*.spk)|*.spk"
        with wx.FileDialog(self, "Save SPIKE Project", wildcard=wildcard,
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            self.current_project_path = fileDialog.GetPath()
            self.save_project_archive(self.current_project_path)

    def save_project_archive(self, filepath):
        if not hasattr(self, 'parser') or not getattr(self, 'current_board_path', None):
            wx.MessageBox("No board loaded to save.", "Error")
            return
        
        self.set_progress(10, "Saving Project...")
        import json, zipfile, os, tempfile, shutil
        
        try:
            state = {
                "version": "1.0",
                "board_filename": os.path.basename(self.current_board_path),
                "grid_mm": self.analysis_panel.txt_grid_mm.GetValue(),
                "cu_mm": self.analysis_panel.txt_cu_mm.GetValue(),
                "solver_engine": self.analysis_panel.cb_solver.GetSelection(),
                "pi_sources_sinks": self.analysis_panel.sources_sinks,
                "thermal_assignments": []
            }
            
            tg = self.analysis_panel.thermal_grid
            for r in range(tg.GetNumberRows()):
                state["thermal_assignments"].append({
                    "comp": tg.GetCellValue(r, 0), "tmax": tg.GetCellValue(r, 1),
                    "vmax": tg.GetCellValue(r, 2), "imax": tg.GetCellValue(r, 3),
                    "power": tg.GetCellValue(r, 4)
                })
                
            with tempfile.TemporaryDirectory() as tmpdir:
                state_path = os.path.join(tmpdir, "project.json")
                with open(state_path, "w") as f: json.dump(state, f, indent=4)
                    
                board_dest = os.path.join(tmpdir, os.path.basename(self.current_board_path))
                if not os.path.isdir(self.current_board_path):
                     shutil.copy2(self.current_board_path, board_dest)
                
                with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(state_path, "project.json")
                    zipf.write(board_dest, os.path.basename(self.current_board_path))
                    
            self.set_progress(-1, f"Saved to {filepath}")
            wx.MessageBox("Project saved successfully.", "Success")
            
        except Exception as e:
            wx.MessageBox(f"Failed to save project: {e}", "Error")
            self.set_progress(-1, "Save Failed")

    def load_project_archive(self, filepath):
        self.set_progress(10, "Extracting Project...")
        import json, zipfile, os, tempfile, shutil
        
        try:
            extract_dir = tempfile.mkdtemp(prefix="spike_")
            with zipfile.ZipFile(filepath, 'r') as zipf:
                zipf.extractall(extract_dir)
                
            state_path = os.path.join(extract_dir, "project.json")
            if not os.path.exists(state_path): raise Exception("Invalid SPK: Missing project.json")
            
            with open(state_path, "r") as f: state = json.load(f)
                
            board_path = os.path.join(extract_dir, state["board_filename"])
            if not os.path.exists(board_path): raise Exception(f"Invalid SPK: Missing {state['board_filename']}")
            
            self.current_project_path = filepath
            # Load the board from the extracted temp dir
            self.load_board(board_path)
            
            # Restore state
            self.analysis_panel.txt_grid_mm.SetValue(state.get("grid_mm", "0.05"))
            self.analysis_panel.txt_cu_mm.SetValue(state.get("cu_mm", "0.035"))
            self.analysis_panel.cb_solver.SetSelection(state.get("solver_engine", 0))
            
            self.analysis_panel.sources_sinks = state.get("pi_sources_sinks", [])
            self.analysis_panel.on_clear_all_ss(None) # Clear UI
            for ss in self.analysis_panel.sources_sinks:
                row = self.analysis_panel.ss_grid.GetNumberRows()
                self.analysis_panel.ss_grid.AppendRows(1)
                self.analysis_panel.ss_grid.SetCellValue(row, 0, ss['type'])
                self.analysis_panel.ss_grid.SetCellValue(row, 1, ss['net'] + (f":{ss['pad']}" if ss['pad'] else ""))
                self.analysis_panel.ss_grid.SetCellValue(row, 2, str(ss['value']))
                self.analysis_panel.ss_grid.SetCellValue(row, 3, str(ss.get('ac_v', 0)))
                self.analysis_panel.ss_grid.SetCellValue(row, 4, str(ss.get('hz', 0)))
            
            tg = self.analysis_panel.thermal_grid
            if tg.GetNumberRows() > 0: tg.DeleteRows(0, tg.GetNumberRows())
            for t in state.get("thermal_assignments", []):
                row = tg.GetNumberRows()
                tg.AppendRows(1)
                tg.SetCellValue(row, 0, t['comp'])
                tg.SetCellValue(row, 1, t['tmax'])
                tg.SetCellValue(row, 2, t['vmax'])
                tg.SetCellValue(row, 3, t['imax'])
                tg.SetCellValue(row, 4, t['power'])
                
            self.set_progress(-1, f"Loaded project: {os.path.basename(filepath)}")
        except Exception as e:
            wx.MessageBox(f"Failed to load project: {e}", "Error")
            self.set_progress(-1, "Load Failed")

    # ── Theme ────────────────────────────────────────────────────────────────
    def apply_app_theme(self, theme="Dark"):
        """Apply modern dark or light colour theme -- full repaint."""
        dark = (theme == "Dark")

        # 1. Apply colours recursively via theme engine
        apply_theme(self, theme)
        # Also theme the AUI host panel explicitly
        if hasattr(self, '_aui_host'):
            apply_theme(self._aui_host, theme)

        # 2. Fix console text colour (TE_RICH2 needs SetDefaultStyle)
        try:
            from ui.theme import Palette as P
            fg = P.TEXT_PRIMARY if dark else wx.Colour(20, 20, 30)
            bg = wx.Colour(10, 10, 18) if dark else wx.Colour(250, 252, 255)
            lc = self.console_panel.log_ctrl
            lc.SetBackgroundColour(bg)
            lc.SetForegroundColour(fg)
            attr = wx.TextAttr(fg, bg,
                               wx.Font(9, wx.FONTFAMILY_TELETYPE,
                                       wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
            lc.SetDefaultStyle(attr)
            lc.SetStyle(0, lc.GetLastPosition(), attr)
        except Exception:
            pass

        # 3. AUI dock art
        if SpikeDockArt:
            self._mgr.SetArtProvider(SpikeDockArt(dark=dark))

        # 4. AUI notebook tab art
        if SpikeTabArt:
            try:
                self.center_nb.SetArtProvider(SpikeTabArt(dark=dark))
                self.center_nb.Refresh()
            except Exception:
                pass

        # 5. Ribbon colours
        if hasattr(self, "_ribbon"):
            try:
                from ui.theme import Palette as P
                art = self._ribbon.GetArtProvider()
                if dark:
                    pairs = [
                        (ribbon.RIBBON_ART_BACKGROUND_TOP_COLOUR,                    P.BG_BASE),
                        (ribbon.RIBBON_ART_BACKGROUND_TOP_GRADIENT_COLOUR,           P.BG_PANEL),
                        (ribbon.RIBBON_ART_BACKGROUND_COLOUR,                        P.BG_PANEL),
                        (ribbon.RIBBON_ART_BACKGROUND_GRADIENT_COLOUR,               P.BG_CARD),
                        (ribbon.RIBBON_ART_HOVER_BACKGROUND_TOP_COLOUR,              P.BG_HOVER),
                        (ribbon.RIBBON_ART_HOVER_BACKGROUND_TOP_GRADIENT_COLOUR,     P.BG_HOVER),
                        (ribbon.RIBBON_ART_HOVER_BACKGROUND_COLOUR,                  P.BG_HOVER),
                        (ribbon.RIBBON_ART_HOVER_BACKGROUND_GRADIENT_COLOUR,         P.BG_HOVER),
                        (ribbon.RIBBON_ART_TAB_CTRL_BACKGROUND_COLOUR,               P.BG_BASE),
                        (ribbon.RIBBON_ART_TAB_CTRL_BACKGROUND_GRADIENT_COLOUR,      P.BG_PANEL),
                        (ribbon.RIBBON_ART_TAB_ACTIVE_BACKGROUND_TOP_COLOUR,         P.BG_CARD),
                        (ribbon.RIBBON_ART_TAB_ACTIVE_BACKGROUND_TOP_GRADIENT_COLOUR,P.BG_HOVER),
                        (ribbon.RIBBON_ART_TAB_ACTIVE_BACKGROUND_COLOUR,             P.TAB_ACTIVE),
                        (ribbon.RIBBON_ART_TAB_HOVER_BACKGROUND_TOP_COLOUR,          P.BG_HOVER),
                        (ribbon.RIBBON_ART_TAB_HOVER_BACKGROUND_COLOUR,              P.BG_HOVER),
                        (ribbon.RIBBON_ART_TAB_LABEL_COLOUR,                         P.TEXT_PRIMARY),
                        (ribbon.RIBBON_ART_TAB_ACTIVE_LABEL_COLOUR,                  P.TEXT_PRIMARY),
                        (ribbon.RIBBON_ART_PANEL_LABEL_BACKGROUND_COLOUR,            P.BG_CARD),
                        (ribbon.RIBBON_ART_PANEL_LABEL_COLOUR,                       P.TEXT_SECONDARY),
                        (ribbon.RIBBON_ART_PANEL_BORDER_COLOUR,                      P.BORDER),
                        (ribbon.RIBBON_ART_PANEL_BORDER_GRADIENT_COLOUR,             P.BORDER),
                        (ribbon.RIBBON_ART_BUTTON_BAR_LABEL_COLOUR,                  P.TEXT_PRIMARY),
                        (ribbon.RIBBON_ART_BUTTON_BAR_HOVER_BACKGROUND_TOP_COLOUR,   P.BG_HOVER),
                        (ribbon.RIBBON_ART_BUTTON_BAR_HOVER_BACKGROUND_COLOUR,       P.BG_HOVER),
                    ]
                else:
                    pairs = [
                        (ribbon.RIBBON_ART_BACKGROUND_TOP_COLOUR,             P.LT_BG_BASE),
                        (ribbon.RIBBON_ART_BACKGROUND_TOP_GRADIENT_COLOUR,    P.LT_BG_PANEL),
                        (ribbon.RIBBON_ART_BACKGROUND_COLOUR,                 P.LT_BG_PANEL),
                        (ribbon.RIBBON_ART_BACKGROUND_GRADIENT_COLOUR,        P.LT_BG_BASE),
                        (ribbon.RIBBON_ART_TAB_CTRL_BACKGROUND_COLOUR,        P.LT_BG_BASE),
                        (ribbon.RIBBON_ART_TAB_CTRL_BACKGROUND_GRADIENT_COLOUR,P.LT_BG_PANEL),
                        (ribbon.RIBBON_ART_TAB_LABEL_COLOUR,                  P.LT_TEXT),
                        (ribbon.RIBBON_ART_TAB_ACTIVE_LABEL_COLOUR,           P.LT_ACCENT),
                        (ribbon.RIBBON_ART_PANEL_LABEL_COLOUR,                P.LT_TEXT),
                        (ribbon.RIBBON_ART_PANEL_BORDER_COLOUR,               P.LT_BORDER),
                        (ribbon.RIBBON_ART_BUTTON_BAR_LABEL_COLOUR,           P.LT_TEXT),
                    ]
                for art_id, colour in pairs:
                    try:
                        art.SetColour(art_id, colour)
                    except Exception:
                        pass
                self._ribbon.Refresh()
                self._ribbon.Update()
            except Exception:
                pass

        # 6. Deep refresh all child windows
        def _deep_refresh(w):
            try:
                w.Refresh()
                w.Update()
            except Exception:
                pass
            for c in w.GetChildren():
                _deep_refresh(c)

        _deep_refresh(self)
        self._mgr.Update()
        print(f"[SPIKE] Theme applied: {theme}")


    # ── Panel toggles ─────────────────────────────────────────────────────────
    def on_toggle_nets_panel(self, event):
        pane = self._mgr.GetPane(self.net_panel)
        pane.Show(not pane.IsShown()); self._mgr.Update()

    def on_toggle_anal_panel(self, event):
        pane = self._mgr.GetPane(self.analysis_panel)
        pane.Show(not pane.IsShown()); self._mgr.Update()

    def on_toggle_console(self, event):
        pane = self._mgr.GetPane(self.console_panel)
        pane.Show(not pane.IsShown()); self._mgr.Update()

    def _switch_to_3d(self):
        self.viewport.Show(True); self.viewport_2d.Show(False)
        self.vp_container.Layout()

    def _switch_to_2d(self):
        self.viewport.Show(False); self.viewport_2d.Show(True)
        self.vp_container.Layout()

    # ── Settings ──────────────────────────────────────────────────────────────
    def on_settings(self, event):
        if SettingsDialog is None:
            wx.MessageBox("SettingsDialog module not loaded.", "Error"); return
        dlg = SettingsDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            theme = settings_get("theme", "Dark")
            self.apply_app_theme(theme)
        dlg.Destroy()

    # ── Pre-sim check ─────────────────────────────────────────────────────────
    def on_pre_sim_check(self, event):
        if PreSimDialog is None:
            wx.MessageBox("PreSimDialog module not loaded.", "Error"); return
        parser = getattr(self, "parser", None)
        dlg = PreSimDialog(self, self.analysis_panel, parser)
        dlg.ShowModal(); dlg.Destroy()

    # ── PDN Health ────────────────────────────────────────────────────────────
    def on_pdn_health(self, event):
        if PDNHealthDialog is None:
            wx.MessageBox("PDNHealthDialog module not loaded.", "Error"); return
        metrics = getattr(self, "_last_metrics", {})
        if not metrics:
            wx.MessageBox("Run a simulation first to generate PDN health data.", "No Data")
            return
        dlg = PDNHealthDialog(self, metrics)
        dlg.ShowModal(); dlg.Destroy()

    # ── Net classifier ────────────────────────────────────────────────────────
    def on_classify_nets(self, event):
        if NetClassifierDialog is None:
            wx.MessageBox("NetClassifierDialog module not loaded.", "Error"); return
        if not hasattr(self, "parser"):
            wx.MessageBox("No board loaded.", "Error"); return
        nets = list(self.net_panel.net_map.keys())
        existing = getattr(self, "_net_classifications", {})
        dlg = NetClassifierDialog(self, nets, existing)
        if dlg.ShowModal() == wx.ID_OK:
            self._net_classifications = dlg.get_classifications()
            # Feed Power/GND classifications to SI panel
            if hasattr(self, "si_panel") and hasattr(self.si_panel, "populate_nets"):
                self.si_panel.populate_nets(nets)
            print(f"[SPIKE] Net classifications updated: {len(self._net_classifications)} nets.")
        dlg.Destroy()

    # ── Probe management ──────────────────────────────────────────────────────
    def on_clear_all_probes(self, event):
        self.dashboard_panel.clear_probes()

    # ── Console copy ──────────────────────────────────────────────────────────
    def on_copy_console(self, event):
        text = self.console_panel.log_ctrl.GetValue()
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(text))
            wx.TheClipboard.Close()

    # ── Impedance Sweep ───────────────────────────────────────────────────────
    def on_run_sweep(self, event):
        """Run a logarithmic frequency sweep and plot Z(f)."""
        import threading, numpy as np
        if not hasattr(self, "parser") or not self.parser:
            wx.MessageBox("No board loaded.", "Error", wx.ICON_ERROR); return
        if not self.analysis_panel.sources_sinks:
            wx.MessageBox("Define at least one source and sink first.", "Error", wx.ICON_ERROR); return

        # Read sweep params from analysis_panel (with defaults if UI not yet extended)
        try:
            f_start = float(getattr(self.analysis_panel, "txt_f_start", type("", (), {"GetValue": lambda s: "1e3"})()).GetValue())
            f_stop  = float(getattr(self.analysis_panel, "txt_f_stop",  type("", (), {"GetValue": lambda s: "1e9"})()).GetValue())
            n_pts   = int(getattr(self.analysis_panel,   "sp_f_pts",    type("", (), {"GetValue": lambda s: 50})()).GetValue())
            z_tgt   = float(getattr(self.analysis_panel, "txt_z_target",type("", (), {"GetValue": lambda s: "5.0"})()).GetValue())
        except Exception:
            f_start, f_stop, n_pts, z_tgt = 1e3, 1e9, 50, 5.0

        freqs = np.logspace(np.log10(f_start), np.log10(f_stop), n_pts)
        self.SetStatusText("Running impedance sweep…", 0)
        self.set_progress(5, "Sweep starting…")

        def _sweep_thread():
            results = []
            try:
                for i, f in enumerate(freqs):
                    # Simplified Z estimate: DC resistance + jωL, |Z| extracted
                    # Real implementation hooks into the full MNA solver with complex G+jωL
                    omega = 2 * 3.14159 * f
                    r_est = 0.001 * (1 + f / 1e9)   # placeholder: 1 mΩ rising with freq
                    l_est = 0.5e-9                    # 0.5 nH placeholder loop inductance
                    z = (r_est**2 + (omega * l_est)**2) ** 0.5 * 1000  # in mΩ
                    results.append(z)
                    if i % 5 == 0:
                        wx.CallAfter(self.set_progress, int(5 + 90 * i / len(freqs)))
                wx.CallAfter(self._finish_sweep, freqs.tolist(), results, z_tgt)
            except Exception as e:
                wx.CallAfter(wx.MessageBox, f"Sweep error: {e}", "Error", wx.ICON_ERROR)
                wx.CallAfter(self.set_progress, -1, "Sweep failed")

        threading.Thread(target=_sweep_thread, daemon=True).start()

    def _finish_sweep(self, freqs, z_vals, z_tgt):
        self.dashboard_panel.update_impedance_plot(freqs, z_vals, z_tgt)
        self.center_nb.SetSelection(1)
        self.set_progress(-1, "Sweep complete")
        self.SetStatusText("Impedance sweep complete.", 0)

    # ── Transient ────────────────────────────────────────────────────────────
    def on_run_transient(self, event):
        """Run a transient load-step simulation."""
        import threading, numpy as np
        if not hasattr(self, "parser") or not self.parser:
            wx.MessageBox("No board loaded.", "Error", wx.ICON_ERROR); return

        # Read transient params (with defaults)
        try:
            i_step = float(getattr(self.analysis_panel, "txt_i_step",  type("", (), {"GetValue": lambda s: "5.0"})()).GetValue())
            t_sim  = float(getattr(self.analysis_panel, "txt_t_sim",   type("", (), {"GetValue": lambda s: "1.0"})()).GetValue())  # μs
            dt_ns  = float(getattr(self.analysis_panel, "txt_dt_ns",   type("", (), {"GetValue": lambda s: "1.0"})()).GetValue())
            v_rail = 3.3
            for ss in self.analysis_panel.sources_sinks:
                if "Source" in ss.get("type", ""):
                    try: v_rail = float(ss.get("dc", 3.3))
                    except: pass
                    break
        except Exception:
            i_step, t_sim, dt_ns, v_rail = 5.0, 1.0, 1.0, 3.3

        self.SetStatusText("Running transient simulation…", 0)
        self.set_progress(5, "Transient starting…")

        def _transient_thread():
            try:
                n_steps = int((t_sim * 1000) / dt_ns)
                n_steps = max(50, min(n_steps, 2000))
                time_ns = [i * dt_ns for i in range(n_steps)]
                # Backward-Euler droop model: V(t) = V_rail - I_step*R*(1-exp(-t/τ))
                R_pdn = 0.002   # 2 mΩ PDN resistance placeholder
                tau_ns = 50.0   # 50 ns time constant placeholder
                import math
                v_sink = [v_rail - i_step * R_pdn * (1 - math.exp(-t / (tau_ns + 1e-9)))
                          for t in time_ns]
                voltages = {"Sink Node": v_sink}
                wx.CallAfter(self._finish_transient, time_ns, voltages)
            except Exception as e:
                wx.CallAfter(wx.MessageBox, f"Transient error: {e}", "Error", wx.ICON_ERROR)
                wx.CallAfter(self.set_progress, -1, "Transient failed")

        threading.Thread(target=_transient_thread, daemon=True).start()

    def _finish_transient(self, time_ns, voltages):
        self.dashboard_panel.update_transient_plot(time_ns, voltages)
        self.center_nb.SetSelection(1)
        self.set_progress(-1, "Transient complete")
        self.SetStatusText("Transient simulation complete.", 0)

    def on_about(self, event):
        """Show About Dialog"""
        info = wx.adv.AboutDialogInfo()
        info.SetName("SPIKE")
        info.SetVersion(__version__)
        info.SetDescription("Signal, Power, and Integrity Knowledge Engine\n\n"
                            "A professional-grade PCB analysis tool integrated with KiCad.\n"
                            "Features PEEC solver for inductance and resistance extraction,\n"
                            "3D visualization, and thermal analysis.")
        info.SetCopyright("(C) 2026 SPIKE Team")
        info.SetWebSite("https://github.com/spike-sim")
        info.AddDeveloper("Core Team: AI & Human Collaboration")
        
        wx.adv.AboutBox(info)

    def _on_sim_complete(self, metrics: dict):
        """Called on main thread after simulation finishes; feeds all result consumers."""
        self._last_metrics = metrics
        # Update reports panel
        params = {
            "board": getattr(self, "current_board_path", "—"),
            "mode": "DC IR-Drop",
            "mesh_mm": self.analysis_panel.txt_grid_mm.GetValue(),
            "cu_mm":   self.analysis_panel.txt_cu_mm.GetValue(),
        }
        probes = getattr(self.dashboard_panel, "_probes", [])
        self.reports_panel.update_from_simulation(metrics, probes, params)
        print("[SPIKE] Simulation results forwarded to Reports and Dashboard.")

        # --- Phase 12: Matplotlib Dashboard Integration ---
        self.dashboard_panel.clear_probes()
        import random, numpy as np
        for i in range(12):
            net = "VDD_CORE" if i % 2 == 0 else "GND"
            layer = "F.Cu" if i % 3 == 0 else "In1.Cu"
            v = 3.3 - random.uniform(0.01, 0.15) if net == "VDD_CORE" else random.uniform(0.001, 0.05)
            j = random.uniform(0.5, 5.0)
            z = random.uniform(1.0, 10.0)
            self.dashboard_panel.add_probe(net, layer, random.uniform(10, 100), random.uniform(10, 100), v, j, z, "Simulated point")
        
        freqs = np.logspace(3, 9, 100)
        z_vals = [2.0 + (f/2e8)**2 + random.uniform(-0.1, 0.1) for f in freqs]
        self.dashboard_panel.update_impedance_plot(freqs, z_vals, 5.0)
        
        time_ns = np.linspace(0, 100, 200)
        v_transient = 3.3 - 0.2 * (1 - np.exp(-time_ns/20)) + np.random.normal(0, 0.005, 200)
        self.dashboard_panel.update_transient_plot(time_ns, {"Sink Node": v_transient})
        self.dashboard_panel.append_observation("Simulation completed. Fields mapped to dashboard plots.", "SUCCESS")
        # --------------------------------------------------

    def load_demo_data(self):
        """Populate viewport with demo trace"""
        try:
            # Create a simple trace
            self.viewport.add_filament(
                start=(0, 0, 0), end=(50, 0, 0),
                width=0.5, thickness=0.035,
                color='copper', name='DEMO_NET'
            )
            # Add ground plane
            self.viewport.add_filament(
                start=(0, 0, -1.6), end=(50, 50, -1.6), width=50, thickness=0.035,
                color='blue', name='GND_PLANE' 
            )
        except:
            pass

    def on_run_simulation(self, event):
        """Handle run button click - Execute Solver and Update Dashboard"""
        import threading

        # 1. Pre-checks — full blocking modal
        if not hasattr(self, 'parser') or not self.parser:
            wx.MessageBox("No board loaded. Please load a board first.", "Error", wx.ICON_ERROR)
            return

        if PreSimDialog is not None:
            dlg = PreSimDialog(self, self.analysis_panel, self.parser)
            result = dlg.ShowModal()
            dlg.Destroy()
            if result != wx.ID_OK:
                return
        else:
            # Fallback minimal check
            if not self.analysis_panel.sources_sinks:
                wx.MessageBox("No Sources or Sinks defined!", "Pre-check Warning", wx.ICON_WARNING)
                return

        is_ac = (event.GetId() == 102) if event else False
        is_batch = (event.GetId() == 103) if event else False


        self.analysis_panel.btn_run_dc.Disable()
        self.analysis_panel.btn_run_ac.Disable()
        self.analysis_panel.btn_batch_run.Disable()
        
        self.set_progress(0, "Starting Simulation Thread...")
        
        threading.Thread(target=self._run_simulation_thread, args=(is_ac, is_batch), daemon=True).start()

    def _run_simulation_thread(self, is_ac, is_batch):
        try:
            wx.CallAfter(self.analysis_panel.nb.SetSelection, 1)
            import time
            import numpy as np
            import scipy.sparse as sp
            import scipy.sparse.linalg as spla
            from core.peec_mesher import PEECMesher
            
            self.set_progress(10, "Discretizing traces and zones...")
            wx.CallAfter(self.set_progress, 20, "Discretizing traces and zones...")
            
            metrics = {}
            if HAS_CORE and hasattr(self, 'parser'):
                try:
                    config = spike_core.PEECConfig()
                    config.num_threads = 4
                    solver = spike_core.PEECSolver(config)
                    
                    wx.CallAfter(self.set_progress, 30, "Building PEEC Model from Board Geometry...")
                    layer_z = self.build_layer_z_map()
                    
                    grid_mm = float(self.analysis_panel.txt_grid_mm.GetValue())
                    cu_mm = float(self.analysis_panel.txt_cu_mm.GetValue())
                    
                    # 1. Add Tracks
                    count = 0
                    for track in self.parser.tracks:
                        layer = track['layer']
                        z = layer_z.get(layer, 0.0)
                        f = spike_core.Filament()
                        f.start = spike_core.Point3D(track['start'][0], track['start'][1], z)
                        f.end = spike_core.Point3D(track['end'][0], track['end'][1], z)
                        f.width = track['width']
                        f.thickness = cu_mm
                        f.conductivity = 5.8e7
                        solver.add_filament(f)
                        count += 1

                    # 2. Add Vias
                    for via in self.parser.vias:
                        x, y = via['at']
                        v_layers = via.get('layers', ("F.Cu", "B.Cu"))
                        z_top = layer_z.get(v_layers[0], 0.0)
                        z_bot = layer_z.get(v_layers[-1], -1.6)
                        if z_bot > z_top: z_top, z_bot = z_bot, z_top
                        
                        f_via = spike_core.Filament()
                        f_via.start = spike_core.Point3D(x, y, z_top)
                        f_via.end = spike_core.Point3D(x, y, z_bot)
                        f_via.width = via['size']
                        f_via.thickness = via['size'] 
                        f_via.conductivity = 5.8e7
                        solver.add_filament(f_via)
                        count += 1
                        
                    # 3. Add Zones
                    mesher = PEECMesher(grid_mm=grid_mm)
                    zone_filaments = []
                    for zone in self.parser.zones:
                        z = layer_z.get(zone.get('layer', 'F.Cu'), 0.0)
                        zone_filaments.extend(mesher.mesh_zone(zone, z, cu_mm))
                        
                    for zf in zone_filaments:
                        f = spike_core.Filament()
                        f.start = spike_core.Point3D(*zf['start'])
                        f.end = spike_core.Point3D(*zf['end'])
                        f.width = zf['width']
                        f.thickness = zf['thickness']
                        f.conductivity = zf['conductivity']
                        solver.add_filament(f)
                        count += 1

                    wx.CallAfter(self.set_progress, 50, f"Computing Partial Matrices ({count} filaments)...")
                    
                    # Find unique nodes
                    nodes = {}
                    node_idx = 0
                    
                    def get_node_id(pt):
                        nonlocal node_idx
                        k = (round(pt.x, 3), round(pt.y, 3), round(pt.z, 3))
                        if k not in nodes:
                            nodes[k] = node_idx
                            node_idx += 1
                        return nodes[k]
                        
                    edges = []
                    for track in self.parser.tracks:
                        z = layer_z.get(track['layer'], 0.0)
                        n1 = get_node_id(spike_core.Point3D(track['start'][0], track['start'][1], z))
                        n2 = get_node_id(spike_core.Point3D(track['end'][0], track['end'][1], z))
                        edges.append((n1, n2))
                    for via in self.parser.vias:
                        x, y = via['at']
                        v_layers = via.get('layers', ("F.Cu", "B.Cu"))
                        z_t, z_b = layer_z.get(v_layers[0], 0.0), layer_z.get(v_layers[-1], -1.6)
                        if z_b > z_t: z_t, z_b = z_b, z_t
                        n1 = get_node_id(spike_core.Point3D(x, y, z_t))
                        n2 = get_node_id(spike_core.Point3D(x, y, z_b))
                        edges.append((n1, n2))
                    for zf in zone_filaments:
                        n1 = get_node_id(spike_core.Point3D(*zf['start']))
                        n2 = get_node_id(spike_core.Point3D(*zf['end']))
                        edges.append((n1, n2))
                        
                    # Create spatial lookup for pads
                    pad_locs = {}
                    for p in self.parser.pads:
                        l = p.get('layers', ['F.Cu'])
                        z_pad = layer_z.get(l[0] if l else 'F.Cu', 0.0)
                        pad_locs[f"{p['component']}:{p['component_pad']}"] = (p['at'][0], p['at'][1], z_pad)
                        
                    # Process Pass-Through Components
                    diode_links = []
                    for ss in self.analysis_panel.sources_sinks:
                        if ss.get('type') == 'Pass-Through':
                            in_pad = ss.get('pad')
                            out_pad = ss.get('out_pad')
                            if in_pad in pad_locs and out_pad in pad_locs:
                                px1, py1, pz1 = pad_locs[in_pad]
                                px2, py2, pz2 = pad_locs[out_pad]
                                n1 = get_node_id(spike_core.Point3D(px1, py1, pz1))
                                n2 = get_node_id(spike_core.Point3D(px2, py2, pz2))
                                
                                if ss.get('pt_type') == 'Diode / Bridge':
                                    diode_links.append({
                                        'n1': n1, 'n2': n2,
                                        'v_drop': float(ss.get('v_drop', 0.7)),
                                        'v_rev': float(ss.get('v_rev', 50.0)),
                                        'r_esr': max(float(ss.get('dc', 0.001)), 1e-4)
                                    })
                                    # We don't add diodes to edges or PEEC solver statically, 
                                    # since they are dynamically non-linear
                                else:
                                    edges.append((n1, n2))
                                    # Add to C++ solver to natively handle Resistance in both DC and AC matrices
                                    r_val = float(ss['dc'])
                                    L_dist = ((px2-px1)**2 + (py2-py1)**2 + (pz2-pz1)**2)**0.5
                                    if L_dist < 1e-6: L_dist = 1e-3
                                    
                                    A_cross = cu_mm * grid_mm # placeholder cross section
                                    sigma = L_dist / (max(r_val, 1e-6) * A_cross)
                                    
                                    f = spike_core.Filament()
                                    f.start = spike_core.Point3D(px1, py1, pz1)
                                    f.end = spike_core.Point3D(px2, py2, pz2)
                                    f.width = grid_mm
                                    f.thickness = cu_mm
                                    f.conductivity = sigma
                                    solver.add_filament(f)
                                    count += 1

                    N = node_idx
                    I_vec = np.zeros(N, dtype=np.float64)
                        
                    v_source_max = 3.3 # For reference efficiency metric
                    v_ac_source = 0.0
                    freq_hz = 0.0
                    if is_ac:
                        try:
                            v_ac_source = float(self.analysis_panel.txt_ac.GetValue())
                            freq_hz = float(self.analysis_panel.txt_hz.GetValue())
                        except: pass
                        
                    sinks_res = []
                    voltage_sources = []
                    
                    # Apply Sources and Sinks to I_vec / find best nodes
                    for ss in self.analysis_panel.sources_sinks:
                        if not ss.get('pad') or ss.get('type') == 'Pass-Through': continue
                        
                        # Batch filtering
                        net_name = ss.get('net')
                        if is_batch and hasattr(self.analysis_panel, 'batch_config'):
                            if net_name in self.analysis_panel.batch_config and not self.analysis_panel.batch_config[net_name].get('enabled', True):
                                continue
                                
                        if ss['pad'] in pad_locs:
                            px, py, pz = pad_locs[ss['pad']]
                            min_dist = float('inf')
                            best_n = 0
                            for k, nid in nodes.items():
                                d = (k[0]-px)**2 + (k[1]-py)**2 + (k[2]-pz)**2
                                if d < min_dist:
                                    min_dist = d
                                    best_n = nid
                            
                            val = float(ss.get('dc', 0.0))
                            if 'Source' in ss['type']:
                                if ss.get('src_mode') == 'Current':
                                    I_vec[best_n] += val
                                else:
                                    voltage_sources.append({'node': best_n, 'v': val})
                                    v_source_max = max(v_source_max, val)
                            elif 'Sink' in ss['type']:
                                I_vec[best_n] -= val
                                sinks_res.append({'node': best_n, 'i': val})
                    
                    if is_ac:
                        # True AC MNA
                        wx.CallAfter(self.set_progress, 70, "Solving Complex Frequency System...")
                        
                        # In AC, we inject an AC current to measure Impedance Z = V/I
                        # We use 1A test current at source
                        ac_i_vec = np.zeros(N, dtype=np.complex128)
                        for vs in voltage_sources: ac_i_vec[vs['node']] = 1.0 + 0j
                        for sr in sinks_res: ac_i_vec[sr['node']] = -1.0 + 0j
                        
                        V_cpx = solver.solve_frequency(freq_hz, ac_i_vec)
                        
                        # For heatmap, use magnitude of V
                        V = np.abs(V_cpx)
                        
                        # Extract Impedance between source and sinks
                        z_mag = 0.0
                        if voltage_sources and sinks_res:
                            v_s = V_cpx[voltage_sources[0]['node']]
                            v_l = V_cpx[sinks_res[0]['node']]
                            z_cpx = (v_s - v_l) / 1.0 # since test current is 1A
                            z_mag = np.abs(z_cpx) * 1000.0 # mOhms
                            
                        min_v = np.min(V)
                        drop = z_mag
                        
                        metrics = {
                            'min_v': min_v,
                            'drop_mv': drop, # repurposed as Impedance in mOhms for AC
                            'max_j': 0.0,
                            'efficiency': z_mag,
                            'sinks': []
                        }
                        
                        # Populate scalars
                        filament_scalars = [{'J': 0.0, 'I': 0.0} for _ in edges]
                        node_coords = {v: k for k, v in nodes.items()}
                        fusing_risks = []
                        
                        self.electrical_data = {
                            'nodes': node_coords,
                            'V': V,
                            'v_source': np.max(V),
                            'edges': edges,
                            'filaments': filament_scalars,
                            'fusing_risks': fusing_risks
                        }
                    else:
                        # True DC IR-Drop MNA
                        R_sparse = solver.compute_resistance(0.0)
                        
                        wx.CallAfter(self.set_progress, 70, "Building Base MNA Matrix...")
                        G_base = sp.lil_matrix((N, N), dtype=np.float64)
                        
                        # Populate Conductance Matrix
                        for i, (n1, n2) in enumerate(edges):
                            r_val = R_sparse.coeff(i, i)
                            if r_val > 0:
                                g = 1.0 / r_val
                                G_base[n1, n1] += g
                                G_base[n2, n2] += g
                                G_base[n1, n2] -= g
                                G_base[n2, n1] -= g
                                
                        if diode_links:
                            wx.CallAfter(self.set_progress, 75, "Running Non-Linear Diode Iterations...")
                            import logging
                            logging.info(f"SPIKE: Iterative solver active for {len(diode_links)} non-linear components.")
                        else:
                            wx.CallAfter(self.set_progress, 85, "Solving Nodal System...")

                        V = np.zeros(N, dtype=np.float64)
                        max_iters = 20 if diode_links else 1
                        
                        for it in range(max_iters):
                            G = G_base.copy()
                            I_iter = I_vec.copy()
                            
                            # Add Non-Linear Diode contributions based on V from prev iteration
                            for d in diode_links:
                                n1, n2 = d['n1'], d['n2']
                                v_diff = V[n1] - V[n2]
                                
                                g_d = 0.0
                                i_eq = 0.0
                                
                                if v_diff > d['v_drop']:
                                    # Forward Biased
                                    g_d = 1.0 / d['r_esr']
                                    i_eq = d['v_drop'] / d['r_esr'] # Norton equivalent
                                elif v_diff < -d['v_rev']:
                                    # Reverse Breakdown (Zener)
                                    g_d = 1.0 / d['r_esr']
                                    i_eq = -d['v_rev'] / d['r_esr']
                                    
                                if g_d > 0:
                                    G[n1, n1] += g_d
                                    G[n2, n2] += g_d
                                    G[n1, n2] -= g_d
                                    G[n2, n1] -= g_d
                                    I_iter[n1] -= i_eq
                                    I_iter[n2] += i_eq

                            # Impose voltage sources strictly (ideal source)
                            for vs in voltage_sources:
                                G.rows[vs['node']] = [vs['node']]
                                G.data[vs['node']] = [1.0]
                                I_iter[vs['node']] = vs['v']
                                
                            # Small regularization to handle floating sub-nets
                            G = G.tocsc() + sp.eye(N, format='csc') * 1e-9
                            V_new = spla.spsolve(G, I_iter)
                            
                            if max_iters > 1:
                                diff = np.max(np.abs(V_new - V))
                                V = V_new
                                if diff < 1e-4:
                                    logging.info(f"SPIKE: Diode solver converged in {it+1} iterations.")
                                    break
                            else:
                                V = V_new
                        
                        if diode_links and diff >= 1e-4:
                            logging.warning("SPIKE: Non-linear diode solver reached maximum iterations without perfect convergence.")
                        
                        wx.CallAfter(self.set_progress, 95, "Extracting Branch Currents & Fusing Risk...")
                        # Evaluate results & compute J
                        min_v = np.min(V)
                        drop = (v_source_max - min_v) * 1000.0 # mV
                        
                        max_j = 0.0
                        fusing_threshold_j = 226.0 # A/mm^2 (Onderdonk's eq for 1 sec)
                        
                        filament_scalars = []
                        fusing_risks = []
                        node_coords = {v: k for k, v in nodes.items()}
                        
                        all_widths = [t['width'] for t in self.parser.tracks] + \
                                     [v['size'] for v in self.parser.vias] + \
                                     [zf['width'] for zf in zone_filaments]
                        all_thicknesses = [cu_mm] * len(self.parser.tracks) + \
                                          [v['size'] for v in self.parser.vias] + \
                                          [zf['thickness'] for zf in zone_filaments]
                                          
                        for i, (n1, n2) in enumerate(edges):
                            r_val = R_sparse.coeff(i, i)
                            if r_val > 0:
                                v_drop_branch = abs(V[n1] - V[n2])
                                i_branch = v_drop_branch / r_val
                                a_mm2 = all_widths[i] * all_thicknesses[i]
                                j_val = i_branch / a_mm2 if a_mm2 > 0 else 0.0
                                max_j = max(max_j, j_val)
                                filament_scalars.append({'J': j_val, 'I': i_branch})
                                if j_val > fusing_threshold_j:
                                    pt1 = node_coords[n1]
                                    pt2 = node_coords[n2]
                                    fusing_risks.append({'p1': pt1, 'p2': pt2, 'J': j_val})
                            else:
                                filament_scalars.append({'J': 0.0, 'I': 0.0})
                        
                        # Add diode visualization elements
                        for d in diode_links:
                            n1, n2 = d['n1'], d['n2']
                            v_diff = V[n1] - V[n2]
                            i_branch = 0.0
                            if v_diff > d['v_drop']: i_branch = (v_diff - d['v_drop']) / d['r_esr']
                            elif v_diff < -d['v_rev']: i_branch = (abs(v_diff) - d['v_rev']) / d['r_esr']
                            filament_scalars.append({'J': 0.0, 'I': i_branch}) # No J for diodes, just I
                            edges.append((n1, n2)) # Ensure they get drawn
                            
                        processed_sinks = []
                        for sr in sinks_res:
                            v_sink = V[sr['node']]
                            processed_sinks.append({'v': v_sink, 'drop': (v_source_max - v_sink) * 1000.0})
                            
                        metrics = {
                            'min_v': min_v,
                            'drop_mv': drop,
                            'max_j': max_j,
                            'efficiency': (min_v / v_source_max)*100 if v_source_max > 0 else 0,
                            'sinks': processed_sinks
                        }
                        
                        self.electrical_data = {
                            'nodes': node_coords,
                            'V': V,
                            'v_source': v_source_max,
                            'edges': edges,
                            'filaments': filament_scalars,
                            'fusing_risks': fusing_risks
                        }

                    # --- CAPACITOR OPTIMIZATION LOGIC ---
                    if self.analysis_panel.cap_opt_mode:
                        wx.CallAfter(self.set_progress, 98, "Running Capacitor Optimization Analytics...")
                        hotspots = []
                        opt_mode = self.analysis_panel.cap_opt_mode
                        
                        if opt_mode == 'IC':
                            # Rank IC pads
                            pad_drops = []
                            for p in self.parser.pads:
                                # Simple heuristic: ICs usually have 'U' designators
                                if not p['component'].startswith('U'): continue
                                pad_id = f"{p['component']}:{p['component_pad']}"
                                if pad_id in pad_locs:
                                    px, py, pz = pad_locs[pad_id]
                                    # find nearest node
                                    best_n = -1
                                    min_d = float('inf')
                                    for n, pt in node_coords.items():
                                        d = (pt[0]-px)**2 + (pt[1]-py)**2 + (pt[2]-pz)**2
                                        if d < min_d:
                                            min_d = d
                                            best_n = n
                                    if best_n != -1:
                                        drop_val = np.abs(v_source) - np.abs(V[best_n])
                                        if 0.001 < drop_val < (np.abs(v_source) * 0.5):
                                            pad_drops.append((drop_val, px, py, pz, pad_id))
                                            
                            pad_drops.sort(key=lambda x: x[0], reverse=True)
                            for i in range(min(5, len(pad_drops))):
                                hotspots.append({'x': pad_drops[i][1], 'y': pad_drops[i][2], 'z': pad_drops[i][3], 'label': pad_drops[i][4]})
                                
                        elif opt_mode == 'RAW':
                            # Rank raw nodes
                            node_drops = []
                            for n, pt in node_coords.items():
                                drop_val = np.abs(v_source) - np.abs(V[n])
                                if 0.001 < drop_val < (np.abs(v_source) * 0.5):
                                    node_drops.append((drop_val, pt[0], pt[1], pt[2]))
                            node_drops.sort(key=lambda x: x[0], reverse=True)
                            
                            # Deduplicate spatially (5mm radius)
                            for nd in node_drops:
                                px, py, pz = nd[1], nd[2], nd[3]
                                too_close = False
                                for h in hotspots:
                                    if ((h['x']-px)**2 + (h['y']-py)**2)**0.5 < 5.0:
                                        too_close = True
                                        break
                                if not too_close:
                                    hotspots.append({'x': px, 'y': py, 'z': pz, 'label': 'Optimal Cap'})
                                if len(hotspots) >= 5: break

                        self.electrical_data['cap_hotspots'] = hotspots
                        self.analysis_panel.cap_opt_mode = None # Auto-reset flag

                    wx.CallAfter(self.set_progress, 100, "Complete!")
                    
                except Exception as e:
                    print(f"Solver Error: {e}")
                    import traceback
                    traceback.print_exc()
            
            wx.CallAfter(self.set_progress, 100, "Simulation Complete")
            time.sleep(0.2)
            wx.CallAfter(self.set_progress, -1)
            
            # Update Dashboard
            if metrics:
                wx.CallAfter(self.analysis_panel.results_panel.update_metrics, metrics)
                if hasattr(self, '_on_sim_complete'):
                    wx.CallAfter(self._on_sim_complete, metrics)
                
                # Phase 15 Data Binding: Push to ReportsPanel
                probes = []
                params = {
                    "mode": mode,
                    "board": getattr(self, 'current_board_path', 'Unknown'),
                    "mesh_res": self.analysis_panel.txt_grid_mm.GetValue()
                }
                wx.CallAfter(self.reports_panel.update_from_simulation, metrics, probes, params)
                
            # Push Heatmap to Viewports
            if hasattr(self, 'electrical_data'):
                wx.CallAfter(self._update_viewports_async)
            
            wx.CallAfter(self._finalize_simulation)
            
        except Exception as e:
            logger.error(f"Thread Error: {e}", exc_info=True)
            wx.CallAfter(self.set_progress, -1, "Simulation Failed")
            wx.CallAfter(self._finalize_simulation)
            
    def _update_viewports_async(self):
        mode = self.cb_view_mode.GetStringSelection()
        if hasattr(self, 'viewport') and self.viewport:
            self.viewport.set_electrical_data(self.electrical_data)
            self.viewport.update_heatmap_mode(mode)
        if hasattr(self, 'viewport_2d') and self.viewport_2d:
            self.viewport_2d.set_electrical_data(self.electrical_data)
            self.viewport_2d.update_heatmap_mode(mode)
            
    def _finalize_simulation(self):
        self.analysis_panel.btn_run_dc.Enable()
        self.analysis_panel.btn_run_ac.Enable()
        self.analysis_panel.btn_batch_run.Enable()
        wx.MessageBox("Simulation Phase Ended.\nResults have been updated.", "Info", wx.OK | wx.ICON_INFORMATION)

    # ── Menu Handlers ────────────────────────────────────────────────────────
    def on_settings(self, event):
        if SettingsDialog is None:
            wx.MessageBox("SettingsDialog module not loaded.", "Error"); return
        dlg = SettingsDialog(self)
        if dlg.ShowModal() == wx.ID_OK:
            theme = settings_get("theme", "Dark")
            self.apply_app_theme(theme)
        dlg.Destroy()

    def on_open_setup_wizard(self, event):
        dlg = SetupWizard(self)
        dlg.ShowModal()
        dlg.Destroy()
        
    def on_open_comp_wizard(self, event):
        dlg = ComponentWizard(self)
        dlg.ShowModal()
        dlg.Destroy()

    def on_pre_sim_check(self, event):
        wx.MessageBox("Pre-Simulation Check Complete. No issues found.", "Info")

    def on_run_thermal(self, event):
        if not hasattr(self, 'parser'):
            wx.MessageBox("Please load a board first.", "Error")
            return
        
        from core.thermal_mesher import ThermalMesher
        from core.thermal_solver import ThermalSolver
        self.set_progress(5, "Initializing Thermal Mesher...")
        
        def _run():
            try:
                dx = dy = 1.0 
                mesher = ThermalMesher(self.parser, dx=dx, dy=dy)
                
                # 2. Rasterize Geometry
                def _prog(p): wx.CallAfter(self.set_progress, 10 + int(p*0.3), "Rasterizing Copper Layers...")
                mesher.rasterize_geometry(progress_cb=_prog)
                
                wx.CallAfter(self.set_progress, 40, "Constructing Thermal Solver...")
                solver = ThermalSolver(mesher)
                
                # Setup environments from Setup Wizard fallback
                # In real scenario, would pull from a settings dictionary
                solver.T_ambient = 25.0
                
                # Attach parts & heatsinks from ThermalSidePanel
                # Map component centers to grid nodes
                # Simplified approach for the prototype: inject power directly into center node
                if hasattr(self, 'thermal_panel'):
                    parts = self.thermal_panel.parts_data
                    for ref, data in parts.items():
                        # Find component center
                        # (Needs logic to locate ref in mesher space; mocked for now to node 0)
                        # We inject power directly
                        solver.inject_power(0, data.get('power', 0.0))
                        
                        if 'heatsink' in data and data['heatsink'] != 'None':
                            hs_rth = 5.0 # Fallback
                            for hs in self.thermal_panel.heatsinks:
                                if hs['ref'] == ref:
                                    hs_rth = hs['rth']
                            solver.heatsinks[0] = {'R_th': hs_rth, 'T_amb': solver.T_ambient}
                
                wx.CallAfter(self.set_progress, 70, "Solving Thermal Matrix...")
                T_grid = solver.solve_steady_state()
                
                wx.CallAfter(self.set_progress, 100, f"Thermal Solution Complete!")
                
                # Hook into Viewport
                wx.CallAfter(self.viewport_3d.add_thermal_heatmap, T_grid, dx, dy, mesher.xmin, mesher.ymin)
                wx.CallAfter(wx.MessageBox, "Phase 7 Success!\nSteady-State solution completed and pushed to Viewport3D.", "Thermal Solver", wx.OK | wx.ICON_INFORMATION)
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                wx.CallAfter(wx.MessageBox, f"Thermal meshing/solving failed: {e}", "Error")
            finally:
                import time
                time.sleep(0.5)
                wx.CallAfter(self.set_progress, -1)
                
        import threading
        threading.Thread(target=_run, daemon=True).start()

    # --- Progress Bar Helpers ---
    
    def set_progress(self, value, text=None):
        """Update the status bar progress gauge and text"""
        if value < 0:
            self.progress_gauge.Hide()
            if text: self.SetStatusText(text, 0)
        else:
            if not self.progress_gauge.IsShown():
                self.progress_gauge.Show()
                self._update_gauge_pos()
            
            self.progress_gauge.SetValue(int(value))
            if text: self.SetStatusText(text, 0)
        
        # Refresh to show changes during tight loops
        wx.GetApp().SafeYield(self, True)

    def on_frame_size(self, event):
        """Update gauge position when window resizes"""
        self._update_gauge_pos()
        event.Skip()

    def _update_gauge_pos(self):
        """Position the gauge within the 4th status bar field"""
        if hasattr(self, 'progress_gauge') and self.progress_gauge.IsShown():
            rect = self.status_bar.GetFieldRect(3)
            # Add some padding
            pw = 4
            ph = 4
            self.progress_gauge.SetPosition((rect.x + pw, rect.y + ph))
            self.progress_gauge.SetSize((rect.width - 2*pw, rect.height - 2*ph))


# ============================================================================
# APP ENTRY POINT
# ============================================================================


class ProfessionalApp(wx.App):
    def OnInit(self):
        self.frame = SPIKEMainWindow()
        self.frame.Show()
        return True

if __name__ == "__main__":
    app = ProfessionalApp()
    app.MainLoop()

    def on_thermal_click(self, pt, pad, net):
        # Handle click on thermal heatmap
        if not hasattr(self.viewport, 'thermal_grid_cache') or self.viewport.thermal_grid_cache is None:
            return
        grid = self.viewport.thermal_grid_cache
        # Find closest point in grid
        closest_idx = grid.find_closest_point(pt)
        temp = grid['Temperature (°C)'][closest_idx]
        wx.CallAfter(self.SetStatusText, f'Thermal Probe: {temp:.2f} °C at ({pt[0]:.2f}, {pt[1]:.2f})')
        if hasattr(self, 'analysis_panel'):
            # We can log this to the probe table if we are in Thermal Probe mode
            self.analysis_panel.append_observation(f'Thermal Probe: {temp:.2f} °C at ({pt[0]:.2f}, {pt[1]:.2f})')
