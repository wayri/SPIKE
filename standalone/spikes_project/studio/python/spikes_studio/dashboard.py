"""Versioned dashboard layout and real recorded-signal readouts.

This module deliberately contains no wx imports. Layout creation, signal
admission, plotting summaries and run-provenance wording stay testable without
starting the native UI. Every displayed value is derived from an admitted
recording; an empty dashboard never invents demo data.
"""

from copy import deepcopy
import math
import uuid

import numpy as np


KINDS = ('Meter', 'Scope', 'Indicator', 'Source control', 'Diagram block', 'Note')

INSTRUMENT_ACTIONS = (
    ('Meter', 'Meter', 'Add a numeric meter with a range bar'),
    ('Scope', 'Scope', 'Add a time-domain scope from recorded samples'),
    ('Indicator', 'Limit', 'Add an in-range / outside-limits indicator'),
    ('Source control', 'Source', 'Add a bounded continuous-simulation source control'),
    ('Diagram block', 'Block', 'Add a diagram block; connectors are visual, not electrical nets'),
    ('Note', 'Note', 'Add an explanatory diagram note'),
)


def empty_dashboard():
    return {'version': 1, 'widgets': []}


def widget(kind, expression=''):
    if kind not in KINDS:
        raise ValueError('Unknown instrument')
    return dict(
        id=uuid.uuid4().hex,
        kind=kind,
        title=kind,
        expression=expression,
        x=20,
        y=20,
        width=480 if kind == 'Scope' else 280,
        height=280 if kind == 'Scope' else 160,
        minimum=0.,
        maximum=5.,
        source='',
    )


def validate_dashboard(data):
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('Unsupported dashboard version')
    rows = data.get('widgets')
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError('Dashboard supports up to 200 instruments')
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid dashboard instrument')
        ident = row.get('id')
        if not isinstance(ident, str) or not ident or ident in seen:
            raise ValueError('Duplicate or missing instrument ID')
        seen.add(ident)
        if row.get('kind') not in KINDS:
            raise ValueError('Unsupported dashboard instrument')
        for key in ('title', 'expression', 'source'):
            if not isinstance(row.get(key), str) or len(row[key]) > 2048:
                raise ValueError('Invalid instrument text')
        for key in ('x', 'y', 'width', 'height', 'minimum', 'maximum'):
            value = row.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Instrument dimensions/limits must be finite')
        if not 0 <= row['x'] <= 20000 or not 0 <= row['y'] <= 20000:
            raise ValueError('Instrument position is outside canvas bounds')
        if not 180 <= row['width'] <= 2000 or not 120 <= row['height'] <= 2000:
            raise ValueError('Instrument size must be 180-2000 x 120-2000')
        if row['minimum'] >= row['maximum']:
            raise ValueError('Minimum must be less than maximum')
        binding=row.get('dut_binding')
        if binding is not None:
            if not isinstance(binding,dict):raise ValueError('Invalid DUT binding')
            for key in ('device','connector','pin','gpio','direction'):
                if not isinstance(binding.get(key),str) or len(binding[key])>128:raise ValueError('Invalid DUT pin mapping')
            if binding['direction'] not in ('Read','Write'):raise ValueError('DUT direction must be Read or Write')
            if type(binding.get('safe_value')) is not int or binding['safe_value'] not in (0,1):raise ValueError('DUT safe level must be 0 or 1')
    connections=data.get('connections',[])
    if not isinstance(connections,list) or len(connections)>400:raise ValueError('Dashboard supports up to 400 diagram connectors')
    links=set()
    for link in connections:
        if not isinstance(link,dict) or link.get('from') not in seen or link.get('to') not in seen or link['from']==link['to']:raise ValueError('Invalid diagram endpoints')
        pair=(link['from'],link['to'])
        if pair in links:raise ValueError('Duplicate diagram connector')
        links.add(pair)
    return data


def connect_widgets(data,source,target):
    result=deepcopy(data);result.setdefault('connections',[]).append({'from':source,'to':target});return validate_dashboard(result)


def remove_widget(data,ident):
    result=deepcopy(data);result['widgets']=[r for r in result['widgets'] if r['id']!=ident]
    result['connections']=[c for c in result.get('connections',[]) if ident not in (c['from'],c['to'])]
    return validate_dashboard(result)


def update_widget(data, ident, **changes):
    result = deepcopy(data)
    row = next((item for item in result['widgets'] if item['id'] == ident), None)
    if row is None:
        raise ValueError('Select an instrument first')
    row.update(changes)
    return validate_dashboard(result)


def snap(value, minimum=0):
    return max(minimum, round(value / 20) * 20)


def scope_bins(time, values, pixels):
    """Return time-positioned extrema so narrow adaptive-step peaks survive."""
    time = np.asarray(time)
    values = np.asarray(values)
    if len(time) != len(values) or len(time) < 2 or time[-1] <= time[0]:
        return []
    if np.any(np.diff(time) < 0):
        raise ValueError('Scope timestamps must be ordered')
    pixels = max(1, min(2000, int(pixels)))
    indices = np.searchsorted(time, np.linspace(time[0], time[-1], pixels + 1))
    indices[-1] = len(time)
    return [
        (index, float(np.min(values[start:end])), float(np.max(values[start:end])))
        for index, (start, end) in enumerate(zip(indices[:-1], indices[1:]))
        if end > start
    ]


def read_signal(engine, expression):
    if engine is None:
        raise ValueError('Run a simulation to acquire data')
    if not expression.strip():
        raise ValueError('Bind a signal or expression')
    quantity = engine.evaluate(expression)
    values = np.broadcast_to(quantity.values, engine.time.shape)
    if not len(values):
        raise ValueError('No acquired samples')
    if np.iscomplexobj(values):
        raise ValueError('Use abs(), real() or imag() for complex data')
    if not np.all(np.isfinite(values)):
        raise ValueError('Signal contains non-finite samples')
    return engine.time, values, str(quantity.unit)


def signal_limits(values):
    """Choose display limits from admitted finite values, never sample fixtures."""
    values = np.asarray(values, dtype=float)
    if not len(values) or not np.all(np.isfinite(values)):
        raise ValueError('Starter instruments require finite acquired samples')
    low, high = float(np.min(values)), float(np.max(values))
    if low == high:
        pad = max(abs(low) * .1, 1e-12)
    else:
        pad = (high - low) * .05
    return low - pad, high + pad


def starter_dashboard(engine, canvas_width=1000):
    """Build a compact starter scope/meter using only available run signals."""
    names = list(engine.signals) if engine is not None else []
    # Do not make a blank ground trace the first instrument just because the
    # backend enumerates node 0 first. Prefer a recorded voltage response, then
    # a current channel, while retaining exact samples and names.
    names = sorted(names,key=lambda name:(0 if name.casefold()=='v(out)' else
        1 if name.casefold().startswith('i(') else 2 if name.casefold().startswith('v(')
        and name.casefold() not in ('v(0)','v(gnd)') else 3))
    if not names:
        raise ValueError('Acquire a run with recorded signals before creating starters')
    admitted = []
    for name in names:
        try:
            _, values, _ = read_signal(engine, name)
        except ValueError:
            continue
        admitted.append((name, values))
        if len(admitted) == 2:
            break
    if not admitted:
        raise ValueError('The acquired run has no finite real-valued signals for starter instruments')
    width = max(220, min(2000, int(canvas_width)))
    scope_name, values = admitted[0]
    scope = widget('Scope', scope_name)
    low, high = signal_limits(values)
    scope.update(title=f'Scope - {scope_name}', minimum=low, maximum=high)
    scope['width'] = max(280, min(620, width - 40))

    meter_name, values = admitted[1] if len(admitted) > 1 else admitted[0]
    meter = widget('Meter', meter_name)
    low, high = signal_limits(values)
    meter.update(title=f'Meter - {meter_name}', minimum=low, maximum=high)
    if width >= scope['width'] + meter['width'] + 80:
        meter.update(x=scope['x'] + scope['width'] + 20, y=20)
    else:
        meter.update(x=20, y=scope['y'] + scope['height'] + 20)
    return validate_dashboard({'version': 1, 'widgets': [scope, meter]})


def scope_view(time, values, pixels):
    """Summarize the exact admitted scope window for native painting."""
    time = np.asarray(time, dtype=float)
    values = np.asarray(values, dtype=float)
    bins = scope_bins(time, values, pixels)
    if not bins:
        raise ValueError('Scope needs at least two ordered samples')
    low, high = float(np.min(values)), float(np.max(values))
    display_low, display_high = signal_limits(values)
    return {
        'bins': bins,
        'minimum': low,
        'maximum': high,
        'display_minimum': display_low,
        'display_maximum': display_high,
        'latest': float(values[-1]),
        'time_start': float(time[0]),
        'time_end': float(time[-1]),
    }


def meter_fraction(value, minimum, maximum):
    value, minimum, maximum = float(value), float(minimum), float(maximum)
    if not all(math.isfinite(item) for item in (value, minimum, maximum)) or minimum >= maximum:
        raise ValueError('Meter value and limits must be finite and ordered')
    return min(1., max(0., (value - minimum) / (maximum - minimum)))


def reconcile_control(pending, events):
    """Return the exact accepted native-step event for a queued source value."""
    if not pending:
        return None
    events = list(events)
    cursor = pending.get('event_cursor')
    start = pending.get('event_index', 0)
    if cursor is not None:
        matches = [index for index, event in enumerate(events) if _event_identity(event) == tuple(cursor)]
        # If a bounded event deque advanced so far that its cursor disappeared,
        # do not guess that a same-valued older event is our acknowledgement.
        if not matches:
            return None
        start = matches[-1] + 1
    if not isinstance(start, int) or start < 0:
        return None
    for event in events[start:]:
        if event.get('origin') == 'compiled_controller':
            continue
        if event.get('source') == pending.get('source') and math.isclose(
            float(event.get('value')), float(pending.get('value')), rel_tol=0., abs_tol=0.
        ):
            return event
    return None


def _event_identity(event):
    return (event.get('time_s'), event.get('source'), event.get('value'), event.get('origin'))


def run_provenance(result=None, active_snapshot=None, session_state='idle'):
    """Describe result origin without implying hardware connectivity or validation."""
    payload = active_snapshot or result
    if not payload or not payload.get('data'):
        return 'Data source: disconnected - no acquired run | Hardware I/O: disconnected (simulation only)'
    provenance = payload.get('provenance', {})
    parts = ['Data source: continuous simulation' if active_snapshot else 'Data source: recorded run']
    solver = provenance.get('solver')
    if solver:
        parts.append(f'Solver: {solver}')
    integration = provenance.get('integration')
    if integration:
        parts.append(f'Integration: {integration}')
    source = provenance.get('source_sha256')
    if source:
        parts.append(f'Source: {str(source)[:12]}')
    if active_snapshot:
        parts.append(f'Session: {session_state}')
    parts.append('Hardware I/O: disconnected (simulation only)')
    return ' | '.join(parts)
