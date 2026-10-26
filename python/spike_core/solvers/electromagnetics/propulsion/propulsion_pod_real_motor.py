# SPDX-License-Identifier: Apache-2.0
"""Actual STEP-section moving-geometry P1 motor field, with explicit input gates.

CAD-derived geometry remains CERN-OHL-W-2.0; this independently authored adapter
is Apache-2.0. Material/connection declarations are mandatory, not inferred
from a motor name. Isotropic steel is an explicitly admitted approximation.
"""
from __future__ import annotations
import copy,hashlib,json,math
from numbers import Real
import numpy as np
from ..machines.magnetic_fem import solve_magnetostatic, MU0, MagneticMaterial, PlanarMagneticOperator

SOURCE_SHA256='0f6737f1ddba820376e88298cf05725de36048f03c227714bf391e7cf21b07d3'

def _number(v,name,lo,hi):
    if isinstance(v,(bool,np.bool_)) or not isinstance(v,Real) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError(name+' outside finite bounds')
    return float(v)

def _polygons(loops):
    from shapely.geometry import Polygon
    from shapely import symmetric_difference
    shape=Polygon()
    for loop in loops:
        p=Polygon([(round(float(x),12),round(float(y),12)) for x,y in loop])
        if not p.is_valid:raise ValueError('Native section has invalid wire')
        shape=symmetric_difference(shape,p)
    return shape

def _parts(shape):
    if shape.is_empty:return []
    if shape.geom_type=='Polygon':return [shape]
    return [p for g in getattr(shape,'geoms',[]) for p in _parts(g)]

def build_section_mesh(geometry,angle_rad,edge_m=.002,refinements=0):
    """Constrained triangulation of exact tessellated native interfaces.

    Boundary discretization is shared; a topological edge audit rejects
    nonconforming air/material interfaces. Optional uniform red refinement
    preserves those interfaces rather than centroid material assignment.
    """
    from shapely import constrained_delaunay_triangles,segmentize
    from shapely.geometry import Point
    from shapely.affinity import rotate
    from shapely.ops import unary_union
    angle=_number(angle_rad,'angle',-1e5,1e5);edge=_number(edge_m,'edge_m',.0001,.01)
    if type(refinements) is not int or not 0<=refinements<=2:raise ValueError('refinements must be 0..2')
    regions=[];steel=[];rotor=[]
    for body in geometry['bodies']:
        label=body['label'];poly=_polygons(body['loops_m'])
        if label.startswith(('Rotor','Magnet')):poly=rotate(poly,angle,origin=(0,0),use_radians=True)
        if label.startswith(('Core','Tooth')):steel.append(poly)
        elif label.startswith('Rotor'):rotor.append(poly)
        else:regions.append((label,segmentize(poly,edge)))
    regions.extend((('stator_steel',segmentize(unary_union(steel),edge)),('rotor_steel',segmentize(unary_union(rotor),edge))))
    for coil in geometry['coils']:
        for index,loop in enumerate(coil['loops_m']):
            regions.append((coil['label']+':'+str(index),segmentize(_polygons([loop]),edge)))
    outer=segmentize(Point(0,0).buffer(.085,quad_segs=64),edge)
    occupied=unary_union([p for _,p in regions])
    if abs(sum(p.area for _,p in regions)-occupied.area)>1e-10:raise ValueError('Native material sections overlap; geometry not admitted')
    regions.append(('air',outer.difference(occupied)))
    nodes=[];lookup={};triangles=[];ids=[]
    def node(p):
        key=tuple(round(float(x),12) for x in p)
        if key not in lookup:lookup[key]=len(nodes);nodes.append(key)
        return lookup[key]
    for label,shape in regions:
        for poly in _parts(shape):
            for tri in constrained_delaunay_triangles(poly).geoms:
                row=[node(p) for p in list(tri.exterior.coords)[:3]]
                if len(set(row))!=3:raise ValueError('Degenerate section triangle')
                triangles.append(row);ids.append(label)
    for _ in range(refinements):
        mids={};new=[];new_ids=[]
        for row,label in zip(triangles,ids):
            edgeids=[]
            for a,b in ((row[0],row[1]),(row[1],row[2]),(row[2],row[0])):
                key=tuple(sorted((a,b)))
                if key not in mids:mids[key]=node((np.array(nodes[a])+nodes[b])/2)
                edgeids.append(mids[key])
            a,b,c=row;ab,bc,ca=edgeids
            new.extend(((a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca)));new_ids.extend([label]*4)
        triangles,ids=new,new_ids
    if len(nodes)>100000 or len(triangles)>200000:raise ValueError('Native field mesh exceeds kernel budget')
    from collections import Counter
    counts=Counter(tuple(sorted((row[j],row[(j+1)%3]))) for row in triangles for j in range(3))
    if any(n>2 for n in counts.values()):raise ValueError('Nonmanifold section mesh')
    boundary=set()
    for (a,b),n in counts.items():
        if n==1:
            if min(math.hypot(*nodes[a]),math.hypot(*nodes[b]))<.0849:raise ValueError('Nonconforming internal material interface')
            boundary.update((a,b))
    return np.asarray(nodes),np.asarray(triangles,dtype=int),ids,sorted(boundary)

def derive_winding_sides(geometry,acknowledge_terminal_gap_bridge=False,acknowledge_intended_connector_clearance=False):
    """Trace the native twelve two-coil branches, with explicit solder-gap gate.

    STEP has 0.15 mm gaps at phase/neutral bus terminals. These are not metal
    continuity; bridging them is an explicit assembly assumption, not inferred
    equality of names. Each series connector actually touches two coil ends.
    """
    if acknowledge_intended_connector_clearance is not True:raise ValueError('Literal native connector overlaps internal coil link; explicit intended ten-turn connector-clearance override required')
    if acknowledge_terminal_gap_bridge is not True:raise ValueError('Explicit assembly bridge of native 0.15 mm terminal gaps is required')
    coils=geometry['coils'];branches={};terminal={}
    for c in coils:
        links=[v for v in c['contacts'] if v['bus'].startswith('Connect') and v['distance_m']<1e-8]
        close=[v for v in c['contacts'] if v['bus'] in ('PhaseA','PhaseB','PhaseC','Null') and abs(v['distance_m']-.00015)<1e-8]
        if len(links)!=1 or len(close)!=1 or len(c['loops_m'])!=20:raise ValueError('Native coil connection or ten-turn section ambiguous')
        branches.setdefault(links[0]['bus'],[]).append(c);terminal[c['label']]=close[0]
    if len(branches)!=12 or any(len(v)!=2 for v in branches.values()):raise ValueError('Expected twelve two-coil series connectors')
    sides={};counts=[0,0,0];evidence=[]
    for connector,pair in sorted(branches.items()):
        driven=[c for c in pair if terminal[c['label']]['bus']!='Null']
        returns=[c for c in pair if terminal[c['label']]['bus']=='Null']
        if len(driven)!=1 or len(returns)!=1:raise ValueError('Branch must connect one phase to neutral through two coils')
        phase=('PhaseA','PhaseB','PhaseC').index(terminal[driven[0]['label']]['bus']);counts[phase]+=1
        for c in (driven[0],returns[0]):
            entry=terminal[c['label']] if c is driven[0] else next(v for v in c['contacts'] if v['bus']==connector)
            radial=np.array(c['center_m'][:2]);radial/=np.linalg.norm(radial);tangent=np.array([-radial[1],radial[0]])
            points=np.array(entry['coil_point_m'])
            if c is returns[0]:
                # Native terminal piece 0 has a planar end at z=-11 mm.
                # Internal piece9 connector overlap is excluded ONLY under
                # the required explicit intended-clearance interpretation.
                points=points[np.abs(points[:,2]+.011)<1e-8]
                if len(points)<3:raise ValueError('Connector does not identify terminal piece0 face')
            projection=points[:,:2]@tangent
            if np.any(projection*projection[0]<=0):raise ValueError('Entry terminal face spans both winding sides')
            entry_side=float(projection.mean())
            if abs(entry_side)<.001:raise ValueError('Native entry terminal does not resolve a winding side')
            positive=negative=0
            for j,loop in enumerate(c['loops_m']):
                poly=_polygons([loop]);center=np.array(poly.centroid.coords[0]);side=float(center@tangent)
                if abs(poly.area-2.4e-6)>1e-12 or abs(side)<.001:raise ValueError('Unexpected native rectangular conductor section')
                sign=1 if side*entry_side>0 else -1
                positive+=sign>0;negative+=sign<0
                sides[c['label']+':'+str(j)]=[phase,sign/4]
            if positive!=10 or negative!=10:raise ValueError('Native coil signed conductor count is not ten turns')
        evidence.append({'connector':connector,'phase':phase,'phase_coil':driven[0]['label'],'neutral_coil':returns[0]['label']})
    if counts!=[4,4,4]:raise ValueError('Native phase branches are not four-way parallel')
    return sides,{'branches':evidence,'parallel_branches_per_phase':counts,'turns_per_coil':10,'terminal_gap_bridge_m':.00015,'literal_CAD_electrical_continuity_qualified':False,
                  'intended_connector_clearance_override':True,'native_internal_connector_overlap_mm3':4.499186780669489,
                  'polarity_method':'positive current enters phase terminal, traverses ten repeated U-turn sides, series connector, return coil, neutral; source terminal side resolves axial sign'}

def mechanical_period_geometry_proof(geometry,pm_polarity_signs):
    """Validate the source rotor/PM coefficient permutation, not mesh accuracy."""
    from shapely.affinity import rotate
    if len(pm_polarity_signs)!=28 or any(type(x) is not int or x not in (-1,1) for x in pm_polarity_signs):raise ValueError('Twenty-eight declared PM signs required')
    if any(pm_polarity_signs[(j+1)%28]!=-pm_polarity_signs[j] for j in range(28)):raise ValueError('Fourteen-pole-pair claim requires alternating declared PM signs')
    period=2*math.pi/14;Q=np.array([[math.cos(period),-math.sin(period)],[math.sin(period),math.cos(period)]])
    maximum=direction=0.
    for prefix in ('Magnet','Rotor'):
        bodies=sorted((b for b in geometry['bodies'] if b['label'].startswith(prefix)),key=lambda b:b['label'])
        if len(bodies)!=28:raise ValueError('Actual source requires28rotoriron and28magnetparts')
        for j,body in enumerate(bodies):
            target=bodies[(j+2)%28];error=rotate(_polygons(body['loops_m']),period,origin=(0,0),use_radians=True).hausdorff_distance(_polygons(target['loops_m']))
            maximum=max(maximum,error)
            if prefix=='Magnet':
                v=np.array(body['center_m'][:2]);v/=np.linalg.norm(v);v=np.array([-v[1],v[0]])*pm_polarity_signs[j]
                u=np.array(target['center_m'][:2]);u/=np.linalg.norm(u);u=np.array([-u[1],u[0]])*pm_polarity_signs[(j+2)%28]
                direction=max(direction,float(np.linalg.norm(Q@v-u)))
    if maximum>2e-10 or direction>1e-10:raise ValueError('Native rotor coefficient geometry does not satisfy the declared mechanical period')
    return {'mechanical_period_rad':period,'pole_pairs':14,'maximum_geometry_hausdorff_m':maximum,
            'maximum_magnetization_unit_vector_difference':direction,'coefficient_geometry_periodicity_verified':True,
            'numerical_mesh_periodicity_qualified':False,'torque_convergence_qualified':False}

class RealMotorFieldModel:
    """Fixed-connectivity local moving geometry; full physical phase linkage retained.

    Required spec supplies steel/PM laws and exact per-side winding source.
    No directional H070-20 material identity or vendor calibration is implied.
    """
    def __init__(self,geometry,spec):
        if geometry.get('source_sha256')!=SOURCE_SHA256:raise ValueError('Unrecognized OpenMotor source revision')
        required={'steel','pm_remanence_t','pm_relative_permeability','pm_polarity_signs','winding_sides','material_provenance','connection_provenance','acknowledge_isotropic_steel_approximation','edge_m','refinements','torque_step_rad','anchor_angle_rad','maximum_angle_offset_rad','air_gap_layers','acknowledge_intended_connector_clearance'}
        if not isinstance(spec,dict) or set(spec)-{'mesh_motion_annulus_m'}!=required:raise ValueError('Explicit real motor materials, winding and approximation declarations required')
        if spec['acknowledge_isotropic_steel_approximation'] is not True:raise ValueError('Directional steel is not implemented; explicit isotropic approximation acknowledgement required')
        if not all(isinstance(spec[k],str) and len(spec[k])>=12 for k in ('material_provenance','connection_provenance')):raise ValueError('Traceable material and connection provenance required')
        if spec['acknowledge_intended_connector_clearance'] is not True:raise ValueError('Intended ten-turn connector-clearance interpretation must be explicit')
        if not isinstance(spec['steel'],dict) or not set(spec['steel']) in ({'mu_r'},{'relative_permeability'},{'bh_curve'}):raise ValueError('Supply exactly one isotropic steel law, with no implicit PM law')
        MagneticMaterial(spec['steel'])
        self.geometry=copy.deepcopy(geometry);self.spec=copy.deepcopy(spec)
        self.geometry_sha256=hashlib.sha256(json.dumps(geometry,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        self.spec_sha256=hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        self.anchor=_number(spec['anchor_angle_rad'],'anchor angle',-1e5,1e5)
        self.patch=_number(spec['maximum_angle_offset_rad'],'angular patch',1e-5,.001)
        if type(spec['air_gap_layers']) is not int or not 0<=spec['air_gap_layers']<=8:raise ValueError('air_gap_layers must be 0..8')
        self._mesh_geometry=copy.deepcopy(geometry)
        layers=spec['air_gap_layers']
        if layers:
            phi=np.arange(512)*2*math.pi/512
            radii=np.linspace(.04424,.04456,layers+1)
            for k,(a,b) in enumerate(zip(radii,radii[1:])):
                loops=[np.column_stack((r*np.cos(phi),r*np.sin(phi))).tolist() for r in (b,a)]
                self._mesh_geometry['bodies'].append({'label':'air_mesh_separator_'+str(k),'loops_m':loops,'volume_m3':0,'center_m':[0,0,0]})
        self._anchor_mesh=build_section_mesh(self._mesh_geometry,self.anchor,spec['edge_m'],spec['refinements'])
        self._anchor_r=np.linalg.norm(self._anchor_mesh[0],axis=1)
        motion=spec.get('mesh_motion_annulus_m',[.0442,.0446])
        if not isinstance(motion,(list,tuple)) or len(motion)!=2:raise ValueError('Mesh-motion annulus requires two radii')
        motion_a=_number(motion[0],'motion inner radius',.0442,.04457);motion_b=_number(motion[1],'motion outer radius',.04422,.0446)
        if motion_a>=motion_b:raise ValueError('Mesh-motion annulus must be ordered')
        self.mesh_motion_annulus_m=[motion_a,motion_b]
        self._weights=np.clip((motion_b-self._anchor_r)/(motion_b-motion_a),0,1)
        # Chordal native arcs have vertices slightly inside nominal radii.
        # Material ownership, not radius, fixes every interface DOF exactly.
        anchor_tri=self._anchor_mesh[1];anchor_regions=self._anchor_mesh[2]
        fixed=np.array([label=='stator_steel' or label.startswith('Coil') for label in anchor_regions])
        moving=np.array([label=='rotor_steel' or label.startswith('Magnet') for label in anchor_regions])
        fixed_nodes=np.unique(anchor_tri[fixed]);moving_nodes=np.unique(anchor_tri[moving])
        if np.intersect1d(fixed_nodes,moving_nodes).size:raise ValueError('Rotor and stator share mesh nodes; air gap is invalid')
        self._weights[fixed_nodes]=0.;self._weights[moving_nodes]=1.
        a,b,c=self._anchor_mesh[0][self._anchor_mesh[1]].transpose(1,0,2)
        self._anchor_det=(b[:,0]-a[:,0])*(c[:,1]-a[:,1])-(b[:,1]-a[:,1])*(c[:,0]-a[:,0])
        self.br=_number(spec['pm_remanence_t'],'remanence',0,1.6);self.mur=_number(spec['pm_relative_permeability'],'PM permeability',1,2)
        self.delta=_number(spec['torque_step_rad'],'torque difference angle',1e-6,.001)
        magnets=sorted((b for b in geometry['bodies'] if b['label'].startswith('Magnet')),key=lambda b:b['label'])
        if len(magnets)!=28 or len(spec['pm_polarity_signs'])!=28 or any(type(v) is not int or v not in (-1,1) for v in spec['pm_polarity_signs']):raise ValueError('Twenty-eight explicit PM polarity signs required')
        self._pm={b['label']:(b,sign) for b,sign in zip(magnets,spec['pm_polarity_signs'])}
        expected={c['label']+':'+str(j) for c in geometry['coils'] for j in range(len(c['loops_m']))}
        if not isinstance(spec['winding_sides'],dict) or set(spec['winding_sides'])!=expected:raise ValueError('Every native copper cross-section needs an explicit phase and signed current fraction')
        for phase,fraction in spec['winding_sides'].values():
            if type(phase) is not int or phase not in (0,1,2):raise ValueError('Phase must be 0,1,2')
            _number(fraction,'signed phase-current fraction',-1,1)
        self._anchor_chi=np.zeros((len(self._anchor_mesh[1]),3))
        buckets={}
        for index,label in enumerate(self._anchor_mesh[2]):buckets.setdefault(label,[]).append(index)
        anchor_area=np.abs(self._anchor_det)/2
        for label,(phase,fraction) in spec['winding_sides'].items():
            indices=buckets[label];self._anchor_chi[indices,phase]=fraction/anchor_area[indices].sum()
        self._solver_regions=[label if label in ('stator_steel','rotor_steel') or label in self._pm else 'air' for label in self._anchor_mesh[2]]
        self._cache={}

    def _setup_state(self,angle):
        delta=angle-self.anchor
        if abs(delta)>self.patch:raise ValueError('Angle exceeds fixed-connectivity local patch; no silent remesh/rebase is permitted')
        anchor_nodes,tris,regions,boundary=self._anchor_mesh
        turn=delta*self._weights;co=np.cos(turn);si=np.sin(turn)
        nodes=np.column_stack((co*anchor_nodes[:,0]-si*anchor_nodes[:,1],si*anchor_nodes[:,0]+co*anchor_nodes[:,1]))
        a,b,c=nodes[tris].transpose(1,0,2)
        determinant=(b[:,0]-a[:,0])*(c[:,1]-a[:,1])-(b[:,1]-a[:,1])*(c[:,0]-a[:,0])
        if np.any(determinant*self._anchor_det<=0) or np.min(np.abs(determinant/self._anchor_det))<.05:raise ValueError('Air-gap mesh deformation invalidates triangle Jacobians')
        areas=np.abs(determinant)/2
        metal=np.array([label!='air' and not label.startswith('air_mesh_separator') for label in regions])
        if np.max(np.abs(determinant[metal]/self._anchor_det[metal]-1))>1e-7:raise ValueError('Rigid rotor/fixed stator material area changed')
        materials={};chi=self._anchor_chi;r=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
        for label in set(self._solver_regions):
            if label in ('stator_steel','rotor_steel'):materials[label]=copy.deepcopy(self.spec['steel'])
            elif label in self._pm:
                body,sign=self._pm[label];center=np.array(body['center_m'][:2]);radial=center/np.linalg.norm(center)
                tangent=np.array([-radial[1],radial[0]])
                materials[label]={'mu_r':self.mur,'remanence_t':(r@tangent*sign*self.br).tolist()}
            else:materials[label]={'mu_r':1.}
        signed=areas@chi
        if max(abs(signed))>1e-9:raise ValueError('Declared phase winding is not gauge balanced')
        ratio=float(np.min(np.abs(determinant/self._anchor_det)))
        return nodes,tris,regions,boundary,areas,materials,chi,signed,ratio

    def _state(self,currents,angle):
        key=tuple(currents)+(float(angle),)
        if key in self._cache:return self._cache[key]
        nodes,tris,regions,boundary,areas,materials,chi,signed,ratio=self._setup_state(angle)
        solver_regions=self._solver_regions
        solver_materials={label:materials[label] for label in set(solver_regions)}
        result=solve_magnetostatic(nodes_m=nodes.tolist(),triangles=tris.tolist(),region_ids=solver_regions,materials=solver_materials,
            stack_depth_m=.025,dirichlet_a_wb_per_m={k:0. for k in boundary},current_density_a_per_m2=(chi@currents).tolist(),
            absolute_tolerance_a=1e-9,relative_tolerance=1e-9,maximum_iterations=80)
        a=np.asarray(result['potential_a_wb_per_m'])
        flux=.025*np.sum(areas[:,None]*chi*a[tris].mean(axis=1)[:,None],axis=0)
        pmconstant=.025*sum(areas[j]*self.br**2/(2*MU0*self.mur) for j,label in enumerate(regions) if label in self._pm)
        energy=float(result['magnetic_energy_j']+pmconstant);coenergy=float(np.array(currents)@flux-energy)
        out={'flux_linkage_wb_turn':flux.tolist(),'magnetic_energy_j':energy,'magnetic_coenergy_j':coenergy,
             'field':{**result,'nodes_m':nodes.tolist(),'triangles':tris.tolist(),'region_ids':regions,'winding_chi_per_m2':chi.tolist()},
             'diagnostics':{'nodes':len(nodes),'triangles':len(tris),'signed_turn_integrals':signed.tolist(),'convergence':result['convergence'],'mesh_method':'fixed anchor connectivity; rigid rotor plus radial air-gap ALE','anchor_angle_rad':self.anchor,'minimum_jacobian_ratio':ratio,'torque_convergence_qualified':False}}
        if len(self._cache)>=12:self._cache.clear()
        self._cache[key]=out
        return out

    def evaluate(self,currents,angle,include_field=False):
        if not isinstance(currents,(list,tuple,np.ndarray)) or len(currents)!=3:raise ValueError('Three phase currents required')
        i=[_number(v,'current',-150,150) for v in currents]
        if abs(sum(i))>1e-10:raise ValueError('Floating star requires balanced currents')
        theta=_number(angle,'angle',-1e5,1e5)
        if abs(theta-self.anchor)>self.patch+1e-14:raise ValueError('Evaluation angle exceeds the fixed-connectivity patch')
        if type(include_field) is not bool:raise ValueError('include_field must be boolean')
        center=self._state(i,theta)
        torque=self.volume_weighted_virtual_work(i,theta)['torque_n_m']
        out={k:copy.deepcopy(v) for k,v in center.items() if include_field or k!='field'}
        out.update(contract='spike/real-motor-geometry-field/v1',model_status='experimental',production_qualified=False,
                   material_qualified=False,winding_qualified=False,literal_CAD_electrical_continuity_qualified=False,torque_n_m=torque,currents_a=i,angle_rad=theta,
                   torque_method='exact discrete P1 vacuum stress contraction with ALE velocity gradient; mesh/traction convergence still required',
                   source_sha256=SOURCE_SHA256,geometry_sha256=self.geometry_sha256,spec_sha256=self.spec_sha256,limitations=['Actual STEP-derived 24-slot/28-pole section and moving rotor geometry; source-specific material and connection declarations required.',
                   'Explicit isotropic steel approximation; not calibrated directional H070-20 or original N52UH identification.',
                   '2D magnetostatic snapshot; no end turns, losses, voltage-driven transient or hardware qualification.'])
        return out

    def linear_ports(self,angle_rad,include_fields=False):
        """Four actual field states at one local angle; full physical phases.

        Returns Wprime=.5*i^T*L*i+psi^T*i+C. The scalar C includes the
        stated PM recoil reference; a caller may subtract ONE constant from
        all angles, never a separately fitted angle-dependent baseline.
        """
        if 'bh_curve' in self.spec['steel']:raise ValueError('linear_ports requires an explicitly linear steel approximation')
        if type(include_fields) is not bool:raise ValueError('include_fields must be boolean')
        angle=_number(angle_rad,'angle',-1e5,1e5)
        zero=self._state([0.,0.,0.],angle);psi=np.array(zero['flux_linkage_wb_turn'])
        basis=[self._state(np.eye(3)[j].tolist(),angle) for j in range(3)]
        L=np.column_stack([np.array(b['flux_linkage_wb_turn'])-psi for b in basis])
        if np.max(np.abs(L-L.T))>1e-10 or np.linalg.eigvalsh(L).min()<=0:raise ValueError('Actual field linear ports violate reciprocity/positive inductance')
        result={'inductance_h':L.tolist(),'pm_flux_linkage_wb_turn':psi.tolist(),'coenergy_zero_current_j':zero['magnetic_coenergy_j'],
            'Lfull':L.tolist(),'psi_full':psi.tolist(),'C':zero['magnetic_coenergy_j'],
            'angle_rad':angle,'field_solves':4,'source_sha256':SOURCE_SHA256,'geometry_sha256':self.geometry_sha256,'spec_sha256':self.spec_sha256,'model_status':'experimental',
            'production_qualified':False,'material_qualified':False,'winding_qualified':False,'literal_CAD_electrical_continuity_qualified':False,'torque_convergence_qualified':False,
            'solver_errors':[b['diagnostics']['convergence'] for b in [zero]+basis],
            'mesh_diagnostics':zero['diagnostics']}
        if include_fields:result['basis_fields']=[b['field'] for b in [zero]+basis]
        return result

    def fixed_potential_virtual_work(self,currents,angle_rad,delta_rad=None):
        """Shape derivative at the ONE stationary central nodal potential.

        In this isotropic rigid-material fixture all metal-element functionals
        and the fixed winding load are invariant under their rigid nodal map.
        Only vacuum mesh deformation contributes; differencing its element
        integrals before summation avoids subtracting the large PM baseline.
        """
        delta=self.delta if delta_rad is None else _number(delta_rad,'virtual-work delta',1e-7,.001)
        angle=_number(angle_rad,'angle',-1e5,1e5)
        if abs(angle-self.anchor)+delta>self.patch+1e-14:raise ValueError('Virtual-work perturbation exceeds local patch')
        if not isinstance(currents,(list,tuple,np.ndarray)) or len(currents)!=3:raise ValueError('Three balanced currents required')
        i=[_number(x,'current',-150,150) for x in currents]
        if abs(sum(i))>1e-10:raise ValueError('Floating star requires balanced currents')
        central=self._state(i,angle);a=np.array(central['field']['potential_a_wb_per_m'])
        integrals=[]
        for theta in (angle+delta,angle-delta):
            nodes,tris,regions,boundary,area,materials,chi,signed,ratio=self._setup_state(theta)
            solver_regions=self._solver_regions
            solver_materials={label:materials[label] for label in set(solver_regions)}
            op=PlanarMagneticOperator(nodes.tolist(),tris.tolist(),solver_regions,solver_materials,(chi@i).tolist())
            B=np.einsum('eik,ei->ek',op.curl,a[tris])
            air=np.array([name=='air' or name.startswith('air_mesh_separator') for name in regions])
            integrals.append(area[air]*np.sum(B[air]*B[air],axis=1)/(2*MU0))
        torque=-.025*float(np.sum(integrals[0]-integrals[1]))/(2*delta)
        return {'torque_n_m':torque,'delta_rad':delta,'method':'fixed stationary nodal A, vacuum element functional difference before summation',
                'torque_convergence_qualified':False}

    def arkkio_torque(self,currents,angle_rad,inner_radius_m=.04424,outer_radius_m=.04456):
        """Independent clipped-vacuum-annulus Maxwell volume quadrature.

        Uses actual polygon intersections, never a centroid material filter.
        This estimator is not asserted equal to coarse P1 shape derivatives.
        """
        from shapely.geometry import Point,Polygon
        from shapely import constrained_delaunay_triangles
        a=_number(inner_radius_m,'inner vacuum radius',.04421,.04457)
        b=_number(outer_radius_m,'outer vacuum radius',.04422,.04458)
        if a>=b:raise ValueError('Vacuum annulus radii must be ordered')
        theta=_number(angle_rad,'angle',-1e5,1e5)
        if not isinstance(currents,(list,tuple,np.ndarray)) or len(currents)!=3:raise ValueError('Three balanced currents required')
        i=[_number(x,'current',-150,150) for x in currents]
        if abs(sum(i))>1e-10:raise ValueError('Floating star requires balanced currents')
        state=self._state(i,theta);f=state['field'];nodes=np.array(f['nodes_m']);triangles=np.array(f['triangles']);B=np.array(f['element_b_t'])
        annulus=Point(0,0).buffer(b,quad_segs=2048).difference(Point(0,0).buffer(a,quad_segs=2048))
        integral=analytic_work=area_total=0.;quad=np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]])
        for j,row in enumerate(triangles):
            vertices=nodes[row];rr=np.linalg.norm(vertices,axis=1)
            if rr.max()<a:continue
            lower=np.maximum(np.maximum(vertices.min(axis=0),0),-np.minimum(vertices.max(axis=0),0))
            if np.linalg.norm(lower)>b:continue
            poly=Polygon(vertices).intersection(annulus)
            if poly.is_empty:continue
            if f['region_ids'][j]!='air' and not f['region_ids'][j].startswith('air_mesh_separator'):raise ValueError('Maxwell annulus intersects nonvacuum material')
            for part in _parts(poly):
                for triangle in constrained_delaunay_triangles(part).geoms:
                    xyz=np.array(triangle.exterior.coords)[:3];samples=quad@xyz;r=np.linalg.norm(samples,axis=1)
                    if 'p2_barycentric_b_t' in f:
                        v0,v1,v2=vertices
                        matrix=np.column_stack((v1-v0,v2-v0))
                        pair=(samples-v0)@np.linalg.inv(matrix).T
                        bary=np.column_stack((1-pair.sum(axis=1),pair))
                        field=bary@np.array(f['p2_barycentric_b_t'][j])
                        bx,by=field[:,0],field[:,1]
                    else:
                        field=np.broadcast_to(B[j],(len(samples),2));bx,by=B[j]
                    values=(bx*samples[:,0]+by*samples[:,1])*(-bx*samples[:,1]+by*samples[:,0])/r
                    integral+=triangle.area*float(values.mean());area_total+=triangle.area
                    # Independently assemble Cartesian grad(alpha(r)*J*x).
                    alpha=(b-r)/(b-a);er=samples/r[:,None];jx=np.column_stack((-samples[:,1],samples[:,0]))
                    rotation=np.array([[0.,-1.],[1.,0.]])
                    G=alpha[:,None,None]*rotation[None,:,:]-np.einsum('qa,qb->qab',jx,er)/(b-a)
                    stresswork=np.einsum('qa,qab,qb->q',field,G,field)-.5*np.sum(field*field,axis=1)*np.trace(G,axis1=1,axis2=2)
                    analytic_work-=triangle.area*float(stresswork.mean())
        expected=math.pi*(b*b-a*a)
        if abs(area_total/expected-1)>2e-5:raise ValueError('Vacuum annulus quadrature coverage failed')
        return {'torque_n_m':.025*integral/(MU0*(b-a)),'inner_radius_m':a,'outer_radius_m':b,
                'analytic_same_annulus_virtual_work_torque_n_m':.025*analytic_work/MU0,'vacuum_area_m2':area_total,'relative_area_error':area_total/expected-1,
                'method':'clipped full vacuum annulus Arkkio integral with triangle quadrature','torque_convergence_qualified':False}

    def resolved_coenergy_torque(self,currents,angle_rad,delta_rad=None):
        """Independent two-re-solve reference; not used by the main torque port."""
        delta=self.delta if delta_rad is None else _number(delta_rad,'resolved delta',1e-7,.001)
        angle=_number(angle_rad,'angle',-1e5,1e5)
        if abs(angle-self.anchor)+delta>self.patch+1e-14:raise ValueError('Reference perturbation exceeds local patch')
        if not isinstance(currents,(list,tuple,np.ndarray)) or len(currents)!=3:raise ValueError('Three balanced currents required')
        i=[_number(x,'current',-150,150) for x in currents]
        if abs(sum(i))>1e-10:raise ValueError('Floating star requires balanced currents')
        plus=self._state(i,angle+delta);minus=self._state(i,angle-delta)
        return {'torque_n_m':(plus['magnetic_coenergy_j']-minus['magnetic_coenergy_j'])/(2*delta),
                'delta_rad':delta,'method':'two independent stationary PDE solves on same ALE connectivity',
                'torque_convergence_qualified':False}

    def volume_weighted_virtual_work(self,currents,angle_rad,annulus_radii_m=None):
        """Exact P1 discrete vacuum stress contraction with ALE velocity gradient."""
        theta=_number(angle_rad,'angle',-1e5,1e5)
        if not isinstance(currents,(list,tuple,np.ndarray)) or len(currents)!=3:raise ValueError('Three balanced currents required')
        i=[_number(x,'current',-150,150) for x in currents]
        if abs(sum(i))>1e-10:raise ValueError('Floating star requires balanced currents')
        central=self._state(i,theta);nodes,tris,regions,boundary,area,materials,chi,signed,ratio=self._setup_state(theta)
        op=PlanarMagneticOperator(nodes.tolist(),tris.tolist(),self._solver_regions,materials,(chi@i).tolist())
        gradients=np.stack((-op.curl[:,:,1],op.curl[:,:,0]),axis=2)
        weights=self._weights
        if annulus_radii_m is not None:
            if not isinstance(annulus_radii_m,(list,tuple)) or len(annulus_radii_m)!=2:raise ValueError('Annulus radii pair required')
            a=_number(annulus_radii_m[0],'annulus inner radius',.04421,.04457);b=_number(annulus_radii_m[1],'annulus outer radius',.04422,.04458)
            if a>=b:raise ValueError('Annulus radii must be ordered')
            weights=np.clip((b-np.linalg.norm(nodes,axis=1))/(b-a),0,1)
        velocity=weights[:,None]*np.column_stack((-nodes[:,1],nodes[:,0]))
        G=np.einsum('eia,eib->eab',velocity[tris],gradients)
        B=np.array(central['field']['element_b_t']);air=np.array([name=='air' or name.startswith('air_mesh_separator') for name in regions])
        density=(np.einsum('ea,eab,eb->e',B,G,B)-.5*np.sum(B*B,axis=1)*np.trace(G,axis1=1,axis2=2))/MU0
        torque=-.025*float(area[air]@density[air])
        return {'torque_n_m':torque,'annulus_radii_m':annulus_radii_m,'method':'exact discrete P1 Maxwell-stress contraction with ALE nodal-velocity gradient',
                'torque_convergence_qualified':False}
