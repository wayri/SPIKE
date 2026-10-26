# SPDX-License-Identifier: Apache-2.0
"""Explicit power-normalized mixed modes for sampled real-reference networks."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
from typing import Sequence

import numpy as np

from .sparameters import NetworkData


@dataclass(frozen=True)
class MixedModeNetwork:
    network: NetworkData
    port_mapping: tuple[dict, ...]


def mixed_mode_network(network: NetworkData, pairs: Sequence[Sequence[int]],
                       unpaired: Sequence[int] = (), *,
                       port_names: Sequence[str] | None = None) -> MixedModeNetwork:
    """Convert an exact zero-based port partition, ordered D, C, then unpaired.

    Each pair is (positive, negative); references must be equal within a pair.
    Different pairs may have different real references. No interpolation,
    renormalization, passivity repair or causality inference is performed.
    """
    raw = np.asarray(network.parameters)
    if (raw.ndim != 3 or raw.shape[1] != raw.shape[2] or not 1 <= raw.shape[1] <= 64
            or not 1 <= raw.shape[0] <= 32769 or raw.size > 4_194_304):
        raise ValueError('Network must have bounded sampled square matrices')
    count = raw.shape[1]
    frequencies = np.asarray(network.frequencies_hz)
    references = np.asarray(network.reference_impedance_ohm)
    for values, shape, label in ((frequencies, (raw.shape[0],), 'frequencies'),
                                  (references, (count,), 'references')):
        if (values.shape != shape or values.dtype.kind not in 'iuf'
                or not np.isfinite(values).all()):
            raise ValueError(f'Invalid real finite {label}')
    if np.any(frequencies < 0) or np.any(np.diff(frequencies) <= 0):
        raise ValueError('Frequencies must be nonnegative and strictly increasing')
    if np.any(references <= 0):
        raise ValueError('References must be positive')
    names = tuple(port_names) if port_names is not None else tuple(f'P{i+1}' for i in range(count))
    if (len(names) != count or any(not isinstance(n, str) or not n.strip() for n in names)
            or len(set(names)) != count):
        raise ValueError('Port names must be unique nonempty strings')
    ordered_pairs = tuple(tuple(pair) for pair in pairs)
    if not ordered_pairs or any(len(pair) != 2 for pair in ordered_pairs):
        raise ValueError('At least one ordered positive/negative pair is required')
    singles = tuple(unpaired)
    indices = tuple(i for pair in ordered_pairs for i in pair) + singles
    if (len(indices) != count or any(isinstance(i, (bool, np.bool_)) or not isinstance(i, Integral)
                                    for i in indices) or set(indices) != set(range(count))):
        raise ValueError('Pairs and unpaired ports must partition every port exactly once')
    transform = np.zeros((count, count))
    modes, refs = [], []
    for kind, sign in (('differential', -1), ('common', 1)):
        for pair_index, (positive, negative) in enumerate(ordered_pairs):
            if references[positive] != references[negative]:
                raise ValueError('Unequal within-pair references are unsupported')
            row = len(modes)
            transform[row, positive] = 1 / np.sqrt(2)
            transform[row, negative] = sign / np.sqrt(2)
            refs.append(float(references[positive]) * (2 if sign == -1 else .5))
            modes.append({'kind': kind, 'pair_index': pair_index,
                          'positive_port': int(positive), 'negative_port': int(negative),
                          'positive_name': names[positive], 'negative_name': names[negative]})
    for port in singles:
        transform[len(modes), port] = 1
        refs.append(float(references[port]))
        modes.append({'kind': 'single_ended', 'port': int(port), 'name': names[port]})
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        s = network.s_parameters()
        if s.shape != raw.shape or not np.isfinite(s).all():
            raise ValueError('Network contains invalid S parameters')
        converted = transform @ s @ transform.T
    if not np.isfinite(refs).all() or np.any(np.asarray(refs) <= 0):
        raise ValueError('Mode references are outside representable positive range')
    derived = NetworkData(frequencies.copy(), converted, np.array(refs), 'S', 'RI',
                          network.source, list(network.comments), list(network.warnings))
    derived.comments.append('Explicit mixed modes: D pairs, C pairs, then unpaired; zero-based mapping retained separately.')
    return MixedModeNetwork(derived, tuple(modes))
