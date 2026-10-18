# SPDX-License-Identifier: Apache-2.0
"""Source-aware, undoable schematic fragment copy and placement."""
from copy import deepcopy
from collections import Counter
import hashlib
import re
import uuid

from .document import Document


CONTRACT = 'spikes/schematic-fragment/v1'
MAX_COMPONENTS = 1000
_VISUAL_FIELDS = ('x', 'y', 'rotation', 'mirror_x', 'mirror_y',
                  'package', 'variant', 'temperature_k', 'limits', 'model_source',
                  'evidence', 'parameters')
_SEMICONDUCTOR_KINDS = {'npn_ebers_moll', 'nmos_level1', 'bsim_bulk', 'bsim_cmg',
                        'gan_hemt', 'sic_mosfet'}


def _dependency_signature(source):
    """Hash source-owned definitions while excluding top-level instances.

    Repeat placement adds top-level instances, so those records cannot be part
    of the signature. Parameters, models, includes, subcircuits, directives,
    comments, and the title remain binding context and are retained.
    """
    kept=[];depth=0;continuation_kept=True
    for index,line in enumerate(source.splitlines(keepends=True)):
        stripped=line.lstrip();tokens=stripped.split()
        if index==0:
            kept.append(line);continuation_kept=True;continue
        if stripped.startswith('+'):
            if continuation_kept:kept.append(line)
            continue
        if not tokens:
            kept.append(line);continuation_kept=True;continue
        keyword=tokens[0].casefold()
        if depth or keyword=='.subckt':
            kept.append(line);continuation_kept=True
            if keyword=='.subckt':depth+=1
            elif keyword=='.ends':depth=max(0,depth-1)
            continue
        if keyword.startswith('.') or stripped.startswith(('*',';')):
            kept.append(line);continuation_kept=True;continue
        continuation_kept=False
    return hashlib.sha256(''.join(kept).encode('utf-8')).hexdigest()


def _instance_record(source, reference):
    """Return one top-level instance plus its continuation records."""
    lines = source.splitlines(keepends=True)
    matches = []
    depth = 0
    for index, line in enumerate(lines):
        tokens = line.split()
        if not tokens:
            continue
        keyword = tokens[0].casefold()
        if keyword == '.subckt':
            depth += 1
        elif keyword == '.ends':
            depth -= 1
        elif index and depth == 0 and tokens[0].casefold() == reference.casefold():
            end = index + 1
            while end < len(lines) and lines[end].lstrip().startswith('+'):
                end += 1
            matches.append(''.join(lines[index:end]))
    if len(matches) != 1:
        raise ValueError(f'{reference} is not one unique top-level source instance')
    return matches[0]


def copy_fragment(document, component_ids):
    """Capture selected source instances and wholly selected direct wires."""
    selected = set(component_ids)
    parts = [part for part in document.data['components'] if part['id'] in selected]
    if not parts or len(parts) != len(selected):
        raise ValueError('Select existing components to copy')
    if len(parts) > MAX_COMPONENTS:
        raise ValueError(f'Copy is limited to {MAX_COMPONENTS} components')
    if any(':' in part['ref'] for part in parts):
        raise ValueError('Copy top-level instances; edit hierarchical parts at their definition')
    center = (sum(float(part['x']) for part in parts) / len(parts),
              sum(float(part['y']) for part in parts) / len(parts))
    components = []
    for part in parts:
        visual = {key: deepcopy(part[key]) for key in _VISUAL_FIELDS if key in part}
        visual['x'] = float(part['x']) - center[0]
        visual['y'] = float(part['y']) - center[1]
        components.append({'source_id': part['id'], 'ref': part['ref'], 'kind':part['kind'],
                           'nodes': list(part['nodes']),
                           'record': _instance_record(document.data['source'], part['ref']),
                           'model_policy': deepcopy(document.data['model_policy']['components'].get(part['ref'].upper())),
                           'visual': visual})
    wires = []
    for wire in document.data['wires']:
        if ((len(wire['a'])==1 and len(wire['b'])==2 and wire['b'][0] in selected) or
                (len(wire['b'])==1 and len(wire['a'])==2 and wire['a'][0] in selected)):
            raise ValueError('Selection touches an explicit junction route; include its connectivity through Circuit text or duplicate components without that junction branch')
        if len(wire['a']) == len(wire['b']) == 2 and wire['a'][0] in selected and wire['b'][0] in selected:
            item = deepcopy(wire)
            item['waypoints'] = [[float(x) - center[0], float(y) - center[1]]
                                 for x, y in item.get('waypoints', [])]
            wires.append(item)
    return {'contract': CONTRACT, 'source_document_id': document.data['id'],
            'dependency_sha256':_dependency_signature(document.data['source']),
            'components': components, 'wires': wires}


def _validate_payload(payload):
    if not isinstance(payload, dict) or payload.get('contract') != CONTRACT:
        raise ValueError('Clipboard does not contain a SPIKES schematic fragment')
    if not isinstance(payload.get('source_document_id'),str) or not payload['source_document_id']:
        raise ValueError('Schematic fragment is missing its source document identity')
    if not isinstance(payload.get('dependency_sha256'),str) or not re.fullmatch(r'[0-9a-f]{64}',payload['dependency_sha256']):
        raise ValueError('Schematic fragment is missing its source dependency signature')
    components = payload.get('components')
    if not isinstance(components, list) or not components or len(components) > MAX_COMPONENTS:
        raise ValueError('Invalid schematic fragment component count')
    source_ids = set()
    for item in components:
        if not isinstance(item, dict) or not isinstance(item.get('source_id'), str) or not item['source_id']:
            raise ValueError('Invalid schematic fragment component identity')
        if item['source_id'] in source_ids:
            raise ValueError('Duplicate schematic fragment component identity')
        source_ids.add(item['source_id'])
        if not isinstance(item.get('ref'), str) or not item['ref'] or ':' in item['ref']:
            raise ValueError('Invalid schematic fragment source reference')
        if not isinstance(item.get('kind'),str) or not item['kind']:
            raise ValueError('Invalid schematic fragment source kind')
        if not isinstance(item.get('nodes'), list) or not item['nodes']:
            raise ValueError('Invalid schematic fragment terminals')
        if not isinstance(item.get('record'), str) or len(item['record']) > 1024 * 1024:
            raise ValueError('Invalid schematic fragment source record')
        lines=item['record'].splitlines()
        tokens=lines[0].split() if lines else []
        if not tokens or tokens[0].casefold()!=item['ref'].casefold() or any(not line.lstrip().startswith('+') for line in lines[1:]):
            raise ValueError('Fragment source record must contain exactly its declared instance and continuations')
        if item['ref'][0].upper() in {'F','H','K','W'} or re.search(r'(?i)\b[VI]\s*\(',item['record']):
            raise ValueError(f"{item['ref']} has dependent source semantics; duplicate its complete dependency explicitly in Circuit text")
        visual = item.get('visual')
        if (not isinstance(visual, dict) or set(visual)-set(_VISUAL_FIELDS) or
                any(type(visual.get(key)) not in (int, float) for key in ('x', 'y'))):
            raise ValueError('Invalid schematic fragment geometry')
        policy=item.get('model_policy')
        if policy is not None:
            from .model_fidelity import default_policy,validate
            candidate=default_policy();candidate['components'][item['ref'].upper()]=deepcopy(policy);validate(candidate)
    wires = payload.get('wires', [])
    if not isinstance(wires, list) or len(wires) > 10000:
        raise ValueError('Invalid schematic fragment wires')
    for wire in wires:
        if (not isinstance(wire, dict) or len(wire.get('a', [])) != 2 or len(wire.get('b', [])) != 2 or
                wire['a'][0] not in source_ids or wire['b'][0] not in source_ids):
            raise ValueError('Fragment wires must join copied component terminals')
    return components, wires


def _new_reference(reference, used):
    prefix = reference[0].upper()
    if not prefix.isalpha():
        raise ValueError(f'Cannot duplicate source reference {reference}')
    index = 1
    while (prefix + str(index)).casefold() in used:
        index += 1
    result = prefix + str(index)
    used.add(result.casefold())
    return result


def _replace_reference(record, reference):
    match = re.search(r'\S+', record)
    if match is None:
        raise ValueError('Empty schematic fragment source record')
    return record[:match.start()] + reference + record[match.end():]


def _replace_nodes(record,nodes,kind):
    """Rewrite only terminal tokens in one already-bounded source record."""
    physical=list(nodes)
    if kind in _SEMICONDUCTOR_KINDS and len(nodes)>=3:
        physical=[nodes[0],nodes[2],nodes[1],*nodes[3:]]
    lines=record.splitlines(keepends=True)
    spans=list(re.finditer(r'\S+',lines[0]))
    if len(spans)<1+len(physical):
        raise ValueError('Terminal continuation requires explicit Circuit text editing')
    for span,node in reversed(list(zip(spans[1:1+len(physical)],physical))):
        lines[0]=lines[0][:span.start()]+str(node)+lines[0][span.end():]
    return ''.join(lines)


def _insert_records(source, records):
    ending = list(re.finditer(r'(?im)^[ \t]*\.end[ \t]*\r?$', source))
    if len(ending) != 1:
        raise ValueError('Current sheet requires one final .end directive')
    separator = '' if source[:ending[0].start()].endswith(('\n', '\r')) else '\n'
    insertion = ''.join(record if record.endswith(('\n', '\r')) else record + '\n' for record in records)
    return source[:ending[0].start()] + separator + insertion + source[ending[0].start():]


def _isolated_node_map(document, components):
    used = {str(node).casefold() for part in document.data['components'] for node in part['nodes']}
    result = {}
    serial = 1
    for item in components:
        for node in item['nodes']:
            folded = str(node).casefold()
            if folded == '0' or folded in result:
                continue
            stem = re.sub(r'[^A-Za-z0-9_.$+-]', '_', str(node)).strip('_')[:28] or 'net'
            candidate = f'copy_{serial}_{stem}'
            while candidate.casefold() in used:
                serial += 1
                candidate = f'copy_{serial}_{stem}'
            used.add(candidate.casefold())
            result[folded] = candidate
            serial += 1
    return result


def prepare_paste(document, payload):
    """Prepare a non-mutating placement plan against the current source."""
    components, wires = _validate_payload(payload)
    if payload['source_document_id']!=document.data['id']:
        raise ValueError('Selected schematic fragments can only be pasted back into their source sheet; use whole-sheet import for another document')
    if payload['dependency_sha256']!=_dependency_signature(document.data['source']):
        raise ValueError('Sheet parameters, models, directives, or subcircuits changed since copy; copy the selection again')
    used_refs = {part['ref'].casefold() for part in document.data['components']}
    reference_map = {item['source_id']: _new_reference(item['ref'], used_refs) for item in components}
    node_map = _isolated_node_map(document, components)
    remapped_nodes={item['source_id']:['0' if str(node).casefold()=='0' else node_map[str(node).casefold()]
                                       for node in item['nodes']] for item in components}
    records = [_replace_nodes(_replace_reference(item['record'],reference_map[item['source_id']]),
                              remapped_nodes[item['source_id']],item['kind'])
               for item in components]
    candidate_source = _insert_records(document.data['source'], records)
    parsed = Document.from_netlist(candidate_source)
    expected=Counter(part['ref'].casefold() for part in document.data['components'])
    expected.update(reference.casefold() for reference in reference_map.values())
    actual=Counter(part['ref'].casefold() for part in parsed.data['components'])
    if actual!=expected:
        raise ValueError('Fragment source introduced undeclared instances or changed source-owned component identity')
    parsed_by_ref = {part['ref'].casefold(): part for part in parsed.data['components']}
    id_map = {}
    planned_parts = []
    for item in components:
        reference = reference_map[item['source_id']]
        part = deepcopy(parsed_by_ref[reference.casefold()])
        if part['kind']!=item['kind'] or [node.casefold() for node in part['nodes']]!=[node.casefold() for node in remapped_nodes[item['source_id']]]:
            raise ValueError(f'{reference} did not retain its declared source kind and ordered terminals')
        part.update(deepcopy(item['visual']))
        part['ref'] = reference
        part['nodes'] = remapped_nodes[item['source_id']]
        part['id'] = uuid.uuid4().hex
        id_map[item['source_id']] = part['id']
        planned_parts.append(part)
    planned_wires = []
    for copied in wires:
        wire = deepcopy(copied)
        wire['id'] = uuid.uuid4().hex
        wire['a'][0] = id_map[wire['a'][0]]
        wire['b'][0] = id_map[wire['b'][0]]
        planned_wires.append(wire)
    policies={reference_map[item['source_id']].upper():deepcopy(item['model_policy']) for item in components if item.get('model_policy') is not None}
    validation=deepcopy(document.data);validation['source']=candidate_source
    validation['components'].extend(deepcopy(planned_parts));validation['wires'].extend(deepcopy(planned_wires))
    validation['model_policy']['components'].update(deepcopy(policies))
    Document(validation)  # Preview data must be safe to route and paint before click.
    return {'contract': CONTRACT, 'base_source': document.data['source'],
            'source': candidate_source, 'components': planned_parts,
            'wires': planned_wires, 'model_policy':policies,'quarter_turns': 0}


def rotate_plan(plan):
    """Rotate the preview clockwise around its placement anchor."""
    for part in plan['components']:
        part['x'], part['y'] = -float(part['y']), float(part['x'])
        part['rotation'] = (int(part.get('rotation', 0)) + 90) % 360
    for wire in plan['wires']:
        wire['waypoints'] = [[-float(y), float(x)] for x, y in wire.get('waypoints', [])]
        wire['bend'] = 'vertical' if wire.get('bend', 'horizontal') == 'horizontal' else 'horizontal'
    plan['quarter_turns'] = (int(plan.get('quarter_turns', 0)) + 1) % 4
    return plan


def preview(plan, position):
    x, y = map(float, position)
    parts = [dict(deepcopy(part), x=float(part['x']) + x, y=float(part['y']) + y)
             for part in plan['components']]
    wires = []
    for planned in plan['wires']:
        wire = deepcopy(planned)
        wire['waypoints'] = [[float(px) + x, float(py) + y] for px, py in wire.get('waypoints', [])]
        wires.append(wire)
    return parts, wires


def place(document, plan, position):
    """Commit the prepared fragment in one validated undo transaction."""
    if document.data['source'] != plan.get('base_source'):
        raise ValueError('Sheet source changed during placement; paste again')
    parts, wires = preview(plan, position)
    existing_ids = {part['id'] for part in document.data['components']}
    if any(part['id'] in existing_ids for part in parts):
        raise ValueError('Fragment component identity collides with the sheet')
    next_order = max([0] + [wire.get('draw_order', 0) for wire in document.data['wires']]) + 1
    for offset, wire in enumerate(wires):
        wire['draw_order'] = next_order + offset
    def mutate(data):
        data['source'] = plan['source']
        data['components'].extend(deepcopy(parts))
        data['wires'].extend(deepcopy(wires))
        data['model_policy']['components'].update(deepcopy(plan.get('model_policy',{})))
    document.commit(mutate)
    return [part['id'] for part in parts]
