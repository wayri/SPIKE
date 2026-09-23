def _init_setup_tab(self, panel):
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.setup_scroll = wx.ScrolledWindow(panel)
        self.setup_scroll.SetScrollRate(0, 5)
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # --- 1. Header & Toggle ---
        header = wx.BoxSizer(wx.HORIZONTAL)
        self.lbl_sel = wx.StaticText(self.setup_scroll, label="No Net Selected")
        self.lbl_sel.SetFont(wx.Font(11, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        header.Add(self.lbl_sel, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        
        self.btn_toggle_side = wx.Button(self.setup_scroll, label="<< Toggle Sidebar >>", size=(120, -1))
        header.Add(self.btn_toggle_side, 0, wx.ALL, 5)
        scroll_sizer.Add(header, 0, wx.EXPAND)
        
        # --- 2. Pin/Pad Selection List ---
        scroll_sizer.Add(wx.StaticText(self.setup_scroll, label="Select Pin/Pad to Assign:"), 0, wx.LEFT | wx.RIGHT, 10)
        self.pad_list = wx.CheckListBox(self.setup_scroll, size=(-1, 150))
        scroll_sizer.Add(self.pad_list, 0, wx.EXPAND | wx.ALL, 10)
        
        p_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_check_all = wx.Button(self.setup_scroll, label="Check All")
        self.btn_check_all.Bind(wx.EVT_BUTTON, lambda e: [self.pad_list.Check(i) for i in range(self.pad_list.GetCount())])
        self.btn_uncheck_all = wx.Button(self.setup_scroll, label="Uncheck All")
        self.btn_uncheck_all.Bind(wx.EVT_BUTTON, lambda e: [self.pad_list.Check(i, False) for i in range(self.pad_list.GetCount())])
        p_btn_sizer.Add(self.btn_check_all, 1, wx.EXPAND | wx.RIGHT, 5)
        p_btn_sizer.Add(self.btn_uncheck_all, 1, wx.EXPAND)
        scroll_sizer.Add(p_btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        scroll_sizer.Add(wx.StaticLine(self.setup_scroll), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 10)
        
        # --- 3. Voltage Source (VRM) ---
        vrm_box = wx.StaticBoxSizer(wx.VERTICAL, self.setup_scroll, "Source (VRM/Current)")
        v_grid = wx.FlexGridSizer(4, 2, 5, 5) # Label on left, Field on right
        v_grid.AddGrowableCol(1)
        
        v_grid.Add(wx.StaticText(vrm_box.GetStaticBox(), label="Type:"), 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        self.cb_src_type = wx.ComboBox(vrm_box.GetStaticBox(), choices=["Voltage (V)", "Current (A)"], style=wx.CB_READONLY)
        self.cb_src_type.SetSelection(0)
        v_grid.Add(self.cb_src_type, 0, wx.EXPAND)
        
        v_grid.Add(wx.StaticText(vrm_box.GetStaticBox(), label="Value (V/A):"), 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        self.txt_dc = wx.TextCtrl(vrm_box.GetStaticBox(), value="3.3", size=(80, -1))
        v_grid.Add(self.txt_dc, 0)
        
        v_grid.Add(wx.StaticText(vrm_box.GetStaticBox(), label="AC (V):"), 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        self.txt_ac = wx.TextCtrl(vrm_box.GetStaticBox(), value="0.0", size=(80, -1))
        v_grid.Add(self.txt_ac, 0)
        
        v_grid.Add(wx.StaticText(vrm_box.GetStaticBox(), label="Freq (Hz):"), 0, wx.ALIGN_LEFT | wx.ALIGN_CENTER_VERTICAL)
        self.txt_hz = wx.TextCtrl(vrm_box.GetStaticBox(), value="0", size=(80, -1))
        v_grid.Add(self.txt_hz, 0)
        
        vrm_box.Add(v_grid, 0, wx.EXPAND | wx.ALL, 5)
        self.btn_set_source = wx.Button(vrm_box.GetStaticBox(), label="Set as Source")
        self.btn_set_source.Bind(wx.EVT_BUTTON, lambda e: self.on_bulk_assign("Source (V/A)"))
        vrm_box.Add(self.btn_set_source, 0, wx.EXPAND | wx.TOP, 2)
        scroll_sizer.Add(vrm_box, 0, wx.EXPAND | wx.ALL, 5)
        
        # --- 4. Load (Sink) ---
        load_box = wx.StaticBoxSizer(wx.VERTICAL, self.setup_scroll, "Load (Sink)")
        v_grid2 = wx.BoxSizer(wx.HORIZONTAL)
        v_grid2.Add(wx.StaticText(load_box.GetStaticBox(), label="Current (A):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.txt_sink_current = wx.TextCtrl(load_box.GetStaticBox(), value="1.0", size=(80, -1))
        v_grid2.Add(self.txt_sink_current, 0)
        load_box.Add(v_grid2, 0, wx.EXPAND | wx.ALL, 5)
        
        self.btn_add_sink = wx.Button(load_box.GetStaticBox(), label="Add Sink to Selected Pins")
        self.btn_add_sink.Bind(wx.EVT_BUTTON, lambda e: self.on_bulk_assign("Sink (Load)"))
        load_box.Add(self.btn_add_sink, 0, wx.EXPAND | wx.TOP, 2)
        scroll_sizer.Add(load_box, 0, wx.EXPAND | wx.ALL, 5)
        
        # --- 4b. Pass-Through Components ---
        pass_box = wx.StaticBoxSizer(wx.VERTICAL, self.setup_scroll, "Inline/Pass-Through Devices")
        self.btn_add_pass = wx.Button(pass_box.GetStaticBox(), label="+ Bridge Nets via Component")
        self.btn_add_pass.Bind(wx.EVT_BUTTON, self.on_add_pass_through)
        pass_box.Add(self.btn_add_pass, 0, wx.EXPAND | wx.ALL, 5)
        scroll_sizer.Add(pass_box, 0, wx.EXPAND | wx.ALL, 5)
        
        scroll_sizer.Add(wx.StaticLine(self.setup_scroll), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 10)
        
        # --- 5. Assigned Configuration (Source/Sink Table) ---
        scroll_sizer.Add(wx.StaticText(self.setup_scroll, label="Assigned Configuration:"), 0, wx.LEFT, 10)
        self.ss_grid = wx.grid.Grid(self.setup_scroll)
        self.ss_grid.CreateGrid(0, 6)
        self.ss_grid.SetColLabelValue(0, "Type")
        self.ss_grid.SetColLabelValue(1, "Net")
        self.ss_grid.SetColLabelValue(2, "Loc")
        self.ss_grid.SetColLabelValue(3, "Val")
        self.ss_grid.SetColLabelValue(4, "AC")
        self.ss_grid.SetColLabelValue(5, "Hz")
        self.ss_grid.SetRowLabelSize(25)
        self.ss_grid.SetColSize(0, 60); self.ss_grid.SetColSize(1, 60); self.ss_grid.SetColSize(2, 60); self.ss_grid.SetColSize(3, 40)
        scroll_sizer.Add(self.ss_grid, 0, wx.EXPAND | wx.ALL, 5)
        
        ss_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_edit = wx.Button(self.setup_scroll, label="Edit")
        self.btn_remove = wx.Button(self.setup_scroll, label="Remove")
        self.btn_remove.Bind(wx.EVT_BUTTON, self.on_delete_selected)
        self.btn_clear_all = wx.Button(self.setup_scroll, label="Clear All")
        self.btn_clear_all.SetForegroundColour(wx.Colour(180, 0, 0))
        self.btn_clear_all.Bind(wx.EVT_BUTTON, self.on_clear_all_ss)
        ss_btn_sizer.Add(self.btn_edit, 1, wx.RIGHT, 2)
        ss_btn_sizer.Add(self.btn_remove, 1, wx.RIGHT, 2)
        ss_btn_sizer.Add(self.btn_clear_all, 1)
        scroll_sizer.Add(ss_btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        
        # --- 6. Simulation Tools ---
        self.tool_box = wx.StaticBoxSizer(wx.VERTICAL, self.setup_scroll, "Simulation Tools") # Solver Quick Settings
        t_box = self.tool_box.GetStaticBox()
        
        tool_sizer = wx.BoxSizer(wx.VERTICAL) # Stack everything vertically
        
        # Solver Quick Settings
        q_grid = wx.FlexGridSizer(3, 2, 5, 5)
        q_grid.AddGrowableCol(1)
        q_grid.Add(wx.StaticText(t_box, label="Mesh Res(mm):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_grid_mm = wx.TextCtrl(t_box, value="0.05", size=(80, -1))
        q_grid.Add(self.txt_grid_mm, 0)
        
        q_grid.Add(wx.StaticText(t_box, label="Thickness(mm):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_cu_mm = wx.TextCtrl(t_box, value="0.035", size=(80, -1))
        q_grid.Add(self.txt_cu_mm, 0)
        
        q_grid.Add(wx.StaticText(t_box, label="Engine:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.cb_solver = wx.ComboBox(t_box, choices=["Auto", "Dense Direct (<2k)", "Iterative Sparse (>10k)"], style=wx.CB_READONLY)
        self.cb_solver.SetSelection(0)
        q_grid.Add(self.cb_solver, 0, wx.EXPAND)
        
        tool_sizer.Add(q_grid, 0, wx.EXPAND | wx.ALL, 5)
        
        units_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.rb_ma = wx.RadioButton(t_box, label="MA/m²", style=wx.RB_GROUP)
        self.rb_amm = wx.RadioButton(t_box, label="A/mm²")
        units_sizer.Add(self.rb_ma, 0, wx.RIGHT, 10)
        units_sizer.Add(self.rb_amm, 0)
        tool_sizer.Add(units_sizer, 0, wx.ALL, 5)

        # Buttons Stack
        btn_stack = wx.BoxSizer(wx.VERTICAL)
        self.btn_pdn_wizard = wx.Button(t_box, label="PDN Wizard")
        btn_stack.Add(self.btn_pdn_wizard, 0, wx.EXPAND | wx.BOTTOM, 2)
        
        self.btn_adv_settings = wx.Button(t_box, label="Adv. Solver Settings")
        btn_stack.Add(self.btn_adv_settings, 0, wx.EXPAND | wx.BOTTOM, 2)
        
        self.btn_batch_settings = wx.Button(t_box, label="Batch Settings")
        btn_stack.Add(self.btn_batch_settings, 0, wx.EXPAND | wx.BOTTOM, 2)
        
        sep = wx.StaticLine(t_box)
        btn_stack.Add(sep, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 5)
        
        self.btn_debug_mesh = wx.Button(t_box, label="Debug Mesh")
        btn_stack.Add(self.btn_debug_mesh, 0, wx.EXPAND | wx.BOTTOM, 2)
        
        self.btn_run_dc = wx.Button(t_box, label="▶ Run DC Simulation")
        self.btn_run_ac = wx.Button(t_box, label="⚡ Run AC Simulation")
        self.btn_batch_run = wx.Button(t_box, label="▶ Run Batch Simulation")
        self.btn_run_rlc = wx.Button(t_box, label="Run RLC Extraction")
        
        btn_stack.Add(self.btn_run_dc, 0, wx.EXPAND | wx.BOTTOM, 2)
        btn_stack.Add(self.btn_run_ac, 0, wx.EXPAND | wx.BOTTOM, 2)
        btn_stack.Add(self.btn_batch_run, 0, wx.EXPAND | wx.BOTTOM, 2)
        btn_stack.Add(self.btn_run_rlc, 0, wx.EXPAND | wx.BOTTOM, 2)
        
        # BINDINGS
        self.btn_pdn_wizard.Bind(wx.EVT_BUTTON, self.on_pdn_wizard)
        self.btn_adv_settings.Bind(wx.EVT_BUTTON, self.on_adv_settings)
        self.btn_batch_settings.Bind(wx.EVT_BUTTON, self.on_batch_settings)
        self.btn_run_rlc.Bind(wx.EVT_BUTTON, self.on_run_rlc)
        self.ss_grid.Bind(wx.grid.EVT_GRID_CELL_CHANGED, self.on_grid_change)
        self.ss_grid.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.on_grid_select)
        self.pad_list.Bind(wx.EVT_LISTBOX, self.on_pad_choice)
        
        self.btn_batch_run.SetBackgroundColour(wx.Colour(100, 0, 100)); self.btn_batch_run.SetForegroundColour(wx.WHITE)
        self.btn_batch_run.Hide()
        
        tool_sizer.Add(btn_stack, 0, wx.EXPAND | wx.ALL, 5)
        
        # Stop Simulation
        self.chk_stop = wx.CheckBox(t_box, label="Stop Simulation")
        self.chk_stop.Enable(False)
        tool_sizer.Add(self.chk_stop, 0, wx.LEFT | wx.BOTTOM, 10)
        
        self.lnk_view3d = wx.StaticText(t_box, label="View 3D Field Map")
        self.lnk_view3d.SetForegroundColour(wx.BLUE)
        font = self.lnk_view3d.GetFont(); font.SetUnderlined(True)
        self.lnk_view3d.SetFont(font)
        tool_sizer.Add(self.lnk_view3d, 0, wx.ALIGN_CENTER | wx.BOTTOM, 5)
        
        self.tool_box.Add(tool_sizer, 1, wx.EXPAND)
        scroll_sizer.Add(self.tool_box, 0, wx.EXPAND | wx.ALL, 5)
        
        # --- 7. Analysis Probes ---
        self.probe_box = wx.StaticBoxSizer(wx.VERTICAL, self.setup_scroll, "Analysis Probes (Post-Sim)")
        p_box = self.probe_box.GetStaticBox()
        self.probe_box.Add(wx.StaticText(p_box, label="Phase/Mode Selection"), 0, wx.ALIGN_CENTER)
        self.slider_probe = wx.Slider(p_box, value=0, minValue=0, maxValue=100)
        self.probe_box.Add(self.slider_probe, 0, wx.EXPAND | wx.ALL, 5)
        
        self.chk_hover = wx.CheckBox(p_box, label="Hover Info")
        self.chk_hover.SetValue(True)
        self.probe_box.Add(self.chk_hover, 0, wx.ALIGN_RIGHT | wx.RIGHT, 10)
        
        pb_sizer = wx.BoxSizer(wx.HORIZONTAL)
        pb_sizer.Add(wx.Button(p_box, label="Del"), 1, wx.RIGHT, 2)
        pb_sizer.Add(wx.Button(p_box, label="Clear"), 1, wx.RIGHT, 2)
        pb_sizer.Add(wx.Button(p_box, label="Refresh"), 1)
        self.probe_box.Add(pb_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        self.probe_grid = wx.grid.Grid(p_box)
        self.probe_grid.CreateGrid(0, 7)
        for i, lbl in enumerate(["Snap", "ID", "Net", "Loc", "V", "J", "Z"]):
            self.probe_grid.SetColLabelValue(i, lbl)
        self.probe_grid.SetRowLabelSize(0)
        self.probe_grid.SetColSize(0, 35); self.probe_grid.SetColSize(1, 40)
        self.probe_box.Add(self.probe_grid, 0, wx.EXPAND | wx.ALL, 5)
        
        self.probe_box.GetStaticBox().Enable(False) # DISABLED until simulation finish
        scroll_sizer.Add(self.probe_box, 0, wx.EXPAND | wx.ALL, 5)
        
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

    