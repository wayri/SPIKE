import re

new_func = """    def _init_setup_tab(self, panel):
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
        panel.SetSizer(main_sizer)"""

with open('demo_spike.py', 'r', encoding='utf-8') as f:
    data = f.read()

start_idx = data.find('    def _init_setup_tab(self, panel):')
end_idx = data.find('    def on_pdn_wizard(self, event):')

if start_idx != -1 and end_idx != -1:
    new_data = data[:start_idx] + new_func + '\n\n' + data[end_idx:]
    with open('demo_spike.py', 'w', encoding='utf-8') as f:
        f.write(new_data)
    print('Patched demo_spike.py successfully')
else:
    print('Failed to find boundaries')
