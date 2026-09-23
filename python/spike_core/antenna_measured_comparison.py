# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Power-defined exploratory antenna comparison without qualification promotion."""
import math


def evaluate_temporal_admission(solver_log, radiated_to_accepted_ratio):
    """Reject spectral comparison when FDTD stopped early or PEC power is unbalanced."""
    log=str(solver_log)
    checks={
        'complete_excitation':'Cutting to max number of timesteps' not in log,
        'temporal_decay_reached':'Max. number of timesteps was reached before the end-criteria' not in log,
        'execution_observed':'Time for ' in log and 'iterations with' in log,
        'pec_power_balance':isinstance(radiated_to_accepted_ratio,(int,float))
            and not isinstance(radiated_to_accepted_ratio,bool)
            and math.isfinite(radiated_to_accepted_ratio) and .95<=radiated_to_accepted_ratio<=1.05,
    }
    return {'status':'exploratory_only' if all(checks.values()) else 'failed_numerical_admission',
            'checks':checks,'measured_qualification':False,
            'geometry_matched':False,'pec_power_ratio_tolerance':.05}


def compare_forward_gain(*, radiation_intensity_w_sr, accepted_power_w,
                         radiated_power_w, measured_gain_dbd, dbd_to_dbi_db,
                         measurement_accuracy_db):
    values = (radiation_intensity_w_sr, accepted_power_w, radiated_power_w,
              measured_gain_dbd, dbd_to_dbi_db, measurement_accuracy_db)
    if any(isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) for v in values):
        raise ValueError('Finite scalar power and measurement inputs required')
    if min(radiation_intensity_w_sr, accepted_power_w, radiated_power_w, measurement_accuracy_db)<=0:
        raise ValueError('Powers and accuracy must be positive')
    gain=10*math.log10(4*math.pi*radiation_intensity_w_sr/accepted_power_w)
    directivity=10*math.log10(4*math.pi*radiation_intensity_w_sr/radiated_power_w)
    measured=measured_gain_dbd+dbd_to_dbi_db
    return {'accepted_power_gain_dbi':gain,'forward_directivity_dbi':directivity,
            'measured_gain_dbi':measured,'discrepancy_db':gain-measured,
            'radiated_to_accepted_power_ratio':radiated_power_w/accepted_power_w,
            'inside_reported_measurement_accuracy':abs(gain-measured)<=measurement_accuracy_db,
            'measured_qualification':False,
            'reason':'Agreement alone cannot establish matched geometry, convergence or combined uncertainty'}
