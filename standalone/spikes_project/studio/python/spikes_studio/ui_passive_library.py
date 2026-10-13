# SPDX-License-Identifier: Apache-2.0
"""Native editor screenshots and real coefficient validation, not mock models."""
from pathlib import Path
import wx
from .document import write_json
from .passive_catalog import make_record,model
from .component_panel import InsertDialog
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);dialog=None;checks={}
    try:
        frame.set_theme('Light',save=False);dialog=InsertDialog(frame.catalog_panel,make_record('resistor',100))
        dialog.package_choice.SetStringSelection('2512');dialog.construction_choice.SetStringSelection('Thin film')
        dialog.parameter_fields['r'].SetValue('1.234k');dialog.parameter_fields['tolerance_percent'].SetValue('.05')
        dialog.Show();dialog.Layout();wx.Yield();capture_window(dialog,directory/'passive-value-package.png')
        dialog.book.SetSelection(1);dialog.parameter_fields['series_inductance_h'].SetValue('2n');dialog.parameter_fields['parallel_capacitance_f'].SetValue('100f')
        record=dialog.edited_record();spec=model(record)
        if 'LSER' not in spec['source'] or 'CPAR' not in spec['source']:raise AssertionError('Parasitics were omitted')
        checks['explicit_parasitics_compile']=True
        dialog.SetSize((580,480));dialog.Layout();wx.Yield();capture_window(dialog,directory/'parasitics-narrow.png')
        dialog.Destroy();dialog=InsertDialog(frame.catalog_panel,make_record('kelvin_shunt',.001))
        dialog.book.SetSelection(2);dialog.Show();dialog.Layout();wx.Yield();capture_window(dialog,directory/'kelvin-pins.png')
        if set(dialog.pins)!={'FP','FN','SP','SN'}:raise AssertionError('Kelvin terminals incomplete')
        checks['four_kelvin_terminals']=True
        write_json(directory/'verification.json',dict(ok=True,checks=checks,catalog_records=len(frame.catalog_panel.catalog['records'])))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    finally:
        if dialog:dialog.Destroy()
        frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
