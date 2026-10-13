"""Shared application palettes for native widgets, code editors and figures."""
import json
import os
from pathlib import Path

PALETTES={
 'Dark':dict(bg='#17191c',panel='#222529',field='#2a2d32',fg='#e5e7eb',muted='#9ba2ad',grid='#373c43',accent='#75a8de',selected='#333d4b',danger='#e88585',canvas='#191c20'),
 'Light':dict(bg='#edf0f3',panel='#f5f6f8',field='#ffffff',fg='#27313d',muted='#606b79',grid='#dfe4e9',accent='#2863a2',selected='#e1eaf4',danger='#b44040',canvas='#ffffff'),
 'Midnight':dict(bg='#17191c',panel='#222529',field='#2a2d32',fg='#e5e7eb',muted='#9ba2ad',grid='#373c43',accent='#75a8de',selected='#333d4b',danger='#e88585',canvas='#191c20'),
 'High contrast':dict(bg='#000000',panel='#000000',field='#101010',fg='#ffffff',muted='#e1e1e1',grid='#5c5c5c',accent='#fff36b',selected='#353500',danger='#ffaaaa',canvas='#000000'),
}
TRACE_DARK=['#69d8ff','#ffd166','#b8e986','#f19ed2','#c7b2ff','#ff9c72','#80e5d1','#f4f6fb']
TRACE_LIGHT=['#006a99','#986000','#397500','#a52c79','#6740ae','#b44316','#00786a','#354254']


def preferences_path():return Path(os.environ.get('LOCALAPPDATA',Path.home()))/'SPIKES Studio'/'appearance.json'

def load_theme():
    path=preferences_path()
    try:
        if path.stat().st_size>65536:return 'Light'
        name=json.loads(path.read_text(encoding='utf-8'))['theme']
        return name if name in PALETTES else 'Light'
    except (OSError,ValueError,KeyError):return 'Light'

def native_appearance(name):
    import wx
    app=wx.GetApp()
    if hasattr(app,'SetAppearance'):
        app.SetAppearance(wx.App.Appearance.Light if name=='Light' else wx.App.Appearance.Dark)

def apply_window(window,palette):
    import wx
    import wx.grid
    import wx.stc
    import wx.aui
    controls=(wx.TextCtrl,wx.ListBox,wx.ListCtrl,wx.ComboBox,wx.Choice,wx.SearchCtrl)
    window.SetBackgroundColour(palette['field'] if isinstance(window,controls) else palette['panel'])
    window.SetForegroundColour(palette['fg'])
    if isinstance(window,wx.stc.StyledTextCtrl):
        for i in range(256):window.StyleSetBackground(i,palette['canvas']);window.StyleSetForeground(i,palette['fg'])
        window.SetCaretForeground(palette['accent']);window.SetSelBackground(True,palette['selected']);window.SetSelForeground(True,palette['fg'])
        window.StyleSetBackground(wx.stc.STC_STYLE_LINENUMBER,palette['panel']);window.StyleSetForeground(wx.stc.STC_STYLE_LINENUMBER,palette['muted'])
        for style in (wx.stc.STC_C_COMMENT,wx.stc.STC_C_COMMENTLINE):window.StyleSetForeground(style,palette['muted'])
        for style in (wx.stc.STC_C_WORD,wx.stc.STC_C_WORD2):window.StyleSetForeground(style,palette['accent'])
    if isinstance(window,wx.grid.Grid):
        window.SetDefaultCellBackgroundColour(palette['field']);window.SetDefaultCellTextColour(palette['fg'])
        window.SetLabelBackgroundColour(palette['panel']);window.SetLabelTextColour(palette['fg']);window.SetGridLineColour(palette['grid'])
        window.SetSelectionBackground(palette['selected']);window.SetSelectionForeground(palette['fg'])
    if isinstance(window,wx.ToolBar):
        for index in range(window.GetToolsCount()):
            tool=window.GetToolByPos(index)
            if tool and not tool.IsSeparator() and not tool.IsControl():
                window.SetToolNormalBitmap(tool.GetId(),toolbar_icon(tool.GetLabel().lower(),palette))
                window.SetToolDisabledBitmap(tool.GetId(),toolbar_icon(tool.GetLabel().lower(),palette|{'fg':palette['muted'],'accent':palette['muted'],'danger':palette['muted']}))
    if isinstance(window,wx.aui.AuiNotebook):
        art=wx.aui.AuiSimpleTabArt();art.SetColour(wx.Colour(palette['panel']));art.SetActiveColour(wx.Colour(palette['selected']))
        font=wx.Font(10,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL)
        art.SetNormalFont(font);art.SetSelectedFont(font);art.SetMeasuringFont(font);window.SetArtProvider(art);window.SetTabCtrlHeight(32)
    for child in window.GetChildren():apply_window(child,palette)
    window.Refresh()

def figure_theme(figure,palette,name):
    figure.set_facecolor(palette['canvas'])
    colors=TRACE_LIGHT if name=='Light' else TRACE_DARK
    trace_colors={}
    for ax in figure.axes:
        ax.set_facecolor(palette['canvas']);ax.tick_params(colors=palette['muted'],labelsize=9)
        ax.title.set_color(palette['fg']);ax.xaxis.label.set_color(palette['muted']);ax.yaxis.label.set_color(palette['muted'])
        ax.xaxis.offsetText.set_color(palette['muted']);ax.yaxis.offsetText.set_color(palette['muted'])
        for key,spine in ax.spines.items():
            spine.set_color(palette['grid']);spine.set_linewidth(.7)
            spine.set_visible(key in ('left','bottom') or ax.name=='polar')
        ax.tick_params(length=3, width=.6, pad=6)
        for line in ax.get_xgridlines()+ax.get_ygridlines():line.set_color(palette['grid']);line.set_alpha(.5);line.set_linewidth(.6)
        for i,line in enumerate(ax.lines):
            if line.get_label() and not line.get_label().startswith('_'):
                label=line.get_label();trace_colors.setdefault(label,colors[len(trace_colors)%len(colors)]);line.set_color(trace_colors[label])
            elif line.get_linewidth()<.9:line.set_color(palette['grid'])
        for collection in ax.collections:collection.set_edgecolor(palette['accent'])
        for text in ax.texts:text.set_color(palette['muted'])
        legend=ax.get_legend()
        if legend:
            legend.set_frame_on(False)
            legend.get_frame().set_facecolor(palette['panel']);legend.get_frame().set_edgecolor(palette['grid'])
            for text in legend.get_texts():text.set_color(palette['fg'])
            for handle,text in zip(legend.get_lines(),legend.get_texts()):
                if text.get_text() in trace_colors:handle.set_color(trace_colors[text.get_text()])
    for text in figure.texts:text.set_color(palette['fg'])

def toolbar_icon(command,palette,size=22):
    """Small vector-drawn, contrast-aware icons (no raster recoloring)."""
    import wx
    command={'home':'home','back':'back','forward':'forward','pan':'pan','zoom':'view.fit','save':'file.save','subplots':'axes'}.get(command,command)
    bitmap=wx.Bitmap(size,size,32);dc=wx.MemoryDC(bitmap);dc.SetBackground(wx.Brush(palette['panel']));dc.Clear()
    dc.SetPen(wx.Pen(palette['fg'],2));dc.SetBrush(wx.TRANSPARENT_BRUSH)
    if command in ('run.start','run.interactive'):
        dc.SetBrush(wx.Brush(palette['accent']));dc.SetPen(wx.Pen(palette['accent']));dc.DrawPolygon([wx.Point(6,3),wx.Point(19,11),wx.Point(6,19)])
    elif command=='run.stop':dc.SetBrush(wx.Brush(palette['danger']));dc.SetPen(wx.Pen(palette['danger']));dc.DrawRectangle(5,5,12,12)
    elif command=='run.pause':dc.DrawLine(7,4,7,18);dc.DrawLine(15,4,15,18)
    elif command=='file.open':dc.DrawLines([wx.Point(3,18),wx.Point(3,5),wx.Point(9,5),wx.Point(12,8),wx.Point(19,8),wx.Point(19,18),wx.Point(3,18)])
    elif command=='file.save':dc.DrawRectangle(4,3,14,16);dc.DrawRectangle(7,3,8,5);dc.DrawRectangle(7,12,8,7)
    elif command=='view.fit':dc.DrawCircle(9,9,6);dc.DrawLine(14,14,20,20)
    elif command=='home':dc.DrawLines([wx.Point(2,11),wx.Point(11,3),wx.Point(20,11)]);dc.DrawRectangle(6,10,10,10)
    elif command in ('back','forward'):
        a,b=(17,5) if command=='back' else (5,17);dc.DrawLine(a,11,b,11);dc.DrawLine(b,11,11,5);dc.DrawLine(b,11,11,17)
    elif command=='pan':dc.DrawLine(3,11,19,11);dc.DrawLine(11,3,11,19);dc.DrawCircle(11,11,3)
    elif command.startswith('probe'):dc.DrawLine(4,17,17,4);dc.DrawCircle(5,16,3);dc.DrawLine(12,4,18,10)
    else:dc.DrawRectangle(4,3,14,16);dc.DrawLine(7,7,15,7);dc.DrawLine(7,11,15,11);dc.DrawLine(7,15,12,15)
    dc.SelectObject(wx.NullBitmap);return bitmap
