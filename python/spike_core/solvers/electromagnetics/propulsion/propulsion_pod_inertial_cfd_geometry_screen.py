# SPDX-License-Identifier: Apache-2.0
"""Batched existing certified face-axis arithmetic; no independent admission.

False means uncertain, never intersection. True certifies one existing
face-axis separation exactly as the scalar SAT owner's fast path does.
The scalar owner's rational/cross-edge fallback remains necessary.
"""
import numpy as np
from ...thermal_fluid.flow.cfd_tetra_intersections import _filtered_determinants

_FACES=np.array([[0,1,2],[0,1,3],[0,2,3],[1,2,3]])


def face_separation_certificates(vertices,cells,left_ids,right_ids):
    left_ids=np.asarray(left_ids);right_ids=np.asarray(right_ids)
    if left_ids.dtype.kind not in 'iu' or right_ids.dtype.kind not in 'iu':raise ValueError('Integer cell selectors required')
    if left_ids.ndim!=1 or right_ids.shape!=left_ids.shape or len(left_ids)>256:raise ValueError('Matched bounded batch<=256 required')
    if np.any(left_ids<0) or np.any(right_ids<0) or np.any(left_ids>=len(cells)) or np.any(right_ids>=len(cells)):raise ValueError('Cell selector out of range')
    try:
        with np.errstate(all='raise'):
            left=np.asarray(vertices)[np.asarray(cells)[left_ids]];right=np.asarray(vertices)[np.asarray(cells)[right_ids]]
            differences=right[:,None,:,:]-left[:,:,None,:]
            first=np.concatenate([p[:,_FACES[:,1]]-p[:,_FACES[:,0]] for p in (left,right)],axis=1)
            second=np.concatenate([p[:,_FACES[:,2]]-p[:,_FACES[:,0]] for p in (left,right)],axis=1)
            signs=_filtered_determinants(first[:,:,None,None,:],second[:,:,None,None,:],differences[:,None,:,:,:])
    except FloatingPointError:
        return np.zeros(len(left_ids),dtype=bool)
    return np.any(np.all(signs>0,axis=(2,3))|np.all(signs<0,axis=(2,3)),axis=1)
