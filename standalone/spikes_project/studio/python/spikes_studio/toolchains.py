# SPDX-License-Identifier: Apache-2.0
"""User-selected compiler locations; reading settings never executes a tool."""
import json
from pathlib import Path
from .themes import preferences_path

NAMES=('clang++','cl','iverilog','vvp','yosys','ghdl')

def settings_path():return preferences_path().parent/'toolchains.json'

def load():
    path=settings_path()
    if not path.exists():return {}
    if path.stat().st_size>16384:raise ValueError('Toolchain settings exceed 16 KiB')
    value=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict) or value.get('contract')!='spikes/toolchains/v1':raise ValueError('Unsupported toolchain settings')
    paths=value.get('paths')
    if not isinstance(paths,dict) or set(paths)-set(NAMES):raise ValueError('Unknown configured tools')
    if any(not isinstance(p,str) or len(p)>4096 or (p and not Path(p).is_absolute()) for p in paths.values()):raise ValueError('Tool paths must be absolute')
    return paths

def configured(name):
    try:value=load().get(name)
    except (ValueError,OSError):return None
    return str(Path(value)) if value and Path(value).is_file() else None

def save(paths):
    if set(paths)-set(NAMES):raise ValueError('Unknown configured tools')
    for value in paths.values():
        if not isinstance(value,str) or (value and (not Path(value).is_absolute() or not Path(value).is_file())):raise ValueError('Select an existing executable or leave blank for automatic discovery')
    from .document import write_json
    target=settings_path();target.parent.mkdir(parents=True,exist_ok=True)
    write_json(target,{'contract':'spikes/toolchains/v1','paths':paths})

def show(owner):
    import wx
    with wx.Dialog(owner,title='Compiler and HDL toolchains',size=(730,470),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dialog:
        root=wx.BoxSizer(wx.VERTICAL)
        text=wx.StaticText(dialog,label='Select installed executables. Blank entries use PATH / automatic discovery.\nSaving these paths does not run code or approve any component source.')
        root.Add(text,0,wx.ALL,10);grid=wx.FlexGridSizer(cols=2,hgap=8,vgap=7);grid.AddGrowableCol(1)
        fields={}
        try:paths=load()
        except (ValueError,OSError) as exc:
            paths={};text.SetLabel('Invalid saved settings: '+str(exc)+'\nSelect paths and save to repair them. No compiler has been run.')
        for name in NAMES:
            grid.Add(wx.StaticText(dialog,label=name),0,wx.ALIGN_CENTER_VERTICAL)
            fields[name]=wx.FilePickerCtrl(dialog,path=paths.get(name,''),message='Select '+name,style=wx.FLP_OPEN|wx.FLP_USE_TEXTCTRL)
            grid.Add(fields[name],1,wx.EXPAND)
        root.Add(grid,1,wx.EXPAND|wx.ALL,10);root.Add(dialog.CreateButtonSizer(wx.OK|wx.CANCEL),0,wx.ALL,10);dialog.SetSizer(root)
        from .themes import apply_window
        apply_window(dialog,owner.palette)
        while dialog.ShowModal()==wx.ID_OK:
            try:save({name:field.GetPath().strip() for name,field in fields.items()});return
            except (ValueError,OSError) as exc:wx.MessageBox(str(exc),'Toolchain settings',wx.OK|wx.ICON_WARNING,dialog)
