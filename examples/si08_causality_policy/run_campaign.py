# SPDX-License-Identifier: Apache-2.0
"""Offline explicit preparation/constructed-model interpretation example."""
from copy import deepcopy

from python.spike_core.solvers.signal_integrity.networks.sparameter_sampling import resample_sparameter_network
from python.spike_core.solvers.signal_integrity.networks.sparameter_rational import fit_sparameter_rational, REQUEST_CONTRACT


def prepare_report(request, fit_controls=None):
    prepared = resample_sparameter_network(request)
    fitted = None
    if fit_controls is not None:
        if not isinstance(fit_controls, dict) or set(fit_controls) != {'pole_rates_rad_s', 'max_absolute_error'}:
            raise ValueError('Explicit existing rational fit controls required')
        fitted = fit_sparameter_rational({
            'contract': REQUEST_CONTRACT, 'source': deepcopy(prepared['derived_network']),
            **deepcopy(fit_controls)})
    return {'contract': 'spike/si08-causality-policy-report/v1',
            'prepared': prepared, 'constructed_fit': fitted,
            'interpretation': {
                'source_causality': 'unknown_from_finite_samples',
                'constructed_model_causality': fitted['model']['causality'] if fitted else 'not_constructed',
                'out_of_band_accuracy': 'not_qualified',
                'physical_qualified': False, 'production_qualified': False,
                'warning': 'A stable proper constructed model does not establish causality of the original source.'}}
