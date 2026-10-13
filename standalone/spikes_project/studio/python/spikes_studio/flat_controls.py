# SPDX-License-Identifier: Apache-2.0
"""Quiet, keyboard-operable command controls for the wx workbench."""
import wx


if hasattr(wx, 'Accessible'):
    class _ButtonAccessible(wx.Accessible):
        def GetName(self, childId): return wx.ACC_OK, self.GetWindow().GetName()
        def GetRole(self, childId): return wx.ACC_OK, wx.ROLE_SYSTEM_PUSHBUTTON
        def GetState(self, childId):
            control = self.GetWindow(); state = wx.ACC_STATE_SYSTEM_FOCUSABLE
            if not control.IsEnabled(): state |= wx.ACC_STATE_SYSTEM_UNAVAILABLE
            if control.HasFocus(): state |= wx.ACC_STATE_SYSTEM_FOCUSED
            if control.GetValue(): state |= wx.ACC_STATE_SYSTEM_PRESSED
            return wx.ACC_OK, state
        def GetDefaultAction(self, childId): return wx.ACC_OK, 'Press'
        def DoDefaultAction(self, childId):
            control = self.GetWindow()
            if not control.IsEnabled(): return wx.ACC_FAIL
            wx.CallAfter(control.activate); return wx.ACC_OK


class ActionButton(wx.Control):
    """Borderless at rest; visible hover, selection, disabled and focus states."""
    def __init__(self, parent, label='', size=wx.DefaultSize, toggle=False):
        super().__init__(parent, style=wx.BORDER_NONE | wx.WANTS_CHARS, size=size)
        self.SetLabel(label); self.SetName(label)
        self.bitmap = None; self.disabled_bitmap = None
        self.value = False; self.toggle = toggle; self.hover = False; self.pressed = False
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.paint)
        self.Bind(wx.EVT_ENTER_WINDOW, lambda e: self.highlight(True))
        self.Bind(wx.EVT_LEAVE_WINDOW, lambda e: self.highlight(False))
        self.Bind(wx.EVT_LEFT_DOWN, self.down)
        self.Bind(wx.EVT_LEFT_UP, self.up)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.capture_lost)
        self.Bind(wx.EVT_KEY_DOWN, self.key)
        # Char hook precedes the frame's schematic accelerator table (Space).
        self.Bind(wx.EVT_CHAR_HOOK, self.key)
        self.Bind(wx.EVT_SET_FOCUS, self.focus_changed)
        self.Bind(wx.EVT_KILL_FOCUS, self.focus_changed)
        if hasattr(wx, 'Accessible'): self.SetAccessible(_ButtonAccessible(self))
        self.SetInitialSize(size)

    def DoGetBestSize(self):
        width, height = self.GetTextExtent(self.GetLabel())
        return wx.Size(width + 24 + (26 if self.bitmap else 0), max(32, height + 14))

    def SetBitmap(self, bitmap):
        self.bitmap = bitmap; self.InvalidateBestSize(); self.Refresh()

    def SetBitmapDisabled(self, bitmap):
        self.disabled_bitmap = bitmap; self.Refresh()

    def SetValue(self, value): self.value = bool(value); self.Refresh()
    def GetValue(self): return self.value
    def highlight(self, value): self.hover = value; self.Refresh()
    def focus_changed(self, event): self.Refresh(); event.Skip()
    def capture_lost(self, event): self.pressed = False; self.Refresh()

    def down(self, event):
        if self.IsEnabled():
            self.SetFocus(); self.pressed = True; self.CaptureMouse(); self.Refresh()

    def up(self, event):
        activate = self.pressed and self.GetClientRect().Contains(event.GetPosition())
        self.pressed = False
        if self.HasCapture(): self.ReleaseMouse()
        self.Refresh()
        if activate and self.IsEnabled(): self.activate()

    def key(self, event):
        if event.GetKeyCode() in (wx.WXK_SPACE, wx.WXK_RETURN) and self.IsEnabled(): self.activate()
        else: event.Skip()

    def activate(self):
        if not self.IsEnabled(): return
        if self.toggle: self.SetValue(not self.value)
        event = wx.CommandEvent(wx.EVT_TOGGLEBUTTON.typeId if self.toggle else wx.EVT_BUTTON.typeId, self.GetId())
        event.SetEventObject(self); event.SetInt(int(self.value)); self.GetEventHandler().ProcessEvent(event)

    def paint(self, event):
        from .themes import PALETTES
        ancestor = self
        while ancestor and not hasattr(ancestor, 'palette'): ancestor = ancestor.GetParent()
        palette = ancestor.palette if ancestor else PALETTES['Light']
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.GetParent().GetBackgroundColour())); dc.Clear()
        rect = self.GetClientRect(); rect.Deflate(1)
        active = self.IsEnabled() and (self.value or self.pressed or self.hover)
        if active:
            dc.SetPen(wx.TRANSPARENT_PEN); dc.SetBrush(wx.Brush(palette['selected']))
            dc.DrawRoundedRectangle(rect, 4)
        if self.HasFocus():
            dc.SetPen(wx.Pen(palette['accent'], 1)); dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawRoundedRectangle(rect, 4)
        dc.SetFont(self.GetFont())
        dc.SetTextForeground(palette['muted'] if not self.IsEnabled() else palette['accent'] if self.value else palette['fg'])
        width, height = dc.GetTextExtent(self.GetLabel()); x = 12
        bitmap = self.bitmap if self.IsEnabled() or not self.disabled_bitmap else self.disabled_bitmap
        if bitmap and bitmap.IsOk():
            if not self.GetLabel(): x = (rect.width - bitmap.GetWidth()) // 2
            dc.DrawBitmap(bitmap, x, (rect.height - bitmap.GetHeight()) // 2, True); x += 26
        dc.DrawText(self.GetLabel(), x, (rect.height - height) // 2)
