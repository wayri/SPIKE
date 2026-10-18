# SPDX-License-Identifier: Apache-2.0
"""Compact contextual navigation for the separate Qt-free workbench."""
import wx
from .designer_icons import tool
from .flat_controls import ActionButton

PRIMARY_VIEWS = [('Schematic', 0), ('Waveforms', 1), ('Netlist', 2), ('Dashboard', 13)]
SCHEMATIC_TOOLS = [('Select', 'edit.box_select'), ('Wire · W', 'edit.wire'),
    ('Move · M', 'edit.move'), ('Duplicate · Ctrl+Shift+D', 'edit.duplicate'), ('Rotate · Space', 'edit.rotate'),
    ('Properties · E', 'edit.properties'), ('Probe V · P', 'probe.voltage'),
    ('Parts', 'view.component_catalog'), ('Fit', 'view.fit_schematic')]


class RunCommandBar(wx.Panel):
    """Themeable native buttons; older wx toolbars hard-code black label text."""
    def __init__(self, owner):
        super().__init__(owner)
        self.owner=owner;self.buttons={};self.row=wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(self.row)

    def AddTool(self, ident, label, bitmap, shortHelp=''):
        compact=label if label in ('Run batch','Continuous','Runs') else ''
        compact={'Run batch':'Run','Continuous':'Live'}.get(compact,compact)
        button=ActionButton(self,label=compact,size=(36,34) if not compact else wx.DefaultSize)
        button.SetName(label)
        if label=='Run batch':button.SetValue(True)
        button.SetBitmap(bitmap);button.SetToolTip(shortHelp or label)
        button.Bind(wx.EVT_BUTTON,lambda event:self.owner.execute_command(
            next(command for command,identifier in self.owner.ids.items() if identifier==ident)))
        self.buttons[ident]=button;self.row.Add(button,0,wx.ALL,3)

    def AddSeparator(self):self.row.AddSpacer(10)
    def AddControl(self, control):self.row.Add(control,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4)
    def FindById(self, ident):return self.buttons.get(ident)
    def EnableTool(self, ident, enabled):self.buttons[ident].Enable(enabled)
    def SetToolNormalBitmap(self, ident, bitmap):self.buttons[ident].SetBitmap(bitmap)
    def SetToolDisabledBitmap(self, ident, bitmap):self.buttons[ident].SetBitmapDisabled(bitmap)
    def Realize(self):self.SetMinSize(self.row.GetMinSize());self.Layout();return True


class WorkbenchHeader(wx.Panel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        from .navigation import NavigationHistory
        self.history=NavigationHistory();self.replaying=False
        outer = wx.BoxSizer(wx.VERTICAL); navigation = wx.WrapSizer(wx.HORIZONTAL)
        brand = wx.StaticText(self, label='SPIKES')
        font = brand.GetFont(); font.SetWeight(wx.FONTWEIGHT_BOLD); font.SetPointSize(12); brand.SetFont(font)
        navigation.Add(brand, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        self.views = {}
        self.navigation_buttons={}
        for label,command in [('Back','view.back'),('Forward','view.forward'),('Home','view.home')]:
            control=tool(self,owner,label,lambda ident=command:owner.execute_command(ident),visible_label=label)
            navigation.Add(control,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,2);self.navigation_buttons[command]=control
        self.choice = wx.Choice(self, choices=[label for label,_index in PRIMARY_VIEWS], size=(175, -1))
        self.choice.SetToolTip('Main views; specialist tools are in Libraries, Analysis, Tools and Simulation menus')
        self.choice.Bind(wx.EVT_CHOICE, lambda event: self.go_page(PRIMARY_VIEWS[self.choice.GetSelection()][1]))
        self.choice.Hide()  # Keep the adapter for existing integrations; tabs are the visible navigation.
        owner.GetSizer().Detach(owner.run_bar);owner.run_bar.Reparent(self)
        navigation.Add(owner.run_bar,0,wx.ALIGN_CENTER_VERTICAL|wx.LEFT,12)
        self.sidebar_button=ActionButton(self,label='Navigator',toggle=True)
        self.sidebar_button.SetName('Schematic navigator');self.sidebar_button.SetValue(True)
        self.sidebar_button.SetToolTip('Show or hide the schematic component navigator')
        self.sidebar_button.Bind(wx.EVT_TOGGLEBUTTON,lambda event:self.toggle_sidebar())
        navigation.Add(self.sidebar_button,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4)
        outer.Add(navigation, 0, wx.EXPAND)
        self.tab_panel=wx.Panel(self);self.tab_row=wx.WrapSizer(wx.HORIZONTAL);self.tab_panel.SetSizer(self.tab_row)
        for label,index in PRIMARY_VIEWS:self.add_tab(index,label)
        self.location=wx.StaticText(self,label='Schematic');outer.Add(self.tab_panel,0,wx.EXPAND|wx.LEFT,8)
        outer.Add(self.location,0,wx.LEFT|wx.BOTTOM,12)
        self.tools = wx.Panel(self); row = wx.WrapSizer(wx.HORIZONTAL)
        owner.command_controls = []
        for label, command in SCHEMATIC_TOOLS:
            control = tool(self.tools, owner, label, lambda ident=command: owner.execute_command(ident),visible_label=label.split(' · ')[0])
            row.Add(control, 0, wx.ALL, 2);owner.command_controls.append((control, command))
        self.tools.SetSizer(row);outer.Add(self.tools, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 7)
        outer.Add(wx.StaticLine(self), 0, wx.EXPAND);self.SetSizer(outer)
        self.changed(owner.book.GetSelection())

    def toggle_sidebar(self):
        owner=self.owner
        if self.sidebar_button.GetValue():
            if not owner.workspace.IsSplit():
                owner.project_sidebar.Show();owner.workspace.SplitVertically(owner.project_sidebar,owner.book,250)
        elif owner.workspace.IsSplit():owner.workspace.Unsplit(owner.project_sidebar)
        owner.Layout()

    def changed(self, index):
        if index not in self.views:self.add_tab(index,self.owner.book.GetPageText(index))
        self.choice.SetSelection(next((i for i,(_label,page) in enumerate(PRIMARY_VIEWS) if page==index),wx.NOT_FOUND))
        for page, control in self.views.items(): control.SetValue(page == index)
        self.tools.Show(self.owner.canvas_available(index))
        # Waveforms and dashboard provide their own signal/instrument inspectors.
        # Do not spend their canvas width on the unrelated schematic palette.
        show_editor = self.owner.canvas_available(index) and self.sidebar_button.GetValue()
        self.sidebar_button.Show(self.owner.canvas_available(index))
        if hasattr(self.owner, 'workspace'):
            if show_editor and not self.owner.workspace.IsSplit() and not self.owner.browser_pinned:
                self.owner.project_sidebar.Show()
                self.owner.workspace.SplitVertically(self.owner.project_sidebar, self.owner.book, 250)
            elif not show_editor and self.owner.workspace.IsSplit():
                self.owner.workspace.Unsplit(self.owner.project_sidebar)
        self.Layout(); self.owner.Layout()
        if hasattr(self.owner, 'commands'): self.owner.context_tools()
        self.record(('workspace',index))

    def add_tab(self,index,label):
        control=ActionButton(self.tab_panel,label=label,toggle=True);control.SetName(label+' workspace tab')
        control.SetToolTip('Switch to '+label+'; specialist tabs can be floated from their context menu')
        control.Bind(wx.EVT_TOGGLEBUTTON,lambda event:self.go_page(index))
        if index not in {page for _label,page in PRIMARY_VIEWS}:
            def context(event):
                menu=wx.Menu();item=menu.Append(wx.ID_ANY,'Open in floating window')
                control.Bind(wx.EVT_MENU,lambda e:self.owner.tool_windows.open(index),item);control.PopupMenu(menu);menu.Destroy()
            control.Bind(wx.EVT_CONTEXT_MENU,context)
        self.tab_row.Add(control,0,wx.ALL,2);self.views[index]=control

    def record(self,target):
        if not self.replaying:self.history.visit(target)
        names={page:label for label,page in PRIMARY_VIEWS}
        self.location.SetLabel(('Window: ' if target[0]=='tool' else 'Workspace: ')+names.get(target[1],self.owner.book.GetPageText(target[1])))
        self.sync_navigation()

    def sync_navigation(self):
        self.navigation_buttons['view.back'].Enable(self.history.can_back)
        self.navigation_buttons['view.forward'].Enable(self.history.can_forward)
        self.navigation_buttons['view.back'].SetToolTip('Back · Alt+Left' if self.history.can_back else 'No previous section')
        self.navigation_buttons['view.forward'].SetToolTip('Forward · Alt+Right' if self.history.can_forward else 'No next section')
        self.navigation_buttons['view.home'].SetToolTip('Home · Alt+Home — return to schematic')

    def go_page(self,index):
        # Do not send the user to the empty schematic host while its editor is split.
        previous=self.replaying;self.replaying=True
        try:
            if index==0 and self.owner.split_view:self.owner.toggle_split()
            if index==0 and getattr(self.owner,'editor_split',None) and self.owner.editor_split.active:self.owner.editor_split.close()
            self.owner.book.SetSelection(index)
            if index in self.owner.tool_windows.entries:self.owner.tool_windows.entries[index][0].Raise()
            else:self.owner.Raise()
        finally:self.replaying=previous
        if index not in self.owner.tool_windows.entries:self.record(('workspace',index))
        else:self.record(('tool',index))

    def follow(self,target):
        if target is None:return
        self.replaying=True
        try:
            if target[0]=='tool':self.owner.tool_windows.open(target[1])
            else:self.go_page(target[1])
        finally:self.replaying=False
        self.sync_navigation()

    def back(self):self.follow(self.history.back())
    def forward(self):self.follow(self.history.forward())
    def home(self):self.go_page(0)
