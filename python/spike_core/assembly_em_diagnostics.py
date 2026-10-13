# SPDX-License-Identifier: Apache-2.0
"""Observed native material-sampling diagnostics; no inferred convergence."""
import re


def native_material_sampling(log_text, compiled):
    indices=sorted({int(v) for v in re.findall(r'Unused primitive \(type: Polyhedron\) detected in property: spike_retained_(\d+)!',log_text)})
    primitives=compiled['primitives'];unresolved=[]
    for index in indices:
        if index>=len(primitives):raise ValueError('ASSEMBLY_EM_DIAGNOSTIC: unknown native material property')
        primitive=primitives[index]
        unresolved.append({'primitive_index':index,'conductive':primitive['material']['conductivity_s_m']>0,
                           'occurrence_id':primitive.get('occurrence_id'),'material_id':primitive.get('material_id')})
    conductive=sum(v['conductive'] for v in unresolved)
    return {'contract':'spike/assembly-em-material-sampling/v1','native_unused_primitive_count':len(indices),
            'unused_conductive_primitive_count':conductive,'unused_nonconductive_primitive_count':len(indices)-conductive,
            'unresolved_primitives':unresolved,'geometry_sampling_complete':False if indices else None,
            'evidence':'Native unused-polyhedron warnings; absence of a warning is not a convergence certificate.'}
