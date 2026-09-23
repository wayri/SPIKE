"""Published E6/E12/E24 preferred values, not rounded geometric approximations."""
import math
E24=(10,11,12,13,15,16,18,20,22,24,27,30,33,36,39,43,47,51,56,62,68,75,82,91)
SERIES={'E6':(10,15,22,33,47,68),'E12':(10,12,15,18,22,27,33,39,47,56,68,82),'E24':E24}


def recommend(value,series='E24'):
    if not math.isfinite(value) or not 1e-18<=value<=1e18:raise ValueError('Enter a positive passive value between 1e-18 and 1e18 SI')
    if series not in SERIES:raise ValueError('Choose E6, E12 or E24')
    exponent=math.floor(math.log10(value))-1
    candidates=sorted({float(f'{base*10.0**power:.12g}') for power in range(exponent-1,exponent+2) for base in SERIES[series]})
    low=max(v for v in candidates if v<=value);high=min(v for v in candidates if v>=value)
    nearest=min((low,high),key=lambda v:abs(v-value))
    return {'lower':low,'nearest':nearest,'upper':high,'error_percent':100*(nearest-value)/value}
