# SPDX-License-Identifier: Apache-2.0
"""Sourced HC package facts; digital execution is separate from circuit readiness."""
from python.spikes.standard_logic import catalog


def records():
    result = []
    for item in catalog():
        result.append({'id': 'ti.'+item['part'].lower(), 'manufacturer': 'Texas Instruments',
            'mpn': item['part'], 'category': 'logic_ic',
            'description': f"{len(item['gates'])}-channel {item['family'].upper()} HC logic; functional model available via standard_logic API",
            'nominal': {'value': len(item['gates']), 'unit': 'count', 'label': f"{len(item['gates'])} gates"},
            'tolerance': {'kind': 'not_applicable', 'display': 'Digital function; not a tolerance specification'},
            'ratings': [{'name': 'recommended_supply', 'value': [2, 6], 'unit': 'V',
                         'condition': 'Recommended operating supply', 'qualifier': 'datasheet'}],
            'package': item['package'], 'pins': item['pins'],
            'model': {'kind': 'functional_digital_only', 'readiness': 'vendor_model_required',
                      'limitations': item['limitations']+' Native circuit placement is not enabled.'},
            'source': {'url': item['source_url'], 'accessed_on': item['accessed_on'],
                       'document': 'TI SNx4HC'+item['part'][6:8]+' datasheet, 14-pin package',
                       'fields': ['identity', 'Boolean function', '14-pin numbering', 'supply range']}})
    return result
