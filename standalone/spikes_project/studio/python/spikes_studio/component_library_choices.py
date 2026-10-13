# SPDX-License-Identifier: Apache-2.0
"""Exact-MPN selection adapters, not model qualification or invented coverage."""
from .manufacturer_parts import load_catalog
import re
from .fuzzy_search import ranked

FAMILIES={'resistor':{'resistor'},'termination':{'resistor'},'capacitor':{'capacitor'},'supercapacitor':{'capacitor'},'led':{'led'},'diode':{'diode'},'nmos_enhancement':{'mosfet'},'pmos_enhancement':{'mosfet'},'opamp_one_pole':{'operational_amplifier'},'comparator_ic':{'comparator'},'ntc':{'ntc_thermistor'},'ptc':{'ptc_resettable_fuse'},'fuse':{'fuse'}}


def matching_parts(family,text='',records=None):
    categories=FAMILIES.get(family,{family})
    records=load_catalog()['records'] if records is None else records
    logic_names={'nand':'NAND','nor':'NOR','not':'NOT','and':'AND','or':'OR','xor':'XOR'}
    def matches_category(r):
        if r['category'] in categories:return True
        if family=='instrumentation_amplifier' and r['category']=='instrumentation_amplifier':return True
        if family in ('npn','pnp') and r['category']=='bipolar_transistor':
            return re.search(r'\b'+family.upper()+r'\b',r['description'].upper()) is not None
        return (family in logic_names and r['category']=='logic_ic' and
                ('-channel '+logic_names[family]+' HC logic') in r['description'])
    rows=sorted([r for r in records if matches_category(r)],key=lambda r:(r['manufacturer'].casefold(),r['mpn'].casefold()))
    return ranked(rows,text,text=lambda r:' '.join((r['mpn'],r['manufacturer'],r['description'])))


def label(record):
    status='Ideal nominal approximation' if record['model']['readiness']=='placeable_ideal_nominal' else 'Model required'
    return f"{record['manufacturer']} · {record['mpn']} · {record['nominal']['label'] if record.get('nominal') else status} · {status}"
