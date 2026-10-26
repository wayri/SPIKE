# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Positive log evidence of complete excitation and requested energy decay."""
import math
import re


def screen_fdtd_completion(log, *, expected_runs, end_criteria):
    if not isinstance(log,str) or len(log.encode('utf-8'))>8*1024**2:
        raise ValueError('Bounded FDTD log required')
    if type(expected_runs) is not int or not 1<=expected_runs<=16:
        raise ValueError('Invalid expected excitation count')
    if type(end_criteria) not in (int,float) or not 0<end_criteria<1:
        raise ValueError('Invalid energy decay criterion')
    sections=log.split('Create FDTD operator')[1:]
    rows=[]; threshold=10*math.log10(end_criteria)
    for section in sections:
        pulses=re.findall(r'Excitation signal length is:\s*(\d+) timesteps',section)
        finishes=re.findall(r'Time for\s+(\d+) iterations with',section)
        energies=re.findall(r'Timestep:\s*(\d+).*?Energy:.*?\(\s*(-\s*\d+(?:\.\d+)?)dB\)',section)
        complete=len(pulses)==1 and len(finishes)==1 and bool(energies)
        steps=int(finishes[0]) if len(finishes)==1 else None
        pulse=int(pulses[0]) if len(pulses)==1 else None
        db=float(energies[-1][1].replace(' ','')) if energies else None
        checks={'completion_record':complete,
                'complete_pulse':complete and steps>pulse,
                'observed_decay':complete and int(energies[-1][0])<=steps and db<=threshold+.01,
                'no_truncation_warning':not any(w in section for w in (
                    'Cutting to max number of timesteps',
                    'Max. number of timesteps was reached before the end-criteria'))}
        rows.append({'checks':checks,'iterations':steps,'pulse_timesteps':pulse,'last_energy_db':db})
    return {'screen_passed':len(rows)==expected_runs and all(all(r['checks'].values()) for r in rows),
            'expected_runs':expected_runs,'observed_runs':len(rows),'required_decay_db':threshold,'runs':rows,
            'scope':'Logged completion and energy decay only; not time-window convergence or physical qualification.'}
