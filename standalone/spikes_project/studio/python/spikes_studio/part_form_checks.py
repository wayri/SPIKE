# SPDX-License-Identifier: Apache-2.0
"""Real widget/model acceptance checks shared with the frozen package smoke."""


def verify(frame, check):
    import wx
    from .component_panel import InsertDialog
    from .desktop import Properties
    from .document import Document, RC_DECK
    from .library_browser import insertion_plan, apply_insertion
    from .model_fidelity import preflight
    from copy import deepcopy

    panel=frame.catalog_panel
    check(isinstance(panel.parameters, wx.Panel) and not isinstance(panel.parameters, wx.TextCtrl),
          'catalog values use labeled fields, not a JSON text editor')
    record=next(row for row in panel.catalog['records']
                if row['family']=='resistor' and not row.get('model_type'))
    dialog=InsertDialog(panel,record)
    try:
        dialog.parameter_fields['r'].SetValue('4.7k')
        dialog.mode_choice.SetSelection(1);dialog.update_fidelity_controls()
        dialog.parameter_fields['series_inductance_h'].SetValue('5n')
        edited=dialog.edited_record()
        check(edited['parameters']['r']==4700 and
              edited['model_type']=='lumped_passive_rlc_v1',
              'non-ideal resistor selector retains the requested value')
        doc=Document.from_netlist(RC_DECK)
        plan=insertion_plan(doc,edited,{key:control.GetValue() for key,control in dialog.pins.items()})
        apply_insertion(doc,plan,edited['id'])
        from .part_properties import parse
        check(any(element.kind=='inductor' and element.value==5e-9
                  for element in parse(doc.data['source']).elements),
              'non-ideal insertion stamps the requested series inductance')
    finally:dialog.Destroy()

    original=frame.doc
    selected=set(frame.canvas.selected)
    dialog=None
    try:
        frame.doc=Document.from_netlist(RC_DECK)
        frame.canvas.selected={frame.doc.data['components'][2]['id']}
        dialog=Properties(frame)
        dialog.EndModal=lambda code: None
        dialog.fields['value'].SetValue('220u')
        dialog.capacitor_model.choice.SetSelection(2);dialog.capacitor_model.refresh()
        dialog.capacitor_model.fields['esr_ohm'].SetValue('50m')
        dialog.apply()
        check(dialog.applied and len(frame.doc.undo_stack)==1,
              'value and non-ideal capacitor apply as one undo transaction')
        lowered=preflight(deepcopy(frame.doc.data))['effective_source']
        check('RSPKPAR_C1' in lowered,
              'non-ideal capacitor input reaches the executable netlist')
        frame.doc.undo()
        check('C1' not in frame.doc.data['model_policy']['components'],
              'undo restores the previous model policy')
        dialog.Destroy();dialog=None
        cases=(('Q1','Q1 c b 0','NPN(IS=1f BF=100 CBE=2p TF=1n)','bf','200','forward_alpha',200/201),
               ('M1','M1 d g 0 b','NMOS(VTO=1 KP=1m CGD=1p)','cgd','3p','charge_c2',3e-12),
               ('Z1','Z1 d g 0 b tj','SPK_GAN(THRESHOLD_VOLTAGE_V=2)','thermal_capacitance_j_per_k','.02','thermal_capacitance_j_per_k',.02),
               ('Z1','Z1 d g 0 b tj','SPK_SIC(THRESHOLD_VOLTAGE_V=3)','gate_drain_capacitance_f','5p','gate_drain_capacitance_f',5e-12))
        for ref,instance,card,key,value,param,expected in cases:
            frame.doc=Document.from_netlist(f'Active property check\n{instance} shared\n.model shared {card}\n.op\n.end\n')
            frame.refresh_document(force_source=True)
            frame.canvas.selected={frame.doc.data['components'][0]['id']}
            dialog=Properties(frame);dialog.EndModal=lambda code:None
            choice=next(i for i,(mode,_) in enumerate(dialog.model_options) if mode=='custom_model')
            dialog.model_choice.SetSelection(choice);dialog.render_model()
            dialog.model_fields[key].SetValue(value)
            dialog.apply()
            element=parse(frame.doc.data['source']).elements[0]
            check(dialog.applied and abs(dict(element.semiconductor_parameters)[param]-expected)<1e-15 and
                  element.model_name.startswith('SPIKES_') and len(frame.doc.undo_stack)==1,
                  card.split('(')[0]+' labeled parameters reach a private executable model in one transaction')
            dialog.Destroy();dialog=None
        dialog=Properties(frame);dialog.EndModal=lambda code:None
        dialog.thermal_assessment.controls['max_junction_c'].SetValue('150')
        dialog.thermal_assessment.controls['supplied_temperature_c'].SetValue('140')
        dialog.apply()
        from .thermal_report import report
        rows=report(frame.doc.data,{'data':{}})['parts']
        check(dialog.applied and rows[0]['status']=='warning',
              'labeled thermal assessment fields feed the existing margin report')
        dialog.Destroy();dialog=None
        from .model_library_editor import ModelLibraryEditor
        with ModelLibraryEditor(frame,'.model local IGBT(RG=5 CGE=2n TNOM=27)') as editor:
            check(editor.export_button.GetContainingSizer() is not None,
                  'model library export action belongs to the dialog layout')
            editor.controls['CGE'].SetValue('3n')
            check('CGE=3n' in editor.source_text(),'IGBT library parameters are labeled and exportable without claiming native execution')
        source='.subckt amplifier in_p in_n vp vn out params: gain=100000 rout=50\nE1 out 0 in_p in_n {gain}\n.ends amplifier\n'
        with ModelLibraryEditor(frame,source) as editor:
            editor.controls['GAIN'].SetValue('200000')
            edited=editor.source_text()
            check('GAIN=200000' in edited and edited.endswith('E1 out 0 in_p in_n {gain}\n.ends amplifier\n'),
                  'IC and opamp subcircuit defaults edit without changing pins or body')
    finally:
        if dialog:dialog.Destroy()
        frame.doc=original;frame.canvas.selected=selected;frame.refresh_document()
