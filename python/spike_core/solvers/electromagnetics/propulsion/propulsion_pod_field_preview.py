# SPDX-License-Identifier: Apache-2.0
"""Bounded presentation samples of an actual solved P1 or P2 magnetic field.

The output triangulation is a display grid, never a claimed solver mesh. Each
sample retains its owning source element; no field is extrapolated outside it.
"""
import hashlib
import json
import numpy as np


def magnetic_preview(field, grid_nodes=49):
    from matplotlib.tri import Triangulation
    if type(grid_nodes) is not int or not 9<=grid_nodes<=97:
        raise ValueError('Display grid must have 9..97 nodes per axis')
    nodes=np.asarray(field['nodes_m'],float);tri=np.asarray(field['triangles'])
    B=np.asarray(field['element_b_t'],float);regions=field['region_ids']
    if nodes.ndim!=2 or nodes.shape[1]!=2 or tri.ndim!=2 or tri.shape[1]!=3 or tri.dtype.kind not in 'iu':
        raise ValueError('Actual planar solver mesh required')
    if B.shape!=(len(tri),2) or len(regions)!=len(tri) or not np.isfinite(np.r_[nodes.ravel(),B.ravel()]).all():
        raise ValueError('Aligned finite source field required')
    if np.any(tri<0) or np.any(tri>=len(nodes)):raise ValueError('Invalid source triangle index')
    Bvertices=None
    if 'p2_barycentric_b_t' in field:
        Bvertices=np.asarray(field['p2_barycentric_b_t'],float)
        if Bvertices.shape!=(len(tri),3,2) or not np.isfinite(Bvertices).all():
            raise ValueError('P2 magnetic field requires three vertex values per element')
    oriented=tri.copy();p=nodes[tri]
    signed=(p[:,1,0]-p[:,0,0])*(p[:,2,1]-p[:,0,1])-(p[:,1,1]-p[:,0,1])*(p[:,2,0]-p[:,0,0])
    if np.any(signed==0):raise ValueError('Degenerate source triangle')
    oriented[signed<0]=oriented[signed<0][:,[0,2,1]]
    finder=Triangulation(nodes[:,0],nodes[:,1],oriented).get_trifinder()
    x=np.linspace(nodes[:,0].min(),nodes[:,0].max(),grid_nodes)
    y=np.linspace(nodes[:,1].min(),nodes[:,1].max(),grid_nodes)
    display=np.array([[a,b] for b in y for a in x]);faces=[]
    for j in range(grid_nodes-1):
        for i in range(grid_nodes-1):
            a=j*grid_nodes+i;b=a+1;c=a+grid_nodes;d=c+1
            faces.extend(((a,b,d),(a,d,c)))
    faces=np.asarray(faces);centres=display[faces].mean(axis=1)
    owners=finder(centres[:,0],centres[:,1]);vertex_owners=finder(display[:,0],display[:,1])
    valid=(owners>=0)&np.all(vertex_owners[faces]>=0,axis=1)
    faces=faces[valid];owners=owners[valid]
    sampled=B[owners]
    if Bvertices is not None:
        # A quadratic Az has a linear B in every affine triangle. Evaluate at
        # the actual query barycentric coordinates, preserving source ordering.
        points=p[owners];delta=centres[valid]-points[:,0]
        e=points[:,1]-points[:,0];f=points[:,2]-points[:,0]
        det=e[:,0]*f[:,1]-e[:,1]*f[:,0]
        l1=(delta[:,0]*f[:,1]-delta[:,1]*f[:,0])/det
        l2=(e[:,0]*delta[:,1]-e[:,1]*delta[:,0])/det
        bary=np.column_stack([1-l1-l2,l1,l2])
        sampled=np.einsum('ei,eij->ej',bary,Bvertices[owners])
    used=np.unique(faces);remap=np.full(len(display),-1,dtype=int);remap[used]=np.arange(len(used))
    source={'nodes_m':nodes.tolist(),'triangles':tri.tolist(),'element_b_t':B.tolist(),'region_ids':regions}
    if Bvertices is not None:source['p2_barycentric_b_t']=Bvertices.tolist()
    source_hash=hashlib.sha256(json.dumps(source,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return {'nodes_m':display[used].tolist(),'triangles':remap[faces].tolist(),
            'region_ids':[regions[int(k)] for k in owners],'element_b_t':sampled.tolist(),
            'source_element_ids':owners.tolist(),'source_field_sha256':source_hash,
            'presentation_only':True,'source_field_order':2 if Bvertices is not None else 1,
            'geometry_note':'Display-grid patches sampled at centroids from owning source elements; patches are not source elements or exact material interfaces.'}
