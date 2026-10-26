# SPDX-License-Identifier: Apache-2.0
"""Experimental attached-flow, no-swirl annular BEM hover reference.

Returns geometry-derived quasi-steady reaction loads, not resolved blade CFD.
See docs/validation/PROPULSION_POD_PROPELLER_DERIVATION_20261023.md.
"""
from bisect import bisect_right
from functools import lru_cache
import hashlib
import json
import math

CONTRACT = 'spike/hover-bem-propeller/v1'
RESULT_CONTRACT = 'spike/hover-bem-propeller-result/v1'
_KEYS = {'contract', 'blade_count', 'radial_stations_m', 'chord_m', 'twist_rad',
         'density_kg_m3', 'dynamic_viscosity_pa_s', 'speed_of_sound_m_s', 'polar',
         'radial_cells', 'relative_tolerance', 'max_iterations'}


def _number(value, name, *, positive=False):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError(f'{name}: finite real number required')
    value = float(value)
    if positive and value <= 0:
        raise ValueError(f'{name}: positive value required')
    return value


def _interpolate(stations, values, radius):
    i = min(len(stations)-2, max(0, bisect_right(stations, radius)-1))
    weight = (radius-stations[i])/(stations[i+1]-stations[i])
    return values[i]*(1-weight)+values[i+1]*weight


def _induction(radius, chord, theta, blades, slope, cd, tol, maximum):
    """Unique nonnegative root x=vi/(omega*r); density/speed cancel analytically."""
    def terms(x):
        blade = .5*blades*chord*math.sqrt(1+x*x)*(slope*(theta-math.atan(x))-cd*x)
        momentum = 4*math.pi*radius*x*x
        return blade, momentum
    low, high = 0., math.tan(theta)
    for iteration in range(1, maximum+1):
        x = .5*(low+high)
        blade, momentum = terms(x)
        residual = blade-momentum
        scale = max(abs(blade), momentum)
        relative = abs(residual)/scale if scale else 0.
        if relative <= tol:
            return x, relative, iteration
        if residual > 0:
            low = x
        else:
            high = x
    raise ValueError('BEM annular momentum root failed to converge; no loads accepted')


@lru_cache(maxsize=64)
def _prepare(canonical):
    spec = json.loads(canonical)
    if set(spec) != _KEYS or spec['contract'] != CONTRACT:
        raise ValueError('Unexpected/missing hover BEM request fields or contract')
    blades, cells = spec['blade_count'], spec['radial_cells']
    maximum = spec['max_iterations']
    if type(blades) is not int or not 1 <= blades <= 12:
        raise ValueError('blade_count must be an integer in [1,12]')
    if type(cells) is not int or not 4 <= cells <= 1024:
        raise ValueError('radial_cells must be an integer in [4,1024]')
    if type(maximum) is not int or not 1 <= maximum <= 160:
        raise ValueError('max_iterations must be an integer in [1,160]')
    tol = _number(spec['relative_tolerance'], 'relative_tolerance', positive=True)
    if not 1e-13 <= tol <= 1e-6:
        raise ValueError('relative_tolerance must lie in [1e-13,1e-6]')
    arrays = []
    for name in ('radial_stations_m', 'chord_m', 'twist_rad'):
        raw = spec[name]
        if not isinstance(raw, list) or not 2 <= len(raw) <= 256:
            raise ValueError(f'{name}: 2..256 explicit stations required')
        arrays.append([_number(x, name, positive=True) for x in raw])
    stations, chords, twists = arrays
    if len(chords) != len(stations) or len(twists) != len(stations):
        raise ValueError('Radius/chord/twist arrays must have equal lengths')
    if any(b <= a for a, b in zip(stations, stations[1:])):
        raise ValueError('Radial stations must strictly increase')
    if stations[0] < 1e-6 or stations[-1] > 100 or stations[-1]/stations[0] > 100:
        raise ValueError('Experimental radius range or hub ratio exceeded')
    polar = spec['polar']
    if not isinstance(polar, dict) or set(polar) != {'lift_slope_per_rad', 'drag_coefficient',
            'alpha_valid_rad', 'reynolds_valid', 'source'}:
        raise ValueError('Explicit linear attached polar and provenance required')
    slope = _number(polar['lift_slope_per_rad'], 'lift slope', positive=True)
    cd = _number(polar['drag_coefficient'], 'drag coefficient')
    if not 0 < slope <= 10 or not 0 <= cd <= .2:
        raise ValueError('Linear polar slope/drag outside experimental bounds')
    if not isinstance(polar['source'], str) or not polar['source'].strip() or len(polar['source']) > 2048:
        raise ValueError('Polar source/assumption description required')
    bounds = []
    for name in ('alpha_valid_rad', 'reynolds_valid'):
        raw = polar[name]
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError(f'{name}: [lower,upper] required')
        a, b = [_number(x, name) for x in raw]
        if not 0 <= a < b:
            raise ValueError(f'{name}: nonnegative ordered bounds required')
        bounds.append((a, b))
    alpha_bounds, reynolds_bounds = bounds
    # Every bisection trial stays in this declared attached polar range.
    if alpha_bounds[0] != 0 or max(twists) > min(.3, alpha_bounds[1]) or max(twists)*slope > 1.5:
        raise ValueError('Twist/linear lift exceeds attached polar or experimental small-angle gate')
    for radius, chord in zip(stations, chords):
        if blades*chord/(2*math.pi*radius) > .3:
            raise ValueError('Local solidity exceeds experimental 0.3 gate')
    rho = _number(spec['density_kg_m3'], 'density', positive=True)
    viscosity = _number(spec['dynamic_viscosity_pa_s'], 'viscosity', positive=True)
    sound = _number(spec['speed_of_sound_m_s'], 'speed of sound', positive=True)
    dr = (stations[-1]-stations[0])/cells
    rings = []
    for i in range(cells):
        radius = stations[0]+(i+.5)*dr
        chord = _interpolate(stations, chords, radius)
        theta = _interpolate(stations, twists, radius)
        x, residual, iteration = _induction(radius, chord, theta, blades, slope, cd, tol, maximum)
        phi = math.atan(x)
        rings.append((radius, chord, theta, x, phi, slope*(theta-phi), residual, iteration))
    return spec, tuple(rings), dr, rho, viscosity, sound, reynolds_bounds


def evaluate_propeller(spec, omega_rad_s):
    """Return positive resisting torque and positive-axis thrust for omega >= 0.

    Negative rotation, axial advance, stalled/extrapolated polars, tip Mach>0.3,
    invalid roots and nonrepresentable derived values raise ValueError. No
    partially successful loads are returned. Returned radial flow is annular
    actuator-disk evidence, not a sampled 3-D CFD velocity field.
    """
    if not isinstance(spec, dict):
        raise ValueError('Propeller spec must be an object')
    try:
        canonical = json.dumps(spec, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError('Finite JSON propeller specification required') from exc
    if len(canonical.encode()) > 128_000:
        raise ValueError('Propeller request exceeds128kB')
    request, rings, dr, rho, viscosity, sound, reynolds_bounds = _prepare(canonical)
    omega = _number(omega_rad_s, 'omega_rad_s')
    if omega < 0:
        raise ValueError('Negative rotation is unsupported; mirror geometry and axis in a separate request')
    if omega*request['radial_stations_m'][-1]/sound > .3:
        raise ValueError('Tip Mach exceeds incompressible experimental0.3 gate')
    blades = request['blade_count']
    cd = request['polar']['drag_coefficient']
    radial, thrusts, torques, induced_terms, profile_terms = [], [], [], [], []
    for radius, chord, theta, x, phi, cl, residual, iteration in rings:
        tangential = omega*radius
        axial = x*tangential
        speed = math.hypot(tangential, axial)
        reynolds = rho*speed*chord/viscosity
        mach = speed/sound
        if omega and (not reynolds_bounds[0] <= reynolds <= reynolds_bounds[1] or mach > .3):
            raise ValueError('Annulus Reynolds/Mach outside supplied polar or incompressible gate')
        dynamic = .5*rho*speed*speed
        lift = dynamic*blades*chord*cl*dr
        drag = dynamic*blades*chord*cd*dr
        thrust = lift*math.cos(phi)-drag*math.sin(phi)
        torque = radius*(lift*math.sin(phi)+drag*math.cos(phi))
        area = 2*math.pi*radius*dr
        momentum_thrust = 2*rho*area*axial*axial
        induced = thrust*axial
        profile = drag*speed
        mass_flow = rho*area*axial
        far_wake_power = .5*mass_flow*(2*axial)**2
        if not all(math.isfinite(v) for v in (reynolds, mach, thrust, torque, induced, profile, mass_flow, far_wake_power)):
            raise ValueError('Propeller derived values exceed numerical range')
        if omega and (thrust <= 0 or torque <= 0 or momentum_thrust <= 0):
            raise ValueError('Positive-speed force underflow or nonpositive branch rejected')
        thrusts.append(thrust); torques.append(torque)
        induced_terms.append(induced); profile_terms.append(profile)
        radial.append({'radius_m':radius, 'width_m':dr, 'disk_area_m2':area,
            'chord_m':chord, 'twist_rad':theta, 'alpha_rad':theta-phi if omega else theta,
            'inflow_angle_rad':phi if omega else 0., 'lift_coefficient':cl if omega else 0.,
            'disk_axial_velocity_m_s':axial, 'far_wake_axial_velocity_m_s':2*axial,
            'relative_speed_m_s':speed, 'reynolds':reynolds, 'mach':mach,
            'thrust_n':thrust, 'torque_nm':torque, 'momentum_thrust_n':momentum_thrust,
            'induced_power_w':induced, 'profile_drag_power_w':profile,
            'far_wake_kinetic_power_w':far_wake_power, 'mass_flow_kg_s':mass_flow,
            'root_relative_residual':residual if omega else 0., 'root_iterations':iteration if omega else 0})
    thrust = math.fsum(thrusts); torque = math.fsum(torques)
    power = torque*omega
    induced = math.fsum(induced_terms); profile = math.fsum(profile_terms)
    scale = max(power, induced+profile)
    defect = abs(power-induced-profile)/scale if scale else 0.
    active_area = math.pi*(request['radial_stations_m'][-1]**2-request['radial_stations_m'][0]**2)
    ideal_power = thrust*math.sqrt(thrust/(2*rho*active_area)) if thrust else 0.
    residual = max((r['root_relative_residual'] for r in radial), default=0.)
    tol = request['relative_tolerance']
    if not all(math.isfinite(v) for v in (thrust, torque, power, induced, profile, ideal_power)):
        raise ValueError('Aggregate propeller values exceed numerical range')
    if defect > max(10*tol, 1e-12) or induced < ideal_power*(1-10*tol):
        raise ValueError('Propeller reduced energy identity or ideal-wake bound failed')
    return {'contract':RESULT_CONTRACT, 'status':'completed', 'model_status':'experimental',
        'production_qualified':False, 'model':'hover_annular_bem_attached_linear_polar_no_swirl',
        'omega_rad_s':omega, 'torque_nm':torque, 'thrust_n':thrust, 'power_w':power,
        'induced_power_w':induced, 'profile_drag_power_w':profile,
        'ideal_uniform_active_disk_power_w':ideal_power, 'active_disk_area_m2':active_area,
        'relative_energy_residual':defect, 'maximum_momentum_relative_residual':residual,
        'radial_airflow':radial, 'spec_sha256':hashlib.sha256(canonical.encode()).hexdigest(),
        'validity':{'attached_polar':True, 'polar_source':request['polar']['source'],
            'resolved_cfd':False, 'wake_swirl_resolved':False, 'angular_momentum_wake_verified':False,
            'quasi_steady':True, 'axis_convention':'positive thrust along declared propeller axis; positive torque resists positive motor rotation'},
        'limitations':['Hover in unbounded still air only; no chamber/stand/ground/rotor interference',
            'Annular no-swirl actuator disk and supplied linear lift/constant drag, not blade-resolved CFD',
            'No tip/root-loss correction, wake swirl, dynamic inflow, stall, compressibility or measured qualification',
            'Profile drag power is aerodynamic dissipation; it is not mapped to motor or structure heat',
            'Cached dimensionless annular roots depend only on exact unchanged geometry/polar controls; instantaneous loads use actual omega/fluid inputs']}
