# SPDX-License-Identifier: Apache-2.0
"""Source-bound scoped labels, not an independent schematic connectivity graph."""
from copy import deepcopy
import re
import uuid

KINDS = ('local', 'global', 'hierarchical')
NAME = re.compile(r'[A-Za-z0-9_.$+-]{1,128}')


def _project(data):
    from .part_properties import parse
    return parse(data['source'])


def _terminal(data, terminal):
    parts = {p['id']: p for p in data['components']}
    if (not isinstance(terminal, (list, tuple)) or len(terminal) != 2
            or not isinstance(terminal[0], str) or terminal[0] not in parts
            or type(terminal[1]) is not int
            or not 0 <= terminal[1] < len(parts[terminal[0]]['nodes'])):
        raise ValueError('Choose an existing component terminal or wire')
    part = parts[terminal[0]]
    return part, part['nodes'][terminal[1]].lower(), part['ref'].rpartition(':')[0].upper()


def _resolve(project, scope, kind, name):
    if kind not in KINDS or not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError('Use a local, global or hierarchical label and one simple SPICE node name (1..128 characters)')
    name = name.lower()
    if kind == 'global':
        if name != '0' and name not in project.global_nodes:
            raise ValueError('Global labels require an actual .global declaration; hierarchy must be edited in Circuit text')
        return name
    instance = next((h for h in project.hierarchy if h.path == scope), None)
    if kind == 'hierarchical':
        if instance is None or name not in instance.pins:
            raise ValueError('Hierarchical labels must name a declared port of this exact sheet instance')
        result = instance.nodes[instance.pins.index(name)]
        # The native parser resolves a .global name before formal port bindings.
        if name in project.global_nodes and result != name:
            raise ValueError('This formal port is shadowed by .global; correct the source before labeling it')
        return result
    if name == '0' or name in project.global_nodes:
        return name
    if instance and name in instance.pins:
        return instance.nodes[instance.pins.index(name)]
    return f'{scope.lower()}:{name}' if scope else name


def _check(data, item, project):
    if not isinstance(item, dict) or set(item) - {'id', 'kind', 'name', 'terminal', 'sheet_path', 'net', 'wire_id'}:
        raise ValueError('Invalid net label fields')
    if not isinstance(item.get('id'), str) or not item['id'] or len(item['id']) > 128:
        raise ValueError('Invalid net label ID')
    part, node, scope = _terminal(data, item.get('terminal'))
    if item.get('sheet_path') != scope or item.get('net') != node:
        raise ValueError('Net label attachment or sheet scope is stale')
    from .pin_geometry import ordered_nodes
    element = next((e for e in project.elements if e.name.upper() == part['ref'].upper()), None)
    if element is None or item['terminal'][1] >= len(ordered_nodes(element)) or ordered_nodes(element)[item['terminal'][1]].lower() != node:
        raise ValueError('Net label terminal disagrees with authoritative Circuit text')
    if _resolve(project, scope, item.get('kind'), item.get('name')) != node:
        raise ValueError('Label name does not resolve to the attached electrical net in this scope')
    if 'wire_id' in item:
        wire = next((w for w in data['wires'] if w['id'] == item['wire_id']), None)
        if wire is None:
            raise ValueError('Net label wire no longer exists')
        endpoint = wire['a']
        if len(endpoint) == 1:
            junction = next(j for j in data['junctions'] if j['id'] == endpoint[0])
            endpoint = junction['source_terminal']
        if _terminal(data, endpoint)[1] != node:
            raise ValueError('Net label wire does not share the attached terminal net')


def validate(data):
    """Validate saved metadata against one native source elaboration."""
    labels = data.get('labels', [])
    if not isinstance(labels, list) or len(labels) > 10000:
        raise ValueError('Invalid net label list (maximum 10000)')
    if not labels:
        return
    project = _project(data)
    seen = set()
    for item in labels:
        _check(data, item, project)
        if item['id'] in seen:
            raise ValueError('Duplicate net label ID')
        seen.add(item['id'])


def reconcile(data):
    """Keep only still-truthful labels after explicit source/route replacement."""
    if not data.get('labels'):
        return []
    project = _project(data)
    retained = []
    for item in data['labels']:
        try:
            _check(data, item, project)
        except (ValueError, KeyError, IndexError, StopIteration):
            continue
        retained.append(deepcopy(item))
    return retained


def attachment(data, value):
    """Normalize Canvas.plot_attachment or a stable component/pin pair."""
    if isinstance(value, dict):
        terminal = [value.get('part_id', value.get('component_id')), value.get('pin_index')]
        wire_id = value.get('wire_id')
        if not wire_id and value.get('attach_point') is not None:
            from .editor_geometry import route, nearest_route_point
            parts = {p['id']: p for p in data['components']}
            junctions = {j['id']: j for j in data['junctions']}
            for wire in reversed(data['wires']):
                if nearest_route_point(route(parts, wire, junctions), value['attach_point'])[2] < 1e-6:
                    wire_id = wire['id']
                    break
    else:
        terminal, wire_id = value, None
    _terminal(data, terminal)
    return list(terminal), wire_id


def defaults(data, value):
    terminal, _ = attachment(data, value)
    _, node, scope = _terminal(data, terminal)
    project = _project(data)
    instance = next((h for h in project.hierarchy if h.path == scope), None)
    ports = [pin for pin, net in zip(instance.pins, instance.nodes) if net == node] if instance else []
    name = ports[0] if ports else node.rpartition(':')[2]
    return dict(name=name, kind='local', sheet_path=scope, net=node, ports=ports)


def _rename(data, old, new):
    """Conservative top-level whole-net rewrite with known consumer migration."""
    if old == '0':
        raise ValueError('SPICE reference node 0 cannot be renamed')
    source = data['source']
    if re.search(r'(?im)^\s*\.(subckt|include|inc|lib|ic|nodeset|measure|meas|control)\b', source) or any(':' in p['ref'] for p in data['components']):
        raise ValueError('Renaming hierarchy/includes/node directives is unsupported; edit and verify Circuit text explicitly')
    project = _project(data)
    if old in project.global_nodes:
        raise ValueError('Renaming an existing declared-global net requires explicit Circuit text review')
    if re.search(r'(?i)\bv\s*\(', source):
        raise ValueError('Source voltage-reference expressions require explicit Circuit text editing')
    if data.get('controller_setup') is not None or data.get('analytics_extensions') or data.get('power_tree', {}).get('stages'):
        raise ValueError('Detach controller/analytics/power-tree bindings before renaming nets; review their references explicitly')
    from .pin_geometry import ordered_nodes
    actual = {e.name.upper(): ordered_nodes(e) for e in project.elements}
    if any(actual.get(p['ref'].upper()) != p['nodes'] for p in data['components']):
        raise ValueError('Schematic terminals disagree with Circuit text; reapply the source before renaming')
    from .part_properties import rewrite_nodes
    for part in data['components']:
        nodes = [new if n.lower() == old else n for n in part['nodes']]
        if nodes != part['nodes']:
            source = rewrite_nodes(source, part['ref'], nodes)
            part['nodes'] = nodes
    data['source'] = source
    def expression(text):
        return re.sub(r'(?i)\bv\s*\(([^)]*)\)', lambda m: 'V(' + ','.join(new if n.strip().lower() == old else n.strip() for n in m[1].split(',')) + ')', text)
    from python.spikes.contracts import ProbeDescriptor
    for probe in data['probes']:
        probe['expression'] = expression(probe['expression'])
        probe['descriptor'] = ProbeDescriptor.parse(probe['expression']).to_dict()
    for instrument in [*data['instruments'], *data['dashboard']['widgets']]:
        instrument['expression'] = expression(instrument['expression'])
    data['expressions'] = [expression(e) for e in data['expressions']]
    for junction in data['junctions']:
        if junction['source_node'].lower() == old:
            junction['source_node'] = new
    for wire in data['wires']:
        model = wire.get('parasitics', {})
        if model.get('reference', '').lower() == old:
            model['reference'] = new
    for label in data.get('labels', []):
        if label['net'] == old:
            label.update(net=new, name=new)


def attach(document, kind, name, value, label_id=None):
    """Add/edit one label and any admitted native net rename in one undo step."""
    candidate = deepcopy(document.data)
    labels = candidate.setdefault('labels', [])
    if label_id is not None and not any(v['id'] == label_id for v in labels):
        raise ValueError('Net label no longer exists')
    terminal, wire_id = attachment(candidate, value)
    _, node, scope = _terminal(candidate, terminal)
    if not isinstance(name, str) or not NAME.fullmatch(name) or kind not in KINDS:
        raise ValueError('Choose a label scope and enter one simple SPICE name')
    name = name.lower()
    project = _project(candidate)
    # A scoped label can only describe an existing hierarchy connection. It
    # cannot alter every instance of a shared definition through a flat pin.
    if not scope and kind != 'hierarchical' and name != node:
        _rename(candidate, node, name)
        node = name
        project = _project(candidate)
    if kind == 'global' and name != '0' and name not in project.global_nodes:
        if project.hierarchy or re.search(r'(?im)^\s*\.(subckt|include|inc|lib|control)\b', candidate['source']):
            raise ValueError('Declare .global in Circuit text and verify all instances before placing this global label')
        lines = candidate['source'].splitlines(keepends=True)
        ends = [i for i, line in enumerate(lines) if line.strip().lower() == '.end']
        if len(ends) != 1:
            raise ValueError('Global label creation requires one top-level .end')
        lines.insert(ends[0], f'.global {name}\n')
        candidate['source'] = ''.join(lines)
        project = _project(candidate)
    item = dict(id=label_id or uuid.uuid4().hex, kind=kind, name=name,
                terminal=terminal, sheet_path=scope, net=node)
    if wire_id:
        item['wire_id'] = wire_id
    _check(candidate, item, project)
    if any(v['id'] != label_id and v['terminal'] == terminal and v['kind'] == kind and v['name'] == name for v in labels):
        raise ValueError('This terminal already has that net label')
    candidate['labels'] = [item if v['id'] == label_id else v for v in labels] if label_id else [*labels, item]
    validate(candidate)
    document.commit(lambda data: data.update(candidate))
    return deepcopy(item)


def remove(document, ident):
    """Remove presentation only; native net names and .global remain explicit."""
    if not any(v['id'] == ident for v in document.data.get('labels', [])):
        raise ValueError('Net label no longer exists')
    document.commit(lambda data: data.__setitem__('labels', [v for v in data['labels'] if v['id'] != ident]))


def show(owner, value, label_id=None):
    import wx
    from .themes import apply_window
    if owner.job_running:
        raise ValueError('Stop the simulation before editing net labels')
    if owner.source.GetText() != owner.doc.data['source']:
        raise ValueError('Apply Circuit text changes before editing net labels')
    previous = next((v for v in owner.doc.data.get('labels', []) if v['id'] == label_id), None)
    if previous:
        value = dict(part_id=previous['terminal'][0], pin_index=previous['terminal'][1], wire_id=previous.get('wire_id'))
    initial = defaults(owner.doc.data, value)
    with wx.Dialog(owner, title='Edit net label' if previous else 'Place net label', size=(580, 430), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER) as dialog:
        box = wx.BoxSizer(wx.VERTICAL)
        box.Add(wx.StaticText(dialog, label='Electrical name'), 0, wx.ALL, 10)
        name = wx.TextCtrl(dialog, value=(previous or initial)['name']); box.Add(name, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        box.Add(wx.StaticText(dialog, label='Label scope'), 0, wx.ALL, 10)
        kind = wx.Choice(dialog, choices=['Local - current sheet instance', 'Global - explicit .global net', 'Hierarchical - declared sheet port'])
        kind.SetSelection(KINDS.index((previous or initial)['kind'])); box.Add(kind, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        info = wx.StaticText(dialog, label=''); box.Add(info, 0, wx.EXPAND | wx.ALL, 10)
        def preview(event=None):
            scope = initial['sheet_path'] or '(root)'
            text = f"Sheet instance: {scope}\nAttached native net: {initial['net']}\n"
            if kind.GetSelection() == 2:
                text += 'Existing bound ports: ' + (', '.join(initial['ports']) or '(none)')
            elif kind.GetSelection() == 1:
                text += 'Global names connect across instances only through native .global declarations.'
            else:
                text += 'Same local names in different instances remain distinct unless source ports/globals connect them.'
            text += '\nTop-level renaming merges the complete named net. Hierarchical renaming requires Circuit text.'
            info.SetLabel(text); info.Wrap(max(300, dialog.GetClientSize().width - 30)); dialog.Layout()
        kind.Bind(wx.EVT_CHOICE, preview); dialog.Bind(wx.EVT_SIZE, lambda e: (preview(), e.Skip()))
        error = wx.StaticText(dialog, label=''); box.Add(error, 1, wx.EXPAND | wx.ALL, 10)
        box.Add(dialog.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        def accept(event):
            try:
                attach(owner.doc, KINDS[kind.GetSelection()], name.GetValue().strip(), value, label_id)
            except ValueError as exc:
                error.SetLabel(str(exc)); error.Wrap(max(300, dialog.GetClientSize().width - 30)); dialog.Layout(); return
            dialog.EndModal(wx.ID_OK)
        dialog.Bind(wx.EVT_BUTTON, accept, id=wx.ID_OK); dialog.SetSizer(box); apply_window(dialog, owner.palette); preview()
        if dialog.ShowModal() != wx.ID_OK:
            return
    owner.refresh_document(force_source=True)


def draw(canvas, dc, palette):
    import wx
    from .editor_geometry import terminal, route,transform
    from .pin_geometry import pins
    data = canvas.owner.doc.data
    parts = {p['id']: p for p in data['components']}; wires = {w['id']: w for w in data['wires']}
    junctions = {j['id']: j for j in data['junctions']}
    canvas.label_hits = []
    visible={p['id'] for p in canvas.visible_parts()} if hasattr(canvas,'visible_parts') else set(parts)
    for item in data.get('labels', []):
        if item['terminal'][0] not in visible:continue
        ident, index = item['terminal']; at = terminal(parts[ident], index)
        if item.get('wire_id') in wires:
            points = route(parts, wires[item['wire_id']], junctions)
            a, b = points[(len(points) - 1) // 2:(len(points) - 1) // 2 + 2]
            at = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        anchor = canvas.point(*at)
        text = item['name']
        dc.SetFont(wx.Font(9,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL))
        dc.SetTextForeground(palette['accent']); dc.SetPen(wx.Pen(palette['accent'], 1))
        width, height = dc.GetTextExtent(text)
        body=transform(parts[ident],*pins(parts[ident])[index].body);pin_at=terminal(parts[ident],index)
        dx,dy=pin_at[0]-body[0],pin_at[1]-body[1]
        if item.get('wire_id') in wires:dx,dy=1,0
        if abs(dx)>=abs(dy):point=wx.Point(anchor.x-width-25 if dx<0 else anchor.x+14,anchor.y-height-15)
        else:point=wx.Point(anchor.x+14,anchor.y-height-18 if dy<0 else anchor.y+15)
        left, top, right, bottom = point.x - 5, point.y - 3, point.x + width + 5, point.y + height + 3
        middle = (top + bottom) // 2; tip = max(5, height // 2)
        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        if item['kind'] == 'global':
            outline = [(left, top), (right, top), (right + tip, middle), (right, bottom), (left, bottom)]
            dc.DrawPolygon([wx.Point(x, y) for x, y in outline]); right += tip
        elif item['kind'] == 'hierarchical':
            outline = [(left - tip, middle), (left, top), (right, top), (right + tip, middle), (right, bottom), (left, bottom)]
            dc.DrawPolygon([wx.Point(x, y) for x, y in outline]); left -= tip; right += tip
        connection=wx.Point(right if dx<0 and abs(dx)>=abs(dy) else left,middle)
        dc.DrawLine(anchor,connection);dc.DrawText(text,point)
        canvas.label_hits.append((wx.Rect(left - 2, top - 2, right - left + 4, bottom - top + 4), item))
