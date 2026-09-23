"""
Analysis Dashboard Panel
Displays real-time simulation results, probes, and analytical observations
"""
import wx
import wx.grid

class AnalysisDashboardPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.init_ui()
        
    def init_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Create splitter for top/bottom sections
        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        
        # TOP: Probing Section
        top_panel = wx.Panel(splitter)
        top_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Probe Controls
        probe_ctrl_box = wx.StaticBoxSizer(wx.HORIZONTAL, top_panel, "Probe Controls")
        
        self.chk_hover_probe = wx.CheckBox(probe_ctrl_box.GetStaticBox(), label="Enable Hover Probe")
        self.chk_hover_probe.SetValue(True)
        probe_ctrl_box.Add(self.chk_hover_probe, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        
        probe_ctrl_box.Add(wx.StaticText(probe_ctrl_box.GetStaticBox(), label="Probe Mode:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.choice_probe_mode = wx.Choice(probe_ctrl_box.GetStaticBox(), choices=["Voltage", "Current Density", "Impedance", "All Fields"])
        self.choice_probe_mode.SetSelection(0)
        probe_ctrl_box.Add(self.choice_probe_mode, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        
        self.btn_add_probe = wx.Button(probe_ctrl_box.GetStaticBox(), label="+ Add Probe")
        self.btn_clear_probes = wx.Button(probe_ctrl_box.GetStaticBox(), label="Clear All")
        probe_ctrl_box.Add(self.btn_add_probe, 0, wx.RIGHT, 5)
        probe_ctrl_box.Add(self.btn_clear_probes, 0)
        
        top_sizer.Add(probe_ctrl_box, 0, wx.EXPAND | wx.ALL, 5)
        
        # Multi-Probe Table
        probe_table_box = wx.StaticBoxSizer(wx.VERTICAL, top_panel, "Active Probes")
        
        self.probe_grid = wx.grid.Grid(probe_table_box.GetStaticBox())
        self.probe_grid.CreateGrid(0, 9)
        self.probe_grid.SetColLabelValue(0, "ID")
        self.probe_grid.SetColLabelValue(1, "Net")
        self.probe_grid.SetColLabelValue(2, "Layer")
        self.probe_grid.SetColLabelValue(3, "X (mm)")
        self.probe_grid.SetColLabelValue(4, "Y (mm)")
        self.probe_grid.SetColLabelValue(5, "V (V)")
        self.probe_grid.SetColLabelValue(6, "J (A/mm²)")
        self.probe_grid.SetColLabelValue(7, "Z (mΩ)")
        self.probe_grid.SetColLabelValue(8, "Notes")
        
        self.probe_grid.SetRowLabelSize(30)
        self.probe_grid.SetColSize(0, 40)
        self.probe_grid.SetColSize(1, 100)
        self.probe_grid.SetColSize(2, 60)
        self.probe_grid.SetColSize(3, 60)
        self.probe_grid.SetColSize(4, 60)
        self.probe_grid.SetColSize(5, 70)
        self.probe_grid.SetColSize(6, 80)
        self.probe_grid.SetColSize(7, 70)
        self.probe_grid.SetColSize(8, 150)
        
        probe_table_box.Add(self.probe_grid, 1, wx.EXPAND | wx.ALL, 5)
        
        top_sizer.Add(probe_table_box, 1, wx.EXPAND | wx.ALL, 5)
        top_panel.SetSizer(top_sizer)
        
        # BOTTOM: Analytical Observations
        bottom_panel = wx.Panel(splitter)
        bottom_sizer = wx.BoxSizer(wx.VERTICAL)
        
        obs_box = wx.StaticBoxSizer(wx.VERTICAL, bottom_panel, "Analytical Observations & Insights")
        
        # Toolbar for observations
        obs_toolbar = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_auto_analyze = wx.Button(obs_box.GetStaticBox(), label="🔍 Auto-Analyze")
        self.btn_export_obs = wx.Button(obs_box.GetStaticBox(), label="📄 Export")
        self.btn_clear_obs = wx.Button(obs_box.GetStaticBox(), label="Clear")
        
        obs_toolbar.Add(self.btn_auto_analyze, 0, wx.RIGHT, 5)
        obs_toolbar.Add(self.btn_export_obs, 0, wx.RIGHT, 5)
        obs_toolbar.Add(self.btn_clear_obs, 0)
        obs_box.Add(obs_toolbar, 0, wx.ALL, 5)
        
        # Observations text area
        self.txt_observations = wx.TextCtrl(obs_box.GetStaticBox(), 
                                           style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self.txt_observations.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        
        # Add sample observations
        sample_text = """═══════════════════════════════════════════════════════════════
SIMULATION ANALYSIS REPORT
═══════════════════════════════════════════════════════════════

[INFO] Simulation completed successfully
[INFO] Analysis mode: DC Power Distribution

CRITICAL FINDINGS:
──────────────────────────────────────────────────────────────
⚠ High current density detected on Net: 24V
  • Location: (45.2, 67.8) mm
  • Current Density: 125.4 A/mm²
  • Recommendation: Increase trace width or add copper pour

✓ Net: GND shows uniform distribution
  • Average impedance: 0.8 mΩ
  • Max voltage drop: 12 mV

PERFORMANCE METRICS:
──────────────────────────────────────────────────────────────
• Total power dissipation: 2.4 W
• Maximum temperature rise: 15°C
• PDN impedance @ DC: 1.2 mΩ

RECOMMENDATIONS:
──────────────────────────────────────────────────────────────
1. Add decoupling capacitors near high-current loads
2. Consider via stitching for thermal management
3. Review trace widths on power nets

═══════════════════════════════════════════════════════════════
"""
        self.txt_observations.SetValue(sample_text)
        
        obs_box.Add(self.txt_observations, 1, wx.EXPAND | wx.ALL, 5)
        
        bottom_sizer.Add(obs_box, 1, wx.EXPAND | wx.ALL, 5)
        bottom_panel.SetSizer(bottom_sizer)
        
        # Split 60/40
        splitter.SplitHorizontally(top_panel, bottom_panel)
        splitter.SetSashPosition(300)
        splitter.SetMinimumPaneSize(150)
        
        main_sizer.Add(splitter, 1, wx.EXPAND)
        self.SetSizer(main_sizer)
        
    def add_probe(self, probe_id, net, layer, x, y, voltage=None, current_density=None, impedance=None, notes=""):
        """Add a probe to the table"""
        row = self.probe_grid.GetNumberRows()
        self.probe_grid.AppendRows(1)
        
        self.probe_grid.SetCellValue(row, 0, str(probe_id))
        self.probe_grid.SetCellValue(row, 1, str(net))
        self.probe_grid.SetCellValue(row, 2, str(layer))
        self.probe_grid.SetCellValue(row, 3, f"{x:.2f}")
        self.probe_grid.SetCellValue(row, 4, f"{y:.2f}")
        
        if voltage is not None:
            self.probe_grid.SetCellValue(row, 5, f"{voltage:.4f}")
        if current_density is not None:
            self.probe_grid.SetCellValue(row, 6, f"{current_density:.2f}")
        if impedance is not None:
            self.probe_grid.SetCellValue(row, 7, f"{impedance:.3f}")
        
        self.probe_grid.SetCellValue(row, 8, notes)
        
        # Make ID column read-only
        self.probe_grid.SetReadOnly(row, 0)
        
    def clear_probes(self):
        """Clear all probes from the table"""
        if self.probe_grid.GetNumberRows() > 0:
            self.probe_grid.DeleteRows(0, self.probe_grid.GetNumberRows())
            
    def append_observation(self, text, level="INFO"):
        """Append an observation to the text area"""
        current = self.txt_observations.GetValue()
        prefix = {
            "INFO": "[INFO]",
            "WARNING": "⚠",
            "CRITICAL": "🔴",
            "SUCCESS": "✓"
        }.get(level, "[INFO]")
        
        new_text = f"{current}\n{prefix} {text}"
        self.txt_observations.SetValue(new_text)
        self.txt_observations.SetInsertionPointEnd()
