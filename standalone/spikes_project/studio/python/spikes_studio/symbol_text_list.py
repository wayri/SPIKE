# SPDX-License-Identifier: Apache-2.0
"""Bounded native symbol-and-text list preserving the ListBox selection API."""
import wx
from .symbol_icons import SymbolImages


class SymbolTextList(wx.VListBox):
    def __init__(self,parent,palette,resolver=None,size=wx.DefaultSize):
        super().__init__(parent,size=size)
        self.rows=[];self.resolver=resolver or (lambda index,text:'component')
        self.refresh_symbols(palette)

    def refresh_symbols(self,palette):
        self.palette=palette;self.images=SymbolImages(None,palette);self.SetBackgroundColour(palette['canvas']);self.Refresh()

    def Set(self,items):
        selected=self.GetStringSelection();self.rows=list(items);self.SetItemCount(len(self.rows))
        self.SetSelection(self.rows.index(selected) if selected in self.rows else wx.NOT_FOUND);self.Refresh()

    def GetString(self,index):return self.rows[index]
    def GetStringSelection(self):
        index=self.GetSelection();return self.rows[index] if 0<=index<len(self.rows) else ''
    def GetCount(self):return len(self.rows)
    def OnMeasureItem(self,index):return 28
    def OnDrawBackground(self,dc,rect,index):
        color=self.palette['selected'] if self.IsSelected(index) else self.palette['canvas']
        dc.SetPen(wx.TRANSPARENT_PEN);dc.SetBrush(wx.Brush(color));dc.DrawRectangle(rect)
    def OnDrawItem(self,dc,rect,index):
        image=self.images.image_list.GetBitmap(self.images.index(self.resolver(index,self.rows[index])))
        dc.DrawBitmap(image,rect.x+5,rect.y+(rect.height-image.GetHeight())//2,True)
        dc.SetTextForeground(self.palette['fg']);dc.SetClippingRegion(rect)
        dc.DrawText(self.rows[index],rect.x+32,rect.y+(rect.height-dc.GetTextExtent(self.rows[index])[1])//2)
        dc.DestroyClippingRegion()
