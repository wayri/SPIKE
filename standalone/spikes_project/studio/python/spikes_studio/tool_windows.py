# SPDX-License-Identifier: Apache-2.0
"""State-preserving native tool windows; no duplicate models or simulations."""
import wx
from .flat_controls import ActionButton
from .themes import apply_window

TOOL_COMMANDS = {
    'Libraries': {'view.parts':4, 'view.component_catalog':11, 'view.manufacturer_parts':16,
                  'view.symbol_designer':14, 'view.controller':12},
    'Analysis': {'view.directives':7, 'view.frequency':8, 'view.power_tree':9,
                 'view.analytics':10, 'view.offline_report':15},
    'Tools': {'view.ide':3, 'view.battery_laboratory':17, 'view.monte_carlo':18},
    'Simulation': {'run.manager':6},
    'Help': {'help.open':5},
}


class ToolWindows:
    def __init__(self, owner):
        self.owner=owner;self.entries={}
        owner.book.floating_tools=self

    def open(self, index):
        book=self.owner.book
        paired=getattr(self.owner,'editor_split',None)
        if paired and paired.active and paired.page_index==index:paired.close()
        if index not in range(book.GetPageCount()):raise ValueError('Tool page is unavailable')
        if index==11 and self.owner.browser_pinned:self.owner.pin_browser(False)
        if index not in self.entries:
            page=book.GetPage(index);title=book.GetPageText(index)
            if book.GetSelection()==index:
                if hasattr(self.owner,'workflow_bar'):self.owner.workflow_bar.go_page(0)
                else:book.SetSelection(0)
            book.RemovePage(index)
            placeholder=wx.Panel(book);placeholder.SetSizer(wx.BoxSizer(wx.VERTICAL))
            book.InsertPage(index,placeholder,title)
            window=wx.Frame(self.owner,title='SPIKES · '+title,size=(1060,760))
            from .app_identity import set_window_icons
            set_window_icons(window);window.SetMinSize((700,500))
            layout=wx.BoxSizer(wx.VERTICAL);bar=wx.BoxSizer(wx.HORIZONTAL)
            label=wx.StaticText(window,label='Shared circuit and session · closing this window retains its state')
            bar.Add(label,1,wx.ALL|wx.ALIGN_CENTER_VERTICAL,8)
            dock=ActionButton(window,label='Return to workspace')
            dock.Bind(wx.EVT_BUTTON,lambda event:self.dock(index));bar.Add(dock,0,wx.ALL,5)
            layout.Add(bar,0,wx.EXPAND)
            page.Reparent(window);layout.Add(page,1,wx.EXPAND);window.SetSizer(layout)
            self.entries[index]=(window,page,placeholder)
            window.Bind(wx.EVT_CLOSE,lambda event:self.hide(index,event))
            apply_window(window,self.owner.palette)
        window,page,_=self.entries[index]
        page.Show();window.Show();window.Raise();window.Layout()
        if index==11 and not getattr(window,'catalog_fitted',False):
            self.owner.catalog_panel.initial_layout=False;wx.CallAfter(self.owner.catalog_panel.fit_initial_layout);window.catalog_fitted=True
        if hasattr(self.owner,'workflow_bar'):self.owner.workflow_bar.record(('tool',index))
        if hasattr(self.owner,'workflow_bar') and index in self.owner.workflow_bar.views and index not in (0,1,2,13):
            tab=self.owner.workflow_bar.views.pop(index);self.owner.workflow_bar.tab_row.Detach(tab);tab.Destroy();self.owner.workflow_bar.Layout();self.owner.Layout()
        return window

    def hide(self,index,event):
        if event.CanVeto():
            event.Veto();self.entries[index][0].Hide()
            if hasattr(self.owner,'workflow_bar'):self.owner.workflow_bar.location.SetLabel('Workspace: '+self.owner.book.GetPageText(self.owner.book.GetSelection()))
        else:event.Skip()

    def dock(self,index):
        window,page,placeholder=self.entries.pop(index)
        book=self.owner.book;title=book.GetPageText(index)
        window.GetSizer().Detach(page)
        book.RemovePage(index);page.Reparent(book);book.InsertPage(index,page,title)
        placeholder.Destroy();window.Destroy();book.SetSelection(index);self.owner.Layout()

    def find_page(self,page):
        return next((index for index,(_,actual,_) in self.entries.items() if actual is page),wx.NOT_FOUND)
