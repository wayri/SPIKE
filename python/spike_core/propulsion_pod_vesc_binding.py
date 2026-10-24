# SPDX-License-Identifier: Apache-2.0
"""Source-derived VESC bridge terminal proof; never a firmware/model claim."""
import hashlib
import json

PHASES = (('a','P6','Q5','Q6','/Mosfet driver/H3_VS','/Mosfet driver/H3_LOW','R54'),
          ('b','P7','Q3','Q4','/Mosfet driver/H2_VS','GND',''),
          ('c','P9','Q1','Q2','/Mosfet driver/H1_VS','/Mosfet driver/H1_LOW','R53'))

def prepare_vesc_binding(design, board_occurrence_id):
    if not isinstance(design,dict) or design.get('name')!='BLDC_4':
        raise ValueError('Expected the selected BLDC_4 source design')
    if not isinstance(board_occurrence_id,str) or not board_occurrence_id.strip():
        raise ValueError('Explicit board occurrence identity is required')
    components={c['reference']:c for c in design['components']}
    def padnets(ref,pad):
        return {p.get('net_name','') for p in design['pads'] if p.get('component')==ref and p.get('name')==pad}
    proof=[]
    for index,(phase,terminal,high,low,net,return_net,shunt) in enumerate(PHASES):
        for ref in (high,low):
            if components[ref]['value']!='IRFS7530':
                raise ValueError('Source MOSFET identity changed: '+ref)
        checks=[padnets(terminal,'1')=={net},padnets(high,'D')=={'V_SUPPLY'},
                padnets(high,'S')=={net},padnets(low,'D')=={net},padnets(low,'S')=={return_net}]
        if not all(checks):
            raise ValueError('Phase terminal or half-bridge topology changed: '+phase)
        if shunt and not {return_net,'GND'}<=set(components[shunt]['nets']):
            raise ValueError('Source shunt return path changed: '+shunt)
        proof.append({'phase':phase,'terminal_reference':terminal,'phase_net':net,
            'high_side_reference':high,'low_side_reference':low,'low_side_return_net':return_net,
            'shunt_reference':shunt or None,'shunt_resistance_ohm':None if shunt else 0.,
            'thermal_high_node':3+2*index,'thermal_low_node':4+2*index,
            'source_component_ids':{ref:components[ref].get('id','') for ref in (terminal,high,low)}})
    if padnets('P4','1')!={'V_SUPPLY'} or padnets('P5','1')!={'GND'}:
        raise ValueError('Source supply terminals changed')
    return {'contract':'spike/vesc-source-bridge-binding/v1','board_occurrence_id':board_occurrence_id,
        'design_id':design['design_id'],'phases':proof,'supply_positive_reference':'P4',
        'supply_return_reference':'P5','phase_rotation_convention':'A=P6,B=P7,C=P9; motor terminal orientation still requires explicit physical mapping',
        'topology_verified':True,'firmware_executed':False,'hardware_calibrated':False,
        'model_scope':'averaged synchronous half bridges; source proof does not establish switching, deadtime, shunt values or real motor parameters',
        'source_inventory_sha256':hashlib.sha256(json.dumps(proof,sort_keys=True).encode()).hexdigest()}
