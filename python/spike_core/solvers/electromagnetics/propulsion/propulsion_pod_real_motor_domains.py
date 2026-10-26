# SPDX-License-Identifier: Apache-2.0
"""Static native rotor/stator domains for a separately owned annulus coupling.

Derived CAD coordinates retain CERN-OHL-W-2.0. The omitted vacuum annulus is
not numerically solved here; a caller must supply an admitted coupling law.
Straight interface chords approximate ideal circular traces explicitly.
"""
from __future__ import annotations
import copy,hashlib,json,math
from collections import Counter
import numpy as np
from .propulsion_pod_real_motor import SOURCE_SHA256, _polygons, _parts, _number


def build_real_motor_domains(geometry,spec,trace_vertex_count=257,edge_m=None,*,repeat_rotor_sector=False,uniform_refinements=0,vacuum_trace_layers_m=(),interior_marked_triangles=None,interior_marking_steps=None):
    """Return rotor disk and stator annulus at native theta=0, SI coordinates.

    Ordered interface vertices are CCW at common angles 2*pi*j/N. The stator
    interface is an inner boundary; its outward normal points into the gap.
    All returned winding currents refer to fixed physical phases A/B/C.
    """
    from shapely.geometry import Polygon
    from shapely import segmentize,constrained_delaunay_triangles
    from shapely.ops import unary_union
    if not isinstance(geometry,dict) or geometry.get('source_sha256')!=SOURCE_SHA256:raise ValueError('Native OpenMotor source revision required')
    if not isinstance(spec,dict) or spec.get('acknowledge_intended_connector_clearance') is not True or spec.get('acknowledge_isotropic_steel_approximation') is not True:raise ValueError('Explicit material and intended-winding interpretation required')
    if type(trace_vertex_count) is not int or not 65<=trace_vertex_count<=2049:raise ValueError('Trace requires integer65..2049')
    if type(repeat_rotor_sector) is not bool:raise ValueError('Sector repetition must be boolean')
    if type(uniform_refinements) is not int or not 0<=uniform_refinements<=2:raise ValueError('Uniform refinements must be integer0..2')
    if interior_marked_triangles is not None:
        if not isinstance(interior_marked_triangles,dict) or set(interior_marked_triangles)!={'rotor','stator'}:raise ValueError('Marked refinement requires both domain bindings')
        if interior_marking_steps is not None:raise ValueError('Use one marked refinement input form')
        interior_marking_steps=[interior_marked_triangles]
    steps=[] if interior_marking_steps is None else interior_marking_steps
    if not isinstance(steps,list) or len(steps)>8 or any(not isinstance(x,dict) or set(x)!={'rotor','stator'} for x in steps):raise ValueError('At most eight explicitly bound adaptive levels required')
    if repeat_rotor_sector and trace_vertex_count%14:raise ValueError('Repeated rotor trace count must be divisible by14')
    edge=_number(spec.get('edge_m') if edge_m is None else edge_m,'edge_m',.0001,.01)
    if 'bh_curve' in spec.get('steel',{}):raise ValueError('Static linear Schur domains currently require declared linear steel')
    br=_number(spec['pm_remanence_t'],'remanence',0,1.6);mur=_number(spec['pm_relative_permeability'],'PM permeability',1,2)
    signs=spec['pm_polarity_signs']
    if not isinstance(signs,list) or len(signs)!=28 or any(type(x) is not int or x not in(-1,1) for x in signs):raise ValueError('Twenty-eight explicit PM signs required')
    a,b,outer=.04430,.04450,.085
    angles=np.arange(trace_vertex_count)*2*math.pi/trace_vertex_count
    rotor_trace=np.column_stack((a*np.cos(angles),a*np.sin(angles)))
    stator_trace=np.column_stack((b*np.cos(angles),b*np.sin(angles)))
    outer_count=max(256,16*math.ceil(2*math.pi*outer/(16*edge)))
    phi=np.arange(outer_count)*2*math.pi/outer_count
    outer_trace=np.column_stack((outer*np.cos(phi),outer*np.sin(phi)))
    rotor_body=[];stator_body=[];rotor_steel=[];stator_steel=[];pm={}
    magnets=sorted((x for x in geometry['bodies'] if x['label'].startswith('Magnet')),key=lambda x:x['label'])
    if len(magnets)!=28:raise ValueError('Twenty-eight native magnets required')
    period_proof=None
    if repeat_rotor_sector:
        from .propulsion_pod_real_motor import mechanical_period_geometry_proof
        period_proof=mechanical_period_geometry_proof(geometry,signs)
    for magnet,sign in zip(magnets,signs):
        radial=np.array(magnet['center_m'][:2]);radial/=np.linalg.norm(radial)
        pm[magnet['label']]={'mu_r':mur,'remanence_t':(br*sign*np.array([-radial[1],radial[0]])).tolist()}
    for body in geometry['bodies']:
        label=body['label'];poly=segmentize(_polygons(body['loops_m']),edge)
        if label.startswith('Rotor'):rotor_steel.append(poly)
        elif label.startswith(('Core','Tooth')):stator_steel.append(poly)
        elif label in pm:rotor_body.append((label,poly))
        else:raise ValueError('Unexpected native magnetic body')
    rotor_body.append(('rotor_steel',unary_union(rotor_steel)))
    stator_body.append(('stator_steel',unary_union(stator_steel)))
    expected=set()
    for coil in geometry['coils']:
        for index,loop in enumerate(coil['loops_m']):
            label=coil['label']+':'+str(index);expected.add(label)
            stator_body.append((label,segmentize(_polygons([loop]),edge)))
    if set(spec['winding_sides'])!=expected:raise ValueError('Every native conductor side needs declared signed phase source')
    rotor_domain=Polygon(rotor_trace);stator_domain=Polygon(outer_trace,[stator_trace])
    for label,poly in rotor_body:
        if not rotor_domain.covers(poly):raise ValueError('Rotor material crosses omitted-annulus cutoff')
    for label,poly in stator_body:
        if not stator_domain.covers(poly):raise ValueError('Stator/copper material crosses omitted-annulus cutoff')
    if not isinstance(vacuum_trace_layers_m,(tuple,list)):raise ValueError('Vacuum layer distances must be a sequence')
    widths=[_number(x,'vacuum layer distance',1e-6,.0002) for x in vacuum_trace_layers_m]
    if widths!=sorted(set(widths)):raise ValueError('Vacuum layer distances must be strictly increasing')
    from shapely.geometry import Point
    origin=Point(0,0)
    rotor_occupied=unary_union([x for _,x in rotor_body]);stator_occupied=unary_union([x for _,x in stator_body])
    rotor_radius=max(math.hypot(x,y) for poly in _parts(rotor_occupied) for x,y in poly.exterior.coords)
    stator_radius=stator_occupied.distance(origin)
    if widths:
        for name,body,radius,sign,occupied in [('rotor',rotor_body,a,-1,rotor_occupied),('stator',stator_body,b,1,stator_occupied)]:
            previous=radius
            for j,width in enumerate(widths):
                current=radius+sign*width
                inner,outer_radius=sorted((previous,current))
                ring=Polygon(np.column_stack((outer_radius*np.cos(angles),outer_radius*np.sin(angles))),
                    [np.column_stack((inner*np.cos(angles),inner*np.sin(angles)))])
                if not ring.intersection(occupied).is_empty:raise ValueError('Requested trace layer intersects native material; not a pure vacuum band')
                body.append(('trace_vacuum_'+str(j),ring));previous=current

    def mesh(name,domain,parts,trace,outer_ring):
        occupied=unary_union([poly for _,poly in parts])
        if abs(sum(poly.area for _,poly in parts)-occupied.area)>1e-10:raise ValueError('Native domain contains conflicting material overlap')
        parts=list(parts)+[('air',domain.difference(occupied))]
        lookup={};nodes=[];triangles=[];regions=[]
        def node(p):
            key=tuple(round(float(x),12) for x in p)
            if key not in lookup:
                if len(nodes)>=100000:raise ValueError('Static native domain exceeds geometry node budget during preparation')
                lookup[key]=len(nodes);nodes.append(key)
            return lookup[key]
        repeated=name=='rotor' and repeat_rotor_sector
        if repeated:
            sector=Polygon([(0,0),*trace[:trace_vertex_count//14+1]])
            parts=[(label,shape.intersection(sector)) for label,shape in parts]
        for label,shape in parts:
            for poly in _parts(shape):
                for tri in constrained_delaunay_triangles(poly).geoms:
                    row=[node(p) for p in list(tri.exterior.coords)[:3]]
                    if len(set(row))!=3:raise ValueError('Degenerate domain triangle')
                    triangles.append(row);regions.append(label)
        def refine(selected=None):
            nonlocal triangles,regions
            midpoint={};radius=a if name=='rotor' else b
            incidence=Counter(tuple(sorted((row[j],row[(j+1)%3]))) for row in triangles for j in range(3))
            for triangle_id,row in enumerate(triangles):
                if selected is not None and triangle_id not in selected:continue
                for j in range(3):
                    u,v=row[j],row[(j+1)%3];key=tuple(sorted((u,v)))
                    if key in midpoint:continue
                    r0,r1=np.linalg.norm(nodes[u]),np.linalg.norm(nodes[v])
                    # Retain the exact original polygon trace/outer boundary:
                    # red refinement in the interior; conforming green closure
                    # beside protected boundary edges. No curved projection.
                    if incidence[key]==1 and abs(r0-radius)<2e-10 and abs(r1-radius)<2e-10:continue
                    if incidence[key]==1 and abs(r0-outer)<2e-10 and abs(r1-outer)<2e-10:continue
                    midpoint[key]=node((np.asarray(nodes[u])+nodes[v])/2)
            new_triangles=[];new_regions=[]
            for row,label in zip(triangles,regions):
                mids=[midpoint.get(tuple(sorted((row[j],row[(j+1)%3])))) for j in range(3)]
                count=sum(x is not None for x in mids)
                if count==0:children=[row]
                elif count==3:
                    a0,b0,c0=row;ab,bc,ca=mids
                    children=[[a0,ab,ca],[ab,b0,bc],[ca,bc,c0],[ab,bc,ca]]
                elif count==1:
                    j=next(k for k in range(3) if mids[k] is not None)
                    a0,b0,c0=row[j],row[(j+1)%3],row[(j+2)%3];m=mids[j]
                    children=[[a0,m,c0],[m,b0,c0]]
                else:
                    j=next(k for k in range(3) if mids[k] is not None and mids[(k+1)%3] is not None)
                    a0,b0,c0=row[j],row[(j+1)%3],row[(j+2)%3];ab,bc=mids[j],mids[(j+1)%3]
                    children=[[b0,bc,ab],[a0,ab,c0],[ab,bc,c0]]
                if len(new_triangles)+len(children)>200000:raise ValueError('Refinement exceeds triangle budget')
                new_triangles.extend(children);new_regions.extend([label]*len(children))
            triangles,regions=new_triangles,new_regions
        for refinement in range(uniform_refinements):refine()
        if repeated:
            base_nodes=np.array(nodes);base_triangles=list(triangles);base_regions=list(regions)
            nodes=[];triangles=[];regions=[];lookup={};seams={}
            centers={x['label']:np.asarray(x['center_m'][:2]) for x in magnets}
            for k in range(14):
                t=k*2*math.pi/14;c,s=math.cos(t),math.sin(t);Q=np.array([[c,-s],[s,c]])
                mapped=[]
                for point in base_nodes:
                    moved=Q@point;r=float(np.linalg.norm(moved));angle=math.atan2(moved[1],moved[0])
                    seam=int(round(angle/(2*math.pi/14)))%14
                    if r<1e-11 or abs(math.sin(angle-seam*2*math.pi/14))*r<2e-11:
                        # Source rotational proof is tighter than this explicit
                        # 0.1 nm seam welding tolerance; no source body averaging.
                        key=(seam if r>=1e-11 else 0,round(r,10))
                        if key not in seams:
                            rr=key[1];aa=seam*2*math.pi/14
                            seams[key]=node((rr*math.cos(aa),rr*math.sin(aa)))
                        mapped.append(seams[key])
                    else:mapped.append(node(moved))
                label_map={}
                for label in set(base_regions):
                    if label not in centers:label_map[label]=label;continue
                    target=Q@centers[label]
                    candidate=min(centers,key=lambda x:np.linalg.norm(centers[x]-target))
                    if np.linalg.norm(centers[candidate]-target)>1e-10:raise ValueError('Repeated PM identity mismatch')
                    label_map[label]=candidate
                triangles.extend([[mapped[j] for j in row] for row in base_triangles])
                regions.extend([label_map[label] for label in base_regions])
            # Trace vertices are the exact retained uniform ring, welded only
            # at the periodic seams within the tolerance declared above.
            for point in trace:
                key=tuple(round(float(x),12) for x in point)
                if key not in lookup:
                    nearest=int(np.argmin(np.linalg.norm(np.asarray(nodes)-point,axis=1)))
                    if np.linalg.norm(np.asarray(nodes[nearest])-point)>1.1e-10:raise ValueError('Repeated trace vertex missing')
                    lookup[key]=nearest
        def fingerprint():
            payload={'nodes_m':nodes,'triangles':triangles,'regions':regions,'spec':spec,
                'geometry':geometry,'trace':trace.tolist(),'outer':outer_ring.tolist() if len(outer_ring) else []}
            return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        marking_history=[]
        for step in steps:
            coarse_fingerprint=fingerprint();binding=step[name]
            if not isinstance(binding,dict) or set(binding)!={'mesh_sha256','triangle_ids'} or binding['mesh_sha256']!=coarse_fingerprint:raise ValueError('Stale or malformed coarse mesh marking binding')
            ids=binding['triangle_ids']
            if not isinstance(ids,list) or any(type(j) is not int or j<0 or j>=len(triangles) for j in ids):raise ValueError('Marked triangle indices outside bound coarse mesh')
            selected=set(ids)
            if repeated:
                base_count=len(triangles)//14
                if base_count*14!=len(triangles):raise ValueError('Rotor sector triangle orbit unavailable')
                orbit={j%base_count for j in selected}
                selected={j+k*base_count for j in orbit for k in range(14)}
            marking={'requested_count':len(set(ids)),'orbit_closed_count':len(selected),
                'rotor_14fold_orbit_closure':bool(repeated),'coarse_mesh_sha256':coarse_fingerprint}
            old_nodes=np.asarray(nodes).copy();old_triangles=np.asarray(triangles).copy()
            refine(selected)
            # Every added point is a rounded coarse-edge midpoint; verify
            # this geometric nesting independently of the marking indicator.
            from scipy.spatial import cKDTree
            mids=np.concatenate([(old_nodes[old_triangles[:,j]]+old_nodes[old_triangles[:,(j+1)%3]])/2 for j in range(3)])
            added=np.asarray(nodes[len(old_nodes):])
            error=float(cKDTree(mids).query(added)[0].max()) if len(added) else 0.
            if error>2e-12:raise ValueError('Refined node is not a nested coarse-edge midpoint')
            marking['maximum_added_node_midpoint_error_m']=error
            marking_history.append(marking)
        interface=[lookup[tuple(round(float(x),12) for x in point)] for point in trace]
        outer_ids=[lookup[tuple(round(float(x),12) for x in point)] for point in outer_ring]
        counts=Counter(tuple(sorted((row[k],row[(k+1)%3]))) for row in triangles for k in range(3))
        if any(v>2 for v in counts.values()):raise ValueError('Nonmanifold static domain')
        allowed=set(interface+outer_ids);freeedges=[key for key,value in counts.items() if value==1]
        if any(a not in allowed or b not in allowed for a,b in freeedges):raise ValueError('Static domain has a nonconforming internal interface')
        trace_edges={tuple(sorted((interface[j],interface[(j+1)%len(interface)]))) for j in range(len(interface))}
        if not trace_edges.issubset({key for key,v in counts.items() if v==1}):raise ValueError('Uniform trace was subdivided or lost')
        xy=np.array(nodes);tr=np.array(triangles);v=xy[tr];e=v[:,1]-v[:,0];f=v[:,2]-v[:,0];areas=np.abs(e[:,0]*f[:,1]-e[:,1]*f[:,0])/2
        chi=np.zeros((len(tr),3));bucket={}
        for j,label in enumerate(regions):bucket.setdefault(label,[]).append(j)
        if name=='stator':
            for label,(phase,fraction) in spec['winding_sides'].items():
                if type(phase) is not int or phase not in(0,1,2):raise ValueError('Phase index must be0,1,2')
                fraction=_number(fraction,'signed phase-current fraction',-1,1);ids=bucket[label]
                chi[ids,phase]=fraction/areas[ids].sum()
        signed=areas@chi
        if max(abs(signed))>1e-9:raise ValueError('Static winding source is not gauge balanced')
        solver_regions=[label if label in pm or label in('rotor_steel','stator_steel') else 'air' for label in regions]
        lengths=np.linalg.norm(v[:,[1,2,0]]-v[:,[0,1,2]],axis=2)
        cosine=np.clip((lengths**2+np.roll(lengths,1,axis=1)**2-np.roll(lengths,-1,axis=1)**2)/(2*lengths*np.roll(lengths,1,axis=1)),-1,1)
        min_angles=np.min(np.arccos(cosine),axis=1)*180/math.pi
        trace_set=set(interface)
        adjacent=np.array([j for j,row in enumerate(tr) if sum(int(x) in trace_set for x in row)>=2])
        radii=np.linalg.norm(v[adjacent],axis=2)
        trace_stats={'elements':len(adjacent),'maximum_edge_m':float(lengths[adjacent].max()),
            'minimum_angle_deg':float(min_angles[adjacent].min()),
            'maximum_radial_span_m':float(np.ptp(radii,axis=1).max()),
            'minimum_radial_span_m':float(np.ptp(radii,axis=1).min())}
        stats={}
        for label in set(solver_regions):
            ids=np.array([j for j,x in enumerate(solver_regions) if x==label])
            stats[label]={'elements':len(ids),'maximum_edge_m':float(lengths[ids].max()),
                'minimum_angle_deg':float(min_angles[ids].min()),'maximum_area_m2':float(areas[ids].max())}
        materials={label:(copy.deepcopy(spec['steel']) if label in('rotor_steel','stator_steel') else copy.deepcopy(pm[label]) if label in pm else {'mu_r':1.}) for label in set(solver_regions)}
        for value in materials.values():
            if 'relative_permeability' in value:value['mu_r']=value.pop('relative_permeability')
        if len(nodes)>100000 or len(triangles)>200000:raise ValueError('Static native domain exceeds P1 geometry budget')
        result={'nodes_m':xy.tolist(),'triangles':tr.tolist(),'region_ids':regions,'solver_region_ids':solver_regions,
                'materials':materials,'element_area_m2':areas.tolist(),'winding_chi_per_m2':chi.tolist(),
                'element_geometry_statistics':stats,
                'mesh_sha256':fingerprint(),'marked_refinement':marking_history[-1] if marking_history else None,
                'marked_refinement_history':marking_history,
                'trace_adjacent_element_statistics':trace_stats,
                'interface_vertex_ids':interface,'interface_angles_rad':angles.tolist(),'outer_boundary_vertex_ids':outer_ids,
                'dirichlet_vertex_ids':outer_ids,'signed_turn_integrals':signed.tolist(),
                'domain_area_m2':float(areas.sum()),'interface_radius_m':a if name=='rotor' else b,'interface_orientation':'counterclockwise',
                'interface_boundary_role':'outer' if name=='rotor' else 'inner'}
        result['domain_payload_sha256']=_domain_payload_hash(result)
        return result
    rotor=mesh('rotor',rotor_domain,rotor_body,rotor_trace,[])
    stator=mesh('stator',stator_domain,stator_body,stator_trace,outer_trace)
    return {'contract':'spike/openmotor-static-magnetic-domains/v1','source_sha256':SOURCE_SHA256,
            '_native_preparation':{'geometry':copy.deepcopy(geometry),'spec':copy.deepcopy(spec),'trace_vertex_count':trace_vertex_count,'edge_m':edge,
                'repeat_rotor_sector':repeat_rotor_sector,'uniform_refinements':uniform_refinements,'vacuum_trace_layers_m':widths,
                'interior_marking_steps':copy.deepcopy(steps)},
            'geometry_sha256':hashlib.sha256(json.dumps(geometry,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'spec_sha256':hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'rotor_sector_repeated':repeat_rotor_sector,'rotor_period_geometry_proof':period_proof,
            'uniform_interior_refinements':uniform_refinements,
            'vacuum_trace_layers_m':widths,'native_material_radial_bounds_m':{'rotor_maximum':rotor_radius,'stator_minimum':stator_radius},
            'periodic_seam_welding_tolerance_m':1e-10 if repeat_rotor_sector else 0.,
            'source_license':'CERN-OHL-W-2.0','trace_vertex_count':trace_vertex_count,
            'rotor_interface_radius_m':a,'stator_interface_radius_m':b,'outer_radius_m':outer,
            'rotor':rotor,'stator':stator,'omitted_vacuum_annulus_m':[a,b],
            'straight_chord_radial_error_bound_m':b*(1-math.cos(math.pi/trace_vertex_count)),
            'circle_trace_geometry_exact':False,'boundary_interpolation':'straight P1 geometry; P2 midside trace values use corresponding ideal circle angles',
            'material_qualified':False,'winding_qualified':False,'production_qualified':False,
            'limitations':['Static native rotor/stator geometry only; no annulus coupling or motor solve is executed by this helper.',
                           'Circular trace is represented by straight chords; ideal annulus coupling requires independent ring-refinement/geometry-consistency checks.',
                           'Intended ten-turn interpretation overrides literal connector overlap; material inputs remain explicit substitutions.']}


def _domain_payload_hash(domain):
    return hashlib.sha256(json.dumps({k:v for k,v in domain.items() if k!='domain_payload_sha256'},sort_keys=True,separators=(',',':')).encode()).hexdigest()


def refine_existing_domains(domains,marks):
    """Replay verified native preparation plus one fingerprint-bound AMR step.

    No arbitrary mesh geometry enters this path. Prior adaptive steps are
    retained and each level enforces the unchanged geometry resource limits.
    """
    if not isinstance(domains,dict) or domains.get('contract')!='spike/openmotor-static-magnetic-domains/v1' or domains.get('source_sha256')!=SOURCE_SHA256 or '_native_preparation' not in domains:raise ValueError('Retained native preparation required')
    for name in('rotor','stator'):
        if _domain_payload_hash(domains[name])!=domains[name].get('domain_payload_sha256'):raise ValueError('Modified mesh/source payload cannot reuse adaptive marks')
    prep=copy.deepcopy(domains['_native_preparation'])
    if not isinstance(marks,dict) or set(marks)!={'rotor','stator'}:raise ValueError('Both domain marking bindings required')
    for name in('rotor','stator'):
        if not isinstance(marks[name],dict) or marks[name].get('mesh_sha256')!=domains[name]['mesh_sha256']:raise ValueError('Adaptive marks are stale')
    prep['interior_marking_steps'].append(copy.deepcopy(marks))
    return build_real_motor_domains(**prep)


def p2_interface_trace(operator,domain):
    """Order actual P2 trace DOFs by ideal-circle angle, including midsides.

    No DOF is silently projected out. Any Fourier truncation is the coupling
    owner's explicit approximation and must retain its own convergence gate.
    """
    vertices=domain['interface_vertex_ids'];N=len(vertices)
    edge_lookup={tuple(map(int,row)):j for j,row in enumerate(operator.edges)}
    ordered=[]
    for j,vertex in enumerate(vertices):
        edge=tuple(sorted((vertex,vertices[(j+1)%N])))
        if edge not in edge_lookup:raise ValueError('Missing actual P2 interface edge')
        ordered.extend((int(vertex),int(operator.vertex_count+edge_lookup[edge])))
    if set(ordered)!=set(operator.boundary_dofs(vertices)):raise ValueError('P2 interface tag contains an interior chord or missing edge')
    angles=np.arange(2*N)*math.pi/N;radius=domain['interface_radius_m'];ideal=radius*np.column_stack((np.cos(angles),np.sin(angles)))
    actual=operator.nodes_m[ordered]
    return {'dof_ids':ordered,'angles_rad':angles.tolist(),'nodes_m':actual.tolist(),
            'ideal_circle_nodes_m':ideal.tolist(),'maximum_radial_chord_error_m':float(np.max(np.abs(np.linalg.norm(actual,axis=1)-radius))),
            'all_trace_dofs_retained':True,'fourier_projection_performed':False}

__all__=['build_real_motor_domains','p2_interface_trace','refine_existing_domains']
