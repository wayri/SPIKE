# SPDX-License-Identifier: Apache-2.0
"""Independent series-capacitor sharing review; never automatic voltage uprating."""
import math


def review_series_capacitor_leg(request):
    if not isinstance(request, dict) or set(request) != {'contract', 'voltage_v', 'capacitors'} or request['contract'] != 'spike/series-capacitor-leg/v1':
        raise ValueError('PDN_SERIES_FIELDS: exact voltage and capacitor leg required')
    def number(value, name, positive=False):
        try:
            valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        except OverflowError:
            valid = False
        if not valid or value < 0 or value > 1e200 or (value > 0 and value < 1e-200) or (positive and value == 0):
            raise ValueError(f'PDN_SERIES_VALUE: invalid {name}')
        return float(value)
    voltage = number(request['voltage_v'], 'voltage')
    capacitors = request['capacitors']
    if not isinstance(capacitors, list) or not 2 <= len(capacitors) <= 32:
        raise ValueError('PDN_SERIES_RESOURCE: supply 2..32 capacitors')
    admitted, names = [], set()
    for c in capacitors:
        if not isinstance(c, dict) or set(c) != {'id', 'capacitance_f', 'tolerance_fraction', 'rated_voltage_v', 'leakage_resistance_ohm', 'balancing_resistance_ohm'}:
            raise ValueError('PDN_SERIES_FIELDS: exact individual capacitor parameters required')
        if not isinstance(c['id'], str) or not c['id'] or len(c['id']) > 80 or c['id'] in names:
            raise ValueError('PDN_SERIES_ID: unique bounded capacitor identities required')
        names.add(c['id'])
        cap = number(c['capacitance_f'], 'capacitance', True)
        tolerance = number(c['tolerance_fraction'], 'tolerance')
        if tolerance >= 1:
            raise ValueError('PDN_SERIES_VALUE: tolerance must be below one')
        rating = number(c['rated_voltage_v'], 'rated voltage', True)
        leak = None if c['leakage_resistance_ohm'] is None else number(c['leakage_resistance_ohm'], 'leakage resistance', True)
        balance = None if c['balancing_resistance_ohm'] is None else number(c['balancing_resistance_ohm'], 'balancing resistance', True)
        effective = None if leak is None else 1/(1/leak + (0 if balance is None else 1/balance))
        admitted.append((c['id'], cap, tolerance, rating, effective))
    inverse = [1/c[1] for c in admitted]
    inverse_sum = math.fsum(inverse)
    complete = all(c[4] is not None for c in admitted)
    resistance_sum = math.fsum(c[4] for c in admitted) if complete else None
    rows = []
    for i, (identity, cap, tolerance, rating, resistance) in enumerate(admitted):
        own = 1/(cap*(1-tolerance))
        others = math.fsum(1/(other[1]*(1+other[2])) for j, other in enumerate(admitted) if j != i)
        worst = voltage * (own/(own+others))
        dc = voltage*(resistance/resistance_sum) if complete else None
        rows.append({'id': identity, 'capacitive_nominal_voltage_v': voltage*(inverse[i]/inverse_sum),
                     'capacitive_worst_tolerance_voltage_v': worst, 'rated_voltage_v': rating,
                     'capacitive_rating_exceeded': worst > rating, 'modeled_dc_voltage_v': dc,
                     'modeled_dc_rating_exceeded': None if dc is None else dc > rating})
    values = [inverse_sum, *(r['capacitive_worst_tolerance_voltage_v'] for r in rows)]
    if not all(math.isfinite(v) and v >= 0 for v in values) or inverse_sum <= 0:
        raise ValueError('PDN_SERIES_VALUE: numerically unrepresentable leg')
    return {'contract': 'spike/series-capacitor-leg-result/v1', 'model_status': 'approximate',
            'equivalent_capacitance_f': 1/inverse_sum, 'voltage_v': voltage, 'capacitors': rows,
            'dc_leakage_model_complete': complete, 'automatic_voltage_uprating_permitted': False,
            'limits': ['Capacitive division assumes zero initial charge, no parallel parasitics and linear C.',
                       'DC estimates require every leakage resistance; provided values are nominal, not certified bounds.',
                       'Balancing resistors do not remove unknown leakage, temperature, bias or aging uncertainty.',
                       'Use explicit intermediate nodes and balancing resistors in the AC/transient model.']}
