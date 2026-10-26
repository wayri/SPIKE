# SPDX-License-Identifier: Apache-2.0
"""Retained neutral export for the finite offline SI08 interoperability campaign."""
from __future__ import annotations

import hashlib
import json

from python.spike_core.solvers.signal_integrity.networks.sparameters import parse_touchstone_text
from python.spike_core.solvers.signal_integrity.networks.sparameter_modes import mixed_mode_network


def capture(text, filename, names, pairs, unpaired=()):
    """Compose existing owners; names are explicit companion metadata, never guessed.

    Mixed differential/common references generally differ, so export neutral JSON
    with per-port references instead of silently flattening them for Touchstone1.
    This is an offline example, not a new worker or instrument contract.
    """
    source = parse_touchstone_text(text, filename)
    converted = mixed_mode_network(source, pairs, unpaired, port_names=names)
    network = converted.network
    result = {
        'contract': 'spike/si08-interoperability-capture/v1',
        'source': {'filename': filename, 'text': text,
                   'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                   'port_names': list(names)},
        'operation': {'pairs': [list(pair) for pair in pairs], 'unpaired': list(unpaired)},
        'port_mapping': list(converted.port_mapping),
        'derived_network': {
            'frequencies_hz': network.frequencies_hz.tolist(),
            'reference_impedance_ohm': network.reference_impedance_ohm.tolist(),
            'wave_convention': 'power_normalized_positive_real_reference',
            'matrix_order': 'receiver_source',
            's_parameters': [[[[float(z.real), float(z.imag)] for z in row]
                              for row in sample] for sample in network.parameters]},
        'source_causality': 'unknown', 'physical_qualified': False,
        'production_qualified': False,
    }
    return json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False)
