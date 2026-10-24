# SPDX-License-Identifier: Apache-2.0
"""Fixed original three-phase sampled current/speed control; not VESC firmware."""
from pathlib import Path
import hashlib
import sys

SOURCE = r'''void control_step(double time_s, double step_s, const double *inputs,
                              double *outputs, double *state) {
    (void)time_s;
    double error=inputs[IN_target_rad_s]-inputs[IN_speed_rad_s];
    double raw=inputs[IN_kp]*error+state[0], limit=inputs[IN_current_limit_a];
    double desired=fmax(0.0,fmin(limit,raw));
    if ((raw>=0.0 && raw<=limit) || (raw>limit && error<0.0) || (raw<0.0 && error>0.0))
        state[0]+=step_s*inputs[IN_ki]*error;
    double derivative[3]={inputs[IN_dpsi_a],inputs[IN_dpsi_b],inputs[IN_dpsi_c]};
    double current[3]={inputs[IN_current_a],inputs[IN_current_b],inputs[IN_current_c]};
    double resistance[3]={inputs[IN_resistance_a],inputs[IN_resistance_b],inputs[IN_resistance_c]};
    double mean=(derivative[0]+derivative[1]+derivative[2])/3.0;
    double norm=0.0;
    for(int j=0;j<3;j++){derivative[j]-=mean;norm+=derivative[j]*derivative[j];}
    norm=sqrt(norm);
    double v[3],vmean=0.0;
    for(int j=0;j<3;j++){
        double request=norm>1e-15 ? desired*derivative[j]/norm : 0.0;
        v[j]=resistance[j]*request+inputs[IN_speed_rad_s]*derivative[j]
            +inputs[IN_current_gain]*(request-current[j]);
        vmean+=v[j]/3.0;
    }
    for(int j=0;j<3;j++)outputs[j]=fmax(0.0,fmin(1.0,0.5+(v[j]-vmean)/inputs[IN_bus_v]));
}'''
INPUTS = ('target_rad_s','speed_rad_s','current_a','current_b','current_c',
          'dpsi_a','dpsi_b','dpsi_c','resistance_a','resistance_b','resistance_c',
          'bus_v','current_limit_a','kp','ki','current_gain')

def create_three_phase_controller(sample_period_s):
    folder=Path(__file__).resolve().parents[2]/'standalone/spikes_project/studio/python'
    if not (folder/'spikes_studio/controller_block.py').is_file():
        raise ValueError('Optional SPIKES Studio controller source runtime is required')
    if str(folder) not in sys.path:
        sys.path.insert(0,str(folder))
    from spikes_studio.controller_block import Controller,PERSISTENT_PROCESS
    config={'contract':'spikes/generic-controller/v1','language':'C','step_s':sample_period_s,
        'state_count':1,'source':SOURCE,'pins':[
            {'name':name,'mode':'AI','node':name,'reference':'0','source':'','vdd':1000.} for name in INPUTS]+[
            {'name':name,'mode':'AO','node':'','reference':'0','source':source,'vdd':1.}
            for name,source in [('duty_a','VdutyA'),('duty_b','VdutyB'),('duty_c','VdutyC')]]}
    return Controller(config,trusted=True,execution_mode=PERSISTENT_PROCESS)

SOURCE_SHA256=hashlib.sha256(SOURCE.encode()).hexdigest()
