# SPDX-License-Identifier: Apache-2.0
"""Grouped native context menus with local callbacks and explicit availability."""
import wx


class ContextMenu:
    def __init__(self,owner):
        self.owner=owner;self.menu=wx.Menu()

    def add(self,label,handler,enabled=True,reason='',checked=None):
        item=self.menu.Append(wx.ID_ANY,label,reason,wx.ITEM_NORMAL if checked is None else wx.ITEM_CHECK)
        item.Enable(bool(enabled))
        if checked is not None:item.Check(bool(checked))
        def invoke(event):
            if not enabled:return
            guard=getattr(self.owner,'guarded',None)
            guard(handler) if guard else handler()
        self.menu.Bind(wx.EVT_MENU,invoke,item)
        return item

    def submenu(self,label):
        child=ContextMenu(self.owner);self.menu.AppendSubMenu(child.menu,label);return child

    def separator(self):self.menu.AppendSeparator()

    def popup(self,window,position=None):
        try:
            if position is None:window.PopupMenu(self.menu)
            else:window.PopupMenu(self.menu,position)
        finally:self.menu.Destroy()


def editor_menu(editor):
    """Operate only on the clicked editor, not on schematic clipboard/history."""
    menu=ContextMenu(editor);selected=bool(editor.GetSelectedText());editable=not editor.GetReadOnly()
    menu.add('Undo\tCtrl+Z',editor.Undo,editable and editor.CanUndo(),'No editor edit to undo')
    menu.add('Redo\tCtrl+Y',editor.Redo,editable and editor.CanRedo(),'No editor edit to redo')
    menu.separator()
    menu.add('Cut\tCtrl+X',editor.Cut,editable and selected,'Select editable text first')
    menu.add('Copy\tCtrl+C',editor.Copy,selected,'Select text first')
    menu.add('Paste\tCtrl+V',editor.Paste,editable and editor.CanPaste(),'Editor is read-only or clipboard has no text')
    menu.add('Delete selection\tDel',editor.Clear,editable and selected,'Select editable text first')
    menu.separator();menu.add('Select all\tCtrl+A',editor.SelectAll,bool(editor.GetText()))
    menu.add('Word wrap',lambda:editor.SetWrapMode(wx.stc.STC_WRAP_NONE if editor.GetWrapMode()!=wx.stc.STC_WRAP_NONE else wx.stc.STC_WRAP_WORD),checked=editor.GetWrapMode()!=wx.stc.STC_WRAP_NONE)
    return menu


def bind_editor(editor):
    import wx.stc
    editor.UsePopUp(wx.stc.STC_POPUP_NEVER)
    def context(event):
        editor.SetFocus();editor_menu(editor).popup(editor)
    editor.Bind(wx.EVT_CONTEXT_MENU,context)
