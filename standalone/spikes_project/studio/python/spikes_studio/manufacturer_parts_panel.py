# SPDX-License-Identifier: Apache-2.0
"""wxPython browser for the focused exact-MPN manufacturer catalog."""
from __future__ import annotations

import webbrowser
import uuid
import wx

from .manufacturer_parts import (
    install, is_placeable, load_catalog, query, source_pins,
    store_vendor_model,
)
from .flat_controls import ActionButton
from .themes import apply_window


_READINESS_LABELS = {
    "placeable_ideal_nominal": "Ideal R/C available",
    "vendor_model_required": "Vendor model required",
}


def _friendly(value):
    text = str(value).replace("_", " ").strip().title()
    for source, replacement in (("Mosfet", "MOSFET"), ("Ntc", "NTC"), ("Ptc", "PTC"), ("Led", "LED")):
        text = text.replace(source, replacement)
    return text


class ManufacturerResultsList(wx.ListCtrl):
    """Sortable virtual report while retaining the old ListBox selection API."""
    COLUMNS = (
        ("Manufacturer", "manufacturer", 125),
        ("MPN", "mpn", 175),
        ("Category", "category", 165),
        ("Nominal", "nominal", 105),
        ("Model readiness", "readiness", 165),
    )

    def __init__(self, parent):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL)
        self.rows = []
        self.sort_key = "manufacturer"
        self.sort_reverse = False
        for index, (label, _key, width) in enumerate(self.COLUMNS):
            self.InsertColumn(index, label, width=width)
        self.Bind(wx.EVT_LIST_COL_CLICK, self._sort)

    def OnGetItemText(self, item, column):
        if not 0 <= item < len(self.rows):
            return ""
        record = self.rows[item]
        values = (
            record["manufacturer"], record["mpn"], _friendly(record["category"]),
            record["nominal"]["label"],
            _READINESS_LABELS.get(record["model"]["readiness"], _friendly(record["model"]["readiness"])),
        )
        return values[column]

    def refresh_symbols(self,palette):
        from .symbol_icons import SymbolImages
        self.images=SymbolImages(None,palette);self.AssignImageList(self.images.image_list,wx.IMAGE_LIST_SMALL);self.Refresh()

    def OnGetItemImage(self,item):
        return self.images.index(self.rows[item]['category']) if hasattr(self,'images') and 0<=item<len(self.rows) else -1

    def OnGetItemColumnImage(self,item,column):return self.OnGetItemImage(item) if column==0 else -1

    def _value(self, record):
        if self.sort_key == "nominal":
            return record["nominal"]["label"].casefold()
        if self.sort_key == "readiness":
            return _READINESS_LABELS.get(record["model"]["readiness"], record["model"]["readiness"]).casefold()
        return str(record[self.sort_key]).casefold()

    def set_rows(self, rows, selected_id=None):
        self.rows = sorted(rows, key=self._value, reverse=self.sort_reverse)
        self.SetItemCount(len(self.rows))
        self.Refresh()
        self.SetSelection(next((i for i, row in enumerate(self.rows) if row["id"] == selected_id), -1))

    def _sort(self, event):
        key = self.COLUMNS[event.GetColumn()][1]
        self.sort_reverse = not self.sort_reverse if key == self.sort_key else False
        self.sort_key = key
        for index, (label, column_key, _width) in enumerate(self.COLUMNS):
            column = self.GetColumn(index)
            column.SetText(label + (' ▼' if self.sort_reverse else ' ▲') if column_key == key else label)
            self.SetColumn(index, column)
        selected = self.GetSelection()
        selected_id = self.rows[selected]["id"] if 0 <= selected < len(self.rows) else None
        self.set_rows(self.rows, selected_id)

    def GetSelection(self):
        return self.GetFirstSelected()

    def SetSelection(self, index):
        old = self.GetFirstSelected()
        if old >= 0:
            self.SetItemState(old, 0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
        if 0 <= index < len(self.rows):
            state = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
            self.SetItemState(index, state, state)
            self.EnsureVisible(index)


class _InsertDialog(wx.Dialog):
    def __init__(self, parent, record):
        super().__init__(parent, title="Add manufacturer component", size=(550, 410))
        box = wx.BoxSizer(wx.VERTICAL)
        note = wx.StaticText(
            self,
            label=(f"{record['manufacturer']} {record['mpn']}\n"
                   "This inserts an ideal nominal R/L/C recipe, not a vendor-precision model.\n"
                   "Ratings and tolerance remain metadata and are not enforced by the solver."),
        )
        note.Wrap(450); box.Add(note, 0, wx.ALL | wx.EXPAND, 12)
        book=wx.Notebook(self);box.Add(book,1,wx.EXPAND|wx.LEFT|wx.RIGHT,12)
        values=wx.Panel(book);layout=wx.BoxSizer(wx.VERTICAL);values.SetSizer(layout)
        nominal=record['nominal']
        layout.Add(wx.StaticText(values,label='Sourced nominal value: '+nominal['label']),0,wx.ALL,12)
        label=wx.StaticText(values,label='Manufacturer values and ratings remain source metadata. Use a generic component for arbitrary values, or edit a placed component explicitly. Model pin order stays fixed.');label.Wrap(480);layout.Add(label,0,wx.ALL,12)
        row=wx.BoxSizer(wx.HORIZONTAL);row.Add(wx.StaticText(values,label='Instances'),0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,8)
        self.count=wx.SpinCtrl(values,min=1,max=100,initial=1);row.Add(self.count,0,wx.ALL,8);layout.Add(row);book.AddPage(values,'Value & model',True)
        connections=wx.Panel(book);connection_box=wx.BoxSizer(wx.VERTICAL);connections.SetSizer(connection_box)
        self.nodes = {}
        prefix='part_'+uuid.uuid4().hex[:8]+'_{n}_'
        grid = wx.FlexGridSizer(cols=2, hgap=8, vgap=8); grid.AddGrowableCol(1)
        for pin in source_pins(record):
            grid.Add(wx.StaticText(connections, label=pin + " → net"), 0, wx.ALIGN_CENTER_VERTICAL)
            control = wx.TextCtrl(connections, value=prefix+pin.lower())
            self.nodes[pin] = control; grid.Add(control, 1, wx.EXPAND)
        connection_box.Add(grid,0,wx.ALL|wx.EXPAND,12)
        hint=wx.StaticText(connections,label='Optional net mapping; no automatic ground. {n} keeps each instance isolated. Names without {n} intentionally share a net.');hint.Wrap(480);connection_box.Add(hint,0,wx.ALL,12);book.AddPage(connections,'Pins & connections')
        box.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.ALIGN_RIGHT, 12)
        self.SetSizer(box)


class ManufacturerPartsPanel(wx.Panel):
    """Fast local search, exact-MPN preview, intake and fail-closed insertion."""
    def __init__(self, parent, owner):
        super().__init__(parent)
        self.owner = owner
        self.catalog = load_catalog()
        self.rows = []
        self.record = None
        outer = wx.BoxSizer(wx.VERTICAL)
        title = wx.StaticText(self, label="Manufacturer parts")
        font = title.GetFont(); font.SetPointSize(font.GetPointSize() + 3); font.SetWeight(wx.FONTWEIGHT_BOLD); title.SetFont(font)
        outer.Add(title, 0, wx.ALL, 8)
        subtitle = wx.StaticText(self, label="Search sourced exact MPNs and review what is safe to place.")
        outer.Add(subtitle, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        scope = wx.CollapsiblePane(self, label="Catalog scope and model qualification", style=wx.CP_DEFAULT_STYLE | wx.CP_NO_TLW_RESIZE)
        scope_note = wx.StaticText(scope.GetPane(), label=self.catalog["scope"] + "\n\n" + self.catalog["limitations"] +
                                   "\n\nCatalog inclusion is not official model qualification. Vendor models remain review-only until separately qualified.")
        scope_note.Wrap(900)
        scope_box = wx.BoxSizer(wx.VERTICAL); scope_box.Add(scope_note, 0, wx.ALL | wx.EXPAND, 8); scope.GetPane().SetSizer(scope_box)
        scope.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED, lambda event: self.Layout())
        outer.Add(scope, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)
        filters = wx.WrapSizer(wx.HORIZONTAL)
        self.search = wx.SearchCtrl(self); self.search.SetDescriptiveText("Search exact MPN, manufacturer, category or description")
        outer.Add(self.search, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)
        manufacturers = ["All manufacturers"] + sorted({r["manufacturer"] for r in self.catalog["records"]})
        categories = ["All categories"] + sorted({r["category"] for r in self.catalog["records"]})
        self.manufacturer = wx.Choice(self, choices=manufacturers); self.manufacturer.SetSelection(0)
        self.category = wx.Choice(self, choices=categories); self.category.SetSelection(0)
        self.readiness = wx.Choice(self, choices=["All readiness", "Placeable ideal R/C", "Vendor model required"]); self.readiness.SetSelection(0)
        filters.Add(self.manufacturer, 0, wx.RIGHT, 8); filters.Add(self.category, 0, wx.RIGHT, 8); filters.Add(self.readiness, 0)
        outer.Add(filters, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 8)
        split = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        left = wx.Panel(split); left_box = wx.BoxSizer(wx.VERTICAL)
        self.matches = wx.StaticText(left, label=""); left_box.Add(self.matches, 0, wx.ALL, 5)
        self.listing = ManufacturerResultsList(left); left_box.Add(self.listing, 1, wx.ALL | wx.EXPAND, 5); left.SetSizer(left_box)
        self.listing.refresh_symbols(owner.palette)
        right = wx.Panel(split); right_box = wx.BoxSizer(wx.VERTICAL)
        self.details_book = wx.Notebook(right)
        overview_page = wx.Panel(self.details_book); overview_box = wx.BoxSizer(wx.VERTICAL)
        self.detail = wx.TextCtrl(overview_page, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        overview_box.Add(self.detail, 1, wx.EXPAND); overview_page.SetSizer(overview_box)
        pins_page = wx.Panel(self.details_book); pins_box = wx.BoxSizer(wx.VERTICAL)
        self.pins_detail = wx.TextCtrl(pins_page, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        pins_box.Add(self.pins_detail, 1, wx.EXPAND); pins_page.SetSizer(pins_box)
        evidence_page = wx.Panel(self.details_book); evidence_box = wx.BoxSizer(wx.VERTICAL)
        self.evidence_detail = wx.TextCtrl(evidence_page, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        evidence_box.Add(self.evidence_detail, 1, wx.EXPAND); evidence_page.SetSizer(evidence_box)
        self.details_book.AddPage(overview_page, "Overview", True)
        self.details_book.AddPage(pins_page, "Pins")
        self.details_book.AddPage(evidence_page, "Evidence")
        right_box.Add(self.details_book, 1, wx.ALL | wx.EXPAND, 5)
        actions = wx.WrapSizer(wx.HORIZONTAL)
        self.insert_button = ActionButton(right, label="Insert ideal R/C approximation...")
        self.source_button = ActionButton(right, label="Open official source")
        self.model_button = ActionButton(right, label="Review user-supplied vendor SPICE...")
        for button in (self.insert_button, self.source_button, self.model_button): actions.Add(button, 0, wx.ALL, 4)
        right_box.Add(actions, 0, wx.EXPAND); right.SetSizer(right_box)
        split.SplitVertically(left, right, 650); split.SetSashGravity(0.6); split.SetMinimumPaneSize(240); outer.Add(split, 1, wx.EXPAND)
        self.SetSizer(outer)
        self.search.Bind(wx.EVT_TEXT, self.refresh)
        self.manufacturer.Bind(wx.EVT_CHOICE, self.refresh); self.category.Bind(wx.EVT_CHOICE, self.refresh); self.readiness.Bind(wx.EVT_CHOICE, self.refresh)
        self.listing.Bind(wx.EVT_LIST_ITEM_SELECTED, self.select); self.listing.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.insert_selected)
        self.listing.Bind(wx.EVT_CONTEXT_MENU,self.context)
        self.insert_button.Bind(wx.EVT_BUTTON, self.insert_selected); self.source_button.Bind(wx.EVT_BUTTON, self.open_source)
        self.model_button.Bind(wx.EVT_BUTTON, self.review_model)
        self.refresh(); apply_window(self, owner.palette)

    def _guarded(self, fn):
        guarded = getattr(self.owner, "guarded", None)
        if guarded: return guarded(fn)
        try: return fn()
        except (ValueError, OSError) as exc: wx.MessageBox(str(exc), "Manufacturer parts", wx.OK | wx.ICON_ERROR, self)

    def refresh(self, event=None):
        manufacturer = None if self.manufacturer.GetSelection() == 0 else self.manufacturer.GetStringSelection()
        category = None if self.category.GetSelection() == 0 else self.category.GetStringSelection()
        readiness = {1: "placeable_ideal_nominal", 2: "vendor_model_required"}.get(self.readiness.GetSelection())
        selected_id = self.record["id"] if self.record else None
        queried = query(self.catalog["records"], self.search.GetValue(), manufacturer=manufacturer, category=category, readiness=readiness)
        self.listing.set_rows(queried, selected_id)
        self.rows = self.listing.rows
        self.matches.SetLabel(f"{len(self.rows)} exact-MPN record(s)")
        selected = self.listing.GetSelection()
        if selected >= 0:
            self.select()
        else:
            self.record = None; self.detail.SetValue("Select a part to review its sourced identity, nominal value, and model status.")
            self.pins_detail.SetValue("Pin order appears here after selection.")
            self.evidence_detail.SetValue("Official source provenance and qualification limits appear here after selection.")
            self.insert_button.Disable(); self.source_button.Disable(); self.model_button.Disable()

    def select(self, event=None):
        self.rows = self.listing.rows
        index = self.listing.GetSelection()
        if not 0 <= index < len(self.rows): return
        self.record = self.rows[index]
        record = self.record
        ratings = "\n".join(f"{item['name']}: {item['value']} {item['unit']}" for item in record["ratings"]) or "No selected ratings"
        self.detail.SetValue(
            f"{record['manufacturer']} {record['mpn']}\n\n{record['description']}\n\n"
            f"Category: {_friendly(record['category'])}\nPackage: {record['package']}\n"
            f"Nominal: {record['nominal']['label']}\nTolerance: {record['tolerance']['display']}\n\n"
            f"Model readiness: {_READINESS_LABELS.get(record['model']['readiness'], _friendly(record['model']['readiness']))}\n"
            f"Model kind: {_friendly(record['model']['kind'])}\n\nSelected ratings\n{ratings}"
        )
        self.pins_detail.SetValue("\n".join(
            f"Pin {pin['number']}  ·  {pin['name']}  ·  {_friendly(pin['role'])}" for pin in record["pins"]
        ))
        self.evidence_detail.SetValue(
            f"Official source\n{record['source']['url']}\n\nAccessed: {record['source']['accessed_on']}\n\n"
            f"Model limitations\n{record['model']['limitations']}\n\n"
            "Catalog inclusion is not model qualification. Ratings are sourced metadata, not enforced solver limits. "
            "User-supplied vendor models remain review-only; parser compatibility, execution, redistribution, and fitted drafts are not qualified."
        )
        self.insert_button.Enable(is_placeable(self.record)); self.source_button.Enable(); self.model_button.Enable()

    def context(self,event):
        from .context_menus import ContextMenu
        position=event.GetPosition()
        if position!=wx.DefaultPosition:
            index=self.listing.HitTest(self.listing.ScreenToClient(position))[0]
            self.listing.SetSelection(index)
            if index>=0:self.select()
            else:
                self.record=None
                for button in (self.insert_button,self.source_button,self.model_button):button.Disable()
                for control in (self.detail,self.pins_detail,self.evidence_detail):control.SetValue('Select an exact manufacturer part.')
        menu=ContextMenu(self.owner);selected=self.record is not None
        menu.add('Insert ideal nominal R/C…',self._insert,selected and is_placeable(self.record) and not self.owner.job_running,'Requires an insertable ideal R/C recipe and idle simulation')
        menu.add('Review user-supplied vendor SPICE…',self._review_model,selected,'Select an exact manufacturer part')
        menu.separator()
        menu.add('Show pinout',lambda:self.details_book.SetSelection(1),selected)
        menu.add('Show provenance / qualification',lambda:self.details_book.SetSelection(2),selected)
        menu.add('Open official source',self.open_source,selected)
        def copy():
            if self.record and wx.TheClipboard.Open():
                try:wx.TheClipboard.SetData(wx.TextDataObject(self.record['mpn']))
                finally:wx.TheClipboard.Close()
        menu.add('Copy exact part number',copy,selected)
        menu.popup(self.listing)

    def insert_selected(self, event=None):
        self._guarded(self._insert)

    def _insert(self):
        if not self.record: raise ValueError("Select an exact manufacturer part")
        if not is_placeable(self.record):
            source_pins(self.record)  # raises the precise acquisition/qualification guidance
        if self.owner.job_running: raise ValueError("Stop simulation before inserting a model")
        if self.owner.source.GetText() != self.owner.doc.data["source"]:
            raise ValueError("Apply circuit text edits before inserting; the draft has been retained")
        with _InsertDialog(self, self.record) as dialog:
            if dialog.ShowModal() != wx.ID_OK: return
            mapping = {pin: control.GetValue() for pin, control in dialog.nodes.items()}
            count = dialog.count.GetValue()
            y = 180 + 160 * ((len(self.owner.doc.data["components"]) + 3) // 4)
            plan = install(self.owner.doc, self.record, mapping, count=count, x=140, y=y, primitive=True)
        self.owner.refresh_document(); self.owner.book.SetSelection(0)
        self.owner.SetStatusText(f"Inserted {count} ideal nominal instance(s): {', '.join(plan['refs'][:8])}; exact MPN metadata is sourced, model is unqualified")

    def open_source(self, event=None):
        if self.record: webbrowser.open(self.record["source"]["url"], new=2)

    def review_model(self, event=None):
        self._guarded(self._review_model)

    def _review_model(self):
        if not self.record: raise ValueError("Select an exact manufacturer part")
        with wx.FileDialog(self, "Select a user-obtained vendor SPICE model", wildcard="SPICE model|*.lib;*.cir;*.mod;*.sp;*.txt", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() != wx.ID_OK: return
            path = dialog.GetPath()
        with wx.TextEntryDialog(self, "Paste the license or usage terms supplied with this file. The source text and SHA-256 are retained project-locally; execution is not approved.", "Vendor model license/terms") as license_dialog:
            if license_dialog.ShowModal() != wx.ID_OK: return
            license_text = license_dialog.GetValue()
        with wx.TextEntryDialog(self, "Enter the exact HTTPS page or download URL from which you obtained this model.", "Vendor model source", self.record["source"]["url"]) as source_dialog:
            if source_dialog.ShowModal() != wx.ID_OK: return
            source_url = source_dialog.GetValue()
        key = store_vendor_model(self.owner.doc, path, self.record, license_text, source_url)
        self.owner.update_title()
        self.owner.SetStatusText(f"Stored review-only vendor model SHA-256 {key[:12]}...; parser compatibility and fitted drafts are not qualification")


class ManufacturerPartsDialog(wx.Dialog):
    """Ready-to-wire resizable host for the catalog panel."""
    def __init__(self, parent, owner):
        super().__init__(parent, title="Manufacturer parts - exact MPN seed", size=(1060, 720),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        box = wx.BoxSizer(wx.VERTICAL)
        self.panel = ManufacturerPartsPanel(self, owner)
        box.Add(self.panel, 1, wx.EXPAND)
        box.Add(self.CreateButtonSizer(wx.CLOSE), 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizer(box)
        apply_window(self, owner.palette)
