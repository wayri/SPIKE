# SPDX-License-Identifier: Apache-2.0
"""Original generic sampled IC-like models; no manufacturer equivalence.

``configuration(id, parameters, pins)`` returns inert C++ source for the existing
Controller API. Explicit ``trusted=True`` is still required to compile; opt into
``execution_mode='persistent_process'`` for reuse. All dynamical state is in the
native ``state[]`` array, including in fresh-process mode. ``records()`` exposes
detached SDK-ready descriptor/configuration snapshots without executing code.

Independent discrete derivation: rectangular integration I += Ki*dt*error,
conditional integration at duty rails, integer carrier phase, Schmitt threshold
memory, and elapsed time since the first sampled fault. No external source/model
was copied. These equations define this generic model, not a physical IC.
Tests use hand-computed tick sequences and exact saturation/threshold invariants.
Native-circuit coupling holds ideal source outputs until the next controller tick;
the netlist's initial source values apply before the first accepted sample.
"""
from copy import deepcopy

from . import compiled_ic_library as library


PWM_ID = 'generic.voltage_mode_pwm'
SUPERVISOR_ID = 'generic.latched_supervisor'

_PWM = r'''// SPDX-License-Identifier: Apache-2.0
void control_step(double time_s, double step_s, const double *inputs,
                  double *outputs, double *state) {
    (void)time_s;
    // Tick count is a contract, not wall-clock time. Reject a mismatched grid.
    if (fabs(step_s - @SAMPLE_PERIOD_S@) > @SAMPLE_PERIOD_S@ * 1e-9) exit(24);
    const double ticks = floor(@SWITCHING_PERIOD_S@ / @SAMPLE_PERIOD_S@ + 0.5);
    if (inputs[IN_vcc] <= @UVLO_OFF_V@) state[0] = 0.0;
    else if (inputs[IN_vcc] >= @UVLO_ON_V@) state[0] = 1.0;
    if (inputs[IN_temperature] >= @THERMAL_TRIP_V@) state[1] = 1.0;
    else if (inputs[IN_temperature] <= @THERMAL_RESET_V@) state[1] = 0.0;
    outputs[OUT_drive] = outputs[OUT_duty] = outputs[OUT_ready] = 0.0;
    outputs[OUT_current_trip] = 0.0;
    if (state[0] == 0.0 || state[1] != 0.0 || inputs[IN_enable] < 0.5) {
        for (int i = 2; i < 8; ++i) state[i] = 0.0;
        return;
    }
    outputs[OUT_ready] = 1.0;
    state[2] = fmin(@SOFT_START_S@, state[2] + step_s);
    const double ceiling = @DUTY_MAX@ * state[2] / @SOFT_START_S@;
    const double error = @REFERENCE_V@ - inputs[IN_feedback];
    const double candidate = state[3] + @KI_PER_V_S@ * step_s * error;
    const double command = @KP_PER_V@ * error + candidate;
    if (!((command > ceiling && error > 0.0) || (command < 0.0 && error < 0.0)))
        state[3] = candidate;
    state[6] = fmin(ceiling, fmax(0.0, command));
    if (state[4] == 0.0) { state[5] = 0.0; state[7] = 0.0; }
    if (inputs[IN_current_sense] >= @CURRENT_LIMIT_V@) state[5] = 1.0;
    if (state[4] >= state[6] * ticks || state[5] != 0.0) state[7] = 1.0;
    outputs[OUT_drive] = state[7] == 0.0 ? 1.0 : 0.0;
    outputs[OUT_duty] = state[6];
    outputs[OUT_current_trip] = state[5];
    state[4] += 1.0;
    if (state[4] >= ticks) state[4] = 0.0;
}
'''

_SUPERVISOR = r'''// SPDX-License-Identifier: Apache-2.0
void control_step(double time_s, double step_s, const double *inputs,
                  double *outputs, double *state) {
    (void)time_s;
    if (fabs(step_s - @SAMPLE_PERIOD_S@) > @SAMPLE_PERIOD_S@ * 1e-9) exit(24);
    if (inputs[IN_vcc] <= @UVLO_OFF_V@) state[0] = 0.0;
    else if (inputs[IN_vcc] >= @UVLO_ON_V@) state[0] = 1.0;
    outputs[OUT_permit] = outputs[OUT_fault] = outputs[OUT_comparator] = 0.0;
    if (state[0] == 0.0) {
        state[1] = state[2] = state[3] = 0.0;
        return;
    }
    const double previous = state[1];
    const double ratio = @DEBOUNCE_S@ / @SAMPLE_PERIOD_S@;
    const double nearest = floor(ratio + 0.5);
    const double delay_ticks = fabs(ratio - nearest) < 1e-9 ? nearest : ceil(ratio);
    if (inputs[IN_sense] >= @TRIP_ON_V@) state[1] = 1.0;
    else if (inputs[IN_sense] <= @TRIP_OFF_V@) state[1] = 0.0;
    if (state[1] == 0.0) state[2] = 0.0;
    else if (previous == 0.0) state[2] = 0.0;
    else state[2] = fmin(delay_ticks, state[2] + 1.0);
    if (state[1] != 0.0 && state[2] >= delay_ticks) state[3] = 1.0;
    if (inputs[IN_reset] >= 0.5 && state[1] == 0.0) state[3] = 0.0;
    outputs[OUT_fault] = state[3];
    outputs[OUT_comparator] = state[1];
    outputs[OUT_permit] = state[3] == 0.0 && inputs[IN_enable] >= 0.5 ? 1.0 : 0.0;
}
'''


def _parameter(name, default, low, high, unit, description):
    return dict(name=name, default=default, minimum=low, maximum=high,
                unit=unit, description=description)


def _pin(name, mode, description, *, vdd=3.3):
    return dict(name=name, mode=mode, node=name if mode.endswith('I') else '',
                reference='0', source='' if mode.endswith('I') else 'V' + name.upper(),
                vdd=vdd, description=description)


def _states(items):
    return [dict(index=i, name=name, unit=unit, initial=0.0, description=description)
            for i, (name, unit, description) in enumerate(items)]


_SUPPLY = [
    _parameter('sample_period_s', 1e-6, 1e-12, 1.0, 's', 'Exact invocation interval.'),
    _parameter('uvlo_on_v', 10.0, 1e-6, 1000.0, 'V', 'Supply rising enable threshold.'),
    _parameter('uvlo_off_v', 8.0, 0.0, 1000.0, 'V', 'Supply falling disable threshold.'),
    _parameter('output_high_v', 5.0, 1e-6, 1000.0, 'V', 'Ideal digital output high voltage.'),
]
_LIMITS = ('Generic, unqualified sampled behavioral model, not a manufacturer MPN, '
           'pin-compatible substitute, continuous IC model or stability guarantee. '
           'Ideal infinite input impedance and voltage-source outputs; no supply loading, '
           'propagation delay, noise, drive impedance, ADC physics or transistor dynamics. '
           'Transient events between samples can be missed. Zero-initialize output sources '
           'for safe circuit startup. Knowledgeable human numerical review required before release.')
_ENTRIES = [
    dict(id=PWM_ID, version='1.0.0', name='Generic voltage-mode PWM controller',
         description='UVLO, soft-start duty ceiling, PI anti-windup, cycle current trip and thermal hysteresis.',
         language='C++', sampled_only=True, source_template=_PWM,
         parameters=_SUPPLY + [
             _parameter('switching_period_s', 20e-6, 8e-12, 1.0, 's', 'Integer carrier period; at least eight samples.'),
             _parameter('reference_v', 2.5, 0.0, 1000.0, 'V', 'Internal feedback target.'),
             _parameter('kp_per_v', 0.2, 0.0, 1e6, '1/V', 'Proportional duty gain.'),
             _parameter('ki_per_v_s', 100.0, 0.0, 1e9, '1/(V*s)', 'Integral duty gain.'),
             _parameter('duty_max', 0.9, 0.0, 1.0, '1', 'Maximum duty command.'),
             _parameter('soft_start_s', 1e-3, 1e-12, 1000.0, 's', 'Time to ramp duty ceiling from zero.'),
             _parameter('current_limit_v', 1.0, 1e-6, 1000.0, 'V', 'Sense-voltage trip, not amperes.'),
             _parameter('thermal_trip_v', 3.0, 1e-6, 1000.0, 'V', 'Rising temperature-sensor voltage shutdown.'),
             _parameter('thermal_reset_v', 2.5, 0.0, 1000.0, 'V', 'Falling temperature-sensor voltage restart.'),
         ],
         pins=[_pin('vcc', 'AI', 'Supply voltage sensed without loading.', vdd=1000.0),
               _pin('enable', 'DI', 'Active-high enable.'),
               _pin('feedback', 'AI', 'Regulated output feedback voltage.', vdd=1000.0),
               _pin('current_sense', 'AI', 'Current transducer/shunt voltage.', vdd=1000.0),
               _pin('temperature', 'AI', 'Rising-with-temperature sensor voltage; ground to disable.', vdd=1000.0),
               _pin('drive', 'DO', 'Ideal edge-aligned PWM gate command.'),
               _pin('duty', 'AO', 'Duty monitor: one volt represents unity duty.', vdd=1.0),
               _pin('ready', 'DO', 'Supply, enable and thermal interlocks satisfied.'),
               _pin('current_trip', 'DO', 'Current trip latched until carrier cycle restart.')],
         state=_states([
             ('powered', '1', 'Supply Schmitt state.'), ('thermal', '1', 'Thermal Schmitt state.'),
             ('soft_elapsed_s', 's', 'Enabled elapsed time, capped at soft-start duration.'),
             ('integral', '1', 'PI duty integral.'), ('phase_tick', 'tick', 'Next carrier sample.'),
             ('current_latch', '1', 'Cycle current-trip latch.'), ('duty', '1', 'Last requested duty.'),
             ('pulse_off', '1', 'Once off, pulse cannot restart within its cycle.')]),
         limitations=_LIMITS + ' Current limiting is sampled, not asynchronous protection. Duty edges are quantized; refine the grid for plant convergence. Soft-start increments on the first enabled sample.'),
    dict(id=SUPERVISOR_ID, version='1.0.0', name='Generic latched voltage supervisor',
         description='Supply UVLO and hysteretic overvoltage comparator with continuous sampled debounce and resettable latch.',
         language='C++', sampled_only=True, source_template=_SUPERVISOR,
         parameters=_SUPPLY + [
             _parameter('trip_on_v', 3.0, 1e-6, 1000.0, 'V', 'Rising sensed-voltage fault threshold.'),
             _parameter('trip_off_v', 2.8, 0.0, 1000.0, 'V', 'Falling comparator-clear threshold.'),
             _parameter('debounce_s', 10e-6, 0.0, 1000.0, 's', 'Time since first observed comparator-high sample; zero trips immediately.')],
         pins=[_pin('vcc', 'AI', 'Supply voltage sensed without loading.', vdd=1000.0),
               _pin('sense', 'AI', 'Monitored voltage.', vdd=1000.0),
               _pin('enable', 'DI', 'Active-high permit enable; does not clear faults.'),
               _pin('reset', 'DI', 'Active-high reset only accepted after comparator clears.'),
               _pin('permit', 'DO', 'High only when powered, enabled, and not latched.'),
               _pin('fault', 'DO', 'Latched fault output; low when unpowered.'),
               _pin('comparator', 'DO', 'Raw hysteretic comparator output; low when unpowered.')],
         state=_states([('powered', '1', 'Supply Schmitt state.'),
                        ('comparator', '1', 'Overvoltage Schmitt state.'),
                        ('debounce_ticks', 'tick', 'Intervals since first comparator-high sample.'),
                        ('fault_latch', '1', 'Fault latch; UVLO power-down clears it.')]),
         limitations=_LIMITS + ' Debounce is quantized upward to sample intervals (integer-ratio tolerance 1e-9 tick). UVLO clears all fault history.'),
]


def catalog():
    """Return the existing compiled-IC library contract, detached and inert."""
    return library.validate(dict(contract=library.CONTRACT, entries=deepcopy(_ENTRIES),
                                 notice=_LIMITS))


def configuration(identifier, parameters=None, pins=None):
    """Resolve safe literals and pin mappings; compilation remains explicit.

    Output digital voltage is controlled by output_high_v (not pin overrides).
    Duty's analog monitor is fixed to a 1 V envelope. Native code rejects a step
    interval different from sample_period_s. Changing a parameter requires a new
    configuration/compilation; no Python numerical update loop is used.
    """
    return library.configuration(identifier, parameters, pins, library=catalog())


def records():
    """Detached reusable SDK snapshots; generic entries have no manufacturer MPN."""
    return [dict(descriptor=entry, configuration=configuration(entry['id']),
                 model_status='generic-sampled-unqualified', manufacturer_mpn=None,
                 license='Apache-2.0', implementation='original SPIKE C++ control_step')
            for entry in catalog()['entries']]


__all__ = ['PWM_ID', 'SUPERVISOR_ID', 'catalog', 'configuration', 'records']
