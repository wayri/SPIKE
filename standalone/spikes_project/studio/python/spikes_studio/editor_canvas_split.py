# SPDX-License-Identifier: Apache-2.0
"""Pair the actual schematic with an existing stateful code page."""
import wx


class EditorCanvasSplit:
    def __init__(self,owner):self.owner=owner;self.page_index=None;self.host=None;self.page=None
    @property
    def active(self):return self.host is not None
    def show(self,index=2,orientation='side_by_side'):
        if index not in (2,3,12) or orientation not in ('side_by_side','top_bottom'):raise ValueError('Choose Netlist, IDE or Controller and a valid split layout')
        owner=self.owner;book=owner.book
        if self.active:self.close()
        if owner.split_view:owner.toggle_split()
        if index in owner.tool_windows.entries:owner.tool_windows.dock(index)
        window=getattr(owner,'controller_code_window',None)
        if index==12 and window:window.restore()
        self.page=book.GetPage(index);self.title=book.GetPageText(index);book.RemovePage(index)
        self.host=wx.SplitterWindow(book,style=wx.SP_LIVE_UPDATE);self.host.SetMinimumPaneSize(120);self.page_index=index
        owner.schematic_host.GetSizer().Detach(owner.canvas);owner.canvas.Reparent(self.host);self.page.Reparent(self.host)
        book.InsertPage(index,self.host,self.title);book.SetSelection(index)
        size=self.host.GetClientSize()
        if orientation=='side_by_side':self.host.SplitVertically(owner.canvas,self.page,max(120,size.width//2))
        else:self.host.SplitHorizontally(owner.canvas,self.page,max(120,size.height//2))
        self.host.SetSashGravity(.5);owner.canvas.Show();self.page.Show();self.host.Layout();owner.Layout()
        owner.SetStatusText('Code / schematic · drag the divider; select a net or pin name in the editor to cross-highlight')
    def close(self):
        if not self.active:return
        owner=self.owner;book=owner.book;host,page,index=self.host,self.page,self.page_index
        self.host=None;self.page=None;self.page_index=None
        host.Unsplit(owner.canvas);book.RemovePage(index)
        owner.canvas.Reparent(owner.schematic_host);owner.schematic_host.GetSizer().Add(owner.canvas,1,wx.EXPAND);owner.canvas.Show()
        page.Reparent(book);book.InsertPage(index,page,self.title);host.Destroy();book.SetSelection(index);owner.schematic_host.Layout();owner.Layout()
