"""Bounded, read-only Plotly reports from acquired data. No solver bridge or CDN."""
from html import escape
import json
from pathlib import Path
import secrets
import re
import numpy as np

CONTRACT = 'spikes/offline-report/v1'
MAX_TRACES = 32
MAX_POINTS = 4000


def snapshot(engine, expressions, *, title='', provenance=None, palette=None):
    if engine is None:raise ValueError('Acquire simulation results first')
    expressions=list(dict.fromkeys(expressions))
    if not expressions or len(expressions)>MAX_TRACES:raise ValueError('Select 1..32 report expressions')
    from .plotting import extrema_indices
    traces=[];measurements=[];units=[]
    for expression in expressions:
        answer=engine.evaluate(expression)
        values=np.broadcast_to(answer.values,engine.time.shape)
        if np.iscomplexobj(values):raise ValueError('Use real(), imag(), abs() or angle() for complex report signals')
        indexes=extrema_indices(values,MAX_POINTS);unit=str(answer.unit)
        if unit not in units:units.append(unit)
        axis=units.index(unit)+1
        traces.append(dict(type='scatter',mode='lines',name=escape(expression),
            x=engine.time[indexes].tolist(),y=values[indexes].tolist(),
            xaxis='x' if axis==1 else f'x{axis}',yaxis='y' if axis==1 else f'y{axis}'))
        # These reductions deliberately use the original array, never chart bins.
        measurements.append(dict(expression=expression,unit=unit,count=len(values),
            minimum=float(np.min(values)),maximum=float(np.max(values)),latest=float(values[-1])))
    p=palette or dict(canvas='#ffffff',fg='#172638',grid='#d7e1eb')
    if any(not re.fullmatch(r'#[0-9a-fA-F]{6}',p[key]) for key in ('canvas','fg','grid')):raise ValueError('Report palette requires hexadecimal colors')
    layout=dict(title=dict(text=escape(title)),paper_bgcolor=p['canvas'],plot_bgcolor=p['canvas'],
        font=dict(color=p['fg']),height=max(480,240*len(units)),hovermode='x unified',
        grid=dict(rows=len(units),columns=1,pattern='independent'),
        legend=dict(orientation='h'),margin=dict(t=90,b=70),uirevision='spikes-report-v1')
    for index,unit in enumerate(units,1):
        suffix='' if index==1 else str(index)
        layout['xaxis'+suffix]=dict(title=dict(text='Simulation time [s]'),gridcolor=p['grid'],matches=None if index==1 else 'x')
        layout['yaxis'+suffix]=dict(title=dict(text=escape(unit)),gridcolor=p['grid'])
    return dict(contract=CONTRACT,title=title,traces=traces,layout=layout,measurements=measurements,
        provenance=dict(provenance or {}),capture=dict(kind='acquired_snapshot',samples=len(engine.time),
        display_points_per_trace=MAX_POINTS,measurement_source='original samples',live=False))


def script_json(value):
    # Prevent project strings from ending a script tag or injecting markup.
    return json.dumps(value,ensure_ascii=True,allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')


def render(report):
    if report.get('contract')!=CONTRACT:raise ValueError('Unknown report version')
    if any(not isinstance(value,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',value) for value in
           (report['layout']['paper_bgcolor'],report['layout']['font']['color'])):raise ValueError('Invalid report colors')
    from plotly.offline import get_plotlyjs
    nonce=secrets.token_hex(24)
    rows=''.join('<tr>'+''.join(f'<td>{escape(str(row[key]))}</td>' for key in
        ('expression','unit','count','minimum','maximum','latest'))+'</tr>' for row in report['measurements'])
    # No imports, network fetches, frames, external forms or executable project code.
    csp=f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    provenance=escape(json.dumps(report['provenance'],indent=2,default=str))
    plotly=get_plotlyjs().replace('</script','<\\/script')
    return f'''<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(report['title'])}</title>
<style>body{{font:14px system-ui;margin:20px;background:{report['layout']['paper_bgcolor']};color:{report['layout']['font']['color']}}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;border-bottom:1px solid #888;padding:8px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}#chart{{width:100%}}</style></head>
<body><h1>{escape(report['title'])}</h1>
<p>Acquired snapshot — not live. Display reduced to at most {MAX_POINTS:,} points per trace. Measurements below use original samples. Native instruments control the simulation.</p>
<div id="chart"></div><h2>Original-sample measurements</h2>
<table><thead><tr><th>Expression</th><th>Unit</th><th>Samples</th><th>Minimum</th><th>Maximum</th><th>Latest</th></tr></thead><tbody>{rows}</tbody></table>
<details><summary>Run provenance</summary><pre>{provenance}</pre></details>
<script nonce="{nonce}">{plotly}</script>
<script nonce="{nonce}">const report={script_json(dict(traces=report['traces'],layout=report['layout']))};
Plotly.newPlot('chart',report.traces,report.layout,{{responsive:true,scrollZoom:true,displaylogo:false,modeBarButtonsToRemove:['sendDataToCloud']}}).then(function(){{document.title='SPIKES report ready';}}).catch(function(error){{document.getElementById('chart').textContent='Plot rendering failed: '+error.message;document.title='SPIKES report failed';}});</script></body></html>'''


def write_report(path, report):
    """One self-contained HTML file; no local server and no companion assets."""
    path=Path(path)
    html=render(report)
    temporary=path.with_name(path.name+'.'+secrets.token_hex(8)+'.tmp')
    try:
        temporary.write_text(html,encoding='utf-8');temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)
    return path
