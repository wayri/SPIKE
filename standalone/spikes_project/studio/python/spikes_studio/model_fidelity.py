"""Fail-closed model policy resolution. Policies never rewrite device physics."""
from copy import deepcopy
import hashlib

TIERS = ('source', 'ideal', 'simplified', 'behavioral', 'physics', 'validated')


def default_policy():
    return {'schematic': {'tier': 'source', 'enforce': False}, 'subsheets': {}, 'components': {}}


def validate(policy):
    if not isinstance(policy, dict) or set(policy) != {'schematic', 'subsheets', 'components'}:
        raise ValueError('Invalid model policy sections')
    entries = [policy['schematic']]
    for section in ('subsheets', 'components'):
        if not isinstance(policy[section], dict) or len(policy[section]) > 10000:
            raise ValueError('Invalid model policy scopes')
        for scope, entry in policy[section].items():
            if not isinstance(scope, str) or not scope or scope != scope.upper():
                raise ValueError('Model scopes must be uppercase instance paths')
            entries.append(entry)
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) - {'tier', 'enforce', 'required_parasitics', 'parasitic_values'}:
            raise ValueError('Invalid model selection')
        if entry.get('tier') not in TIERS or type(entry.get('enforce')) is not bool:
            raise ValueError('Invalid model tier/enforcement')
        parasitics = entry.get('required_parasitics', [])
        from .passive_models import validate as validate_parasitics
        validate_parasitics(entry.get('parasitic_values', {}))
        if not isinstance(parasitics, list) or any(not isinstance(p, str) or not p for p in parasitics):
            raise ValueError('Invalid required parasitics')


def inherited(policy, ref):
    ref = ref.upper(); active = deepcopy(policy['schematic']); origin = 'schematic'
    locked = origin if active['enforce'] else None
    chunks = ref.split(':')
    candidates = [('subsheets', ':'.join(chunks[:i])) for i in range(1, len(chunks))]
    candidates.append(('components', ref))
    ignored = []
    for section, scope in candidates:
        if scope not in policy[section]: continue
        if locked:
            ignored.append(scope); continue
        active = deepcopy(policy[section][scope]); origin = scope
        if active['enforce']: locked = scope
    return active, origin, locked, ignored


def descriptor(part):
    kind = part['kind']
    tier = 'ideal' if kind in ('resistor', 'capacitor', 'inductor', 'voltage_source', 'current_source') else 'simplified'
    supported = kind in ('resistor', 'capacitor', 'inductor', 'voltage_source', 'current_source', 'diode', 'voltage_controlled_switch')
    return {'tier': tier if supported else 'source', 'available_tiers': ['source', tier] if supported else ['source'],
            'pins': deepcopy(part['nodes']), 'kind': kind,
            'qualification': 'Not a validated detailed manufacturer model',
            'validity_ranges': 'Not qualified; consult source model assumptions',
            'temperature_dependence': 'Source/backend-defined; no automatic electrothermal coupling',
            'supported_analyses': (['op', 'dc', 'tran', 'ac'] if tier == 'ideal' else ['op', 'dc', 'tran']) if supported else [],
            'parasitics': [], 'preview': {'resistor': 'p -- R -- n', 'capacitor': 'p -- C -- n',
                'inductor': 'p -- L -- n', 'diode': 'p -- static Shockley D -- n'}.get(kind, 'Source-defined terminal model')}


def resolve(document, analysis=None):
    policy = document.get('model_policy', default_policy()); validate(policy)
    if analysis is None:
        from python.spikes.netlist import parse_netlist
        project = parse_netlist(document['source'], native_extensions=True, transient_capture='rolling')
        analysis = {'transient': 'tran', 'dc_sweep': 'dc', 'operating_point': 'op'}.get(project.analysis.mode, project.analysis.mode)
    rows, errors, warnings = [], [], []
    refs = {p['ref'].upper() for p in document['components']}
    scopes = {':'.join(r.split(':')[:i]) for r in refs for i in range(1, len(r.split(':')))}
    for section, known in (('components', refs), ('subsheets', scopes)):
        for missing in set(policy[section]) - known: errors.append(f'Missing {section} target: {missing}')
    for part in document['components']:
        selection, origin, locked, ignored = inherited(policy, part['ref']); model = descriptor(part)
        if selection['tier'] not in model['available_tiers']:
            errors.append(f"{part['ref']}: {selection['tier']} unavailable; no substitution allowed")
        if analysis not in model['supported_analyses'] and selection['tier'] != 'source':
            errors.append(f"{part['ref']}: selected model not qualified for {analysis}")
        values=selection.get('parasitic_values',{})
        if values and (part['kind']!='capacitor' or ':' in part['ref']):
            errors.append(f"{part['ref']}: parasitic binding requires a top-level capacitor")
        if values and selection['tier']=='ideal':errors.append(f"{part['ref']}: ideal tier excludes parasitics; choose source")
        for parasitic in selection.get('required_parasitics', []):
            if parasitic not in values:errors.append(f"{part['ref']}: required parasitic {parasitic} is not bound to this model")
        model['parasitics']=deepcopy(values)
        warnings.append(f"{part['ref']}: unspecified implicit parasitics excluded; explicit circuit elements remain active")
        rows.append(dict(ref=part['ref'], selection=selection, origin=origin, locked_by=locked,
                         ignored_overrides=ignored, model=model, value=part['value']))
    return dict(contract='spikes/resolved-models/v1', analysis=analysis, components=rows,
                source_sha256=hashlib.sha256(document['source'].encode()).hexdigest(),
                source=document['source'], errors=errors, warnings=warnings)


def preflight(document, analysis=None):
    report = resolve(document, analysis)
    if report['errors']: raise ValueError('Model preflight failed:\n' + '\n'.join(report['errors']))
    from .passive_models import expand
    source=document['source']
    for part,row in zip(document['components'],report['components']):
        source=expand(source,part,row['selection'].get('parasitic_values',{}))
    from python.spikes.netlist import parse_netlist
    parse_netlist(source,native_extensions=True,transient_capture='rolling')
    document['source']=source
    report['effective_source']=source
    report['effective_source_sha256']=hashlib.sha256(source.encode()).hexdigest()
    document['resolved_models'] = report
    return report
