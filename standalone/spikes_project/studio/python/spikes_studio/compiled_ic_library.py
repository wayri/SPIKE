# SPDX-License-Identifier: Apache-2.0
"""Data-only library of generic sampled C controller configurations.

Loading a library never compiles or executes its source.  Returned configurations
use the existing ``spikes/generic-controller/v1`` contract and still require the
caller's explicit trusted-code consent before :class:`Controller` can compile.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import re

from .controller_block import CONTRACT as CONTROLLER_CONTRACT, validate as validate_controller
from .document import write_json


CONTRACT = 'spikes/compiled-ic-library/v1'
MAX_BYTES = 1024 * 1024
_ID = re.compile(r'[a-z][a-z0-9_.-]{0,63}\Z')
_TOKEN = re.compile(r'@[A-Z][A-Z0-9_]{0,63}@')


_PWM_SOURCE = '''void control_step(double time_s, double step_s, const double *inputs,
                  double *outputs, double *state) {
    (void)time_s;
    (void)step_s;
    const double period_ticks = @PERIOD_TICKS@;
    double phase_tick = state[0];
    double duty = inputs[IN_duty];
    if (duty < 0.0) duty = 0.0;
    if (duty > 1.0) duty = 1.0;
    if (!(phase_tick >= 0.0 && phase_tick < period_ticks && phase_tick == floor(phase_tick))) phase_tick = 0.0;
    outputs[OUT_drive] = inputs[IN_enable] >= 0.5 && phase_tick < duty * period_ticks ? 1.0 : 0.0;
    phase_tick += 1.0;
    if (phase_tick >= period_ticks) phase_tick = 0.0;
    state[0] = phase_tick;
}
'''

_PI_SOURCE = '''void control_step(double time_s, double step_s, const double *inputs,
                  double *outputs, double *state) {
    (void)time_s;
    const double error = inputs[IN_reference] - inputs[IN_feedback];
    double integral = state[0] + @KI_PER_S@ * step_s * error;
    double command = @KP@ * error + integral;
    if (command > @OUTPUT_MAX_V@) {
        command = @OUTPUT_MAX_V@;
        if (error > 0.0) integral = state[0];
    } else if (command < @OUTPUT_MIN_V@) {
        command = @OUTPUT_MIN_V@;
        if (error < 0.0) integral = state[0];
    }
    state[0] = integral;
    outputs[OUT_command] = command;
}
'''


def _parameter(name, default, minimum, maximum, unit, description):
    return {'name': name, 'default': default, 'minimum': minimum, 'maximum': maximum,
            'unit': unit, 'description': description}


_ENTRIES = (
    {
        'id': 'generic.sampled_pwm', 'version': '1.0.0', 'name': 'Generic sampled PWM',
        'description': 'Fixed-period, edge-aligned sampled PWM with an explicit phase state.',
        'language': 'C', 'sampled_only': True,
        'parameters': [
            _parameter('sample_period_s', 1e-4, 1e-12, 1.0, 's', 'Controller invocation period.'),
            _parameter('switching_period_s', 1e-3, 2e-12, 1.0, 's', 'PWM carrier period.'),
            _parameter('output_high_v', 3.3, 1e-9, 1000.0, 'V', 'DO high voltage.'),
        ],
        'pins': [
            {'name': 'duty', 'mode': 'AI', 'node': 'duty', 'reference': '0', 'source': '', 'vdd': 1.0},
            {'name': 'enable', 'mode': 'DI', 'node': 'enable', 'reference': '0', 'source': '', 'vdd': 3.3},
            {'name': 'drive', 'mode': 'DO', 'node': '', 'reference': '0', 'source': 'VPWM', 'vdd': 3.3},
        ],
        'state': [{'index': 0, 'name': 'phase_tick', 'unit': 'tick', 'initial': 0.0,
                   'description': 'Integer carrier tick used on the next accepted controller invocation.'}],
        'source_template': _PWM_SOURCE,
        'limitations': 'Discrete sampled logic only. Edges are quantized to sample_period_s; no dead time, propagation delay, analog gate-drive behavior, jitter, vendor model, or continuous-time IC physics.',
    },
    {
        'id': 'generic.sampled_pi', 'version': '1.0.0', 'name': 'Generic sampled PI controller',
        'description': 'Sampled PI controller with output limiting and conditional anti-windup.',
        'language': 'C', 'sampled_only': True,
        'parameters': [
            _parameter('sample_period_s', 1e-4, 1e-12, 1.0, 's', 'Controller invocation period.'),
            _parameter('kp', 0.5, -1e9, 1e9, 'V/V', 'Proportional gain.'),
            _parameter('ki_per_s', 100.0, -1e12, 1e12, 'V/(V*s)', 'Integral gain.'),
            _parameter('output_min_v', 0.0, -1000.0, 1000.0, 'V', 'Lower command limit.'),
            _parameter('output_max_v', 1.0, -1000.0, 1000.0, 'V', 'Upper command limit.'),
            _parameter('output_envelope_v', 1.0, 1e-9, 1000.0, 'V', 'AO symmetric validation envelope.'),
        ],
        'pins': [
            {'name': 'reference', 'mode': 'AI', 'node': 'reference', 'reference': '0', 'source': '', 'vdd': 1000.0},
            {'name': 'feedback', 'mode': 'AI', 'node': 'feedback', 'reference': '0', 'source': '', 'vdd': 1000.0},
            {'name': 'command', 'mode': 'AO', 'node': '', 'reference': '0', 'source': 'VCOMMAND', 'vdd': 1.0},
        ],
        'state': [{'index': 0, 'name': 'integral_v', 'unit': 'V', 'initial': 0.0,
                   'description': 'Accepted integral contribution for the next tick.'}],
        'source_template': _PI_SOURCE,
        'limitations': 'Discrete sampled controller only. No plant, ADC/DAC quantization, latency, noise, saturation physics, vendor model, stability guarantee, or continuous-time IC behavior.',
    },
)


def _strict_json(text):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('Duplicate JSON key in compiled IC library')
            value[key] = item
        return value
    return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))


def _finite_number(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + ' must be a finite number')
    value = float(value)
    if not minimum <= value <= maximum:
        raise ValueError(name + ' is outside its declared range')
    return value


def validate(library):
    if not isinstance(library, dict) or library.get('contract') != CONTRACT:
        raise ValueError('Unsupported compiled IC library contract')
    entries = library.get('entries')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 128:
        raise ValueError('Compiled IC library needs 1..128 entries')
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or not _ID.fullmatch(entry.get('id', '')) or entry['id'] in seen:
            raise ValueError('Compiled IC entry ID must be unique and bounded')
        seen.add(entry['id'])
        if entry.get('language') not in ('C', 'C++') or entry.get('sampled_only') is not True:
            raise ValueError('Compiled IC entries must declare sampled C/C++ behavior')
        for field in ('version', 'name', 'description', 'limitations', 'source_template'):
            if not isinstance(entry.get(field), str) or not entry[field]:
                raise ValueError('Missing compiled IC metadata: ' + field)
        if len(entry['source_template'].encode('utf-8')) > 256 * 1024:
            raise ValueError('Compiled IC source limit: 256 KiB')
        parameters = entry.get('parameters')
        if not isinstance(parameters, list) or not parameters:
            raise ValueError('Compiled IC parameters must be explicit')
        parameter_names = set()
        for parameter in parameters:
            name = parameter.get('name', '') if isinstance(parameter, dict) else ''
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', name) or name in parameter_names:
                raise ValueError('Invalid or duplicate compiled IC parameter')
            parameter_names.add(name)
            low = _finite_number(parameter.get('minimum'), name + '.minimum', -1e300, 1e300)
            high = _finite_number(parameter.get('maximum'), name + '.maximum', low, 1e300)
            _finite_number(parameter.get('default'), name + '.default', low, high)
            if not isinstance(parameter.get('unit'), str) or not isinstance(parameter.get('description'), str):
                raise ValueError('Parameter unit and description are required')
        if 'sample_period_s' not in parameter_names:
            raise ValueError('Compiled IC entry requires sample_period_s')
        states = entry.get('state')
        if not isinstance(states, list) or not 1 <= len(states) <= 64:
            raise ValueError('Compiled IC state must be explicit')
        state_names = set()
        for index, state in enumerate(states):
            if not isinstance(state, dict) or state.get('index') != index or state.get('initial') != 0.0:
                raise ValueError('State must use contiguous zero-initialized controller indices')
            name = state.get('name', '')
            if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', name) or name in state_names:
                raise ValueError('Invalid state name')
            state_names.add(name)
        probe = {'contract': CONTROLLER_CONTRACT, 'language': entry['language'], 'step_s': next(p['default'] for p in parameters if p['name'] == 'sample_period_s'),
                 'state_count': len(states), 'pins': deepcopy(entry.get('pins')), 'source': _TOKEN.sub('1.0', entry['source_template'])}
        validate_controller(probe)
    return library


def catalog():
    """Return a detached, inert descriptor library."""
    return validate({'contract': CONTRACT, 'entries': deepcopy(list(_ENTRIES)),
                     'notice': 'Generic sampled examples only; not vendor-qualified IC models or continuous physical device models.'})


def configuration(identifier, parameters=None, pins=None, *, library=None):
    """Build an existing Controller configuration without compiling it.

    ``pins`` maps a pin name to controller pin-field overrides such as
    ``{'node': 'sense'}`` or ``{'source': 'VGATE'}``.
    """
    value = validate(deepcopy(library if library is not None else catalog()))
    entry = next((item for item in value['entries'] if item['id'] == identifier), None)
    if entry is None:
        raise ValueError('Unknown compiled IC library entry: ' + str(identifier))
    specs = {item['name']: item for item in entry['parameters']}
    supplied = {} if parameters is None else dict(parameters)
    if set(supplied) - set(specs):
        raise ValueError('Unknown compiled IC parameter: ' + sorted(set(supplied) - set(specs))[0])
    resolved = {name: _finite_number(supplied.get(name, spec['default']), name, spec['minimum'], spec['maximum']) for name, spec in specs.items()}
    if identifier == 'generic.sampled_pwm':
        ratio = resolved['switching_period_s'] / resolved['sample_period_s']
        if ratio < 2 or abs(ratio - round(ratio)) > 1e-9:
            raise ValueError('PWM switching_period_s must be an integer multiple of sample_period_s and contain at least two ticks')
    if identifier == 'generic.sampled_pi' and resolved['output_min_v'] >= resolved['output_max_v']:
        raise ValueError('PI output_min_v must be less than output_max_v')
    # Known generic-part contracts apply equally to bundled and imported data.
    # Dispatch is owned code only: never import/evaluate a validator from metadata.
    complex_part = identifier in {'generic.voltage_mode_pwm', 'generic.latched_supervisor'}
    if complex_part:
        required = {'sample_period_s', 'uvlo_on_v', 'uvlo_off_v', 'output_high_v'}
        required |= ({'switching_period_s', 'thermal_reset_v', 'thermal_trip_v', 'soft_start_s'}
                     if identifier == 'generic.voltage_mode_pwm' else {'trip_off_v', 'trip_on_v'})
        if required - resolved.keys():
            raise ValueError('Known compiled part is missing required parameters: ' + ', '.join(sorted(required - resolved.keys())))
        _finite_number(resolved['sample_period_s'], 'sample_period_s', 1e-12, 1.0)
        if resolved['uvlo_off_v'] >= resolved['uvlo_on_v']:
            raise ValueError('uvlo_off_v must be below uvlo_on_v')
        if identifier == 'generic.voltage_mode_pwm':
            ratio = resolved['switching_period_s'] / resolved['sample_period_s']
            if not math.isfinite(ratio) or ratio < 8 or ratio > 1000000 or abs(ratio - round(ratio)) > 1e-9:
                raise ValueError('PWM period requires an integer multiple of 8..1000000 sample ticks')
            if resolved['thermal_reset_v'] >= resolved['thermal_trip_v']:
                raise ValueError('thermal_reset_v must be below thermal_trip_v')
            if resolved['soft_start_s'] < resolved['sample_period_s']:
                raise ValueError('soft_start_s must be at least sample_period_s')
        elif resolved['trip_off_v'] >= resolved['trip_on_v']:
            raise ValueError('trip_off_v must be below trip_on_v')
    replacements = {('@' + name.upper() + '@'): format(number, '.17g') for name, number in resolved.items()}
    if identifier == 'generic.sampled_pwm':
        replacements['@PERIOD_TICKS@'] = str(round(ratio))
    source = entry['source_template']
    for token, replacement in replacements.items():
        source = source.replace(token, replacement)
    if _TOKEN.search(source):
        raise ValueError('Compiled IC source contains an unresolved parameter token')
    configured_pins = deepcopy(entry['pins'])
    overrides = {} if pins is None else dict(pins)
    known = {pin['name'] for pin in configured_pins}
    if set(overrides) - known:
        raise ValueError('Unknown compiled IC pin: ' + sorted(set(overrides) - known)[0])
    for pin in configured_pins:
        update = overrides.get(pin['name'], {})
        if not isinstance(update, dict) or set(update) - {'node', 'reference', 'source', 'vdd'}:
            raise ValueError('Pin overrides may contain node, reference, source, and vdd only')
        pin.update(update)
    if identifier == 'generic.sampled_pwm':
        next(pin for pin in configured_pins if pin['name'] == 'drive')['vdd'] = resolved['output_high_v']
    elif identifier == 'generic.sampled_pi':
        next(pin for pin in configured_pins if pin['name'] == 'command')['vdd'] = resolved['output_envelope_v']
        if max(abs(resolved['output_min_v']), abs(resolved['output_max_v'])) > resolved['output_envelope_v']:
            raise ValueError('PI output limits must fit inside output_envelope_v')
    elif complex_part:
        for pin in configured_pins:
            if pin['mode'] == 'DO':
                pin['vdd'] = resolved['output_high_v']
            elif identifier == 'generic.voltage_mode_pwm' and pin['name'] == 'duty':
                pin['vdd'] = 1.0
    config = {'contract': CONTROLLER_CONTRACT, 'language': entry['language'],
              'step_s': resolved['sample_period_s'], 'state_count': len(entry['state']),
              'pins': configured_pins, 'source': source}
    validate_controller(config)
    return config


def load(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Compiled IC library exceeds 1 MiB')
    return validate(_strict_json(path.read_text(encoding='utf-8')))


def save(path, library=None):
    value = validate(deepcopy(library if library is not None else catalog()))
    if len(json.dumps(value, allow_nan=False).encode('utf-8')) > MAX_BYTES:
        raise ValueError('Compiled IC library exceeds 1 MiB')
    write_json(path, value)


__all__ = ['CONTRACT', 'catalog', 'configuration', 'load', 'save', 'validate']
