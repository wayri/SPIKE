# SPDX-License-Identifier: Apache-2.0
"""Pure, fail-closed capture of source-backed reusable circuit components."""
from __future__ import annotations

import hashlib
import re

from .hierarchy_views import instances
from .part_properties import parse
from .schematic_clipboard import _replace_nodes


_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.$+-]*\Z", re.ASCII)
_LOCAL = re.compile(r"[A-Za-z0-9_.$+-]+\Z", re.ASCII)
_NONPORTABLE = {'.include', '.lib', '.control', '.endc', '.shell', '.host', '.system'}
_UNSAFE_CONTEXT = {'.ic'}


def _records(source):
    """Return source records with continuations kept byte-for-byte."""
    result = []
    for line in source.splitlines(keepends=True):
        if line.lstrip().startswith('+') and result:
            result[-1] += line
        else:
            result.append(line)
    return result


def _logical(record):
    return re.sub(r'\r?\n[ \t]*\+[ \t]*', ' ', record).strip()


def _tokens(record):
    text = _logical(record)
    if not text or text.startswith(('*', ';')):
        return []
    return text.split()


def _reject_nonportable(source):
    for record in _records(source):
        tokens = _tokens(record)
        if not tokens:
            continue
        keyword = tokens[0].casefold()
        if keyword in _NONPORTABLE or keyword in {'shell', 'host'}:
            raise ValueError(f'Cannot capture nonportable source command {tokens[0]}')
        if keyword in _UNSAFE_CONTEXT:
            raise ValueError(f'Cannot capture analysis-context directive {tokens[0]} without changing behavior')


def _source_sections(source):
    """Split top-level records and non-nested definitions without normalizing."""
    top, definitions, current = [], {}, None
    for record in _records(source):
        tokens = _tokens(record)
        keyword = tokens[0].casefold() if tokens else ''
        if keyword == '.subckt':
            if current is not None or len(tokens) < 3:
                raise ValueError('Cannot capture malformed or nested subcircuit source')
            current = {'name': tokens[1], 'records': [record]}
        elif keyword == '.ends':
            if current is None:
                raise ValueError('Cannot capture unmatched .ends source')
            current['records'].append(record)
            key = current['name'].casefold()
            if key in definitions:
                raise ValueError(f'Duplicate subcircuit definition {current["name"]}')
            definitions[key] = current
            current = None
        elif current is None:
            top.append(record)
        else:
            current['records'].append(record)
    if current is not None:
        raise ValueError(f'Unterminated subcircuit definition {current["name"]}')
    return top, definitions


def _context_records(source, scope_path):
    top, definitions = _source_sections(source)
    if not scope_path:
        return top, None, definitions
    item = next((row for row in instances(source) if row.path.casefold() == scope_path.casefold()), None)
    if item is None:
        raise ValueError('Subsheet instance no longer exists')
    definition = definitions.get(item.definition.casefold())
    if definition is None:
        raise ValueError(f'Missing source definition {item.definition}')
    return definition['records'][1:-1], item, definitions


def _record_map(records):
    result = {}
    for record in records:
        tokens = _tokens(record)
        if not tokens or tokens[0].startswith('.'):
            continue
        key = tokens[0].casefold()
        if key in result:
            raise ValueError(f'Source reference {tokens[0]} is not unique in its scope')
        result[key] = record
    return result


def _scope_of(reference):
    return reference.rpartition(':')[0]


def _leaf(reference):
    return reference.rpartition(':')[2]


def _actual_node(scope, hierarchy, local, global_nodes=()):
    local = local.casefold()
    if local == '0':
        return '0'
    if local in global_nodes:
        return local
    if hierarchy is not None:
        bindings = dict(zip(hierarchy.pins, hierarchy.nodes, strict=True))
        if local in bindings:
            return bindings[local]
        return f'{scope.casefold()}:{local}'
    return local


def _local_node(scope, hierarchy, actual):
    actual = actual.casefold()
    if actual == '0':
        return '0'
    if hierarchy is not None:
        matches = [pin for pin, node in zip(hierarchy.pins, hierarchy.nodes, strict=True)
                   if node.casefold() == actual]
        if matches:
            return matches[0]
        prefix = scope.casefold() + ':'
        if actual.startswith(prefix) and ':' not in actual[len(prefix):]:
            return actual[len(prefix):]
        # A declared global keeps its unscoped name in flattened identity.
        if ':' not in actual:
            return actual
        raise ValueError('Selection contains nested hierarchy; capture that subsheet instead')
    if ':' in actual:
        raise ValueError('Selection contains hierarchy; capture within one direct sheet scope')
    return actual


def _port_names(actual_nodes, local_by_actual):
    used = set()
    result = {}
    for actual in actual_nodes:
        stem = 'GND' if actual == '0' else re.sub(r'[^A-Za-z0-9_.$+-]', '_', local_by_actual[actual]).upper()
        if not stem:
            stem = 'PORT'
        if not stem[0].isalpha() and stem[0] != '_':
            stem = 'PORT_' + stem
        candidate, serial = stem, 2
        while candidate.casefold() in used:
            candidate = f'{stem}_{serial}'
            serial += 1
        used.add(candidate.casefold())
        result[actual] = candidate
    return result


def _signal_references(record):
    nodes, branches = [], []
    for match in re.finditer(r'(?i)\bV\s*\(([^)]*)\)', _logical(record)):
        nodes.extend(token.strip() for token in match.group(1).split(',') if token.strip())
    branches.extend(match.group(1) for match in re.finditer(r'(?i)\bI\s*\(\s*([^\s)]+)\s*\)', _logical(record)))
    return nodes, branches


def _rewrite_signal_nodes(record, replacements):
    def replace(match):
        values = [item.strip() for item in match.group(1).split(',')]
        values = [replacements.get(item.casefold(), item) for item in values]
        return 'V(' + ','.join(values) + ')'
    return re.sub(r'(?i)\bV\s*\(([^)]*)\)', replace, record)


def _portable_dependencies(top_records):
    return [record for record in top_records
            if (_tokens(record) and _tokens(record)[0].casefold() in {'.param', '.model', '.func'})]


def _has_parameter_assignments(record):
    text = _logical(record)
    return re.search(r'(?i)\bparams\s*:|(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*\s*=', text) is not None


def _joined(records):
    result = ''
    for record in records:
        if result and not result.endswith(('\n', '\r')):
            result += '\n'
        result += record
    if result and not result.endswith(('\n', '\r')):
        result += '\n'
    return result


def _origin(document, kind, **details):
    data = document.data
    return {'kind': kind, 'document_id': str(data.get('id', '')),
            'revision': data.get('revision'),
            'source_sha256': hashlib.sha256(data['source'].encode('utf-8')).hexdigest(),
            **details}


def _validate_name(name):
    if not isinstance(name, str) or _NAME.fullmatch(name) is None:
        raise ValueError('Component name must be a portable SPICE identifier')
    return name


def _validate_declaration(source, name, pins):
    bindings = [f'capture_pin_{index}' for index in range(len(pins))]
    if bindings:
        bindings[0] = '0'
    deck = ('Capture validation\n' + source.rstrip() + '\n' +
            f'X_CAPTURE_TEST {" ".join(bindings)} {name}\n.op\n.end\n')
    parse(deck)


def capture_selection(document, selected_ids, name):
    """Return a reusable subcircuit for one direct-scope component selection."""
    name = _validate_name(name)
    source = document.data['source']
    _reject_nonportable(source)
    project = parse(source)
    selected = set(selected_ids)
    parts = [part for part in document.data['components'] if part.get('id') in selected]
    if not selected or len(parts) != len(selected):
        raise ValueError('Select existing components to capture')
    scopes = {_scope_of(part['ref']) for part in parts}
    if len(scopes) != 1:
        raise ValueError('Capture selection must belong to one direct sheet scope')
    scope = scopes.pop()
    context, hierarchy, definitions = _context_records(source, scope)
    if hierarchy is not None:
        if ':' in scope:
            raise ValueError('Nested hierarchy selection requires ancestor parameter context; capture the parent subsheet')
        definition = definitions[hierarchy.definition.casefold()]
        if _has_parameter_assignments(definition['records'][0]) or any(
                _tokens(record) and _tokens(record)[0].casefold() == '.param'
                for record in context):
            raise ValueError('Parameterized hierarchy selection cannot be captured without specializing its sheet context')
        parent_records, _, _ = _context_records(source, hierarchy.parent_path)
        instance_record = _record_map(parent_records).get(_leaf(hierarchy.path).casefold())
        if instance_record is None:
            raise ValueError(f'Missing source instance {hierarchy.path}')
        if _has_parameter_assignments(instance_record):
            raise ValueError('Parameterized hierarchy selection cannot be captured without specializing its instance overrides')
    records = _record_map(context)
    selected_refs = {part['ref'].casefold() for part in parts}
    source_records = []
    for part in parts:
        leaf = _leaf(part['ref'])
        record = records.get(leaf.casefold())
        if record is None:
            raise ValueError(f'{part["ref"]} is not a direct source instance in this sheet')
        source_records.append(record)

    parsed_by_name = {element.name.casefold(): element for element in project.elements}
    for part, record in zip(parts, source_records, strict=True):
        element = parsed_by_name.get(part['ref'].casefold())
        if element is None:
            raise ValueError(f'Missing parsed element {part["ref"]}')
        if element.control_source_id and element.control_source_id.casefold() not in selected_refs:
            raise ValueError(f'{part["ref"]} references omitted control branch {element.control_source_id}')
        _, branch_refs = _signal_references(record)
        for branch in branch_refs:
            qualified = f'{scope}:{branch}' if scope else branch
            if qualified.casefold() not in selected_refs:
                raise ValueError(f'{part["ref"]} references omitted branch {qualified}')

    all_nodes = {str(node).casefold() for part in document.data['components'] for node in part['nodes']}
    outside_nodes = {str(node).casefold() for part in document.data['components']
                     if part.get('id') not in selected for node in part['nodes']}
    selected_nodes = {str(node).casefold() for part in parts for node in part['nodes']}
    boundary = []
    for part in parts:
        for raw in part['nodes']:
            actual = str(raw).casefold()
            if (actual == '0' or actual in project.global_nodes or actual in outside_nodes) and actual not in boundary:
                boundary.append(actual)
    referenced_local = []
    for record in source_records:
        nodes, _ = _signal_references(record)
        referenced_local.extend(nodes)
    for local in referenced_local:
        if _LOCAL.fullmatch(local) is None:
            raise ValueError(f'Unsupported voltage-reference node {local}')
        actual = _actual_node(scope, hierarchy, local, project.global_nodes)
        if actual not in all_nodes and actual != '0':
            raise ValueError(f'Selection references omitted net {actual}')
        if actual not in selected_nodes and actual not in boundary:
            boundary.append(actual)

    local_by_actual = {node: _local_node(scope, hierarchy, node)
                       for node in selected_nodes | set(boundary)}
    ports = _port_names(boundary, local_by_actual)
    if not ports:
        raise ValueError('Selection has no crossing or ground net to expose as a reusable port')
    internal_order = []
    for part in parts:
        for raw in part['nodes']:
            actual = str(raw).casefold()
            if actual not in boundary and actual not in internal_order:
                internal_order.append(actual)
    used_names = {port.casefold() for port in ports.values()}
    body_names = {}
    for actual in internal_order:
        stem = local_by_actual[actual]
        candidate, serial = stem, 2
        if candidate.casefold() in used_names:
            candidate = '_CAP_' + stem
        while candidate.casefold() in used_names:
            candidate = f'_CAP_{stem}_{serial}'
            serial += 1
        used_names.add(candidate.casefold())
        body_names[actual] = candidate
    local_replacements = {local_by_actual[node].casefold(): port for node, port in ports.items()}
    local_replacements.update({local_by_actual[node].casefold(): alias
                               for node, alias in body_names.items()
                               if local_by_actual[node].casefold() != alias.casefold()})
    rewritten_by_leaf = {}
    for part, record in zip(parts, source_records, strict=True):
        rewritten_nodes = []
        for node in part['nodes']:
            key = str(node).casefold()
            rewritten_nodes.append(ports[key] if key in ports else body_names[key])
        rewritten = _replace_nodes(record, rewritten_nodes, part['kind'])
        rewritten_by_leaf[_leaf(part['ref']).casefold()] = _rewrite_signal_nodes(rewritten, local_replacements)

    top, _ = _source_sections(source)
    dependencies = [] if hierarchy is None else _portable_dependencies(top)
    ordered_body = []
    for record in context:
        tokens = _tokens(record)
        if not tokens:
            continue
        keyword = tokens[0].casefold()
        if keyword in {'.param', '.model', '.func'}:
            ordered_body.append(record)
        elif keyword in rewritten_by_leaf:
            ordered_body.append(rewritten_by_leaf[keyword])
    header = f'.subckt {name} {" ".join(ports[node] for node in boundary)}\n'
    declaration = _joined(dependencies) + header + _joined(ordered_body)
    declaration += f'.ends {name}\n'
    _validate_declaration(declaration, name, [ports[node] for node in boundary])
    return {'source': declaration, 'pins': [ports[node] for node in boundary],
            'origin': _origin(document, 'selection', selected_ids=[part['id'] for part in parts],
                              scope_path=scope or None)}


def _definition_dependencies(definition, definitions):
    needed, visiting = set(), set()
    def visit(key):
        if key in needed:
            return
        if key in visiting:
            raise ValueError('Recursive subcircuit dependency cannot be captured')
        visiting.add(key)
        item = definitions[key]
        for record in item['records'][1:-1]:
            tokens = _tokens(record)
            if tokens and not tokens[0].startswith('.') and tokens[0][0].upper() == 'X':
                param_at = next((i for i, token in enumerate(tokens[1:], 1)
                                 if '=' in token or token.casefold() == 'params:'), len(tokens))
                if param_at < 3:
                    raise ValueError(f'Malformed subcircuit instance {tokens[0]}')
                child = tokens[param_at - 1].casefold()
                if child not in definitions:
                    raise ValueError(f'{tokens[0]} references omitted definition {child}')
                visit(child)
        visiting.remove(key)
        needed.add(key)
    visit(definition.casefold())
    needed.remove(definition.casefold())
    return needed


def _renamed_definition(item, name):
    records = list(item['records'])
    records[0] = re.sub(r'(?i)(^[ \t]*\.subckt[ \t]+)\S+',
                        lambda match: match.group(1) + name, records[0], count=1)
    records[-1] = re.sub(r'(?i)(^[ \t]*\.ends)(?:[ \t]+\S+)?',
                         lambda match: match.group(1) + ' ' + name, records[-1], count=1)
    return ''.join(records)


def _assignments(text):
    starts = list(re.finditer(r'(?i)(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*=', text))
    result = []
    for index, match in enumerate(starts):
        value = text[match.end():starts[index + 1].start() if index + 1 < len(starts) else len(text)].strip(' \t,')
        if not value:
            raise ValueError(f'Parameter {match.group(1)} has no expression')
        result.append((match.group(1), value))
    return result


def _specialized_definition(item, instance_record, name):
    """Apply one top-level instance's explicit overrides to reusable defaults."""
    logical_instance = _logical(instance_record)
    override_start = re.search(r'(?i)\bparams\s*:|(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*\s*=', logical_instance)
    if override_start is None:
        return _renamed_definition(item, name)
    overrides = _assignments(re.sub(r'(?i)\bparams\s*:', '', logical_instance[override_start.start():], count=1))
    header = _logical(item['records'][0])
    matched = re.match(r'(?is)^\.subckt\s+\S+\s+(.*)$', header)
    if matched is None:
        raise ValueError(f'Malformed subcircuit definition {item["name"]}')
    remainder = matched.group(1)
    default_start = re.search(r'(?i)\bparams\s*:|(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*\s*=', remainder)
    pins_text = remainder[:default_start.start()].strip() if default_start else remainder.strip()
    defaults = (_assignments(re.sub(r'(?i)\bparams\s*:', '', remainder[default_start.start():], count=1))
                if default_start else [])
    values = dict((key.casefold(), value) for key, value in defaults)
    order = [key.casefold() for key, _ in defaults]
    for key, value in overrides:
        folded = key.casefold()
        if folded not in values:
            raise ValueError(f'Instance override {key} is not declared by {item["name"]}')
        values[folded] = value
    records = list(item['records'])
    suffix = (' params: ' + ' '.join(f'{key}={values[key]}' for key in order)) if order else ''
    records[0] = f'.subckt {name} {pins_text}{suffix}\n'
    records[-1] = re.sub(r'(?i)(^[ \t]*\.ends)(?:[ \t]+\S+)?',
                         lambda match: match.group(1) + ' ' + name, records[-1], count=1)
    return _joined(records)


def capture_subsheet(document, scope_path, name):
    """Capture the exact definition selected by an elaborated hierarchy path."""
    name = _validate_name(name)
    source = document.data['source']
    _reject_nonportable(source)
    project = parse(source)
    hierarchy = next((row for row in project.hierarchy if row.path.casefold() == str(scope_path).casefold()), None)
    if hierarchy is None:
        raise ValueError('Subsheet instance no longer exists')
    if hierarchy.parent_path:
        raise ValueError('Nested subsheet capture requires ancestor-local parameter, function, and model context; capture its parent subsheet')
    top, definitions = _source_sections(source)
    target = definitions.get(hierarchy.definition.casefold())
    if target is None:
        raise ValueError(f'Missing source definition {hierarchy.definition}')
    descendants = tuple(row.path for row in project.hierarchy
                        if row.path == hierarchy.path or row.path.startswith(hierarchy.path + ':'))
    descendant_prefixes = tuple(path.casefold() + ':' for path in descendants)
    for element in project.elements:
        if element.name.casefold().startswith(descendant_prefixes):
            nodes = [element.positive_node, element.negative_node,
                     element.control_positive_node, element.control_negative_node,
                     *element.semiconductor_nodes]
            globals_used = {node for node in nodes if node in project.global_nodes}
            if globals_used:
                raise ValueError('Subsheet uses global node(s) that cannot become reusable pins: ' +
                                 ', '.join(sorted(globals_used)))
    dependency_keys = _definition_dependencies(hierarchy.definition, definitions)
    if name.casefold() in dependency_keys:
        raise ValueError(f'Captured name {name} collides with retained dependency {definitions[name.casefold()]["name"]}')
    dependencies = _portable_dependencies(top)
    # Keep dependency declaration order as authored; parser resolution itself is order independent.
    dependencies.extend(_joined(item['records']) for key, item in definitions.items()
                        if key in dependency_keys)
    parent_records, _, _ = _context_records(source, hierarchy.parent_path)
    instance_record = _record_map(parent_records).get(_leaf(hierarchy.path).casefold())
    if instance_record is None:
        raise ValueError(f'Missing source instance {hierarchy.path}')
    has_override = re.search(r'(?i)\bparams\s*:|(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*\s*=',
                             _logical(instance_record)) is not None
    if has_override and hierarchy.parent_path:
        raise ValueError('Nested parameter overrides require their parent parameter context; capture the parent subsheet')
    target_source = _specialized_definition(target, instance_record, name)
    declaration = _joined(dependencies) + target_source
    _validate_declaration(declaration, name, hierarchy.pins)
    return {'source': declaration, 'pins': list(hierarchy.pins),
            'origin': _origin(document, 'subsheet', scope_path=hierarchy.path,
                              definition=hierarchy.definition)}
