# SPDX-License-Identifier: Apache-2.0
"""Visual parameter selection for inert sampled controller libraries."""
import wx
from . import compiled_ic_library as library


class CompiledICDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title='Sampled controller block library',
                         size=(720, 620), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.library = library.catalog()
        self.result = None
        box = wx.BoxSizer(wx.VERTICAL)
        self.choice = wx.Choice(self)
        box.Add(self.choice, 0, wx.EXPAND | wx.ALL, 12)
        self.description = wx.StaticText(self)
        box.Add(self.description, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        self.form = wx.ScrolledWindow(self)
        self.form.SetScrollRate(0, 10)
        box.Add(self.form, 1, wx.EXPAND | wx.ALL, 12)
        self.notice = wx.StaticText(self)
        box.Add(self.notice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        row = wx.WrapSizer(wx.HORIZONTAL)
        for label, action in [('Import library…', self.import_library),
                              ('Export library…', self.export_library),
                              ('Load into editor', self.accept)]:
            button = wx.Button(self, label=label)
            button.Bind(wx.EVT_BUTTON, lambda event, fn=action: self.guarded(fn))
            row.Add(button, 0, wx.ALL, 4)
        cancel = wx.Button(self, wx.ID_CANCEL)
        row.Add(cancel, 0, wx.ALL, 4)
        box.Add(row, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizer(box)
        self.SetMinSize((540, 600))
        self.choice.Bind(wx.EVT_CHOICE, self.refresh_fields)
        self.Bind(wx.EVT_SIZE, self.resized)
        self.populate()

    def guarded(self, action):
        try:
            action()
        except (ValueError, OSError) as error:
            wx.MessageBox(str(error), 'Block library', wx.OK | wx.ICON_ERROR, self)

    def populate(self):
        self.choice.SetItems([entry['name'] for entry in self.library['entries']])
        self.choice.SetSelection(0)
        self.refresh_fields()

    def entry(self):
        return self.library['entries'][self.choice.GetSelection()]

    def refresh_fields(self, event=None):
        self.form.DestroyChildren()
        fields = wx.FlexGridSizer(cols=2, vgap=10, hgap=14)
        fields.AddGrowableCol(1)
        self.fields = {}
        entry = self.entry()
        self.description.SetLabel(entry['description'])
        for spec in entry['parameters']:
            fields.Add(wx.StaticText(self.form, label=spec['name'].replace('_', ' ').capitalize()
                                     + ' [' + spec['unit'] + ']'), 0, wx.ALIGN_CENTER_VERTICAL)
            control = wx.TextCtrl(self.form, value=format(spec['default'], '.12g'))
            control.SetToolTip(spec['description'] + f" Range: {spec['minimum']} to {spec['maximum']}")
            self.fields[spec['name']] = control
            fields.Add(control, 0, wx.EXPAND)
        self.form.SetSizer(fields)
        self.form.FitInside()
        self.notice.SetLabel(entry['limitations'] + '\nLoading never compiles or executes code. '
                             'Review pin connections in Pin properties, then explicitly trust and compile.')
        self.wrap()
        self.Layout()

    def wrap(self):
        width = max(300, self.GetClientSize().width-30)
        self.description.Wrap(width)
        self.notice.Wrap(width)

    def resized(self, event):
        if hasattr(self, 'notice'):
            # Reset text before Wrap to avoid retaining previous narrow breaks.
            self.description.SetLabel(self.entry()['description'])
            self.notice.SetLabel(self.entry()['limitations'] + '\nLoading never compiles or executes code. '
                                 'Review pin connections in Pin properties, then explicitly trust and compile.')
            self.wrap()
        event.Skip()

    def configuration(self):
        parameters = {}
        for name, field in self.fields.items():
            try:
                parameters[name] = float(field.GetValue())
            except ValueError as error:
                raise ValueError('Enter a numeric value for '+name) from error
        return library.configuration(self.entry()['id'], parameters, library=self.library)

    def accept(self):
        self.result = self.configuration()
        self.EndModal(wx.ID_OK)

    def import_library(self):
        with wx.FileDialog(self, 'Import sampled controller library', wildcard='Controller libraries (*.spkctl)|*.spkctl|JSON (*.json)|*.json',
                           style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                value = library.load(dialog.GetPath())
                self.library = value
                self.populate()

    def export_library(self):
        with wx.FileDialog(self, 'Export sampled controller library', defaultFile='controllers.spkctl',
                           wildcard='Controller libraries (*.spkctl)|*.spkctl',
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                library.save(dialog.GetPath(), self.library)
