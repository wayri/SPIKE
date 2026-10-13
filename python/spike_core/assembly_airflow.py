# SPDX-License-Identifier: Apache-2.0
"""Assembly CAD air-complement to experimental native OpenFOAM CHT execution."""
import hashlib
import itertools
import json
from pathlib import Path
from .assembly_airflow_runtime import run_air_mesh
from .assembly_airflow_mesh import validate_geometry
from .openfoam_polymesh import write_polymesh
from .openfoam_multiregion import prepare_runnable_multiregion_case
from .openfoam_multiregion_execution import run_multiregion_case

CONTRACT = 'spike/assembly-airflow-request/v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def evidence(value, contract='spike/solver-mesh/v1'):
    return {'id': 'assembly-airflow', 'sha256': digest(value), 'qualified': True, 'contract': contract}


def validate_request(request):
    required = {'contract', 'geometry', 'materials', 'region_properties', 'mode',
                'ambient_temperature_k', 'numerics'}
    if not isinstance(request, dict) or not required <= set(request) or set(request)-required-{'flow_rate_m3_s', 'inlet', 'outlet', 'perfect_solid_contact_acknowledged'}:
        raise ValueError('AIRFLOW_CONTRACT: unexpected fields')
    if request['contract'] != CONTRACT or request['mode'] not in ('forced', 'natural', 'static'):
        raise ValueError('AIRFLOW_CONTRACT: unsupported mode')
    validate_geometry(request['geometry'])
    if type(request.get('perfect_solid_contact_acknowledged', False)) is not bool:
        raise ValueError('AIRFLOW_CONTACT: perfect-contact acknowledgement must be boolean')
    names = {s['id'] for s in request['geometry']['solids']}
    if set(request['region_properties']) != names:
        raise ValueError('AIRFLOW_REGIONS: properties must cover every source solid')
    materials = {m['id']: m for m in request['materials']}
    from .openfoam_materials import normalize_material
    if not 1 <= len(materials) == len(request['materials']) <= 65:
        raise ValueError('AIRFLOW_MATERIAL: unique bounded materials required')
    for material in request['materials']:
        normalize_material(material)
    for solid in request['geometry']['solids']:
        if solid['material_id'] not in materials or materials[solid['material_id']]['phase'] != 'solid':
            raise ValueError('AIRFLOW_MATERIAL: every solid needs declared solid properties')
    if type(request['ambient_temperature_k']) not in (int, float) or not 0 < request['ambient_temperature_k'] < 1e5:
        raise ValueError('AIRFLOW_TEMPERATURE: positive finite kelvin required')
    if 'air' not in materials or materials['air']['phase'] != 'fluid':
        raise ValueError('AIRFLOW_MATERIAL: explicit air material required')
    if request['mode'] == 'natural' and 'density_model' not in materials['air']:
        raise ValueError('AIRFLOW_BUOYANCY: explicit bounded density model required')
    if request['mode'] == 'static' and 'density_model' in materials['air']:
        raise ValueError('AIRFLOW_STATIC: constant density required')
    for value in request['region_properties'].values():
        if set(value) != {'role', 'power_w'} or type(value['power_w']) not in (int, float) or not 0 <= value['power_w'] <= 1e9:
            raise ValueError('AIRFLOW_SOURCE: explicit finite nonnegative source watts required')
        if value['role'] not in ('board', 'package', 'heatsink', 'enclosure', 'potting', 'coating'):
            raise ValueError('AIRFLOW_REGIONS: unsupported solid role')
    if request['mode'] == 'forced':
        if type(request.get('flow_rate_m3_s')) not in (float, int) or not 0 < request['flow_rate_m3_s'] <= 1e3:
            raise ValueError('AIRFLOW_FAN: positive prescribed flow required')
        for key in ('inlet', 'outlet'):
            value = request.get(key)
            if not isinstance(value, dict) or set(value) != {'axis', 'coordinate_mm'} or type(value['axis']) is not int or value['axis'] not in (0, 1, 2) or type(value['coordinate_mm']) not in (float, int) or not abs(value['coordinate_mm']) <= 1e6:
                raise ValueError('AIRFLOW_BOUNDARY: explicit bounded plane selector required')
        if request['inlet'] == request['outlet']:
            raise ValueError('AIRFLOW_BOUNDARY: inlet and outlet must differ')
    elif set(request) & {'flow_rate_m3_s', 'inlet', 'outlet'}:
        raise ValueError('AIRFLOW_BOUNDARY: flow fields require forced mode')
    digest(request)


def prepare_airflow_case(request, meshed, output_dir):
    validate_request(request)
    root = Path(output_dir)
    cells, points = meshed['cells'], meshed['vertices']
    grouped, faces = {}, {}
    for cell in cells:
        region = cell['material_id']
        grouped.setdefault(region, []).append(cell)
        for face in itertools.combinations(cell['vertices'], 3):
            faces.setdefault(tuple(sorted(face)), []).append(region)
    patches = {r: {} for r in grouped}
    ownership = {r: {} for r in grouped}
    interfaces = {}
    mesh_digest = digest(meshed)
    for face, regions in faces.items():
        if len(regions) == 2 and regions[0] == regions[1]:
            continue
        if len(regions) == 2:
            left, right = sorted(regions)
            if left != 'air' and right != 'air' and not request.get('perfect_solid_contact_acknowledged', False):
                raise ValueError('AIRFLOW_CONTACT: explicitly acknowledge perfect solid-solid contact; finite contact resistance is unsupported')
            iid = left+'_'+right
            interfaces[iid] = {'id': iid, 'region_a': left, 'region_b': right,
                'patch_a': left+'_to_'+right, 'patch_b': right+'_to_'+left,
                'kind': 'conjugate', 'evidence': evidence({'mesh': mesh_digest, 'interface': iid}, 'spike/qualified-contact/v1')}
            for region, other in ((left, right), (right, left)):
                name = region+'_to_'+other
                patch = patches[region].setdefault(name, {'name': name, 'type': 'mappedWall',
                    'neighbour_region': other, 'neighbour_patch': other+'_to_'+region,
                    'interface_id': iid, 'faces': []})
                patch['faces'].append(list(face))
                ownership[region][name] = 'interface:'+iid
        elif len(regions) == 1:
            region = regions[0]
            name, owner, kind = 'exterior', 'external:fixed_temperature', 'wall'
            if region == 'air' and request['mode'] == 'forced':
                selected = [key for key in ('inlet', 'outlet') if all(abs(points[v][request[key]['axis']]-request[key]['coordinate_mm']) <= 1e-7 for v in face)]
                if len(selected) > 1:
                    raise ValueError('AIRFLOW_BOUNDARY: overlapping selectors')
                if selected:
                    name = selected[0]
                    owner = 'fan:prescribed' if name == 'inlet' else 'external:pressure_outlet'
                    kind = 'patch'
            patches[region].setdefault(name, {'name': name, 'type': kind, 'faces': []})['faces'].append(list(face))
            ownership[region][name] = owner
        else:
            raise ValueError('AIRFLOW_MESH: nonmanifold cell face')
    if request['mode'] == 'forced' and not {'inlet', 'outlet'} <= set(patches['air']):
        raise ValueError('AIRFLOW_BOUNDARY: selectors must intersect exterior air faces')
    regions, sources, meshes = [], [], {}
    for region, group in sorted(grouped.items()):
        used = sorted({v for cell in group for v in cell['vertices']})
        remap = {old: new for new, old in enumerate(used)}
        local_cells = [{**cell, 'vertices': [remap[v] for v in cell['vertices']]} for cell in group]
        local_patches = [{**patch, 'faces': [[remap[v] for v in face] for face in patch['faces']]}
                         for patch in patches[region].values()]
        mesh = {'contract': 'spike/solver-mesh/v1', 'units': 'mm', 'coordinate_system': 'right_handed_xyz',
                'vertices': [points[v] for v in used], 'cells': local_cells, 'object_map': {},
                'counts': {'vertices': len(used), 'cells': len(group)}}
        job = {'contract': 'spike/openfoam-polymesh-request/v1', 'region_id': region, 'mesh': mesh,
            'mesh_evidence': evidence(mesh), 'boundary_patches': local_patches}
        if region != 'air':
            job['cell_zones'] = [{'name': 'source', 'cell_ids': [c['id'] for c in group]}]
        meshes[region] = write_polymesh(job, root/'meshes'/region/'polyMesh')
        solid = None if region == 'air' else request['geometry']['solids'][int(region.split('_')[1])]
        props = {} if solid is None else request['region_properties'][solid['id']]
        regions.append({'id': region, 'kind': 'fluid' if solid is None else 'solid',
            'role': 'air' if solid is None else props['role'], 'material_id': 'air' if solid is None else solid['material_id'],
            'mesh_evidence': meshes[region]['poly_mesh_evidence'], 'boundary_ownership': ownership[region]})
        if props.get('power_w', 0) > 0:
            sources.append({'id': region+'_power', 'solid_region_id': region, 'power_w': props['power_w'],
                'evidence': evidence(props, 'spike/component-power-table/v1'),
                'fv_option': {'cell_zone': 'source', 'volumetric_power_w_m3': props['power_w']/(meshed['volumes_mm3'][region]*1e-9)}})
    environment = {'enclosure': 'open', 'radiation': False, 'vacuum': False, 'medium': 'air',
        'ambient_temperature_k': request['ambient_temperature_k'],
        'gravity_m_s2': [0, 0, -9.81] if request['mode'] == 'natural' else [0, 0, 0]}
    if request['mode'] != 'natural' and not any(m.get('density_model') for m in request['materials']):
        environment['dpdt_enabled'] = False
    fans = []
    if request['mode'] == 'forced':
        fans = [{'id': 'prescribed', 'fluid_region_id': 'air', 'flow_rate_m3_s': request['flow_rate_m3_s'],
            'boundary_patch': 'inlet', 'boundary_evidence': meshes['air']['poly_mesh_evidence']}]
        environment['pressure_outlets'] = [{'fluid_region_id': 'air', 'boundary_patch': 'outlet',
            'static_pressure_pa': 101325, 'backflow_temperature_k': request['ambient_temperature_k']}]
    heatsinks = []
    for region in regions:
        if region['role'] != 'heatsink':
            continue
        mounts = [i for i in interfaces.values() if region['id'] in (i['region_a'], i['region_b'])
                  and 'air' not in (i['region_a'], i['region_b'])]
        if not mounts:
            raise ValueError('AIRFLOW_HEATSINK: heatsink role requires an actual shared solid mounting face')
        heatsinks.extend({'id': region['id']+'_mount_'+str(index), 'region_id': region['id'],
                         'mount_interface_id': interface['id']} for index, interface in enumerate(mounts))
    translated = {'contract': 'spike/openfoam-multiregion-request/v1', 'job_id': 'assembly_airflow',
        'mesh_evidence': evidence({k:v['poly_mesh_digest'] for k,v in meshes.items()}, 'spike/openfoam-multiregion-mesh-set/v1'),
        'materials': request['materials'], 'regions': regions, 'interfaces': list(interfaces.values()),
        'heat_sources': sources, 'environment': environment, 'fans': fans, 'heatsinks': heatsinks, 'numerics': request['numerics']}
    (root/'translated-request.json').write_text(json.dumps(translated, indent=2), encoding='utf-8')
    return prepare_runnable_multiregion_case(translated, root/'case', root/'meshes')


def run_assembly_airflow(request, output_dir, *, cancellation_event=None, timeout_s=600, memory_limit_mb=4096):
    validate_request(request)
    if cancellation_event is not None and cancellation_event.is_set():
        return {'status': 'cancelled', 'fields': {}}
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root/'request.json').write_text(json.dumps(request, indent=2), encoding='utf-8')
    mesh = run_air_mesh(request['geometry'], root/'mesh', cancellation_event=cancellation_event,
                        timeout_s=min(timeout_s, 600), memory_limit_mb=min(memory_limit_mb, 8192))
    prepared = prepare_airflow_case(request, mesh, root)
    if prepared['status'] != 'prepared_runnable_case':
        return prepared
    result = run_multiregion_case(root/'case', timeout_s=timeout_s, memory_limit_mb=memory_limit_mb,
                                 cancellation_event=cancellation_event)
    result.update(request_sha256=digest(request), source_ids=mesh['source_ids'],
        air_model=request['mode'], production_qualified=False)
    (root/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result
