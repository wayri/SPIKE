"""Code-drawn, theme-aware toolbar glyphs (no external bitmap assets)."""
import wx


def icon(label,palette):
    bitmap=wx.Bitmap(28,28);dc=wx.MemoryDC(bitmap)
    dc.SetBackground(wx.Brush(palette['bg']));dc.Clear()
    dc.SetPen(wx.Pen(palette['fg'],2));dc.SetBrush(wx.TRANSPARENT_BRUSH)
    def lines(points):dc.DrawLines([wx.Point(*p) for p in points])
    if 'Wire' in label:
        lines([(4,22),(13,22),(13,6),(24,6)]);dc.DrawCircle(4,22,2);dc.DrawCircle(24,6,2)
    elif 'Rotate' in label:
        dc.DrawEllipticArc(5,5,18,18,0,270);lines([(20,4),(24,10),(17,10)])
    elif 'Mirror' in label:
        dc.DrawLine(14,3,14,25);lines([(4,7),(10,14),(4,21),(4,7)]);lines([(24,7),(18,14),(24,21),(24,7)])
        if 'Y' in label:dc.DrawLine(3,25,25,25)
    elif 'Lasso' in label:
        lines([(5,5),(20,4),(24,15),(17,23),(5,20),(3,10),(5,5)])
    elif 'Select' in label:
        lines([(6,3),(6,24),(12,18),(17,25),(20,23),(15,16),(24,15),(6,3)])
    elif 'Probe' in label or 'Differential' in label:
        lines([(4,24),(17,11),(21,15),(8,28)]);dc.DrawLine(19,13,25,4)
        if 'Differential' in label:dc.DrawLine(4,5,11,5);dc.DrawLine(7,2,7,8)
    elif 'Plots' in label:
        lines([(4,3),(4,24),(26,24)]);lines([(5,19),(10,8),(15,18),(21,5),(25,11)])
    elif 'Split' in label:
        dc.DrawRectangle(3,4,23,20);dc.DrawLine(14,4,14,24)
    elif 'Fit' in label:
        for a,b,c in [((3,11),(3,3),(11,3)),((17,3),(25,3),(25,11)),((25,17),(25,25),(17,25)),((11,25),(3,25),(3,17))]:lines([a,b,c])
    elif 'Dashboard' in label:
        dc.DrawCircle(14,14,10);dc.DrawLine(14,14,20,7)
    elif 'Properties' in label:
        for y,x in ((7,9),(14,19),(21,12)):dc.DrawLine(3,y,25,y);dc.DrawRectangle(x-2,y-3,4,6)
    else:
        dc.DrawRectangle(7,6,14,16)
        for y in (9,14,19):dc.DrawLine(3,y,7,y);dc.DrawLine(21,y,25,y)
        if 'Manufacturer' in label:dc.DrawCircle(14,14,3)
        elif 'Design' in label:dc.DrawLine(9,20,23,3)
        else:dc.DrawLine(10,14,18,14)
    dc.SelectObject(wx.NullBitmap);return bitmap


def tool(parent,owner,label,action):
    control=wx.BitmapButton(parent,bitmap=icon(label,owner.palette),size=(38,36))
    control.SetName(label);control.SetToolTip(label)
    control.Bind(wx.EVT_BUTTON,lambda event:owner.guarded(action))
    owner.designer_icon_controls=getattr(owner,'designer_icon_controls',[])+[(control,label)]
    return control
