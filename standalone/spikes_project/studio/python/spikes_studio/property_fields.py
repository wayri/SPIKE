# SPDX-License-Identifier: Apache-2.0
"""Native labeled property controls; serialization stays behind the UI boundary."""
from copy import deepcopy
import json
import math
import wx

LIMITS = {'voltage_v': 'Maximum voltage [V]', 'current_a': 'Maximum current [A]',
          'power_w': 'Maximum dissipation [W]', 'temperature_k': 'Maximum temperature [K]',
          'electric_field_v_m': 'Maximum electric field [V/m]'}


class PropertyFields(wx.Panel):
    """Retain the existing GetValue/SetValue contract without a JSON text box.

    Unknown structured metadata is retained unchanged, never flattened or lost.
    A mixed selection is left untouched unless the user supplies a whole value.
    """
    def __init__(self, parent, value, *, kind, mixed=False):
        super().__init__(parent)
        self.kind = kind
        self.controls = {}
        self.original = '<multiple values>' if mixed else json.dumps(value, indent=2)
        self.data = deepcopy(value)
        self.mixed = mixed
        box = wx.BoxSizer(wx.VERTICAL)
        self.grid = wx.FlexGridSizer(cols=1, hgap=8, vgap=6)
        self.grid.AddGrowableCol(0)
        box.Add(self.grid, 0, wx.EXPAND)
        self.SetSizer(box)
        self.populate()

    def populate(self):
        self.grid.Clear(delete_windows=True)
        self.controls = {}
        items = list(enumerate(self.data)) if self.kind == 'nodes' else list(self.data.items())
        if self.kind == 'limits':
            items = [(key, self.data.get(key)) for key in dict.fromkeys([*LIMITS, *self.data])]
        if not items:
            self.grid.Add(wx.StaticText(self, label='No additional part metadata.'))
            self.grid.Add(wx.StaticText(self, label='Electrical values are edited above.'))
        for key, value in items:
            label = f'Pin {key + 1} → net' if self.kind == 'nodes' else LIMITS.get(key, str(key).replace('_', ' ').capitalize())
            self.grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            if isinstance(value, (dict, list)):
                self.grid.Add(wx.StaticText(self, label=f'{len(value)} stored entries — retained unchanged'))
                continue
            text = '<multiple values>' if self.mixed else '' if value is None else str(value)
            control = wx.TextCtrl(self, value=text)
            control.SetName(label)
            if self.kind == 'limits':
                control.SetToolTip('Positive SI value or engineering suffix; leave blank for no declared limit.')
            self.controls[key] = (control, text, value)
            self.grid.Add(control, 1, wx.EXPAND)
        self.Layout()

    def GetValue(self):
        if all(control.GetValue() == text for control, text, _ in self.controls.values()):
            return self.original
        if self.mixed:
            raise ValueError('Mixed pin/metadata fields cannot be partially replaced; select one component first.')
        result = deepcopy(self.data)
        from python.spikes.netlist import parse_spice_number
        for key, (control, before, previous) in self.controls.items():
            text = control.GetValue().strip()
            if text == before:
                continue
            if self.kind == 'nodes':
                result[key] = text
            elif self.kind == 'limits':
                if not text:
                    result.pop(key, None)
                else:
                    number = parse_spice_number(text, 'scalar')
                    if not math.isfinite(number) or number <= 0:
                        raise ValueError(f'{LIMITS.get(key, key)} must be positive and finite')
                    result[key] = number
            elif isinstance(previous, bool):
                if text.lower() not in ('true', 'false'):
                    raise ValueError(f'{key}: enter True or False')
                result[key] = text.lower() == 'true'
            elif isinstance(previous, (float, int)):
                result[key] = parse_spice_number(text, 'scalar')
            else:
                result[key] = text
        return json.dumps(result, indent=2, allow_nan=False)

    def SetValue(self, text):
        value = json.loads(text)
        if not isinstance(value, list if self.kind == 'nodes' else dict):
            raise ValueError('Incorrect property structure')
        self.data = value
        self.mixed = False
        self.populate()
        # The owning properties form retains the pre-edit serialization for
        # dirty detection; no serialized text is shown in this control.
        self.original = json.dumps(value, indent=2)


class CapacitorModelFields(wx.Panel):
    """Edit the existing capacitor model policy; no new physics or hidden defaults."""
    def __init__(self, parent, document, parts):
        super().__init__(parent)
        from .model_fidelity import inherited
        self.parts = parts
        self.initial_policy = deepcopy(document['model_policy'])
        entries = [inherited(document['model_policy'], part['ref']) for part in parts]
        self.editable = all(part['kind'] == 'capacitor' and ':' not in part['ref'] for part in parts)
        # Editing an enforced component itself is allowed; an enforced parent is not.
        lock = next((entry[2] for part, entry in zip(parts, entries)
                     if entry[2] and entry[2] != part['ref'].upper()), None)
        self.editable = self.editable and not lock
        box = wx.BoxSizer(wx.VERTICAL)
        self.choice = wx.Choice(self, choices=['Use schematic / subsheet default', 'Ideal — omit implicit parasitics',
                                              'Non-ideal — ESR, ESL and leakage'])
        selected = [entry[0] for entry in entries]
        self.values = deepcopy(selected[0].get('parasitic_values', {}))
        self.mixed = any(entry != selected[0] for entry in selected)
        self.initial_choice = 0 if self.mixed else 2 if self.values else 1 if selected[0]['tier'] == 'ideal' else 0
        self.choice.SetSelection(self.initial_choice)
        self.choice.Enable(self.editable)
        self.choice.SetName('Capacitor ideal or non-ideal model')
        box.Add(self.choice, 0, wx.EXPAND | wx.BOTTOM, 8)
        self.fields = {}
        grid = wx.FlexGridSizer(cols=1, hgap=8, vgap=6); grid.AddGrowableCol(0)
        for key, label in (('esr_ohm', 'Series resistance / ESR [ohm]'),
                           ('esl_h', 'Series inductance / ESL [H]'), ('leakage_ohm', 'Leakage resistance [ohm]')):
            grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            control = wx.TextCtrl(self, value=str(self.values.get(key, '')) if not self.mixed else '')
            control.SetName(label); self.fields[key] = control; grid.Add(control, 1, wx.EXPAND)
        box.Add(grid, 0, wx.EXPAND)
        note = ('Locked by enforced parent: ' + lock if lock else
                'Explicit linear package model. Blank fields omit that parasitic; no inferred ratings or self-heating.')
        self.note = wx.StaticText(self, label=note); self.note.Wrap(310)
        box.Add(self.note, 0, wx.TOP, 8); self.SetSizer(box)
        self.initial_text = {key: control.GetValue() for key, control in self.fields.items()}
        self.choice.Bind(wx.EVT_CHOICE, self.refresh)
        self.refresh()

    def refresh(self, event=None):
        for control in self.fields.values():
            control.Enable(self.editable and self.choice.GetSelection() == 2)

    def dirty(self):
        return self.choice.GetSelection() != self.initial_choice or any(
            control.GetValue() != self.initial_text[key] for key, control in self.fields.items())

    def apply_to(self, document):
        if not self.dirty():
            return
        if not self.editable:
            raise ValueError('This model selection is locked or unsupported')
        from python.spikes.netlist import parse_spice_number
        from .passive_models import validate
        selected = self.choice.GetSelection()
        values = {key: parse_spice_number(control.GetValue(), 'scalar')
                  for key, control in self.fields.items() if control.GetValue().strip()} if selected == 2 else {}
        validate(values)
        if selected == 2 and not values:
            raise ValueError('Enter at least one non-ideal parameter, or choose Ideal')
        for part in self.parts:
            ref = part['ref'].upper()
            if selected == 0:
                document['model_policy']['components'].pop(ref, None)
            else:
                old = self.initial_policy['components'].get(ref, {})
                entry=deepcopy(old)
                entry.update(tier='source' if selected == 2 else 'ideal',
                             enforce=old.get('enforce', False),parasitic_values=deepcopy(values))
                document['model_policy']['components'][ref] = entry
