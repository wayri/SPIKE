# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original bounded laminar parallel-plate channel reference; see INTERNAL_AIRFLOW.md.

Momentum is the analytical fully developed solution. Transverse finite volumes
and backward/upwind axial marching solve rho*cp*u*T_x = k*T_yy. No turbulence,
buoyancy, entrance momentum, axial diffusion or solid CHT is inferred.
"""
import copy
import math

import numpy as np

from .assembly_field_handoff import bounded_json
from .multiboard_identity import canonical_json_digest

REQUEST_CONTRACT = 'spike/internal-channel-airflow-request/v1'
RESULT_CONTRACT = 'spike/internal-channel-airflow-result/v1'
MAX_FIELD_VALUES = 100000


def _require(condition, message):
    if not condition:
        raise ValueError('INTERNAL_AIRFLOW: ' + message)


def _keys(value, expected):
    _require(isinstance(value, dict) and set(value) == set(expected),
             'Unexpected or missing request fields.')


def _number(value, label, positive=True):
    _require(type(value) in (int, float), label + ' must be a finite number.')
    try:
        value = float(value)
    except OverflowError as exc:
        raise ValueError('INTERNAL_AIRFLOW: Unrepresentable ' + label) from exc
    _require(math.isfinite(value) and (not positive or value > 0),
             label + ' is outside the finite physical range.')
    return value


def _admit(request):
    bounded_json(request)
    _keys(request, ('contract', 'geometry', 'fluid', 'operating', 'mesh'))
    _require(request['contract'] == REQUEST_CONTRACT, 'Unknown request contract.')
    _keys(request['geometry'], ('length_m', 'gap_m', 'span_m'))
    _keys(request['fluid'], ('density_kg_m3', 'specific_heat_j_kgk',
                           'thermal_conductivity_w_mk', 'dynamic_viscosity_pa_s'))
    _keys(request['operating'], ('mean_velocity_m_s', 'inlet_temperature_k',
                               'lower_wall_heat_flux_w_m2', 'upper_wall_heat_flux_w_m2'))
    _keys(request['mesh'], ('axial_cells', 'transverse_cells'))
    geometry = [_number(request['geometry'][k], k) for k in ('length_m', 'gap_m', 'span_m')]
    fluid = [_number(request['fluid'][k], k) for k in ('density_kg_m3', 'specific_heat_j_kgk',
             'thermal_conductivity_w_mk', 'dynamic_viscosity_pa_s')]
    operating = [_number(request['operating'][k], k, positive='heat_flux' not in k)
                 for k in ('mean_velocity_m_s', 'inlet_temperature_k',
                           'lower_wall_heat_flux_w_m2', 'upper_wall_heat_flux_w_m2')]
    nx, ny = (request['mesh'][k] for k in ('axial_cells', 'transverse_cells'))
    _require(type(nx) is int and type(ny) is int and 2 <= nx <= 1000 and 3 <= ny <= 200
             and nx * ny <= MAX_FIELD_VALUES, 'Mesh budget: nx 2..1000, ny 3..200, nx*ny <= 100000.')
    return geometry, fluid, operating, nx, ny


def run_internal_airflow(request, *, cancel_check=None):
    """Return original solved channel fields in SI; raises on any failed admission.

    x_m contains downstream marching stations, y_m transverse cell centers.
    temperature_k is indexed [axial station][transverse cell]. Span is an ideal
    extrusion extent for heat/mass totals; no sidewall or finite-width flow.
    """
    def cancel():
        _require(cancel_check is None or not cancel_check(), 'Cancelled.')

    cancel()
    geometry, fluid, operating, nx, ny = _admit(request)
    length, gap, span = geometry
    rho, cp, conductivity, viscosity = fluid
    speed, inlet, lower, upper = operating
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise'):
            re = rho * speed * (2 * gap) / viscosity
            pe = rho * cp * speed * length / conductivity
            _require(math.isfinite(re) and math.isfinite(pe) and 0 < re <= 1000 and pe >= 10,
                     'Screening envelope requires 0 < Re_Dh <= 1000 and Pe_length >= 10.')
            dx, dy = length / nx, gap / ny
            eta = (np.arange(ny) + .5) / ny
            # Exact cell average of 6*U*eta*(1-eta), avoiding primitive cancellation.
            velocity = 6 * speed * (eta * (1 - eta) - 1 / (12 * ny * ny))
            mass = rho * velocity * dy * span
            capacity_flow = cp * mass
            diffusion = conductivity * dx * span / dy
            diagonal = capacity_flow + 2 * diffusion
            diagonal[[0, -1]] -= diffusion
            _require(np.isfinite(diagonal).all() and np.all(capacity_flow > 0)
                     and np.min(capacity_flow) > 1e-12 * np.max(diagonal),
                     'Nonrepresentable or ill-conditioned channel coefficients.')
            source = np.zeros(ny)
            source[0], source[-1] = lower * dx * span, upper * dx * span
            _require(np.isfinite(source).all(), 'Nonrepresentable wall heat input.')
            # Independently derived tridiagonal elimination; pivots are positive
            # for this strictly diagonally dominant M-matrix.
            pivots = diagonal.copy()
            factors = np.zeros(ny)
            for j in range(1, ny):
                factors[j] = -diffusion / pivots[j - 1]
                pivots[j] += factors[j] * diffusion
            _require(np.isfinite(pivots).all() and np.all(pivots > 0), 'Invalid channel pivots.')
            rise = np.zeros((nx, ny))
            previous = np.zeros(ny)
            maximum_residual = 0.
            for i in range(nx):
                cancel()
                rhs = capacity_flow * previous + source
                for j in range(1, ny):
                    rhs[j] -= factors[j] * rhs[j - 1]
                current = np.empty(ny)
                current[-1] = rhs[-1] / pivots[-1]
                for j in range(ny - 2, -1, -1):
                    current[j] = (rhs[j] + diffusion * current[j + 1]) / pivots[j]
                residual = capacity_flow * (current - previous) - source
                exchange = diffusion * np.diff(current)
                residual[:-1] -= exchange
                residual[1:] += exchange
                maximum_residual = max(maximum_residual, float(np.max(np.abs(residual))))
                rise[i] = current
                previous = current
            temperatures = inlet + rise
            lower_wall = temperatures[:, 0] + lower * dy / (2 * conductivity)
            upper_wall = temperatures[:, -1] + upper * dy / (2 * conductivity)
            _require(np.isfinite(temperatures).all() and np.isfinite(lower_wall).all()
                     and np.isfinite(upper_wall).all() and np.min(temperatures) > 0
                     and np.min(lower_wall) > 0 and np.min(upper_wall) > 0,
                     'Computed fluid/wall temperature is nonfinite or below absolute zero.')
            flow = float(np.sum(mass))
            gain = float(capacity_flow @ rise[-1])
            wall_input = (lower + upper) * length * span
            heat_scale = max((abs(lower) + abs(upper)) * length * span, abs(gain), 1e-30)
            arithmetic_floor = 256 * np.finfo(float).eps * nx * ny * float(np.max(diagonal)) * max(
                float(np.max(np.abs(rise))), 1e-30)
            tolerance = float(1e-9 * heat_scale + arithmetic_floor)
            imbalance = wall_input - gain
            _require(math.isfinite(tolerance) and abs(imbalance) <= tolerance,
                     'Global coolant energy balance failed.')
            residual_tolerance = 1e-10 * heat_scale + arithmetic_floor / nx
            _require(maximum_residual <= residual_tolerance, 'Channel equation residual failed.')
            ideal_flow = rho * speed * gap * span
            mass_error = abs(flow - ideal_flow)
            _require(0 < flow and math.isfinite(flow) and mass_error <= 1e-12 * ideal_flow,
                     'Channel mass conservation failed.')
            pressure_drop = 12 * viscosity * speed * length / gap**2
            _require(math.isfinite(pressure_drop) and pressure_drop > 0,
                     'Pressure drop is not representable.')
            result = {'contract': RESULT_CONTRACT, 'status': 'experimental', 'model_status': 'experimental',
                'production_qualified': False, 'flow_regime': 'laminar_prescribed', 'turbulence_model': 'none',
                'request_digest': canonical_json_digest(request), 'units': 'SI',
                'request_snapshot': copy.deepcopy(request),
                'field_location': 'downstream_axial_station_by_transverse_cell',
                'inlet_temperature_k': inlet, 'x_m': ((np.arange(nx) + 1) * dx).tolist(),
                'y_m': (eta * gap).tolist(), 'velocity_u_m_s': velocity.tolist(),
                'temperature_k': temperatures.tolist(),
                'bulk_temperature_k': (inlet + rise @ capacity_flow / float(np.sum(capacity_flow))).tolist(),
                'wall_temperature_k': {'lower': lower_wall.tolist(), 'upper': upper_wall.tolist()},
                'mass_flow_kg_s': flow, 'pressure_drop_pa': pressure_drop,
                'reynolds_hydraulic': re, 'peclet_length': pe,
                'heat_balance': {'wall_input_w': wall_input, 'coolant_enthalpy_gain_w': gain,
                    'imbalance_w': imbalance, 'relative_imbalance': abs(imbalance) / heat_scale,
                    'acceptance_tolerance_w': tolerance},
                'diagnostics': {'maximum_equation_residual_w': maximum_residual,
                    'maximum_mass_imbalance_kg_s': mass_error,
                    'maximum_temperature_rise_k': max(0., float(np.max(temperatures)) - inlet,
                        float(np.max(lower_wall)) - inlet, float(np.max(upper_wall)) - inlet),
                    'maximum_absolute_temperature_change_k': max(float(np.max(np.abs(rise))),
                        float(np.max(np.abs(lower_wall - inlet))), float(np.max(np.abs(upper_wall - inlet)))),
                    'omitted_viscous_heating_rise_k': pressure_drop / (rho * cp),
                    'mesh_convergence_verified': False, 'axial_scheme': 'first_order_upwind',
                    'transverse_scheme': 'centered_finite_volume'},
                'resources': {'axial_cells': nx, 'transverse_cells': ny, 'field_values': nx * ny,
                              'maximum_field_values': MAX_FIELD_VALUES},
                'limitations': ['ideal parallel plates with prescribed fully developed laminar velocity',
                    'constant properties and prescribed uniform wall heat flux; no solid CHT or assembly geometry',
                    'user must justify constant properties over the full computed fluid/wall temperature range',
                    'no turbulence, buoyancy, recirculation, entrance momentum or finite-span sidewalls',
                    'axial diffusion, viscous heating, pressure-work heating and radiation omitted',
                    'Re/Pe admission is a screening envelope, not proof of applicability to hardware',
                    'wall temperature uses a half-cell linear reconstruction; mesh refinement required',
                    'no measured validation, independent external CFD comparison or production qualification']}
    except (FloatingPointError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError('INTERNAL_AIRFLOW: Numerical range exceeded.') from exc
    cancel()
    result['result_digest'] = canonical_json_digest(result)
    bounded_json(result)
    return copy.deepcopy(result)
