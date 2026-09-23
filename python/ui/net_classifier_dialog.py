"""
SPIKE Net Classifier Dialog
Scans board nets and auto-classifies them; user can override per-net.
"""
import wx
import wx.grid
import re


# Classification rules — (pattern, class_name, color_hex)
_RULES = [
    (re.compile(r"^(VCC|VDD|VBUS|VMAIN|3V3|3\.3V|5V|12V|24V|1V[0-9]|2V[0-9]|V_[A-Z]+)", re.I), "Power",          "#E94560"),
    (re.compile(r"^(GND|AGND|PGND|DGND|EARTH|VSS)",                                          re.I), "Ground",         "#20A020"),
    (re.compile(r"(CLK|OSC|XTAL|SCK|SCLK)",                                                   re.I), "Clock",          "#FFD700"),
    (re.compile(r"(USB|PCIE|HDMI|DDR|MIPI|LVDS|SERDES)",                                      re.I), "High-Speed Bus",  "#00BFFF"),
    (re.compile(r"(_[PN]$|_P$|_N$|DIFF_)",                                                    re.I), "Diff Pair",      "#FF8C00"),
    (re.compile(r"(SDA|SCL|TX|RX|MOSI|MISO|CS|INT|IRQ)",                                     re.I), "Low-Speed Bus",  "#9370DB"),
    (re.compile(r"(RST|RESET|EN|ENABLE|BOOT|PWRKEY)",                                         re.I), "Control",        "#20B2AA"),
]

_DEFAULT_CLASS = "Generic Signal"
_DEFAULT_COLOR = "#888888"

CLASS_NAMES = ["Power", "Ground", "Clock", "High-Speed Bus", "Diff Pair",
               "Low-Speed Bus", "Control", "Generic Signal", "Ignored"]


def classify_net(net_name: str) -> str:
    for pattern, cls, _ in _RULES:
        if pattern.search(net_name):
            return cls
    return _DEFAULT_CLASS


def classify_all(net_names: list) -> dict:
    return {n: classify_net(n) for n in net_names}


class NetClassifierDialog(wx.Dialog):
    """
    Shows all nets with their auto-detected classification.
    User can override per net via a drop-down.
    Returns a dict {net_name: class_str} on ID_OK.
    """

    def __init__(self, parent, net_names: list, existing: dict = None):
        super().__init__(parent,
                         title="Net Classification Wizard",
                         size=(800, 580),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.net_names = sorted(net_names)
        self.initial   = existing or {}
        self._data     = {}   # {net_name: class_str}
        self._build_ui()
        self._populate()
        self.CentreOnParent()

    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = wx.BoxSizer(wx.VERTICAL)

        # Header
        hdr = wx.Panel(self)
        hdr.SetBackgroundColour(wx.Colour(15, 52, 96))
        hdr_sz = wx.BoxSizer(wx.HORIZONTAL)
        t = wx.StaticText(hdr, label="  🏷  Net Classification Wizard")
        t.SetForegroundColour(wx.WHITE)
        t.SetFont(wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        hdr_sz.Add(t, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        hdr_sz.AddStretchSpacer()
        note = wx.StaticText(hdr, label="Auto-detect assigns classes from net names. Override any row.  ")
        note.SetForegroundColour(wx.Colour(180, 200, 255))
        hdr_sz.Add(note, 0, wx.ALIGN_CENTER_VERTICAL)
        hdr.SetSizer(hdr_sz)
        outer.Add(hdr, 0, wx.EXPAND)

        # Filter bar
        filt_sz = wx.BoxSizer(wx.HORIZONTAL)
        self.txt_filter = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.txt_filter.SetHint("Filter nets…")
        self.txt_filter.Bind(wx.EVT_TEXT, self._on_filter)
        filt_sz.Add(wx.StaticText(self, label="Filter:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        filt_sz.Add(self.txt_filter, 1, wx.EXPAND | wx.RIGHT, 10)

        self.cb_filter_class = wx.Choice(self, choices=["All Classes"] + CLASS_NAMES)
        self.cb_filter_class.SetSelection(0)
        self.cb_filter_class.Bind(wx.EVT_CHOICE, self._on_filter)
        filt_sz.Add(wx.StaticText(self, label="Class:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        filt_sz.Add(self.cb_filter_class, 0, wx.ALIGN_CENTER_VERTICAL)

        outer.Add(filt_sz, 0, wx.EXPAND | wx.ALL, 8)

        # Grid
        self.grid = wx.grid.Grid(self)
        self.grid.CreateGrid(0, 3)
        self.grid.SetColLabelValue(0, "Net Name")
        self.grid.SetColLabelValue(1, "Auto-Detected")
        self.grid.SetColLabelValue(2, "Override Class")
        self.grid.SetColSize(0, 220)
        self.grid.SetColSize(1, 160)
        self.grid.SetColSize(2, 180)
        self.grid.SetRowLabelSize(40)
        outer.Add(self.grid, 1, wx.EXPAND | wx.ALL, 8)

        # Stats
        self.lbl_stats = wx.StaticText(self, label="")
        outer.Add(self.lbl_stats, 0, wx.LEFT | wx.BOTTOM, 12)

        # Buttons
        btn_sz = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_auto_all = wx.Button(self, label="♻ Re-run Auto-Detect")
        self.btn_reset    = wx.Button(self, label="↩ Reset Overrides")
        ok  = wx.Button(self, wx.ID_OK,     "✔  Accept")
        can = wx.Button(self, wx.ID_CANCEL, "✖  Cancel")
        ok.SetDefault()
        btn_sz.Add(self.btn_auto_all, 0, wx.RIGHT, 6)
        btn_sz.Add(self.btn_reset, 0, wx.RIGHT, 6)
        btn_sz.AddStretchSpacer()
        btn_sz.Add(ok, 0, wx.RIGHT, 6)
        btn_sz.Add(can, 0, wx.RIGHT, 8)
        outer.Add(btn_sz, 0, wx.EXPAND | wx.BOTTOM, 10)

        self.SetSizer(outer)
        ok.Bind(wx.EVT_BUTTON, self._on_ok)
        can.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL))
        self.btn_auto_all.Bind(wx.EVT_BUTTON, self._on_auto_all)
        self.btn_reset.Bind(wx.EVT_BUTTON,    self._on_reset)
        self.grid.Bind(wx.grid.EVT_GRID_CELL_CHANGED, self._on_cell_change)

    # ------------------------------------------------------------------
    def _populate(self, filter_text="", filter_class="All Classes"):
        # Save existing edits first
        self._sync_grid_to_data()

        # Rebuild
        if self.grid.GetNumberRows() > 0:
            self.grid.DeleteRows(0, self.grid.GetNumberRows())

        for net in self.net_names:
            auto_cls = classify_net(net)
            cur_cls  = self._data.get(net) or self.initial.get(net) or auto_cls

            # Apply filters
            if filter_text and filter_text.lower() not in net.lower():
                continue
            if filter_class != "All Classes" and cur_cls != filter_class:
                continue

            row = self.grid.GetNumberRows()
            self.grid.AppendRows(1)
            self.grid.SetCellValue(row, 0, net)
            self.grid.SetReadOnly(row, 0)
            self.grid.SetCellValue(row, 1, auto_cls)
            self.grid.SetReadOnly(row, 1)

            # Choice editor for col 2
            editor = wx.grid.GridCellChoiceEditor(CLASS_NAMES, allowOthers=False)
            self.grid.SetCellEditor(row, 2, editor)
            self.grid.SetCellValue(row, 2, cur_cls)

            # Color coding
            color = self._cls_color(auto_cls)
            for col in range(3):
                self.grid.SetCellBackgroundColour(row, col, wx.Colour(30, 30, 45))
                self.grid.SetCellTextColour(row, 1, color)

        self._update_stats()

    def _on_filter(self, event):
        self._populate(self.txt_filter.GetValue(),
                       self.cb_filter_class.GetString(self.cb_filter_class.GetSelection()))

    def _on_cell_change(self, event):
        row = event.GetRow()
        net = self.grid.GetCellValue(row, 0)
        cls = self.grid.GetCellValue(row, 2)
        self._data[net] = cls
        self._update_stats()

    def _sync_grid_to_data(self):
        for r in range(self.grid.GetNumberRows()):
            net = self.grid.GetCellValue(r, 0)
            cls = self.grid.GetCellValue(r, 2)
            if net:
                self._data[net] = cls

    def _on_auto_all(self, event):
        self._data = classify_all(self.net_names)
        self._populate(self.txt_filter.GetValue(),
                       self.cb_filter_class.GetString(self.cb_filter_class.GetSelection()))

    def _on_reset(self, event):
        self._data = {}
        self._populate()

    def _on_ok(self, event):
        self._sync_grid_to_data()
        # Fill in any nets not shown due to filtering
        for net in self.net_names:
            if net not in self._data:
                self._data[net] = self.initial.get(net) or classify_net(net)
        self.EndModal(wx.ID_OK)

    def _update_stats(self):
        if not self._data:
            for net in self.net_names:
                self._data[net] = classify_net(net)
        counts = {}
        for cls in self._data.values():
            counts[cls] = counts.get(cls, 0) + 1
        parts = [f"{cls}: {n}" for cls, n in sorted(counts.items())]
        self.lbl_stats.SetLabel("  ".join(parts))

    @staticmethod
    def _cls_color(cls):
        for _, name, hex_col in _RULES:
            pass
        mapping = {r[1]: r[2] for r in _RULES}
        hex_col = mapping.get(cls, _DEFAULT_COLOR)
        r, g, b = int(hex_col[1:3], 16), int(hex_col[3:5], 16), int(hex_col[5:7], 16)
        return wx.Colour(r, g, b)

    def get_classifications(self) -> dict:
        """Return {net_name: class_str} after dialog accepted."""
        return dict(self._data)
