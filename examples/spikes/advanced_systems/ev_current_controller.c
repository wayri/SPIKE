/* Educational averaged DC-equivalent drive. Not firmware or a safety controller.
 * inputs: current[A], omega[rad/s], throttle[0..1], brake[0..1]
 * outputs: average voltage[V], temperature estimate[degC], bus estimate[V]
 * state: PI integral, thermal rise, motor speed. Fixed hypothetical 72 V battery.
 */
#include <math.h>
static double clip(double x,double lo,double hi) { return fmax(lo,fmin(hi,x)); }
void control_step(double time_s,double step_s,const double *inputs,
                  double *outputs,double *state) {
    (void)time_s;
    /* 12-bit signed +/-150 A ADC, no modeled conversion latency. */
    double measured=inputs[0]/0.001;
    double current=round(clip(measured,-150,150)/300*4095)*300/4095;
    state[2]+=step_s*(0.12*measured-0.02*state[2])/0.30;
    double speed=state[2], throttle=clip(inputs[2],0,1), brake=clip(inputs[3],0,1);
    double target=brake>0.01 ? -60*brake*clip(speed/30,0,1) : 100*throttle;
    /* Illustrative thermal foldback; not a rated protection system. */
    target*=clip((110-(25+state[1]))/20,0,1);
    double error=target-current;
    double bus=clip(72-0.03*current,60,80);
    double unconstrained=0.12*speed+0.4*error+state[0];
    outputs[0]=clip(unconstrained,-bus,bus);
    state[0]+=step_s*(40*error+20*(outputs[0]-unconstrained));
    /* Lumped conduction-only controller loss, Rtheta=1 K/W, Cth=100 J/K. */
    state[1]+=step_s*(current*current*0.015-state[1])/100;
    outputs[1]=25+state[1];outputs[2]=bus;
    outputs[3]=0.12*speed;outputs[4]=speed;outputs[5]=measured;
}
