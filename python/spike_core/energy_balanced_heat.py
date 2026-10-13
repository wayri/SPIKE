# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original first-law reduction of resolved multi-terminal device samples.

Each port uses passive-sign voltage/current. Piecewise-linear port signals
give quadratic terminal power. Stored energy is independently supplied and
piecewise linear: heat = sum(v*i) - dE/dt. This is a resolved-data bridge,
not a semiconductor equation, SPICE parser or switching-event inference.
"""
import math
from fractions import Fraction


def _exact_interval(samples, j, left, right, energy):
    """Sign of the aggregate heat polynomial for exact supplied binary floats.

    No product underflow or nearly coincident roots may erase negative heat.
    For q(x)=a+b*x+c*x² on [0,1], test endpoints and, for an interior
    convex minimum, 4*a*c-b². Integrate rational coefficients before conversion
    to prevent intermediate underflow; the published J/W remain finite floats.
    """
    a = b = c = Fraction(0)
    for voltage, current in samples:
        v, i = Fraction(voltage[j]), Fraction(current[j])
        dv = Fraction(voltage[j+1])-v
        di = Fraction(current[j+1])-i
        a += v*i
        b += v*di+i*dv
        c += dv*di
    duration = Fraction(right)-Fraction(left)
    terminal = duration*(a+b/2+c/3)
    change = Fraction(energy[j+1])-Fraction(energy[j])
    a -= change/duration
    if a < 0 or a+b+c < 0:
        return None
    if c > 0 and -2*c < b < 0 and 4*a*c-b*b < 0:
        return None
    return terminal, terminal-change


def evaluate_energy_balanced_heat(model, temperature_k):
    # Shared validation remains owned by the public heat-source boundary.
    from .electrical_heat_sources import (
        _keys, _require, _array, _ascending, _sum, _finite,
    )
    _keys(model, ('kind', 'time_s', 'ports', 'stored_energy_j', 'energy_policy'), 'energy balance model')
    _require(model['kind'] == 'energy_balanced_terminal_waveform',
             'unsupported_model', 'Unsupported energy-balanced model kind.')
    _require(model['energy_policy'] == 'passive_ports_minus_stored_energy',
             'energy_policy', 'Require passive-sign ports and complete stored energy.')
    times = _array(model['time_s'], 'time_s', 2, True)
    energy = _array(model['stored_energy_j'], 'stored_energy_j', 2, True)
    _ascending(times, 'time_s')
    _require(len(energy) == len(times), 'array_length', 'Stored energy and time must align.')
    ports = model['ports']
    _require(isinstance(ports, list) and 1 <= len(ports) <= 64,
             'port_budget', 'Require 1..64 device ports.')
    _require(len(ports)*len(times) <= 100000, 'array_budget', 'Total port sample budget exceeded.')
    samples, seen = [], set()
    for port in ports:
        _keys(port, ('id', 'voltage_v', 'current_a'), 'port')
        pid = port['id']
        _require(isinstance(pid, str) and 0 < len(pid) <= 256 and pid.strip(),
                 'invalid_text', 'Require a nonblank bounded port id.')
        _require(pid not in seen, 'duplicate_port', 'Duplicate port id.')
        seen.add(pid)
        voltage = _array(port['voltage_v'], 'voltage_v', 2)
        current = _array(port['current_a'], 'current_a', 2)
        _require(len(voltage) == len(current) == len(times), 'array_length', 'Port samples must align.')
        samples.append((voltage, current))
    heat, terminal = [], []
    exact_total = Fraction(0)
    for j, (left, right) in enumerate(zip(times, times[1:])):
        integrated = _exact_interval(samples, j, left, right, energy)
        _require(integrated is not None,
                 'nondissipative_power',
                 'Negative heat within an interval: incomplete energy ledger or unresolved sampling.')
        try:
            input_j, heat_j = map(float, integrated)
        except OverflowError as exc:
            from .electrical_heat_sources import ElectricalHeatSourceError
            raise ElectricalHeatSourceError('numeric_range', 'Energy integration overflowed.') from exc
        _require(math.isfinite(input_j), 'numeric_range', 'Terminal energy overflowed.')
        _require(not (input_j == 0 and integrated[0] != 0) and
                 not (heat_j == 0 and integrated[1] != 0),
                 'numeric_range', 'Nonzero interval energy is below the representable range.')
        terminal.append(input_j)
        heat.append(_finite(heat_j, 'interval heat'))
        exact_total += integrated[1]
    total = _sum(heat, 'heat energy')
    duration = times[-1]-times[0]
    try:
        terminal_total = math.fsum(terminal)
    except OverflowError as exc:
        from .electrical_heat_sources import ElectricalHeatSourceError
        raise ElectricalHeatSourceError('numeric_range', 'Terminal energy sum overflowed.') from exc
    _require(math.isfinite(terminal_total), 'numeric_range', 'Terminal energy sum is not representable.')
    try:
        average = float(exact_total/(Fraction(times[-1])-Fraction(times[0])))
    except OverflowError as exc:
        from .electrical_heat_sources import ElectricalHeatSourceError
        raise ElectricalHeatSourceError('numeric_range', 'Average heat overflowed.') from exc
    _require(not (average == 0 and exact_total != 0), 'numeric_range',
             'Positive average heat is below the representable range.')
    return {'average_power_w': _finite(average, 'average heat'),
            'total_energy_j': total, 'interval_energy_j': heat, 'duration_s': duration,
            'terminal_energy_j': terminal_total,
            'stored_energy_change_j': energy[-1]-energy[0],
            'temporal_scope': 'steady_average_only', 'temperature_dependence': 'none_supplied',
            'limitations': ['Resolved passive-sign port samples and complete stored-energy history are caller supplied.',
                            'No arbitrary device equations or unsampled events; averaged heat only.']}
