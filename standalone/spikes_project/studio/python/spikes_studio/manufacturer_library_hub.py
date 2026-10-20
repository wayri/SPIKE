# SPDX-License-Identifier: Apache-2.0
"""Dedicated manufacturer library, separate from generic parameter presets."""
import queue
import json
from pathlib import Path
import threading
import webbrowser
import wx

from .flat_controls import ActionButton
from .manufacturer_discovery import load_catalog, search
from .manufacturer_executable import (
    availability as executable_availability,
    executable_record,
    format_record as format_executable_record,
    install as install_executable,
    load_catalog as load_executable_catalog,
)
from .manufacturer_executable_dialog import ExecutablePlacementDialog
from .manufacturer_parts_panel import ManufacturerPartsPanel
from .themes import apply_window


class ProductList(wx.ListCtrl):
    columns = (('Manufacturer', 'manufacturer', 160), ('Part number', 'part_number', 190),
               ('Category', 'category', 160), ('Description', 'description', 330))

    def __init__(self, parent, palette):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL)
        self.rows = []; self.key = 'manufacturer'; self.reverse = False
        for index, (label, _, width) in enumerate(self.columns):
            self.InsertColumn(index, label, width=width)
        self.refresh_symbols(palette)
        self.Bind(wx.EVT_LIST_COL_CLICK, self.sort)

    def refresh_symbols(self, palette):
        from .symbol_icons import SymbolImages
        self.images = SymbolImages(None, palette)
        self.AssignImageList(self.images.image_list, wx.IMAGE_LIST_SMALL)
        self.Refresh()

    def OnGetItemText(self, row, column):
        return self.rows[row][self.columns[column][1]].replace('_', ' ') if 0 <= row < len(self.rows) else ''

    def OnGetItemImage(self, row):
        return self.images.index(self.rows[row]['category']) if 0 <= row < len(self.rows) else -1

    def OnGetItemColumnImage(self, row, column):
        return self.OnGetItemImage(row) if column == 0 else -1

    def set_rows(self, rows):
        selected = self.GetFirstSelected()
        identity = self.rows[selected]['id'] if 0 <= selected < len(self.rows) else None
        self.rows = sorted(rows, key=lambda row: row[self.key].casefold(), reverse=self.reverse)
        self.SetItemCount(len(self.rows)); self.Refresh()
        for index, row in enumerate(self.rows):
            self.SetItemState(index, wx.LIST_STATE_SELECTED if row['id'] == identity else 0,
                              wx.LIST_STATE_SELECTED)

    def sort(self, event):
        key = self.columns[event.GetColumn()][1]
        self.reverse = not self.reverse if self.key == key else False
        self.key = key; self.set_rows(self.rows)


class ProductCatalog(wx.Panel):
    def __init__(self, parent, owner):
        super().__init__(parent); self.owner = owner; self.catalog = load_catalog(); self.local_models = []
        self.executable_ids = {row['discovery_id'] for row in load_executable_catalog()['records']}
        box = wx.BoxSizer(wx.VERTICAL)
        self.search = wx.SearchCtrl(self)
        self.search.SetDescriptiveText('Find real manufacturer, part number or function…')
        box.Add(self.search, 0, wx.EXPAND | wx.ALL, 8)
        filters = wx.WrapSizer(wx.HORIZONTAL)
        rows = self.catalog['records']
        self.manufacturer = wx.Choice(self, choices=['All manufacturers'] + sorted({r['manufacturer'] for r in rows}))
        self.category = wx.Choice(self, choices=['All categories'] + sorted({r['category'] for r in rows}))
        self.execution = wx.Choice(self, choices=['All executable states', 'Executable approximation available', 'Identity only'])
        for control in (self.manufacturer, self.category, self.execution):
            control.SetSelection(0); filters.Add(control, 0, wx.RIGHT, 8)
            control.Bind(wx.EVT_CHOICE, self.refresh)
        box.Add(filters, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.count = wx.StaticText(self); box.Add(self.count, 0, wx.LEFT | wx.BOTTOM, 8)
        self.listing = ProductList(self, owner.palette); box.Add(self.listing, 1, wx.EXPAND | wx.ALL, 8)
        self.detail = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 155))
        box.Add(self.detail, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        actions = wx.WrapSizer(wx.HORIZONTAL)
        self.product_button = ActionButton(self, label='Product / datasheet')
        self.model_button = ActionButton(self, label='Manufacturer model source')
        self.review_button = ActionButton(self, label='Review a downloaded model…')
        self.local_button = ActionButton(self, label='Find installed local model')
        self.executable_button = ActionButton(self, label='Place executable approximation…')
        for control in (self.product_button, self.model_button, self.local_button, self.review_button,
                        self.executable_button):
            actions.Add(control, 0, wx.ALL, 4)
        box.Add(actions, 0, wx.ALL, 4); self.SetSizer(box)
        self.search.Bind(wx.EVT_TEXT, self.refresh)
        self.listing.Bind(wx.EVT_LIST_ITEM_SELECTED, self.select)
        self.product_button.Bind(wx.EVT_BUTTON, lambda event: self.open_link('product_url'))
        self.model_button.Bind(wx.EVT_BUTTON, lambda event: self.open_link('model_url'))
        self.local_button.Bind(wx.EVT_BUTTON, lambda event: owner.manufacturer_hub.show_local_for(self.selected()))
        self.review_button.Bind(wx.EVT_BUTTON, lambda event: owner.guarded(owner.catalog_panel.vendor))
        self.executable_button.Bind(wx.EVT_BUTTON, self.place_executable)
        self.refresh()

    def selected(self):
        index = self.listing.GetFirstSelected()
        return self.listing.rows[index] if 0 <= index < len(self.listing.rows) else None

    def executable_state(self, row):
        if row is None or row['id'] not in self.executable_ids:
            return {
                'executable': False,
                'qualified': False,
                'reason': 'No reviewed SPIKE executable approximation is bundled for this identity.',
            }
        return executable_availability(row['id'])

    def refresh(self, event=None):
        manufacturer = self.manufacturer.GetStringSelection() if self.manufacturer.GetSelection() else None
        category = self.category.GetStringSelection() if self.category.GetSelection() else None
        rows = search(self.catalog['records'], self.search.GetValue(), manufacturer, category)
        execution = self.execution.GetSelection()
        if execution:
            want_executable = execution == 1
            rows = [row for row in rows if (row['id'] in self.executable_ids) == want_executable]
        self.listing.set_rows(rows)
        executable_count = sum(row['id'] in self.executable_ids for row in rows)
        self.count.SetLabel(f'{len(rows):,} sourced products · {executable_count} native approximation(s) · none manufacturer-qualified')
        self.select()

    def select(self, event=None):
        row = self.selected()
        self.product_button.Enable(row is not None)
        self.model_button.Enable(bool(row and row.get('model_url')))
        state = self.executable_state(row)
        self.executable_button.Enable(bool(state and state['executable']))
        matches = [item for item in self.local_models if row and item['name'].casefold() == row['part_number'].casefold()]
        self.local_button.Enable(bool(matches))
        if not row:
            self.detail.SetValue('Select a real product to see its source and model availability.\n'
                                 'Use Placeable parts for installed electrical records, or Local LTspice to index your own library.\n'
                                 'No arbitrary generic preset is renamed as a manufacturer device.')
            return
        self.detail.SetValue(f"{row['manufacturer']} · {row['part_number']}\n{row['description']}\n\n"
                             f"Source checked: {row['checked_on']}\n{row['product_url']}\n"
                             f"Model: {row.get('model_url') or 'Not reviewed / no model link recorded'}\n"
                             f"Exact-name declarations in your indexed local library: {len(matches)} (not qualified)\n"
                             f"\nExecutable approximation\n{format_executable_record(row['id']) if state['executable'] else state['reason']}\n\n"
                             'Catalog identity and executable approximation are separate tiers. Qualified remains false; ratings are not enforced solver limits.')

    def place_executable(self, event=None):
        guarded = getattr(self.owner, 'guarded', None)
        return guarded(self._place_executable) if guarded else self._place_executable()

    def _place_executable(self):
        row = self.selected()
        if row is None: raise ValueError('Select an exact manufacturer product')
        state = self.executable_state(row)
        if not state['executable']: raise ValueError(state['reason'])
        if self.owner.job_running: raise ValueError('Stop simulation before placing an executable approximation')
        if hasattr(self.owner, 'require_clean_directive_source'):
            self.owner.require_clean_directive_source()
        elif hasattr(self.owner, 'source') and self.owner.source.GetText() != self.owner.doc.data['source']:
            raise ValueError('Apply circuit text edits before placing an executable approximation')
        record = executable_record(row['id'])
        with ExecutablePlacementDialog(self, self.owner, record) as dialog:
            if dialog.ShowModal() != wx.ID_OK: return None
            count = dialog.count.GetValue()
            mapping = dialog.mapping()
            y = 180 + 160 * ((len(self.owner.doc.data['components']) + 3) // 4)
            plan = install_executable(self.owner.doc, record, mapping, count=count, x=140, y=y)
        self.owner.refresh_document()
        if hasattr(self.owner, 'book') and hasattr(self.owner, 'editor_page'):
            self.owner.book.SetSelection(self.owner.editor_page())
        self.owner.SetStatusText(
            f"Inserted {count} expanded native approximation(s): {', '.join(plan['refs'][:8])}; "
            "full package mapping is retained in source, qualified=false"
        )
        return plan

    def open_link(self, key):
        row = self.selected()
        if row and row.get(key): webbrowser.open(row[key], new=2)


class LocalLibrary(wx.Panel):
    """Bounded background inventory; never loads executable model implementations."""
    def __init__(self, parent, owner):
        super().__init__(parent); self.owner = owner; self.index = None; self.messages = queue.Queue(); self.busy = False
        box = wx.BoxSizer(wx.VERTICAL); bar = wx.WrapSizer(wx.HORIZONTAL)
        self.scan_button = ActionButton(self, label='Index local LTspice library…')
        self.save_button = ActionButton(self, label='Export metadata index…')
        self.open_button = ActionButton(self, label='Open metadata index…')
        self.review_button = ActionButton(self, label='Review original source…')
        self.place_button = ActionButton(self, label='Place intrinsic model…')
        self.diagnostics_button = ActionButton(self, label='Scan diagnostics…')
        bar.Add(self.scan_button, 0, wx.ALL, 4); bar.Add(self.save_button, 0, wx.ALL, 4)
        bar.Add(self.open_button, 0, wx.ALL, 4)
        bar.Add(self.review_button, 0, wx.ALL, 4); bar.Add(self.place_button, 0, wx.ALL, 4)
        bar.Add(self.diagnostics_button, 0, wx.ALL, 4)
        box.Add(bar, 0, wx.ALL, 4)
        self.search = wx.SearchCtrl(self); self.search.SetDescriptiveText('Search model name or original library path…')
        box.Add(self.search, 0, wx.EXPAND | wx.ALL, 8)
        self.status = wx.StaticText(self, label='Choose a local library folder. Models stay on your PC; nothing is executed or redistributed.')
        self.status.Wrap(850); box.Add(self.status, 0, wx.EXPAND | wx.ALL, 8)
        self.listing = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for i, (label, width) in enumerate((('Model', 230), ('Type', 110), ('Original file', 490))):
            self.listing.InsertColumn(i, label, width=width)
        box.Add(self.listing, 1, wx.EXPAND | wx.ALL, 8)
        self.detail = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 150))
        box.Add(self.detail, 0, wx.EXPAND | wx.ALL, 8); self.SetSizer(box)
        self.scan_button.Bind(wx.EVT_BUTTON, self.choose)
        self.save_button.Bind(wx.EVT_BUTTON, lambda event: owner.guarded(self.save))
        self.open_button.Bind(wx.EVT_BUTTON, lambda event: owner.guarded(self.open))
        self.review_button.Bind(wx.EVT_BUTTON, lambda event: owner.guarded(self.review))
        self.place_button.Bind(wx.EVT_BUTTON, lambda event: owner.guarded(self.place))
        self.diagnostics_button.Bind(wx.EVT_BUTTON, lambda event: owner.guarded(self.diagnostics))
        self.search.Bind(wx.EVT_TEXT, self.refresh)
        self.listing.Bind(wx.EVT_LIST_ITEM_SELECTED, self.select)
        self.timer = wx.Timer(self); self.Bind(wx.EVT_TIMER, self.poll, self.timer); self.timer.Start(100)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.destroy)
        self.review_button.Disable(); self.place_button.Disable()

    def choose(self, event=None):
        with wx.DirDialog(self, 'Choose the local LTspice lib folder') as dialog:
            if dialog.ShowModal() == wx.ID_OK: self.scan(dialog.GetPath())

    def scan(self, path):
        if self.busy: raise ValueError('Library indexing is already running')
        self.busy = True; self.scan_button.Disable(); self.status.SetLabel('Indexing local model and symbol metadata…')
        messages = self.messages
        def work():
            try:
                from .ltspice_local_library import index_library
                messages.put((index_library(path, max_files=20000), None))
            except Exception as error: messages.put((None, str(error)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self, event=None):
        try: result, error = self.messages.get_nowait()
        except queue.Empty: return
        self.busy = False; self.scan_button.Enable()
        if error: self.status.SetLabel('Index failed: ' + error); return
        self.accept_index(result)

    def accept_index(self, result):
        if not isinstance(result, dict) or result.get('contract') != 'spikes/ltspice-local-library/v1':
            raise ValueError('Not an LTspice metadata index')
        for key in ('models', 'symbols', 'files', 'diagnostics'):
            if not isinstance(result.get(key), list) or len(result[key]) > 100000:
                raise ValueError('Invalid or oversized metadata inventory')
        if not isinstance(result.get('root'), str) or not isinstance(result.get('status'), dict):
            raise ValueError('Invalid metadata root or status')
        for row in result['models']:
            if not isinstance(row, dict) or not all(isinstance(row.get(key), str) and len(row[key]) <= 4096
                                                    for key in ('id', 'name', 'kind', 'source_path', 'sha256')):
                raise ValueError('Invalid model metadata')
            if row['kind'] not in ('model', 'subckt') or not isinstance(row.get('pins'), list) or len(row['pins']) > 1024:
                raise ValueError('Invalid model kind or pin inventory')
            if not all(isinstance(pin, str) and len(pin) <= 512 for pin in row['pins']):
                raise ValueError('Invalid model pin')
        self.index = result; self.refresh()
        if hasattr(self, 'after_index'): self.after_index(result)
        complete = result.get('status', {}).get('complete', False)
        self.status.SetLabel(f"{len(result['models']):,} declarations · {len(result['symbols']):,} symbols · "
                             f"{len(result['diagnostics'])} diagnostics · {'scan finished' if complete else 'partial index'} · not qualified")

    def refresh(self, event=None):
        from .fuzzy_search import ranked
        rows = self.index['models'] if self.index else []
        self.rows = ranked(rows, self.search.GetValue(), text=lambda row: row['name']+' '+row['source_path'])
        self.listing.DeleteAllItems()
        for index, row in enumerate(self.rows[:2000]):
            self.listing.InsertItem(index, row['name']); self.listing.SetItem(index, 1, row['kind'])
            self.listing.SetItem(index, 2, row['source_path'])
        self.detail.SetValue('Showing up to 2,000 matches; refine search for more. Declaration counts include helper models, not distinct manufacturer products.\n'
                             'No includes, DLLs, native callbacks or simulation code are executed by indexing.')
        self.review_button.Disable(); self.place_button.Disable()

    def select(self, event=None):
        index = self.listing.GetFirstSelected()
        if not 0 <= index < len(self.rows): return
        row = self.rows[index]
        self.review_button.Enable(); self.place_button.Enable(row['kind'] == 'model')
        self.detail.SetValue(f"{row['name']} · {row['kind']}\nDeclared pins: {', '.join(row['pins']) or 'Intrinsic model / not declared'}\n"
                             f"Original file: {row['source_path']}\nSHA-256: {row['sha256']}\n"
                             'Local reference only. Dependencies, LTspice-specific constructs, model rights and electrical behavior are not qualified.')

    def selected_model(self):
        index = self.listing.GetFirstSelected()
        if not 0 <= index < min(len(self.rows), 2000): raise ValueError('Select a local model declaration')
        return self.rows[index]

    def review(self):
        from .ltspice_local_library import read_model_file
        row = self.selected_model(); text = read_model_file(self.index, row['id'])
        with wx.Dialog(self, title='Original local model — not executed', size=(900, 700),
                       style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER) as dialog:
            box = wx.BoxSizer(wx.VERTICAL)
            note = wx.StaticText(dialog, label='Original source is hash-checked. Dependencies are not loaded; compatibility and redistribution are not approved.')
            note.Wrap(830); box.Add(note, 0, wx.ALL | wx.EXPAND, 8)
            source = wx.TextCtrl(dialog, value=text, style=wx.TE_READONLY | wx.TE_MULTILINE | wx.HSCROLL)
            source.SetFont(wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
            box.Add(source, 1, wx.ALL | wx.EXPAND, 8)
            box.Add(dialog.CreateButtonSizer(wx.CLOSE), 0, wx.ALL | wx.ALIGN_RIGHT, 8)
            dialog.SetSizer(box); apply_window(dialog, self.owner.palette); dialog.ShowModal()

    def diagnostics(self):
        if not self.index: raise ValueError('Index or open a local library first')
        from collections import Counter
        items = self.index['diagnostics']
        counts = Counter(str(item.get('code', 'unknown')) for item in items if isinstance(item, dict))
        text = 'Scan diagnostics (not model qualification)\n\n' + '\n'.join(f'{key}: {value}' for key, value in sorted(counts.items()))
        text += '\n\nFirst 500 diagnostics:\n' + '\n\n'.join(
            str(item.get('source_path', '')) + '\n' + str(item.get('code', '')) + ': ' + str(item.get('message', ''))
            for item in items[:500] if isinstance(item, dict))
        with wx.Dialog(self, title='Local library scan diagnostics', size=(850, 650),
                       style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER) as dialog:
            box = wx.BoxSizer(wx.VERTICAL)
            box.Add(wx.TextCtrl(dialog, value=text, style=wx.TE_READONLY | wx.TE_MULTILINE), 1, wx.EXPAND | wx.ALL, 8)
            box.Add(dialog.CreateButtonSizer(wx.CLOSE), 0, wx.ALIGN_RIGHT | wx.ALL, 8)
            dialog.SetSizer(box); apply_window(dialog, self.owner.palette); dialog.ShowModal()

    def place(self):
        from .ltspice_local_library import read_model_declaration
        row = self.selected_model()
        if row['kind'] != 'model': raise ValueError('Subcircuits require dependency and pin review; no helper is silently selected')
        if self.owner.job_running: raise ValueError('Stop simulation before inserting a model')
        self.owner.require_clean_directive_source()
        text = read_model_declaration(self.index, row['id'])
        if wx.MessageBox('This embeds the selected original model card in your circuit. Confirm you have the required usage rights.\n\n'
                         'The native parser will reject unsupported types/parameters. No model is executed or qualified merely by importing it.',
                         'Import local intrinsic model', wx.OK | wx.CANCEL | wx.ICON_INFORMATION, self) != wx.OK: return
        self.owner.accept_import(text)

    def save(self):
        if not self.index: raise ValueError('Index a local library first')
        from .document import write_json
        with wx.FileDialog(self, 'Export metadata only (no manufacturer source)', wildcard='SPIKES metadata index|*.spkindex',
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() == wx.ID_OK: write_json(dialog.GetPath(), self.index)

    def open(self):
        if self.busy: raise ValueError('Wait for the current library scan')
        with wx.FileDialog(self, 'Open local metadata index', wildcard='SPIKES metadata index|*.spkindex',
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() != wx.ID_OK: return
            path = Path(dialog.GetPath())
            with path.open('rb') as stream: raw = stream.read(32 * 1024 * 1024 + 1)
            if len(raw) > 32 * 1024 * 1024: raise ValueError('Metadata index exceeds 32 MiB')
            result = json.loads(raw.decode('utf-8'))
            if not isinstance(result, dict): raise ValueError('Invalid metadata index')
            # An imported index must not select its own filesystem/network root.
            with wx.DirDialog(self, 'Confirm the actual local library folder for this index') as folder:
                if folder.ShowModal() != wx.ID_OK: return
                result['root'] = folder.GetPath()
            self.accept_index(result)

    def destroy(self, event):
        if event.GetEventObject() is self: self.timer.Stop()
        event.Skip()


class ManufacturerLibraryHub(wx.Panel):
    def __init__(self, parent, owner):
        super().__init__(parent); box = wx.BoxSizer(wx.VERTICAL)
        self.book = wx.Notebook(self)
        self.products = ProductCatalog(self.book, owner)
        self.parts = ManufacturerPartsPanel(self.book, owner)
        self.local = LocalLibrary(self.book, owner)
        self.local.after_index = self.indexed
        for page, title in ((self.products, 'Manufacturer products'), (self.parts, 'Sourced electrical parts'),
                            (self.local, 'Local LTspice')): self.book.AddPage(page, title)
        actions = wx.WrapSizer(wx.HORIZONTAL)
        def show_boards():
            from .controller_board_browser import show
            return show(owner)
        for label, action in (('Project model review shelf…', owner.catalog_panel.project_model_shelf),
                              ('Controller boards…', show_boards)):
            control = ActionButton(self, label=label)
            control.Bind(wx.EVT_BUTTON, lambda event, fn=action: owner.guarded(fn))
            actions.Add(control, 0, wx.ALL, 4)
        box.Add(actions, 0, wx.ALL, 4)
        box.Add(self.book, 1, wx.EXPAND); self.SetSizer(box)
        self.search = self.products.search; self.listing = self.products.listing
        apply_window(self, owner.palette)

    def refresh_symbols(self, palette):
        self.products.listing.refresh_symbols(palette); self.parts.listing.refresh_symbols(palette)

    def indexed(self, index):
        self.products.local_models = index['models']; self.products.select()

    def show_local_for(self, record):
        if record:
            self.book.SetSelection(2); self.local.search.SetValue(record['part_number']); self.local.search.SetFocus()
