# SPDX-License-Identifier: Apache-2.0
"""Fixed original sampled PI source executed by the real SPIKES C controller.

No arbitrary source is admitted by this service. Running the pod explicitly
compiles/executes this built-in source through Studio's bounded process owner.
Signal ports carry the named SI quantities; they are not physical ADC models.
"""
from pathlib import Path
import hashlib
import sys

SOURCE = r'''void control_step(double time_s, double step_s, const double *inputs,
                              double *outputs, double *state) {
    (void)time_s;
    double error = inputs[IN_target_rad_s] - inputs[IN_speed_rad_s];
    double raw = inputs[IN_kp] * error + state[0];
    double maximum = inputs[IN_current_limit_a];
    double desired = fmax(0.0, fmin(maximum, raw));
    /* Conditional integration: no windup while the current request is limited. */
    if ((raw >= 0.0 && raw <= maximum) || (raw > maximum && error < 0.0)
        || (raw < 0.0 && error > 0.0))
        state[0] += step_s * inputs[IN_ki] * error;
    double da = inputs[IN_dpsi_a], db = inputs[IN_dpsi_b];
    double norm = sqrt(da*da + db*db);
    if (norm < 1e-15) { outputs[0] = 0.0; outputs[1] = 0.0; return; }
    double ia = desired * da/norm, ib = desired * db/norm;
    double va = inputs[IN_resistance_a] * ia + inputs[IN_speed_rad_s] * da
        + inputs[IN_current_gain] * (ia - inputs[IN_current_a]);
    double vb = inputs[IN_resistance_b] * ib + inputs[IN_speed_rad_s] * db
        + inputs[IN_current_gain] * (ib - inputs[IN_current_b]);
    double limit = inputs[IN_voltage_limit_v];
    outputs[0] = fmax(-limit, fmin(limit, va));
    outputs[1] = fmax(-limit, fmin(limit, vb));
}'''

INPUTS = ('target_rad_s', 'speed_rad_s', 'current_a', 'current_b', 'dpsi_a', 'dpsi_b',
          'resistance_a', 'resistance_b', 'voltage_limit_v', 'current_limit_a', 'kp', 'ki', 'current_gain')

def controller_config(sample_period_s, voltage_limit_v):
    return {'contract': 'spikes/generic-controller/v1', 'language': 'C',
        'step_s': sample_period_s, 'state_count': 1, 'source': SOURCE,
        'pins': [{'name': name, 'mode': 'AI', 'node': name, 'reference': '0', 'source': '', 'vdd': 1000.}
                 for name in INPUTS] +
                [{'name': name, 'mode': 'AO', 'node': '', 'reference': '0', 'source': source,
                  'vdd': voltage_limit_v} for name, source in [('phase_a', 'VphaseA'), ('phase_b', 'VphaseB')]]}

def create_controller(sample_period_s, voltage_limit_v):
    # Same optional source-runtime boundary as studio_bridge. No wx module is
    # imported. Frozen builds without Studio sources fail instead of substituting.
    folder = Path(__file__).resolve().parents[5] / 'standalone/spikes_project/studio/python'
    if not (folder / 'spikes_studio/controller_block.py').is_file():
        raise ValueError('The coupled pod requires the optional SPIKES Studio controller source runtime.')
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    from spikes_studio.controller_block import Controller, PERSISTENT_PROCESS
    return Controller(controller_config(sample_period_s, voltage_limit_v),
                      trusted=True, execution_mode=PERSISTENT_PROCESS)

SOURCE_SHA256 = hashlib.sha256(SOURCE.encode()).hexdigest()
