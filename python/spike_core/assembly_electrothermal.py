# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original conservative steady tetra electrothermal fixed-point coupling.

Electric conduction: -div(sigma(T) grad(phi))=0, q=sigma|grad(phi)|².
Thermal field: -div(k grad(T))=q, with explicitly modelled contacts/boundaries.
Contact dissipation is deposited half on each adjacent solid. Additional losses
require declared nonoverlapping source data; no semiconductor law is inferred.
"""
import copy
import math
import numpy as np

from .assembly_electrothermal_setup import prepare_electrothermal
from .assembly_field_geometry import keys,number
from .assembly_field_handoff import bounded_json
from .assembly_field_thermal import run_assembly_field_thermal
from .multiboard_identity import assembly_physics_digest,canonical_json_digest


def run_assembly_electrothermal(request, *, cancel_check=None):
    from .assembly_tetra_electrical import solve_assembly_tetra_electrical
    from .electrical_heat_sources import evaluate_electrical_heat_source
    data = prepare_electrothermal(request)
    options = request['iteration']
    thermal_engine = data['thermal_engine']
    mesh = data['mesh']
    temperature = np.full(len(mesh['vertices']),data['initial_temperature_k'])
    cells = {cell['id']:cell for cell in mesh['cells']}
    admitted_sources,source_ids = [],set()
    for source in request['heat_sources']:
        preliminary = evaluate_electrical_heat_source(source,data['initial_temperature_k'])
        if preliminary['id'] in source_ids:
            raise ValueError('ELECTROTHERMAL_SOURCE: duplicate loss source')
        source_ids.add(preliminary['id'])
        distribution = []
        for row in preliminary['distribution']:
            cid = data['local_cells'].get((row['occurrence_id'],row['cell_id']))
            if cid is None:
                raise ValueError('ELECTROTHERMAL_SOURCE: loss mapped outside retained mesh')
            distribution.append((cid,row['weight']))
        admitted_sources.append((source,distribution))

    def cancel():
        if cancel_check is not None and cancel_check():
            raise ValueError('ELECTROTHERMAL_CANCELLED: coupled solve cancelled')

    def evaluate(nodal_temperature):
        cancel()
        means = {cid:float(np.mean(nodal_temperature[cell['vertices']])) for cid,cell in cells.items()}
        conductivity = {}
        for cid,(sigma,alpha,reference,low,high) in data['laws'].items():
            t = means[cid]
            if not low <= t <= high:
                raise ValueError('ELECTROTHERMAL_ENVELOPE: cell temperature leaves declared material law')
            denominator = 1+alpha*(t-reference)
            if not math.isfinite(denominator) or denominator <= 0:
                raise ValueError('ELECTROTHERMAL_MATERIAL: nonfinite or nonpositive resistance law')
            conductivity[cid] = sigma/denominator
            if not math.isfinite(conductivity[cid]) or (sigma > 0 and conductivity[cid] <= 0):
                raise ValueError('ELECTROTHERMAL_MATERIAL: conductivity is not representable')
        electrical = solve_assembly_tetra_electrical({'contract':'spike/assembly-tetra-electrical-request/v1',
                        'mesh':mesh,'conductivity_s_m':conductivity,'terminals':data['terminals'],'contacts':data['contacts']})
        powers = {cid:electrical['cell_power_w'][cid]+electrical['contact_loss_allocations_w'].get(cid,0.) for cid in cells}
        source_results = []
        for source,distribution in admitted_sources:
            sample = math.fsum(weight*means[cid] for cid,weight in distribution)/math.fsum(weight for _,weight in distribution)
            result = evaluate_electrical_heat_source(source,sample)
            for cid,weight in distribution:
                powers[cid] += weight*result['average_power_w']
            source_results.append(result)
        if not all(math.isfinite(p) and p >= 0 for p in powers.values()):
            raise ValueError('ELECTROTHERMAL_LOSS: negative or unrepresentable heating')
        return electrical,powers,source_results

    baseline = copy.deepcopy(request['thermal_problem'])
    if not isinstance(baseline.get('heat_sources'),list):
        raise ValueError('ELECTROTHERMAL_SOURCE: thermal background list required')
    background,seen = {},set()
    for row in baseline['heat_sources']:
        keys(row, ('occurrence_id','cell_id','heat_source_w_m3'))
        key = (row['occurrence_id'],row['cell_id'])
        cid = data['local_cells'].get(key)
        if cid is None or key in seen:
            raise ValueError('ELECTROTHERMAL_SOURCE: unknown/duplicate background heat cell')
        seen.add(key)
        background[cid] = number(row['heat_source_w_m3'])
    history = []
    for iteration in range(options['max_iterations']):
        electrical,powers,sources = evaluate(temperature)
        problem = copy.deepcopy(baseline)
        problem['heat_sources'] = [{'occurrence_id':oid,'cell_id':local,
                                    'heat_source_w_m3':background.get(cid,0.)+powers[cid]/data['volumes'][cid]}
                                   for (oid,local),cid in data['local_cells'].items()]
        cancel()
        if thermal_engine == 'calculix':
            from .calculix_thermal import run_calculix_thermal
            thermal = run_calculix_thermal(data['geometry'],problem,data['thermal_engine_options'],cancel_check=cancel_check)
        else:
            thermal = run_assembly_field_thermal(data['geometry'],problem)
        target = np.array(thermal['field_result']['node_temperatures_k'])
        final_electrical,final_powers,final_sources = evaluate(target)
        defect = float(np.max(np.abs(target-temperature)))
        power_defect_w = math.fsum(abs(final_powers[cid]-powers[cid]) for cid in cells)
        scale = max(math.fsum(powers.values()),math.fsum(final_powers.values()),1e-30)
        relative = power_defect_w/scale
        history.append({'iteration':iteration+1,'unrelaxed_temperature_defect_k':defect,
                        'power_relative_defect':relative,'deposited_heat_w':math.fsum(powers.values()),
                        'thermal_result_digest':thermal['result_digest']})
        if defect <= options['temperature_tolerance_k'] and relative <= options['power_relative_tolerance']:
            thermal_balance = thermal['field_result'].get('heat_balance')
            result = {'contract':'spike/assembly-electrothermal-result/v1','status':'completed','model_status':'experimental',
                      'production_qualified':False,'request_digest':data['original_request_digest'],
                      'thermal_engine':thermal_engine,
                      'assembly_digest':assembly_physics_digest(request['geometry']['assembly']),
                      'electrical':final_electrical,'thermal':thermal,'thermal_problem':problem,'heat_source_results':final_sources,
                      'cell_deposited_power_w':final_powers,'history':history,
                      'coupled_power_defect_w':power_defect_w,
                      'conservation':{'electrical_residual_w':final_electrical['conservation_residual_w'],
                                      'thermal_imbalance_w':thermal_balance['imbalance_w'] if thermal_balance else None,
                                      'thermal_balance_status':'reported' if thermal_balance else 'not_reported',
                                      'thermal_load_feedback_difference_w':math.fsum(final_powers.values())-math.fsum(powers.values())},
                      'limitations':['supplied conforming tetra volumes, not automatic arbitrary PCB CAD extraction',
                                     'steady DC scalar conductivity; no AC/full-wave current extraction',
                                     'spectral and waveform/table sources are averaged heat, not transient switching circuit solves',
                                     'caller-declared nonoverlapping loss data, not arbitrary SPICE/IBIS semiconductor coverage',
                                     'exact matched bonds/thermal contacts only; no unrepresented connector/harness/flex links',
                                     'experimental, no measured/production qualification']}
            if thermal_engine == 'calculix':
                result['limitations'] += ['CalculiX thermal balance is not reported; no synthetic conservation claim',
                    'thermal fixed-point defects use finite-precision CalculiX NT output; tolerances are not field accuracy bounds']
            result['result_digest'] = canonical_json_digest(result)
            bounded_json(result)
            return result
        temperature += options['relaxation']*(target-temperature)
    raise ValueError('ELECTROTHERMAL_NONCONVERGENCE: coupled temperature/power residuals failed iteration budget')
