# SPDX-License-Identifier: Apache-2.0
"""Presentation categories only; device schemas remain backend-owned."""


def parameter_group(key):
    key=key.lower()
    if any(token in key for token in ('temperature','thermal','tnom')):
        return 'Thermal model'
    if key in {'cbe','cbc','cgs','cgd','cds','cgb','cbd','cbs','tf','tr','tt','cjo','cj','cjs','rs','rd','rg','rb','re'} or any(
            token in key for token in ('capacitance','inductance','transit_time','series_resistance','gate_resistance')):
        return 'Charge & parasitics'
    return 'Electrical'
