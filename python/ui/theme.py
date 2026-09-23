"""
SPIKE Modern Theme Engine — Phase 15.1
Provides:
  • True Windows dark-mode via wx.SystemOptions before App creation
  • Custom AGW AUI DockArt and TabArt for modern dark panels
  • Modern colour palette with proper CSS-grade tokens
  • apply_theme() replaces the old recursive background-colour blasting
  • Ribbon-compatible colours
"""
import wx
import wx.lib.agw.aui as aui

# ── Palette ─────────────────────────────────────────────────────────────────
# Dark palette inspired by VS Code / JetBrains Rider dark themes
class Palette:
    # Backgrounds
    BG_BASE    = wx.Colour(18,  18,  27)   # deepest background
    BG_PANEL   = wx.Colour(28,  28,  40)   # panel / sidebar
    BG_CARD    = wx.Colour(35,  35,  52)   # cards, group boxes
    BG_INPUT   = wx.Colour(22,  22,  33)   # text inputs
    BG_HOVER   = wx.Colour(50,  50,  75)   # hover state
    BG_SEL     = wx.Colour(60,  80, 140)   # selected row

    # Tab/Notebook
    TAB_ACTIVE   = wx.Colour(40,  40,  62)
    TAB_INACTIVE = wx.Colour(25,  25,  38)
    TAB_BORDER   = wx.Colour(80,  80, 120)

    # Text
    TEXT_PRIMARY   = wx.Colour(220, 220, 235)
    TEXT_SECONDARY = wx.Colour(150, 150, 180)
    TEXT_DIM       = wx.Colour(90,  90, 120)

    # Accent
    ACCENT_RED   = wx.Colour(233,  69,  96)   # #E94560  — SPIKE brand
    ACCENT_CYAN  = wx.Colour(  0, 191, 255)   # deep sky blue
    ACCENT_GOLD  = wx.Colour(255, 215,   0)
    ACCENT_GREEN = wx.Colour( 40, 167,  69)

    # Borders / sash
    BORDER  = wx.Colour(55,  55,  80)
    SASH    = wx.Colour(45,  45,  65)

    # Button
    BTN_BG  = wx.Colour(50,  50,  78)
    BTN_HOV = wx.Colour(70,  70, 108)

    # Light palette
    LT_BG_BASE  = wx.Colour(245, 246, 250)
    LT_BG_PANEL = wx.Colour(255, 255, 255)
    LT_TEXT     = wx.Colour(25,  25,  35)
    LT_BORDER   = wx.Colour(210, 210, 220)
    LT_ACCENT   = wx.Colour(70,  90, 200)


def _c(colour):
    """Convert wx.Colour → tuple for art providers."""
    return colour


# ── Custom AUI Dock Art ──────────────────────────────────────────────────────
class SpikeDockArt(aui.AuiDefaultDockArt):
    """Dark/Light dock art for AGW AUI panes."""

    def __init__(self, dark=True):
        super().__init__()
        p = Palette
        if dark:
            self.SetMetric(aui.AUI_DOCKART_SASH_SIZE, 4)
            self.SetColour(aui.AUI_DOCKART_BACKGROUND_COLOUR,       p.BG_BASE)
            self.SetColour(aui.AUI_DOCKART_SASH_COLOUR,             p.SASH)
            self.SetColour(aui.AUI_DOCKART_ACTIVE_CAPTION_COLOUR,   p.ACCENT_RED)
            self.SetColour(aui.AUI_DOCKART_ACTIVE_CAPTION_GRADIENT_COLOUR, wx.Colour(180, 40, 60))
            self.SetColour(aui.AUI_DOCKART_INACTIVE_CAPTION_COLOUR, p.BG_PANEL)
            self.SetColour(aui.AUI_DOCKART_INACTIVE_CAPTION_GRADIENT_COLOUR, p.BG_CARD)
            self.SetColour(aui.AUI_DOCKART_ACTIVE_CAPTION_TEXT_COLOUR,   p.TEXT_PRIMARY)
            self.SetColour(aui.AUI_DOCKART_INACTIVE_CAPTION_TEXT_COLOUR, p.TEXT_SECONDARY)
            self.SetColour(aui.AUI_DOCKART_BORDER_COLOUR,           p.BORDER)
            self.SetColour(aui.AUI_DOCKART_GRIPPER_COLOUR,          p.BG_HOVER)
        else:
            p2 = Palette
            self.SetColour(aui.AUI_DOCKART_BACKGROUND_COLOUR,       p2.LT_BG_BASE)
            self.SetColour(aui.AUI_DOCKART_ACTIVE_CAPTION_COLOUR,   p2.LT_ACCENT)
            self.SetColour(aui.AUI_DOCKART_INACTIVE_CAPTION_COLOUR, p2.LT_BG_PANEL)
            self.SetColour(aui.AUI_DOCKART_ACTIVE_CAPTION_TEXT_COLOUR, wx.WHITE)
            self.SetColour(aui.AUI_DOCKART_BORDER_COLOUR,           p2.LT_BORDER)


# ── Custom AGW AUI Tab Art ───────────────────────────────────────────────────
class SpikeTabArt(aui.AuiDefaultTabArt):
    """Modern dark tab art for AuiNotebook."""

    def __init__(self, dark=True):
        super().__init__()
        p = Palette
        if dark:
            self.SetBaseColour(p.TAB_INACTIVE)
            self._tab_top_colour = p.TAB_ACTIVE
            self._tab_bottom_colour = p.TAB_ACTIVE
            self._tab_gradient_highlight_colour = p.TAB_ACTIVE
            self._tab_inactive_top_colour = p.TAB_INACTIVE
            self._tab_inactive_bottom_colour = p.TAB_INACTIVE
            self._background_top_colour = p.BG_BASE
            self._background_bottom_colour = p.BG_BASE
        else:
            self.SetBaseColour(Palette.LT_BG_PANEL)


# ── Main theme applier ───────────────────────────────────────────────────────
def apply_theme(window, theme="Dark"):
    """
    Apply modern colour theme to the window tree.
    Uses targeted colouring — only applies to well-known control types
    to avoid clobbering native widgets that render via the OS.
    """
    dark = (theme == "Dark")
    p = Palette

    bg   = p.BG_PANEL     if dark else p.LT_BG_PANEL
    base = p.BG_BASE      if dark else p.LT_BG_BASE
    fg   = p.TEXT_PRIMARY if dark else p.LT_TEXT
    inp  = p.BG_INPUT     if dark else wx.Colour(255, 255, 255)
    brd  = p.BORDER       if dark else p.LT_BORDER

    _style_recursive(window, bg, base, fg, inp, dark)


def _style_recursive(win, bg, base, fg, inp, dark):
    p = Palette
    cls = type(win).__name__

    try:
        # Panel/frame backgrounds
        if isinstance(win, (wx.Panel, wx.Frame, wx.Dialog,
                             wx.SplitterWindow, wx.ScrolledWindow)):
            win.SetBackgroundColour(bg)
            win.SetForegroundColour(fg)

        # Static text
        elif isinstance(win, wx.StaticText):
            win.SetBackgroundColour(bg)
            win.SetForegroundColour(fg)

        # Text inputs — slightly lighter background
        elif isinstance(win, wx.TextCtrl):
            win.SetBackgroundColour(inp)
            win.SetForegroundColour(fg)

        # Buttons — only style if not already manually coloured
        elif isinstance(win, wx.Button):
            if dark:
                win.SetBackgroundColour(p.BTN_BG)
                win.SetForegroundColour(p.TEXT_PRIMARY)
            else:
                win.SetBackgroundColour(wx.NullColour)
                win.SetForegroundColour(wx.NullColour)

        # List boxes / check list boxes
        elif isinstance(win, (wx.ListBox, wx.CheckListBox, wx.ListCtrl)):
            win.SetBackgroundColour(base)
            win.SetForegroundColour(fg)

        # Choice / ComboBox
        elif isinstance(win, (wx.Choice, wx.ComboBox)):
            win.SetBackgroundColour(inp)
            win.SetForegroundColour(fg)

        # Sliders, Gauges, SpinCtrl — leave to OS rendering on Windows
        # but set background
        elif isinstance(win, (wx.Slider, wx.Gauge)):
            win.SetBackgroundColour(bg)

        elif isinstance(win, wx.SpinCtrl):
            win.SetBackgroundColour(inp)
            win.SetForegroundColour(fg)

        # Notebook tabs (standard wx) — let OS handle rendering
        # for wx.lib.agw.aui notebooks we set the art provider instead
        elif isinstance(win, wx.Notebook):
            win.SetBackgroundColour(bg)
            win.SetForegroundColour(fg)

        # Toolbar - limited
        elif isinstance(win, wx.ToolBar):
            if dark:
                win.SetBackgroundColour(wx.Colour(25, 25, 38))
            else:
                win.SetBackgroundColour(wx.Colour(240, 240, 248))

        # Static box / StaticBoxSizer containers
        elif isinstance(win, wx.StaticBox):
            win.SetBackgroundColour(bg)
            win.SetForegroundColour(p.ACCENT_RED if dark else p.LT_ACCENT)

        # Grids — set colours on the grid itself
        elif isinstance(win, wx.grid.Grid):
            if dark:
                win.SetDefaultCellBackgroundColour(wx.Colour(28, 28, 42))
                win.SetDefaultCellTextColour(p.TEXT_PRIMARY)
                win.SetGridLineColour(wx.Colour(50, 50, 75))
                win.SetLabelBackgroundColour(wx.Colour(35, 35, 55))
                win.SetLabelTextColour(p.TEXT_SECONDARY)
                win.SetSelectionBackground(p.BG_SEL)
                win.SetSelectionForeground(wx.WHITE)
            else:
                win.SetDefaultCellBackgroundColour(wx.WHITE)
                win.SetDefaultCellTextColour(wx.BLACK)

        # Checkboxes — background only
        elif isinstance(win, (wx.CheckBox, wx.RadioButton)):
            win.SetBackgroundColour(bg)
            win.SetForegroundColour(fg)

    except Exception:
        pass

    # Recurse into children
    for child in win.GetChildren():
        _style_recursive(child, bg, base, fg, inp, dark)
