import wx
import wx.grid
from ui.wizards import ComponentWizard, HeatsinkManagerWizard

class ThermalSidePanel(wx.Panel):
    """
    Dedicated Side Panel for Thermal Management.
    Lists parts, their thermal assignments, heatsinks, and transient profiles.
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.parts_data = {} # ref -> {Tj_max, Theta_JC, Dissipation, Profile, Heatsink}
        self.heatsinks = []  # list of configured heatsinks
        self._build_ui()
        
    def _build_ui(self):
        sz = wx.BoxSizer(wx.VERTICAL)
        
        # --- Toolbar ---
        tb_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_part_wiz = wx.Button(self, label="🔧 Part Properties")
        btn_hs_wiz = wx.Button(self, label="🧊 Heatsink Manager")
        tb_row.Add(btn_part_wiz, 0, wx.RIGHT, 5)
        tb_row.Add(btn_hs_wiz, 0, wx.RIGHT, 5)
        self.chk_pure = wx.CheckBox(self, label='Pure View')
        tb_row.Add(self.chk_pure, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.btn_render = wx.Button(self, label='Render Video')
        tb_row.Add(self.btn_render, 0, wx.RIGHT, 5)
        sz.Add(tb_row, 0, wx.ALL | wx.EXPAND, 5)
        
        # --- Active Parts Grid ---
        sz.Add(wx.StaticText(self, label="Active Heat Sources:"), 0, wx.LEFT | wx.TOP, 5)
        self.grid = wx.grid.Grid(self)
        self.grid.CreateGrid(0, 5)
        self.grid.SetColLabelValue(0, "Ref")
        self.grid.SetColLabelValue(1, "Power (W)")
        self.grid.SetColLabelValue(2, "θjc")
        self.grid.SetColLabelValue(3, "Profile")
        self.grid.SetColLabelValue(4, "Heatsink")
        self.grid.SetRowLabelSize(0)
        self.grid.EnableEditing(False)
        sz.Add(self.grid, 1, wx.EXPAND | wx.ALL, 5)
        
        self.SetSizer(sz)
        
        # Bindings
        btn_part_wiz.Bind(wx.EVT_BUTTON, self.on_part_wizard)
        btn_hs_wiz.Bind(wx.EVT_BUTTON, self.on_heatsink_wizard)
        
    def on_part_wizard(self, event):
        # We pass self.parts_data so the wizard can update it
        dlg = ComponentWizard(self, thermal_mode=True, data_dict=self.parts_data)
        if dlg.ShowModal() == wx.ID_OK:
            self._refresh_grid()
        dlg.Destroy()
        
    def on_heatsink_wizard(self, event):
        dlg = HeatsinkManagerWizard(self, hs_list=self.heatsinks)
        if dlg.ShowModal() == wx.ID_OK:
            self._refresh_grid()
        dlg.Destroy()
        
    def _refresh_grid(self):
        if self.grid.GetNumberRows() > 0:
            self.grid.DeleteRows(0, self.grid.GetNumberRows())
            
        for ref, data in self.parts_data.items():
            row = self.grid.GetNumberRows()
            self.grid.AppendRows(1)
            self.grid.SetCellValue(row, 0, str(ref))
            self.grid.SetCellValue(row, 1, str(data.get('power', 0)))
            self.grid.SetCellValue(row, 2, str(data.get('theta_jc', '-')))
            self.grid.SetCellValue(row, 3, "Yes" if data.get('profile') else "None")
            self.grid.SetCellValue(row, 4, str(data.get('heatsink', 'None')))
