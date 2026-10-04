"""SPIKE wrapper for the separately licensed, unchanged EMerge examples.

SPDX-License-Identifier: GPL-2.0-or-later
Only public geometry/plotting API contracts are used; no solver implementation.
"""
import ast
import hashlib
import importlib.metadata
import json
import os
import runpy
import uuid
from pathlib import Path


def run_example(relative_path, parameters, spike, execution_options=None):
    root=Path(__file__).resolve().parent
    options=execution_options or {}
    if set(options)-{'serial_sweep','solver','max_adaptive_steps','geometry_only'}:
        raise ValueError('Unknown example execution option')
    if 'geometry_only' in options and type(options['geometry_only']) is not bool:
        raise ValueError('geometry_only must be a boolean')
    if options.get('solver') not in (None,'AUTO','SUPERLU','PARDISO'):
        raise ValueError('Unsupported explicit solver option')
    if 'max_adaptive_steps' in options and (type(options['max_adaptive_steps']) is not int or not 1<=options['max_adaptive_steps']<=20):
        raise ValueError('Adaptive step limit must be an integer from 1 to 20')
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    entry=next((x for x in manifest['examples'] if x['path']==relative_path),None)
    if entry is None:
        raise ValueError('Example is not in the pinned source manifest')
    if entry['suspended']:
        raise RuntimeError('Thermal analyses are suspended in SPIKE-Em')
    source=(root/'source'/relative_path).resolve()
    if not source.is_relative_to(root/'source'):
        raise ValueError('Source path escapes isolated upstream pack')
    raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=entry['sha256']:
        raise ValueError('Pinned upstream example hash changed; create an independent study instead')
    installed=importlib.metadata.version('emerge')
    if not installed.startswith('3.'):
        raise RuntimeError('This catalog requires EMerge3; installed version is '+installed)
    unknown=set(parameters)-set(entry['defaults'])
    if unknown:
        raise ValueError('Unknown upstream parameter(s): '+', '.join(sorted(unknown)))
    # Replacement is opt-in by changed scalar value, preserving original defaults.
    overrides={k:v for k,v in parameters.items() if v!=entry['defaults'][k]}
    effective_parameters={**entry['defaults'],**parameters}
    scene_id=hashlib.sha256(json.dumps({'source':entry['sha256'],'parameters':effective_parameters,'engine':installed},sort_keys=True).encode()).hexdigest()
    scene={'scene_id':scene_id,'run_id':str(uuid.uuid4()),'coordinate_frame':'emerge-global-xyz','coordinate_unit':'m','phase':'geometry' if options.get('geometry_only') else 'solved'}
    class AdaptExample(ast.NodeTransformer):
        field_variables={}
        def visit_Call(self,node):
            node=self.generic_visit(node)
            if (options.get('geometry_only') and isinstance(node.func,ast.Attribute)
                and (node.func.attr.startswith('run') or node.func.attr in ('solve','adaptive_mesh_refinement'))):
                return ast.copy_location(ast.Call(func=ast.Name(id='_spike_refuse_solve',ctx=ast.Load()),args=[],keywords=[]),node)
            # Upstream passes degrees explicitly but plot_ff defaults to a radian label.
            # Only recognize the exact source expression angle * 180 / np.pi.
            if isinstance(node.func,ast.Name) and node.func.id=='plot_ff' and node.args:
                angle=node.args[0]
                if (isinstance(angle,ast.BinOp) and isinstance(angle.op,ast.Div)
                    and isinstance(angle.right,ast.Attribute) and angle.right.attr=='pi'
                    and isinstance(angle.right.value,ast.Name) and angle.right.value.id=='np'
                    and isinstance(angle.left,ast.BinOp) and isinstance(angle.left.op,ast.Mult)
                    and isinstance(angle.left.right,ast.Constant) and angle.left.right.value==180
                    and not any(k.arg=='xlabel' for k in node.keywords)):
                    node.keywords.append(ast.keyword(arg='xlabel',value=ast.Constant('Theta (deg)')))
            if isinstance(node.func,ast.Attribute) and node.func.attr=='generate_mesh':
                return ast.copy_location(ast.Call(func=ast.Name(id='_spike_capture_mesh',ctx=ast.Load()),args=[node.func,*node.args],keywords=node.keywords),node)
            if isinstance(node.func,ast.Attribute) and node.func.attr=='farfield_3d':
                return ast.copy_location(ast.Call(func=ast.Name(id='_spike_compute_farfield',ctx=ast.Load()),args=[node.func,*node.args],keywords=node.keywords),node)
            if isinstance(node.func,ast.Attribute) and node.func.attr=='run_sweep' and options.get('serial_sweep'):
                if node.args:
                    node.args[0]=ast.Constant(False)
                if len(node.args)>1:
                    node.args[1]=ast.Constant(1)
                node.keywords=[k for k in node.keywords if k.arg not in ('parallel','n_workers')]
                if not node.args:
                    node.keywords.append(ast.keyword(arg='parallel',value=ast.Constant(False)))
                if len(node.args)<2:
                    node.keywords.append(ast.keyword(arg='n_workers',value=ast.Constant(1)))
            if isinstance(node.func,ast.Attribute) and node.func.attr=='adaptive_mesh_refinement' and options.get('max_adaptive_steps'):
                node.keywords=[k for k in node.keywords if k.arg!='max_steps']
                node.keywords.append(ast.keyword(arg='max_steps',value=ast.Constant(options['max_adaptive_steps'])))
            if isinstance(node.func,ast.Attribute) and node.func.attr=='set_solver' and options.get('solver'):
                if options['solver']=='AUTO':
                    return ast.copy_location(ast.Constant(None),node)
                node.args=[ast.Attribute(value=ast.Attribute(value=ast.Name(id='em',ctx=ast.Load()),attr='EMSolver',ctx=ast.Load()),attr=options['solver'],ctx=ast.Load())]
            if isinstance(node.func,ast.Attribute) and node.func.attr=='add_farfield3d':
                return ast.copy_location(ast.Call(func=ast.Name(id='_spike_capture_farfield',ctx=ast.Load()),args=[node.func,*node.args],keywords=node.keywords),node)
            if isinstance(node.func,ast.Attribute) and node.func.attr=='add_field':
                quantity='upstream field'
                representation='returned'
                if node.args and isinstance(node.args[0],ast.Call):
                    field_call=node.args[0]
                    if field_call.args and isinstance(field_call.args[0],ast.Constant):
                        quantity=str(field_call.args[0].value)
                    if len(field_call.args)>1 and isinstance(field_call.args[1],ast.Constant):
                        representation=str(field_call.args[1].value)
                elif node.args and isinstance(node.args[0],ast.Name):
                    quantity,representation=self.field_variables.get(node.args[0].id,(quantity,representation))
                return ast.copy_location(ast.Call(func=ast.Name(id='_spike_capture_field',ctx=ast.Load()),args=[node.func,*node.args],keywords=[*node.keywords,ast.keyword(arg='_quantity',value=ast.Constant(quantity)),ast.keyword(arg='_representation',value=ast.Constant(representation))]),node)
            return node
        def visit_Expr(self,node):
            if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr in ('view','show'):
                return ast.copy_location(ast.Pass(),node)
            return self.generic_visit(node)
        def visit_Assign(self,node):
            if len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
                key=node.targets[0].id
                if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr in ('scalar','vector'):
                    call=node.value
                    if call.args and isinstance(call.args[0],ast.Constant):
                        self.field_variables[key]=(str(call.args[0].value),str(call.args[1].value) if len(call.args)>1 and isinstance(call.args[1],ast.Constant) else 'returned')
                if key in overrides:
                    value=overrides.pop(key)
                    if isinstance(entry['defaults'][key],int):
                        if int(value)!=value:
                            raise ValueError(key+' requires an integer')
                        value=int(value)
                    node.value=ast.copy_location(ast.Constant(value=value),node.value)
            return self.generic_visit(node)
    tree=ast.fix_missing_locations(AdaptExample().visit(ast.parse(raw.decode('utf-8-sig'),filename=str(source))))
    os.environ['PYVISTA_OFF_SCREEN']='true'
    import matplotlib
    matplotlib.use('Agg',force=True)
    import matplotlib.pyplot as plt
    plt.show=lambda *args,**kwargs: None
    captured_fields=[]
    field_diagnostics=[]
    field_artifacts=[]
    mesh_artifacts=[]
    farfield_artifacts=[]
    captured_farfields=[]
    farfield_frames={}
    mesh_preview=None
    physical_mesh=runpy.run_path(str(root/'scene_capture.py'))['physical_mesh']
    class GeometryPrepared(BaseException):
        pass
    def refuse_solve():
        raise RuntimeError('Example reached a solve before explicit mesh preparation; geometry-only mode cannot prepare this example')
    def capture_mesh(method,*args,**kwargs):
        nonlocal mesh_preview
        result=method(*args,**kwargs)
        mesh_preview,metadata=physical_mesh(method.__self__,namespace,output,len(mesh_artifacts)+1)
        mesh_artifacts.append(metadata)
        if metadata.get('diagnostic'):
            field_diagnostics.append(metadata['diagnostic'])
        if options.get('geometry_only'):
            raise GeometryPrepared()
        return result
    def compute_farfield(method,*args,**kwargs):
        result=method(*args,**kwargs)
        origin=kwargs.get('origin',args[3] if len(args)>3 else None)
        farfield_frames[id(result)]=[float(v) for v in ((0,0,0) if origin is None else origin)]
        return result
    def capture_field(method,values,*args,_quantity='upstream field',_representation='returned',**kwargs):
        import numpy as np
        if all(hasattr(values,key) for key in ('x','y','z','F')):
            coords=[values.x,values.y,values.z]
            if all(getattr(values,key,None) is not None for key in ('vx','vy','vz')):
                values=(*coords,values.vx,values.vy,values.vz)
            else:
                values=(*coords,values.F)
        if not isinstance(values,(tuple,list)) or len(values) not in (4,6):
            field_diagnostics.append('Unsupported public field tuple for '+_quantity+': '+type(values).__name__+' public attributes '+str([n for n in dir(values) if not n.startswith('_')])[:700])
            return method.__self__
        arrays=[np.asarray(v).reshape(-1) for v in values]
        if len({len(v) for v in arrays})!=1:
            field_diagnostics.append('Mismatched field coordinates for '+_quantity)
            return method.__self__
        artifact=output/('field-'+str(len(field_artifacts)+1)+'.npz')
        np.savez_compressed(artifact,**dict(zip(('x','y','z','value') if len(arrays)==4 else ('x','y','z','vx','vy','vz'),arrays)))
        field_artifacts.append({'file':artifact.name,'quantity':_quantity,'representation':_representation,'coordinate_unit':'m','returned_samples':len(arrays[0]),'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()})
        if len(captured_fields)>=3:
            field_diagnostics.append('Additional spatial display preserved in '+artifact.name+'; preview limited to three views')
            return method.__self__
        valid=np.logical_and.reduce([np.isfinite(v) for v in arrays])
        indices=np.flatnonzero(valid)
        stride=max(1,int(np.ceil(len(indices)/1200)))
        indices=indices[::stride]
        samples=[]
        for i in indices:
            sample={k:float(arrays[j][i].real) for j,k in enumerate(('x','y','z'))}
            if len(arrays)==4:
                sample.update(real=float(arrays[3][i].real),imag=float(arrays[3][i].imag))
            else:
                for j,k in enumerate(('vx','vy','vz'),start=3):
                    sample[k]=float(arrays[j][i].real)
                    sample[k+'_imag']=float(arrays[j][i].imag)
            samples.append(sample)
        if samples:
            captured_fields.append((_quantity,_representation,samples,stride,len(arrays)))
        return method.__self__
    def capture_farfield(method,farfield,*args,**kwargs):
        import numpy as np
        try:
            theta=np.asarray(farfield.theta).reshape(-1)
            phi=np.asarray(farfield.phi).reshape(-1)
            gain=np.asarray(farfield.gain.norm).reshape(-1)
        except (AttributeError,TypeError,ValueError) as error:
            field_diagnostics.append('Unsupported public far-field object: '+str(error))
            return method.__self__
        if len(theta)!=len(phi) or len(theta)!=len(gain) or not len(theta):
            field_diagnostics.append('Mismatched public far-field angle and gain arrays')
            return method.__self__
        if np.iscomplexobj(theta) or np.iscomplexobj(phi) or np.iscomplexobj(gain):
            field_diagnostics.append('Public far-field angle/gain arrays must be real valued')
            return method.__self__
        theta=theta.astype(float);phi=phi.astype(float);gain=gain.astype(float)
        valid=np.isfinite(theta)&np.isfinite(phi)&np.isfinite(gain)&(gain>=0)
        if not valid.any():
            field_diagnostics.append('No finite public far-field direction/gain samples')
            return method.__self__
        with np.errstate(divide='ignore'):
            gain_dbi=20*np.log10(gain)
        artifact=output/('farfield-'+str(len(farfield_artifacts)+1)+'.npz')
        np.savez_compressed(artifact,theta_rad=theta,phi_rad=phi,gain_amplitude_ratio=gain,gain_dbi=gain_dbi)
        frequency=getattr(farfield,'freq',None)
        try:
            frequency_hz=float(np.real(frequency)) if frequency is not None and np.isfinite(frequency) else None
        except (TypeError,ValueError):
            frequency_hz=None
        dBfloor=kwargs.get('dBfloor',-30)
        try:
            dBfloor=float(dBfloor)
        except (TypeError,ValueError):
            dBfloor=-30.0
        if not np.isfinite(dBfloor) or dBfloor>=0:
            dBfloor=-30.0
        rmax=kwargs.get('rmax')
        if rmax is None and len(args)>=5:
            rmax=args[4]
        try:
            display_radius=float(rmax) if rmax is not None else 1.0
        except (TypeError,ValueError):
            display_radius=1.0
        if not np.isfinite(display_radius) or display_radius<=0:
            display_radius=1.0
        offset=kwargs.get('offset',(0,0,0))
        if len(args)>=6:
            offset=args[5]
        try:
            offset=np.asarray(offset,dtype=float).reshape(-1)
        except (TypeError,ValueError):
            offset=np.zeros(3)
        if len(offset)!=3 or not np.isfinite(offset).all():
            offset=np.zeros(3)
        origin=farfield_frames.get(id(farfield))
        if origin is None:
            field_diagnostics.append('Far-field origin unavailable: preserved angle/gain artifact without an aligned scene preview')
        farfield_artifacts.append({'file':artifact.name,'frequency_hz':frequency_hz,'returned_samples':len(theta),'finite_samples':int(valid.sum()),'angle_unit':'rad','gain_quantity':'public gain.norm amplitude ratio; gain_dbi = 20*log10(ratio)','display_radius':display_radius,'display_radius_unit':'m from upstream rmax; presentation scale, not observation distance' if rmax is not None else 'normalized presentation scale; not observation distance','original_display_offset':offset.tolist(),'source_origin_m':origin,'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()})
        if origin is None:
            return method.__self__
        if rmax is None:
            if mesh_preview is None:
                field_diagnostics.append('No physical geometry scale for far-field scene preview')
                return method.__self__
            display_radius=float(np.max(np.ptp(np.asarray(mesh_preview[0]),axis=0)))*.5
        if captured_farfields:
            field_diagnostics.append('Additional far-field display preserved in '+artifact.name+'; preview limited to one view')
            return method.__self__
        finite_gain=gain[valid]
        maximum=float(np.max(finite_gain))
        if maximum<=0:
            field_diagnostics.append('Public far-field gain contains no positive samples')
            return method.__self__
        relative_dbi=np.full_like(gain,-np.inf)
        positive=valid&(gain>0)
        relative_dbi[positive]=20*np.log10(gain[positive]/maximum)
        radial_fraction=np.clip((relative_dbi-dBfloor)/(-dBfloor),0,1)
        indices=np.flatnonzero(positive)
        stride=max(1,int(np.ceil(len(indices)/1200)))
        indices=indices[::stride]
        samples=[]
        for i in indices:
            direction=np.array([np.sin(theta[i])*np.cos(phi[i]),np.sin(theta[i])*np.sin(phi[i]),np.cos(theta[i])])
            xyz=np.asarray(origin)+display_radius*radial_fraction[i]*direction
            samples.append({'x':float(xyz[0]),'y':float(xyz[1]),'z':float(xyz[2]),'real':float(gain_dbi[i]),'imag':0.0})
        if samples:
            captured_farfields.append((samples,stride,artifact.name,frequency_hz,dBfloor,display_radius,origin))
        return method.__self__
    namespace={'__name__':'__main__','__file__':str(source),'_spike_capture_field':capture_field,'_spike_capture_mesh':capture_mesh,'_spike_capture_farfield':capture_farfield,'_spike_compute_farfield':compute_farfield,'_spike_refuse_solve':refuse_solve}
    # Geometry assets resolve beside original source; outputs go in a dedicated run folder.
    previous=Path.cwd()
    output=previous/'artifacts'/'upstream-emerge'/source.stem
    output.mkdir(parents=True,exist_ok=True)
    try:
        os.chdir(output)
        exec(compile(tree,str(source),'exec'),namespace)
    except GeometryPrepared:
        pass
    finally:
        os.chdir(previous)
        (output/'field-manifest.json').write_text(json.dumps({'engine':installed,'source':relative_path,'source_sha256':entry['sha256'],'parameters':effective_parameters,'scene':scene,'upstream_commit':manifest['commit'],'fields':field_artifacts,'meshes':mesh_artifacts,'farfields':farfield_artifacts,'diagnostics':field_diagnostics},indent=2),encoding='utf-8')
    import numpy as np
    provenance={'kind':'emerge-upstream-example','commit':manifest['commit'],'source':relative_path,'engine_version':installed,'execution_options':options,**scene,'qualification':'engine geometry only; no solve' if options.get('geometry_only') else 'executed output; independent convergence validation required'}
    if mesh_preview is not None and hasattr(spike,'publish_mesh'):
        vertices,triangles,artifact,regions=mesh_preview
        spike.publish_mesh(source.stem+' physical model',vertices,triangles,coordinate_unit='m',provenance=json.dumps({**provenance,'scene_role':'physical_geometry','regions':regions,'full_surface_mesh_artifact':artifact,'representation':'complete material-bearing surface corner triangles; no CAD or port fidelity claim'},separators=(',',':')))
    if options.get('geometry_only'):
        if mesh_preview is None:
            raise RuntimeError('Geometry preparation did not yield a bounded physical model: '+'; '.join(field_diagnostics))
        plt.close('all')
        return
    plot_candidates=[]
    for number in plt.get_fignums():
        for ax in plt.figure(number).axes:
            # Publish only actual numerical line curves, not Smith-grid decorations.
            if len(ax.lines)>16:
                continue
            for line in ax.lines:
                # Blended axes/data transforms denote reference decorations such
                # as axhline, not a sampled curve in the plotted x coordinates.
                if line.get_transform()!=ax.transData:
                    continue
                x=np.asarray(line.get_xdata())
                y=np.asarray(line.get_ydata())
                if x.ndim!=1 or y.ndim!=1 or len(x)!=len(y) or len(x)<2 or np.iscomplexobj(y):
                    continue
                try:
                    valid=np.isfinite(x.astype(float))
                except (TypeError,ValueError):
                    continue
                # Bound all views to <100k cells; stride is explicitly identified.
                stride=max(1,int(np.ceil(len(x)/1500)))
                x=x[valid][::stride];y=y[valid][::stride]
                if not len(x):
                    continue
                label=line.get_label()
                if label.startswith('_'):
                    label='curve '+str(len(plot_candidates)+1)
                is_polar=ax.name=='polar'
                signed_polar=is_polar and bool(np.any(y < 0))
                plot_values=[float(v) if np.isfinite(v) else None for v in y]
                if is_polar:
                    x=np.rad2deg(x)
                title=ax.get_title() or source.stem
                x_label=ax.get_xlabel() or ('angle' if is_polar else 'upstream x')
                if is_polar:
                    x_label=x_label.replace('(rad)', '').replace('[rad]', '').strip()
                y_label=ax.get_ylabel() or 'upstream y'
                classification=' '.join((title,label,x_label,y_label)).lower()
                plot_candidates.append({'title':title+' · '+label,'x':x.astype(float).tolist(),'series':[{'name':label,'values':plot_values}],'x_label':x_label,'y_label':y_label,'x_unit':'deg' if is_polar else '','y_unit':'','kind':'polar' if is_polar and not signed_polar else 'line','stride':stride,'signed_polar':signed_polar,'radiation':is_polar or any(token in classification for token in ('gain','radiat','far field','far-field'))})
    radiation=[candidate for candidate in plot_candidates if candidate['radiation']]
    other=[candidate for candidate in plot_candidates if not candidate['radiation']]
    selected=radiation[:1]+other[:1]+radiation[1:2]+other[1:4]
    selected_ids={id(candidate) for candidate in selected}
    selected.extend(candidate for candidate in plot_candidates if len(selected)<6 and id(candidate) not in selected_ids)
    count=0
    for candidate in selected:
        spike.publish_plot(candidate['title'],candidate['x'],candidate['series'],x_label=candidate['x_label'],y_label=candidate['y_label'],x_unit=candidate['x_unit'],y_unit=candidate['y_unit'],kind=candidate['kind'],provenance=json.dumps({**provenance,'sample_stride':candidate['stride'],'signed_polar_cartesian':candidate['signed_polar'],'radiation_priority':candidate['radiation'],'plot_source':'upstream plotted curve; may include modeled/interpolated values, distinct from sampled scattering table','axis_units':'polar angles converted from radians to degrees; other upstream axis labels retained'}))
        count+=1
    # Public scalar.grid access is demonstrated by the upstream examples themselves.
    # Single-frequency examples often make only3D views; retain their actual S data.
    data=namespace.get('data')
    scalar_data=getattr(data,'scalar',None)
    try:
        grid=getattr(scalar_data,'grid',None)
    except ValueError:
        grid=None
        field_diagnostics.append('Scalar dataset is unstructured; field/eigenmode frequencies are published separately')
    if grid is not None:
        frequency=np.asarray(grid.freq).reshape(-1)
        channels=[]
        for out_port in range(1,17):
            for in_port in range(1,17):
                try:
                    scattering=np.asarray(grid.S(out_port,in_port)).reshape(-1)
                except (KeyError,ValueError,IndexError,AttributeError):
                    continue
                if len(scattering)!=len(frequency) or not np.isfinite(scattering).all():
                    continue
                channels.append((out_port,in_port,scattering))
        if channels and np.isfinite(frequency).all():
            # Target 3k table cells (under 4.6k including per-channel rounding)
            # beside 45k geometry, 32.4k spatial and 18k plotted cells.
            stride=max(1,int(np.ceil(len(frequency)*len(channels)/500)))
            rows=[[float(frequency[i]),out_port,in_port,float(s[i].real),float(s[i].imag),float(abs(s[i]))] for out_port,in_port,s in channels for i in range(0,len(frequency),stride)]
            spike.publish_table('Actual upstream scattering samples',['frequency_Hz','output_port','input_port','real','imag','magnitude'],rows,units=['Hz','index','index','1','1','1'],provenance=json.dumps({**provenance,'sample_stride':stride,'port_basis':'final public grid; see original for port combinations','maximum_probed_port':16}))
    if grid is None and getattr(data,'field',None) is not None:
        field_rows=[]
        for i in range(16):
            try:
                f=complex(data.field[i].freq)
            except (IndexError,KeyError,AttributeError,TypeError):
                break
            if np.isfinite(f):
                field_rows.append([i,f.real,f.imag])
        if field_rows:
            spike.publish_table('Returned field solution frequencies',['solution_index','frequency_real_Hz','frequency_imag_Hz'],field_rows,units=['index','Hz','Hz'],provenance=json.dumps(provenance))
    for samples,stride,artifact,frequency_hz,dBfloor,display_radius,origin in captured_farfields:
        coordinate_unit='m'
        spatial_provenance=json.dumps({**provenance,'scene_role':'farfield_pattern','sample_stride':stride,'full_farfield_artifact':artifact,'frequency_hz':frequency_hz,'source_origin_m':origin,'display_radius_m':display_radius,'angular_coordinates':'global xyz: theta from +z, phi from +x toward +y','gain_quantity':'dBi = 20*log10(public gain.norm amplitude ratio)','display_mapping':'radius is relative gain clipped at '+str(dBfloor)+' dB and scaled to '+str(display_radius)+'; presentation radius is not an observation distance; upstream plotting offset ignored','view':'directional gain spatial scalar'})
        if hasattr(spike,'publish_spatial'):
            spike.publish_spatial(source.stem+' directional gain',samples,quantity='directional gain',unit='dBi',coordinate_unit=coordinate_unit,provenance=spatial_provenance)
        else:
            columns=list(samples[0])
            spike.publish_table(source.stem+' directional gain spatial samples',columns,[[row[key] for key in columns] for row in samples],units=[coordinate_unit]*3+['dBi']*(len(columns)-3),provenance=spatial_provenance)
    field_preview_limit=2 if captured_farfields else 3
    if len(captured_fields)>field_preview_limit:
        field_diagnostics.append('Additional spatial field previews omitted to retain the 12-view aggregate limit; full field sidecars are preserved')
    for quantity,representation,samples,stride,width in captured_fields[:field_preview_limit]:
        unit='V/m' if quantity.startswith('E') or quantity=='normE' else 'A/m' if quantity.startswith('H') or quantity=='normH' else 'W/m2' if quantity=='normS' else 'upstream units'
        spatial_provenance=json.dumps({**provenance,'scene_role':'field_samples','sample_stride':stride,'representation':representation,'coordinates':'m','source_sample_count':len(samples),'view':'spatial vector' if width==6 else 'spatial scalar'})
        if hasattr(spike,'publish_spatial'):
            spike.publish_spatial(source.stem+' '+quantity,samples,quantity=quantity,unit=unit,provenance=spatial_provenance)
        else:
            columns=list(samples[0])
            spike.publish_table(source.stem+' '+quantity+' spatial samples',columns,[[row[key] for key in columns] for row in samples],units=['m']*3+[unit]*(len(columns)-3),provenance=spatial_provenance)
    spike.publish_table('Upstream execution record',['source','engine','published_curves','spatial_views','farfield_views','diagnostics','qualification'],[[relative_path,installed,count,min(len(captured_fields),field_preview_limit),len(captured_farfields),'; '.join(field_diagnostics),'Not a convergence or paper-reproduction certificate']],provenance=json.dumps(provenance))
    if count==0:
        print('Example completed; no compatible Matplotlib line curves; spatial samples captured:',len(captured_fields))
    plt.close('all')
