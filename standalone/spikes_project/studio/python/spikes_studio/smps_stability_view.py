# SPDX-License-Identifier: Apache-2.0
"""Presentation of explicit averaged-model results, never schematic extraction."""
import numpy as np

VIEWS = ('Loop Bode', 'Plant Bode', 'Nyquist loop', 'Poles / zeros')


def describe(result):
    lines = ['Averaged CCM voltage-mode design | '+result['backend']+' | not switched circuit simulation',
             'Closed-loop rational-model poles: '+result['stability'],
             'Topology: '+result['config']['topology']]
    for name, value in result['operating_point'].items():
        lines.append(name.replace('_', ' ')+': '+(f'{value:.8g}' if isinstance(value, (int,float)) else str(value)))
    for name in ('valley_current_a','peak_current_a','inductor_ripple_pp_a','output_ripple_pp_v_estimate'):
        lines.append('CCM '+name.replace('_',' ')+f": {result['ccm'][name]:.8g}")
    for point in result['margins']['gain_crossings']:
        lines.append(f"Unity crossover: {point['frequency_hz']:.8g} Hz | phase margin {point['phase_margin_deg']:.6g} deg"+
                     (' | outside display sweep' if not point['in_sweep'] else '')+
                     (' | beyond averaging guidance' if not point['below_averaging_limit'] else ''))
    if not result['margins']['gain_crossings']:
        lines.append('No finite model unity crossover found; no phase margin is inferred.')
    for point in result['margins']['phase_crossings']:
        lines.append(f"Phase crossover: {point['frequency_hz']:.8g} Hz | gain margin {point['gain_margin_db']:.6g} dB"+
                     (' | outside display sweep' if not point['in_sweep'] else '')+
                     (' | beyond averaging guidance' if not point['below_averaging_limit'] else ''))
    if not result['margins']['phase_crossings']:
        lines.append('No finite model phase crossover found; no gain margin is inferred.')
    for label, values in [('Plant poles',result['plant_poles_rad_s']), ('Plant zeros',result['plant_zeros_rad_s']),
                          ('Closed-loop poles',result['closed_loop_poles_rad_s'])]:
        lines.append(label+' [rad/s]: '+(', '.join(f'{re:.7g}{im:+.7g}j' for re,im in values) or 'none'))
    lines += ['WARNING: '+item for item in result['warnings']]
    lines += ['Limit: '+item for item in result['limitations']]
    return '\n'.join(lines)


def render(figure,result,view):
    if view not in VIEWS:raise ValueError('Unknown SMPS stability view')
    frequency = np.asarray(result['frequency_hz'])
    for old in figure.axes:
        if old.name=='rectilinear':old.set_xscale('linear')
    figure.clear()
    if view in ('Loop Bode','Plant Bode'):
        prefix = 'loop' if view=='Loop Bode' else 'plant'
        top = figure.add_subplot(211);bottom = figure.add_subplot(212,sharex=top)
        top.semilogx(frequency,result[prefix+'_gain_db'],label=view)
        bottom.semilogx(frequency,result[prefix+'_phase_deg'])
        top.set_ylabel('Loop gain [dB]' if prefix=='loop' else 'Plant gain [dB re 1 V/duty]')
        bottom.set_ylabel('Phase [deg]');bottom.set_xlabel('Frequency [Hz]')
        top.legend()
        if prefix=='loop':
            top.axhline(0,color='gray',linewidth=.7)
            for point in result['margins']['gain_crossings']:
                if point['in_sweep']:
                    for axis in (top,bottom):axis.axvline(point['frequency_hz'],color='gray',linestyle=':',linewidth=.7)
        axes = [top,bottom]
    elif view=='Nyquist loop':
        axis = figure.add_subplot()
        values = np.asarray(result['loop'])
        axis.plot(values[:,0],values[:,1],label='Positive frequencies')
        axis.plot(values[:,0],-values[:,1],'--',alpha=.5,label='Conjugate mirror (real LTI)')
        axis.plot([-1],[0],'r+',label='-1 reference')
        axis.set_xlabel('Re(L)');axis.set_ylabel('Im(L)');axis.legend()
        axis.set_title('Sampled locus - stability comes from rational closed-loop poles')
        axes=[axis]
    else:
        axis=figure.add_subplot()
        for key,label,marker,color in [('plant_poles_rad_s','Plant poles','x','C0'),
                                       ('plant_zeros_rad_s','Plant zeros','o','C1'),
                                       ('closed_loop_poles_rad_s','Closed-loop poles','+','C2')]:
            values=np.asarray(result[key])
            if len(values):axis.scatter(values[:,0],values[:,1],marker=marker,color=color,label=label)
        axis.axhline(0,color='gray',linewidth=.7);axis.axvline(0,color='gray',linewidth=.7)
        axis.set_xlabel('Re(s) [rad/s]');axis.set_ylabel('Im(s) [rad/s]');axis.legend()
        axes=[axis]
    for axis in axes:axis.grid(True,which='both',alpha=.25)
    figure.set_layout_engine('constrained')
    return axes
