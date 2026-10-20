# SPDX-License-Identifier: Apache-2.0
"""Retain packaged passive model execution in frozen/installed acceptance."""

def verify(frame, library, check):
    from copy import deepcopy
    from .library_browser import native_recipe
    from python.spikes.netlist import parse_netlist
    from python.spikes.native_runner import run_native_project
    for family, pins in (('packaged_resistor3','p 0 0'),
                         ('packaged_kelvin_shunt4','p 0 sp sn'),
                         ('packaged_feedthrough_capacitor3','p out 0')):
        record=deepcopy(next(row for row in frame.catalog_panel.catalog['records']
                             if row['family']==family))
        check(record['model_status']=='generic_unqualified',family+' remains explicitly unqualified')
        record['parameters']['series_resistance_ohm']=10.0
        recipe=native_recipe(record)
        source=recipe['source']+f'X1 {pins} {recipe["name"]}\nVP p 0 1\n'
        if family=='packaged_feedthrough_capacitor3':source+='RLOAD out 0 1k\n'
        source+='.op\n.end\n'
        result=run_native_project(parse_netlist(source,native_extensions=True),library).to_dict()
        check(result['status']=='completed',family+' generated model solves in bundled engine')
        data=result['data'];current=-data['element_current_a']['VP']
        drop=1-data['node_voltage_v']['x1:__spk_core_1']
        check(current>0 and abs(drop-10*current)<1e-9,
              family+' requested force lead resistance reaches native solve')
