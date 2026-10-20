# SPDX-License-Identifier: Apache-2.0
"""Exercise new editing/library paths inside the actual frozen runtime."""
from copy import deepcopy
import json
import re


def verify(frame, check):
    from .component_catalog import native_recipe
    from .component_panel import InsertDialog
    from .discovery_index import DiscoveryIndex
    from .document import Document, RC_DECK
    from .library_browser import insertion_plan, apply_insertion
    from .quick_insert import suggestions

    panel=frame.catalog_panel
    records=[record for record in panel.catalog['records']
             if record.get('model_type')=='lumped_physics_part_v1']
    check(len(records)==5,'five configurable lumped-device families bundled')
    record=next(row for row in records if row['builder_kind']=='resistor3')
    dialog=InsertDialog(panel,record)
    try:
        dialog.parameter_fields['resistance_ohm'].SetValue('4.7k')
        edited=dialog.edited_record()
        check(edited['parameters']['resistance_ohm']==4700,
              'lumped library parameters accept engineering values')
    finally:dialog.Destroy()
    recipe=native_recipe(edited)
    check(recipe['pins']==['P','N','SUB'],'substrate resistor terminal order retained')
    doc=Document.from_netlist(RC_DECK);before=deepcopy(doc.data)
    plan=insertion_plan(doc,edited,{'P':'copy_p','N':'copy_n','SUB':'0'})
    apply_insertion(doc,plan,edited['id'])
    reopened=Document(json.loads(json.dumps(doc.data)))
    saved=reopened.data['metadata']['lumped_physics_models'][plan['model']]
    check(saved['record']['parameters']['resistance_ohm']==4700 and
          saved['pins']==recipe['pins'] and saved['model_status']=='generic_unqualified',
          'lumped placement metadata survives serialization')
    doc.undo();check(doc.data==before,'lumped placement undoes atomically')
    packaged=[row for row in panel.catalog['records'] if row.get('model_type')=='packaged_lumped_device_v1']
    check({row['builder_kind'] for row in packaged}=={'packaged_nmos4','packaged_npn4','packaged_resistor3','packaged_kelvin_shunt4','packaged_feedthrough_capacitor3'},'five packaged transistor and passive model families bundled')
    for record in packaged:
        family=record['builder_kind']
        dialog=InsertDialog(panel,record)
        try:
            dialog.parameter_fields['series_resistance_ohm'].SetValue('250m')
            dialog.parameter_fields['series_inductance_h'].SetValue('2n')
            dialog.parameter_fields['parallel_capacitance_f'].SetValue('3p')
            edited=dialog.edited_record()
        finally:dialog.Destroy()
        check(edited['parameters']['series_resistance_ohm']==0.25 and
              edited['parameters']['series_inductance_h']==2e-9 and
              edited['parameters']['parallel_capacitance_f']==3e-12,
              family+' labeled package parameters accept SI suffixes')
        recipe=native_recipe(edited)
        pins={'packaged_nmos4':['D','G','S','B'],'packaged_npn4':['C','B','E','SUB'],
              'packaged_resistor3':['P','N','SUB'],'packaged_kelvin_shunt4':['FP','FN','SP','SN'],
              'packaged_feedthrough_capacitor3':['IN','OUT','GND']}[family]
        check(recipe['pins']==pins and all('\n'+prefix in recipe['source'] for prefix in ('RPKG','LPKG','CPKG')),
              family+' exports exact pins and explicit package R/L/C')
        document=Document.from_netlist(RC_DECK);before=deepcopy(document.data)
        mapping=dict(zip(pins,['out','in','0','0']))
        plan=insertion_plan(document,edited,mapping);apply_insertion(document,plan,edited['id'])
        reopened=Document(json.loads(json.dumps(document.data)))
        saved=reopened.data['metadata']['packaged_device_models'][plan['model']]
        check(saved['pins']==pins and saved['record']['parameters']==edited['parameters'] and
              saved['model_status']=='generic_unqualified' and saved['package_builder']=='device_parasitics',
              family+' preserves edited parameters and unqualified composition provenance')
        conflict=Document(document.data)
        conflict.apply_source(re.sub(r'(?m)^(RPKG\S+\s+\S+\s+\S+\s+)\S+',
                                     r'\g<1>99',conflict.data['source'],count=1))
        conflicted=deepcopy(conflict.data)
        rejected=False
        try:insertion_plan(conflict,edited,mapping)
        except ValueError:rejected=True
        check(rejected and conflict.data==conflicted,
              family+' rejects edited generated definitions without overwriting them')
        document.undo();check(document.data==before,family+' insertion undoes atomically')
    args=('resistor',panel.catalog['records'])
    check(suggestions(*args)==suggestions(*args,component_index=DiscoveryIndex(args[1])),
          'packaged indexed discovery preserves result order')

    original=frame.doc;selected=set(frame.canvas.selected)
    try:
        frame.doc=Document.from_netlist(RC_DECK);frame.refresh_document(force_source=True)
        resistor=next(part for part in frame.doc.data['components'] if part['ref']=='R1')
        frame.canvas.selected={resistor['id']};before=deepcopy(frame.doc.data)
        import wx
        frame.canvas.SetFocus();wx.Yield()
        frame.copy_circuit();frame.paste()
        check(frame.canvas.fragment_plan is not None and frame.doc.data==before,
              'system clipboard starts a non-mutating fragment preview')
        frame.cancel_fragment_placement()
        check(frame.doc.data==before,'clipboard preview cancels without mutation')
        frame.duplicate_selection()
        check(frame.canvas.fragment_plan is not None and frame.doc.data==before,
              'duplicate starts a non-mutating placement preview')
        frame.rotate_fragment_placement();frame.cancel_fragment_placement()
        check(frame.doc.data==before,'rotated duplicate preview cancels without mutation')
        frame.duplicate_selection();frame.commit_fragment_placement((700,400))
        frame.cancel_fragment_placement()
        check(len(frame.doc.data['components'])==len(before['components'])+1,
              'duplicate preview commits one new component')
        frame.doc.undo();check(frame.doc.data==before,'duplicate placement undoes atomically')
    finally:
        frame.cancel_fragment_placement(None)
        frame.doc=original;frame.canvas.selected=selected;frame.refresh_document(force_source=True)
