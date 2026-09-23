"""
SPIKE GUI - Main Application Entry Point
=========================================

Version: 0.1.6.0

This module provides the wxPython Ribbon UI for SPIKE.

Architecture:
- MainFrame: Top-level window with wx.ribbon.RibbonBar
- AuiManager: Docking panels for 3D view, properties, logs
- Async solver execution: Prevents UI blocking

Usage:
    python -m python.gui.main
"""

import wx
import wx.ribbon as rb
import wx.aui

class SPIKEMainFrame(wx.Frame):
    """
    Main application window with Ribbon UI
    
    Ribbon Structure:
    - Home: Project, Selection, Probes
    - PI Analysis: DC Solver, AC Impedance, Decap Optimizer
    - SI Analysis: TDR, Eye Diagram, S-Parameters
    - Thermal: Steady-State, Transient, Reliability
    - Reports: HTML Generator, Snapshot, Logs
    """
    
    def __init__(self):
        super().__init__(
            parent=None,
            title="SPIKE v0.1.6.0 - Signal, Power, and Integrity Knowledge Engine",
            size=(1600, 900)
        )
        
        # Set minimum size
        self.SetMinSize((1200, 700))
        
        # Initialize AUI Manager for docking
        self.aui_mgr = wx.aui.AuiManager(self)
        
        # Create Ribbon Bar
        self._create_ribbon()
        
        # Create panels (stubs for v0.1.6.0)
        self._create_panels()
        
        # Finalize layout
        self.aui_mgr.Update()
        
        # Center on screen
        self.Centre()
        
    def _create_ribbon(self):
        """Create Ribbon Bar with all tabs"""
        
        # Ribbon bar
        self.ribbon = rb.RibbonBar(self, wx.ID_ANY)
        
        # --- HOME TAB ---
        home_page = rb.RibbonPage(self.ribbon, wx.ID_ANY, "Home")
        
        # Project panel
        project_panel = rb.RibbonPanel(home_page, wx.ID_ANY, "Project")
        project_bar = rb.RibbonButtonBar(project_panel)
        project_bar.AddSimpleButton(wx.ID_ANY, "New", wx.ArtProvider.GetBitmap(wx.ART_NEW))
        project_bar.AddSimpleButton(wx.ID_ANY, "Open", wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN))
        project_bar.AddSimpleButton(wx.ID_ANY, "Save", wx.ArtProvider.GetBitmap(wx.ART_FILE_SAVE))
        
        # Selection panel
        selection_panel = rb.RibbonPanel(home_page, wx.ID_ANY, "Selection")
        selection_bar = rb.RibbonButtonBar(selection_panel)
        selection_bar.AddSimpleButton(wx.ID_ANY, "Nets", wx.ArtProvider.GetBitmap(wx.ART_LIST_VIEW))
        selection_bar.AddSimpleButton(wx.ID_ANY, "Components", wx.ArtProvider.GetBitmap(wx.ART_REPORT_VIEW))
        
        # --- PI ANALYSIS TAB ---
        pi_page = rb.RibbonPage(self.ribbon, wx.ID_ANY, "PI Analysis")
        
        dc_panel = rb.RibbonPanel(pi_page, wx.ID_ANY, "DC Solver")
        dc_bar = rb.RibbonButtonBar(dc_panel)
        dc_bar.AddSimpleButton(wx.ID_ANY, "IR Drop", wx.ArtProvider.GetBitmap(wx.ART_EXECUTABLE_FILE))
        dc_bar.AddSimpleButton(wx.ID_ANY, "Current Density", wx.ArtProvider.GetBitmap(wx.ART_INFORMATION))
        
        ac_panel = rb.RibbonPanel(pi_page, wx.ID_ANY, "AC Impedance")
        ac_bar = rb.RibbonButtonBar(ac_panel)
        ac_bar.AddSimpleButton(wx.ID_ANY, "Z(f) Sweep", wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD))
        ac_bar.AddSimpleButton(wx.ID_ANY, "Decap Optimizer", wx.ArtProvider.GetBitmap(wx.ART_TIP))
        
        # --- THERMAL TAB ---
        thermal_page = rb.RibbonPage(self.ribbon, wx.ID_ANY, "Thermal")
        
        thermal_panel = rb.RibbonPanel(thermal_page, wx.ID_ANY, "Analysis")
        thermal_bar = rb.RibbonButtonBar(thermal_panel)
        thermal_bar.AddSimpleButton(wx.ID_ANY, "Steady-State", wx.ArtProvider.GetBitmap(wx.ART_EXECUTABLE_FILE))
        thermal_bar.AddSimpleButton(wx.ID_ANY, "Transient", wx.ArtProvider.GetBitmap(wx.ART_GO_FORWARD))
        thermal_bar.AddSimpleButton(wx.ID_ANY, "Reliability", wx.ArtProvider.GetBitmap(wx.ART_WARNING))
        
        # --- REPORTS TAB ---
        reports_page = rb.RibbonPage(self.ribbon, wx.ID_ANY, "Reports")
        
        reports_panel = rb.RibbonPanel(reports_page, wx.ID_ANY, "Export")
        reports_bar = rb.RibbonButtonBar(reports_panel)
        reports_bar.AddSimpleButton(wx.ID_ANY, "HTML Report", wx.ArtProvider.GetBitmap(wx.ART_HELP_BOOK))
        reports_bar.AddSimpleButton(wx.ID_ANY, "Screenshot", wx.ArtProvider.GetBitmap(wx.ART_COPY))
        reports_bar.AddSimpleButton(wx.ID_ANY, "Logs", wx.ArtProvider.GetBitmap(wx.ART_REPORT_VIEW))
        
        # Finalize ribbon
        self.ribbon.Realize()
        
        # Add to AUI
        self.aui_mgr.AddPane(
            self.ribbon,
            wx.aui.AuiPaneInfo()
            .Top()
            .CaptionVisible(False)
            .CloseButton(False)
            .PaneBorder(False)
            .Gripper(False)
            .DockFixed(True)
        )
        
    def _create_panels(self):
        """Create dockable panels"""
        
        # Import Viewport3D
        import sys
        from pathlib import Path
        
        # Add python directory to path
        python_dir = Path(__file__).parent.parent
        if str(python_dir) not in sys.path:
            sys.path.insert(0, str(python_dir))
        
        from viz.viewport3d import Viewport3D
        
        # 3D Viewport (center) - Now using PyVista!
        self.viewport = Viewport3D(self)
        
        self.aui_mgr.AddPane(
            self.viewport,
            wx.aui.AuiPaneInfo()
            .Center()
            .Caption("3D Viewport")
            .CloseButton(False)
            .MaximizeButton(True)
        )
        
        # Properties panel (right)
        props_panel = wx.Panel(self)
        props_panel.SetBackgroundColour(wx.WHITE)
        
        props_text = wx.StaticText(
            props_panel,
            label="Properties\n(v0.1.7.0)",
            style=wx.ALIGN_CENTER
        )
        
        props_sizer = wx.BoxSizer(wx.VERTICAL)
        props_sizer.Add(props_text, 1, wx.EXPAND | wx.ALL, 10)
        props_panel.SetSizer(props_sizer)
        
        self.aui_mgr.AddPane(
            props_panel,
            wx.aui.AuiPaneInfo()
            .Right()
            .Caption("Properties")
            .BestSize(300, -1)
            .CloseButton(True)
        )
        
        # Log console (bottom)
        log_panel = wx.Panel(self)
        log_panel.SetBackgroundColour(wx.Colour(20, 20, 20))
        
        log_text = wx.StaticText(
            log_panel,
            label="Log Console (v0.1.7.0)",
            style=wx.ALIGN_LEFT
        )
        log_text.SetForegroundColour(wx.Colour(0, 255, 0))
        
        log_sizer = wx.BoxSizer(wx.VERTICAL)
        log_sizer.Add(log_text, 1, wx.EXPAND | wx.ALL, 10)
        log_panel.SetSizer(log_sizer)
        
        self.aui_mgr.AddPane(
            log_panel,
            wx.aui.AuiPaneInfo()
            .Bottom()
            .Caption("Log Console")
            .BestSize(-1, 200)
            .CloseButton(True)
        )


class SPIKEApp(wx.App):
    """SPIKE Application"""
    
    def OnInit(self):
        self.frame = SPIKEMainFrame()
        self.frame.Show()
        return True


def main():
    """Entry point"""
    app = SPIKEApp()
    app.MainLoop()


if __name__ == "__main__":
    main()
