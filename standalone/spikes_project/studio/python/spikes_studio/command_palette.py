"""Searchable command palette using the same dispatch as menus and shortcuts."""
import wx


def show(owner):
    with wx.Dialog(owner,title='Find command',size=(740,460),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dialog:
        box=wx.BoxSizer(wx.VERTICAL);search=wx.SearchCtrl(dialog)
        listing=wx.ListBox(dialog);detail=wx.StaticText(dialog,label='')
        execute=wx.Button(dialog,wx.ID_OK,'Execute command')
        box.Add(search,0,wx.EXPAND|wx.ALL,10);box.Add(listing,1,wx.EXPAND|wx.LEFT|wx.RIGHT,10)
        box.Add(detail,0,wx.EXPAND|wx.ALL,10);box.Add(execute,0,wx.ALIGN_RIGHT|wx.ALL,10)
        dialog.SetSizer(box);rows=[]
        def selected(event=None):
            i=listing.GetSelection();row=rows[i] if 0<=i<len(rows) else None
            execute.Enable(row is not None and not row['disabled_reason'])
            detail.SetLabel((row['disabled_reason'] or row['description']) if row else 'No matching commands')
            detail.Wrap(max(300,dialog.GetClientSize().width-30));dialog.Layout()
        def refresh(event=None):
            rows[:]=owner.commands.search(search.GetValue(),owner.keymap.bindings)
            listing.Set([r['label']+('  ['+r['shortcut']+']' if r['shortcut'] else '')+(' — unavailable' if r['disabled_reason'] else '') for r in rows])
            if rows:listing.SetSelection(0)
            selected()
        def accept(event):
            if execute.IsEnabled():dialog.EndModal(wx.ID_OK)
        search.Bind(wx.EVT_TEXT,refresh);listing.Bind(wx.EVT_LISTBOX,selected)
        listing.Bind(wx.EVT_LISTBOX_DCLICK,accept);execute.Bind(wx.EVT_BUTTON,accept)
        refresh();search.SetFocus()
        from .themes import apply_window
        apply_window(dialog,owner.palette)
        if dialog.ShowModal()==wx.ID_OK:
            owner.execute_command(rows[listing.GetSelection()]['id'])
