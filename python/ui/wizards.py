import wx

class ComponentWizard(wx.Dialog):
    """Wizard to assign electrical and thermal parameters to components."""
    def __init__(self, parent, thermal_mode=False, data_dict=None):
        super().__init__(parent, title="Component Parameter Wizard", size=(650, 500), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetMinSize((650, 500))
        self.thermal_mode = thermal_mode
        self.data_dict = data_dict if data_dict is not None else {}
        self._build_ui()
        self.CentreOnParent()

    def _build_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        header = wx.StaticText(self, label="Assign Component Parameters" if not self.thermal_mode else "Thermal Part Properties")
        header.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        main_sizer.Add(header, 0, wx.ALL, 15)

        nb = wx.Notebook(self)
        
        # --- Page 1: General/Electrical ---
        p1 = wx.Panel(nb)
        sz1 = wx.BoxSizer(wx.VERTICAL)
        sz1.Add(wx.StaticText(p1, label="Select Reference (e.g. U1, L2):"), 0, wx.ALL, 5)
        self.ref_cb = wx.ComboBox(p1, choices=["U1", "U2", "U3", "L1", "C1"], style=wx.CB_DROPDOWN)
        if self.data_dict and list(self.data_dict.keys()):
            self.ref_cb.SetValue(list(self.data_dict.keys())[0])
        sz1.Add(self.ref_cb, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        if not self.thermal_mode:
            sz1.Add(wx.StaticText(p1, label="Electrical Role:"), 0, wx.LEFT, 5)
            self.role_cb = wx.Choice(p1, choices=["Voltage Source (VRM)", "Current Sink (Load)", "Passive (RLC)"])
            self.role_cb.SetSelection(1)
            sz1.Add(self.role_cb, 0, wx.EXPAND | wx.ALL, 10)
            
            grid_elec = wx.FlexGridSizer(2, 2, 10, 10)
            grid_elec.AddGrowableCol(1)
            grid_elec.Add(wx.StaticText(p1, label="Value (V or A):"), 0, wx.ALIGN_CENTER_VERTICAL)
            self.txt_val = wx.TextCtrl(p1, value="1.5")
            grid_elec.Add(self.txt_val, 1, wx.EXPAND)
            sz1.Add(grid_elec, 0, wx.EXPAND | wx.ALL, 10)
        else:
            sz1.Add(wx.StaticText(p1, label="(Electrical properties disabled in Thermal Mode)"), 0, wx.ALL, 10)
            
        p1.SetSizer(sz1)
        
        # --- Page 2: Thermal ---
        p2 = wx.Panel(nb)
        sz2 = wx.BoxSizer(wx.VERTICAL)
        
        grid_therm = wx.FlexGridSizer(5, 2, 10, 10)
        grid_therm.AddGrowableCol(1)
        
        grid_therm.Add(wx.StaticText(p2, label="Steady-State Power (W):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_power = wx.TextCtrl(p2, value="1.0")
        grid_therm.Add(self.txt_power, 1, wx.EXPAND)
        
        grid_therm.Add(wx.StaticText(p2, label="Max Junction Temp (Tj) [°C]:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_tj = wx.TextCtrl(p2, value="125")
        grid_therm.Add(self.txt_tj, 1, wx.EXPAND)
        
        grid_therm.Add(wx.StaticText(p2, label="Theta JC (θjc) [°C/W]:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_jc = wx.TextCtrl(p2, value="2.5")
        grid_therm.Add(self.txt_jc, 1, wx.EXPAND)
        
        grid_therm.Add(wx.StaticText(p2, label="Theta JB (θjb) [°C/W]:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_jb = wx.TextCtrl(p2, value="8.0")
        grid_therm.Add(self.txt_jb, 1, wx.EXPAND)
        
        sz2.Add(grid_therm, 0, wx.EXPAND | wx.ALL, 10)
        
        sz2.Add(wx.StaticText(p2, label="Transient Dissipation Profile (Time,Power CSV):"), 0, wx.LEFT | wx.RIGHT, 10)
        self.txt_prof = wx.TextCtrl(p2, value="0.0,0.0; 0.1,5.0; 1.0,5.0; 1.1,0.0", style=wx.TE_MULTILINE)
        sz2.Add(self.txt_prof, 1, wx.EXPAND | wx.ALL, 10)
        
        btn_auto = wx.Button(p2, label="🤖 Auto-Detect from BoM / Datasheet")
        btn_auto.Bind(wx.EVT_BUTTON, self.on_auto_detect)
        sz2.Add(btn_auto, 0, wx.EXPAND | wx.ALL, 10)
        
        p2.SetSizer(sz2)
        
        if not self.thermal_mode:
            nb.AddPage(p1, "Electrical")
        nb.AddPage(p2, "Thermal Properties")
        main_sizer.Add(nb, 1, wx.EXPAND | wx.ALL, 10)
        
        # Buttons
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK)
        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_ok.Bind(wx.EVT_BUTTON, self.on_save)
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        self.SetSizer(main_sizer)

    def on_save(self, event):
        ref = self.ref_cb.GetValue()
        if ref:
            prof_str = self.txt_prof.GetValue()
            prof_parsed = []
            if prof_str.strip():
                try:
                    for pair in prof_str.split(';'):
                        if ',' in pair:
                            t, p = pair.split(',')
                            prof_parsed.append([float(t), float(p)])
                except: pass
                
            self.data_dict[ref] = {
                'power': float(self.txt_power.GetValue()),
                'tj_max': float(self.txt_tj.GetValue()),
                'theta_jc': float(self.txt_jc.GetValue()),
                'theta_jb': float(self.txt_jb.GetValue()),
                'profile': prof_parsed
            }
        event.Skip()

    def on_auto_detect(self, event):
        wx.MessageBox("AI Datasheet Scraping integration is required for Auto-Detect.", "Feature Pending", wx.ICON_INFORMATION)


class HeatsinkManagerWizard(wx.Dialog):
    """Wizard to define and attach generic heatsinks to components."""
    def __init__(self, parent, hs_list=None):
        super().__init__(parent, title="Heatsink Manager", size=(500, 350), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.hs_list = hs_list if hs_list is not None else []
        self._build_ui()
        self.CentreOnParent()
        
    def _build_ui(self):
        sz = wx.BoxSizer(wx.VERTICAL)
        sz.Add(wx.StaticText(self, label="Define Virtual Heatsink:"), 0, wx.ALL, 10)
        
        grid = wx.FlexGridSizer(4, 2, 10, 10)
        grid.AddGrowableCol(1)
        
        grid.Add(wx.StaticText(self, label="Target Component Ref:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_ref = wx.TextCtrl(self, value="U1")
        grid.Add(self.txt_ref, 1, wx.EXPAND)
        
        grid.Add(wx.StaticText(self, label="Material:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.cb_mat = wx.Choice(self, choices=["Aluminum Extruded", "Copper Skived", "Generic Ceramic"])
        self.cb_mat.SetSelection(0)
        grid.Add(self.cb_mat, 1, wx.EXPAND)
        
        grid.Add(wx.StaticText(self, label="Effective Surface Area (cm²):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_area = wx.TextCtrl(self, value="25.0")
        grid.Add(self.txt_area, 1, wx.EXPAND)
        
        grid.Add(wx.StaticText(self, label="Est. Resistance Rth (C/W):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_rth = wx.TextCtrl(self, value="5.5")
        grid.Add(self.txt_rth, 1, wx.EXPAND)
        
        sz.Add(grid, 1, wx.EXPAND | wx.ALL, 10)
        
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK, "Attach Heatsink")
        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_ok.Bind(wx.EVT_BUTTON, self.on_save)
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        sz.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        self.SetSizer(sz)
        
    def on_save(self, event):
        self.hs_list.append({
            'ref': self.txt_ref.GetValue(),
            'material': self.cb_mat.GetStringSelection(),
            'area_cm2': float(self.txt_area.GetValue()),
            'rth': float(self.txt_rth.GetValue())
        })
        event.Skip()


class SetupWizard(wx.Dialog):
    """Wizard to setup unified PDN & Thermal simulation environment."""
    def __init__(self, parent):
        super().__init__(parent, title="Unified Setup Wizard (PDN & Thermal)", size=(600, 450), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetMinSize((600, 450))
        self._build_ui()
        self.CentreOnParent()

    def _build_ui(self):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        header = wx.StaticText(self, label="Simulation Environment Setup")
        header.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        main_sizer.Add(header, 0, wx.ALL, 15)

        nb = wx.Notebook(self)
        
        # Page 1: Meshing & Substrate
        p1 = wx.Panel(nb)
        sz1 = wx.BoxSizer(wx.VERTICAL)
        
        grid1 = wx.FlexGridSizer(2, 2, 10, 10)
        grid1.AddGrowableCol(1)
        grid1.Add(wx.StaticText(p1, label="Copper Homogenization Blur [mm]:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_blur = wx.TextCtrl(p1, value="2.0")
        grid1.Add(self.txt_blur, 1, wx.EXPAND)
        
        grid1.Add(wx.StaticText(p1, label="Substrate Material:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.cb_sub = wx.Choice(p1, choices=["FR4", "Polyimide", "Rogers 4350B", "Alumina"])
        self.cb_sub.SetSelection(0)
        grid1.Add(self.cb_sub, 1, wx.EXPAND)
        
        sz1.Add(grid1, 0, wx.EXPAND | wx.ALL, 10)
        p1.SetSizer(sz1)
        
        # Page 2: Environment
        p2 = wx.Panel(nb)
        sz2 = wx.BoxSizer(wx.VERTICAL)
        
        grid2 = wx.FlexGridSizer(3, 2, 10, 10)
        grid2.AddGrowableCol(1)
        
        grid2.Add(wx.StaticText(p2, label="Ambient Temperature [°C]:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_amb = wx.TextCtrl(p2, value="25.0")
        grid2.Add(self.txt_amb, 1, wx.EXPAND)
        
        grid2.Add(wx.StaticText(p2, label="Enclosure Type:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.cb_enc = wx.Choice(p2, choices=["None (Open Air)", "ABS Plastic", "Aluminum Chassis"])
        self.cb_enc.SetSelection(0)
        grid2.Add(self.cb_enc, 1, wx.EXPAND)
        
        grid2.Add(wx.StaticText(p2, label="Airflow (Forced Convection) [m/s]:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_air = wx.TextCtrl(p2, value="0.0")
        grid2.Add(self.txt_air, 1, wx.EXPAND)
        
        sz2.Add(grid2, 0, wx.EXPAND | wx.ALL, 10)
        p2.SetSizer(sz2)
        
        nb.AddPage(p1, "Stackup & Mesh")
        nb.AddPage(p2, "Environment")
        main_sizer.Add(nb, 1, wx.EXPAND | wx.ALL, 10)
        
        btn_sizer = wx.StdDialogButtonSizer()
        btn_ok = wx.Button(self, wx.ID_OK)
        btn_cancel = wx.Button(self, wx.ID_CANCEL)
        btn_sizer.AddButton(btn_ok)
        btn_sizer.AddButton(btn_cancel)
        btn_sizer.Realize()
        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        self.SetSizer(main_sizer)
