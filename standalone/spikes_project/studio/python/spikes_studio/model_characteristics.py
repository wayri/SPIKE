"""Bounded characteristic samples from parsed model parameters, not vendor data."""
import math


def characteristic(element):
    if element.kind=='diode':
        m=element.diode_model;vt=8.617333262145e-5*m.temperature_k*m.emission_coefficient
        # Limit preview to a moderate forward range; no claim of breakdown behavior.
        x=[vt*(-5+25*i/200) for i in range(201)]
        y=[m.saturation_current_a*math.expm1(v/vt) for v in x]
        return dict(x=x,y=y,xlabel='Junction voltage [V]',ylabel='Current [A]',
                    title='Static Shockley model · no stored charge',scale='linear')
    if element.kind=='voltage_controlled_switch':
        m=element.switch_model
        x=[m.threshold_voltage_v+m.transition_voltage_v*(-8+16*i/200) for i in range(201)]
        y=[1/(1/m.off_resistance_ohm+.5*(1+math.tanh((v-m.threshold_voltage_v)/m.transition_voltage_v))*(1/m.on_resistance_ohm-1/m.off_resistance_ohm)) for v in x]
        return dict(x=x,y=y,xlabel='Differential control voltage [V]',ylabel='Resistance [ohm]',
                    title='Smooth switch · no hysteresis',scale='log')
    if element.kind in ('voltage_source','current_source'):
        w=element.waveform
        if w is None:x=[0.,1.];y=[element.value]*2
        elif w.kind=='pwl':x,y=map(list,zip(*w.points))
        else:
            low,high,delay,rise,fall,width,period=w.pulse
            x=[0.,delay];y=[low,low]
            for cycle in range(2):
                base=delay+cycle*period
                x.extend([base,base+rise,base+rise+width,base+rise+width+fall,base+period])
                y.extend([low,high,high,low,low])
        return dict(x=x,y=y,xlabel='Time [s]',ylabel='Voltage [V]' if element.kind=='voltage_source' else 'Current [A]',
                    title='Declared source waveform · ideal terminals',scale='linear')
    raise ValueError('No characteristic evaluator for this family')
