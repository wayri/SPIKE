"""Code-drawn, theme-aware toolbar glyphs (no external bitmap assets)."""
import wx


def icon(label,palette):
    bitmap=wx.Bitmap(28,28);dc=wx.MemoryDC(bitmap)
    dc.SetBackground(wx.Brush(palette['panel']));dc.Clear()
    dc.SetPen(wx.Pen(palette['fg'],2));dc.SetBrush(wx.TRANSPARENT_BRUSH)
    def lines(points):dc.DrawLines([wx.Point(*p) for p in points])
    if label in ('Back','Forward'):
        direction=-1 if label=='Back' else 1
        dc.DrawLine(5,14,23,14);x=5 if direction<0 else 23
        lines([(x-6*direction,7),(x,14),(x-6*direction,21)])
    elif label=='Home':
        lines([(3,13),(14,3),(25,13)]);lines([(6,11),(6,25),(22,25),(22,11)]);dc.DrawRectangle(11,17,6,8)
    elif 'Wire' in label:
        lines([(4,22),(13,22),(13,6),(24,6)]);dc.DrawCircle(4,22,2);dc.DrawCircle(24,6,2)
    elif 'Rotate' in label:
        dc.DrawEllipticArc(5,5,18,18,0,270);lines([(20,4),(24,10),(17,10)])
    elif 'Move' in label:
        dc.DrawLine(4,14,24,14);dc.DrawLine(14,4,14,24)
        for points in [[(8,10),(4,14),(8,18)],[(20,10),(24,14),(20,18)],[(10,8),(14,4),(18,8)],[(10,20),(14,24),(18,20)]]:lines(points)
    elif 'Drag' in label:
        dc.DrawRectangle(4,5,13,13);dc.DrawLine(17,11,24,11);dc.DrawLine(11,18,11,25)
        lines([(18,20),(23,25),(26,17),(18,20)])
    elif 'Interact' in label:
        dc.DrawCircle(12,12,8);lines([(10,8),(10,18),(15,15),(19,21),(22,19),(17,13),(10,8)])
    elif 'Limit' in label:
        lines([(14,3),(26,25),(2,25),(14,3)]);dc.DrawLine(14,10,14,17);dc.DrawCircle(14,21,1)
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


def tool(parent,owner,label,action,visible_label=None):
    from .flat_controls import ActionButton
    control=ActionButton(parent,label=visible_label or '',size=(38,36) if visible_label is None else wx.DefaultSize)
    bitmap=icon(label,owner.palette)
    if visible_label is not None:bitmap=wx.Bitmap(bitmap.ConvertToImage().Scale(20,20,wx.IMAGE_QUALITY_HIGH))
    control.SetBitmap(bitmap)
    if visible_label is not None:control.SetInitialSize(control.GetBestSize())
    control.SetName(label);control.SetToolTip(label)
    control.Bind(wx.EVT_BUTTON,lambda event:owner.guarded(action))
    owner.designer_icon_controls=getattr(owner,'designer_icon_controls',[])+[(control,label)]
    return control
