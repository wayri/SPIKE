# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Explicit experimental OpenCFD kOmegaSST setup; no turbulence qualification.

Public API references (dictionary semantics only, no implementation copied):
https://doc.openfoam.com/2606/tools/processing/models/turbulence/
https://doc.openfoam.com/2606/tools/processing/models/turbulence/ras/linear-evm/rtm/kOmegaSST/
https://doc.openfoam.com/2606/tools/processing/boundary-conditions/rtm/derived/thermal/alphatWallFunction/
"""
import math
import re


def validate_turbulence_model(raw):
    if raw is None:
        return None
    keys = {'type','initial_k_m2_s2','inlet_k_m2_s2','initial_omega_per_s','inlet_omega_per_s','turbulent_prandtl'}
    if not isinstance(raw,dict) or set(raw) != keys or raw['type'] != 'kOmegaSST':
        raise ValueError('Only explicit kOmegaSST initial/inlet k, omega and Prt are admitted')
    result = {'type':'kOmegaSST'}
    for key in keys-{'type'}:
        value = raw[key]
        try:
            valid = type(value) in (int,float) and math.isfinite(value) and 1e-12 <= value <= 1e8
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError('Turbulence parameters require bounded positive finite numbers')
        if key == 'turbulent_prandtl' and not .1 <= value <= 10:
            raise ValueError('Turbulent Prandtl number must be within 0.1..10')
        result[key] = float(value)
    return result


def turbulence_dictionary(model):
    model = validate_turbulence_model(model)
    if model is None:
        return 'simulationType laminar;\n'
    return ('simulationType RAS;\nRAS\n{\n RASModel kOmegaSST;\n turbulence on;\n printCoeffs on;\n'
            f" kOmegaSSTCoeffs {{ Prt {model['turbulent_prandtl']:.17g}; }}\n}}\n")


def admit_turbulence(environment, gravity, materials, fans, fluid_regions):
    from .openfoam_multiregion import MultiRegionOpenFoamError
    try:
        model = validate_turbulence_model(environment.get('turbulence_model'))
    except ValueError as exc:
        raise MultiRegionOpenFoamError(str(exc)) from exc
    if model is not None:
        if any(gravity) or any(item.get('density_model') for item in materials) or not fans:
            raise MultiRegionOpenFoamError('Experimental SST requires forced fans, constant density and zero gravity.')
        if {item['id'] for item in fluid_regions} != {item['fluid_region_id'] for item in fans}:
            raise MultiRegionOpenFoamError('Every SST fluid region needs an explicit inlet fan.')
    return model


def field_bodies(model, ownership):
    """Explicit inlet/backflow scalars and documented wall-function BCs."""
    model = validate_turbulence_model(model)
    if model is None:
        return {}
    if not isinstance(ownership,dict) or not ownership:
        raise ValueError('Explicit patch ownership required')
    fields = {}
    definitions = {'k':('[0 2 -2 0 0 0 0]',model['initial_k_m2_s2'],model['inlet_k_m2_s2']),
                   'omega':('[0 0 -1 0 0 0 0]',model['initial_omega_per_s'],model['inlet_omega_per_s']),
                   'nut':('[0 2 -1 0 0 0 0]',0,0),
                   'alphat':('[1 -1 -1 0 0 0 0]',0,0)}
    walls = {'k':'kqRWallFunction','omega':'omegaWallFunction','nut':'nutkWallFunction',
             'alphat':'compressible::alphatWallFunction'}
    for field,(dimensions,initial,inlet) in definitions.items():
        entries = []
        for patch,owner in sorted(ownership.items()):
            if not isinstance(patch,str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,63}',patch) or not isinstance(owner,str):
                raise ValueError('Invalid turbulence patch ownership')
            if owner.startswith('fan:'):
                body = f'type fixedValue; value uniform {inlet:.17g};' if field in ('k','omega') else 'type calculated; value uniform 0;'
            elif owner == 'external:pressure_outlet':
                body = f'type inletOutlet; inletValue uniform {inlet:.17g}; value uniform {initial:.17g};' if field in ('k','omega') else 'type calculated; value uniform 0;'
            elif owner.startswith('interface:') or owner in ('external:adiabatic','external:fixed_temperature'):
                body = f'type {walls[field]}; value uniform {initial:.17g};'
                if field == 'alphat': body += f" Prt {model['turbulent_prandtl']:.17g};"
            else:
                raise ValueError('Turbulence boundary is outside forced wall-bounded scope')
            entries.append(f' {patch} {{ {body} }}')
        fields[field] = f'dimensions {dimensions};\ninternalField uniform {initial:.17g};\nboundaryField\n{{\n'+ '\n'.join(entries)+'\n}\n'
    return fields


def turbulence_schemes(base):
    marker = 'divSchemes { default none;'
    if marker not in base: raise ValueError('Unexpected trusted fluid scheme template')
    return base.replace(marker,marker+' div(phi,k) Gauss upwind; div(phi,omega) Gauss upwind;',1) + '\nwallDist { method meshWave; }\n'


def turbulence_solution(base):
    marker = 'solvers\n{\n'
    if marker not in base: raise ValueError('Unexpected trusted solver template')
    entries = ''.join(f' {name} {{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0; }}\n' for name in ('k','omega','kFinal','omegaFinal'))
    return base.replace(marker,marker+entries,1)


def yplus_observers(case):
    if not case['environment'].get('turbulence_model'):
        return ''
    return '\n'.join(f" yPlus_{region['id']} {{ type yPlus; libs (fieldFunctionObjects); region {region['id']}; executeControl writeTime; writeControl writeTime; writeToFile true; log true; }}"
                     for region in case['regions'] if region['kind']=='fluid')
