#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render saved CFD comparison evidence; never runs or upgrades solver status."""
import argparse
import html
import json
from pathlib import Path


def render(source):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    source = Path(source).resolve()
    report = json.loads(source.read_text(encoding='utf-8'))
    if report.get('contract') != 'spike/su2-cavity-comparison/v1':
        raise ValueError('Unsupported comparison contract')
    coordinates = report['coordinates']
    runs = report['runs']
    valid = [r for r in runs if 'profiles' in r]
    if not valid:
        raise ValueError('No converged comparison profiles available')
    figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    colors = ['#64748b', '#2563eb', '#b45309', '#15803d']
    for index, run in enumerate(valid):
        for ax, component in zip(axes, ('u', 'v')):
            for engine, style in (('native', '-'), ('su2', '--')):
                ax.plot(coordinates, run['profiles'][engine][component + '_over_lid'],
                        linestyle=style, color=colors[index % len(colors)], linewidth=1.35,
                        label=f"{'SPIKE' if engine == 'native' else 'SU2'} {run['cells']} x {run['cells']}")
    axes[0].set(xlabel='Vertical coordinate y / L (dimensionless)',
                ylabel='Horizontal velocity u / U (dimensionless)', title='Vertical centerline: x / L = 0.5')
    axes[1].set(xlabel='Horizontal coordinate x / L (dimensionless)',
                ylabel='Vertical velocity v / U (dimensionless)', title='Horizontal centerline: y / L = 0.5')
    for ax in axes:
        ax.grid(True, color='#e2e8f0', linewidth=.6)
        ax.axhline(0, color='#475569', linewidth=.7)
        ax.legend(fontsize=8, frameon=False)
        ax.spines[['top', 'right']].set_visible(False)
    plot = source.parent / 'centerlines.svg'
    figure.savefig(plot)
    figure.savefig(source.parent / 'centerlines.png', dpi=150)
    plt.close(figure)
    rows = []
    for run in runs:
        differences = run.get('difference', {})
        cells = [str(run['cells']) + ' x ' + str(run['cells']),
                 run['native_status'], run['su2_status']]
        for component in ('u', 'v'):
            item = differences.get(component)
            cells.append(f"{item['max_abs']:.6g}" if item else 'Not compared')
        rows.append('<tr>' + ''.join('<td>' + html.escape(s) + '</td>' for s in cells) + '</tr>')
    limitations = ''.join('<li>' + html.escape(s) + '</li>' for s in report['limitations'])
    acceptance = html.escape(json.dumps(report['acceptance'], indent=2))
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SPIKE CFD reference comparison</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;color:#182b38;margin:2rem auto;padding:0 1rem;max-width:1100px}}
h1{{font-size:1.8rem}}table{{border-collapse:collapse;width:100%}}td,th{{padding:.6rem;text-align:left;border-bottom:1px solid #d6dfe5}}
img{{width:100%;height:auto}}pre{{white-space:pre-wrap;background:#f3f6f8;padding:1rem}}a{{color:#165b89}}</style>
<h1>Laminar cavity: SPIKE and SU2</h1>
<p>Reynolds number {report['reynolds']}. Square cavity, length L = 1 m,
lid speed U = 1 m/s, density = 1 kg/m3. The top wall moves horizontally;
the other three walls are stationary. X points right and Y points up.</p>
<p><strong>Declared comparison gate: {'PASSED' if report.get('passed') else 'NOT PASSED'}.</strong>
Experimental numerical evidence; no assembly cooling qualification.</p>
<img src="centerlines.svg" alt="Refined velocity centerlines comparing SPIKE and SU2">
<h2>How to read the plots</h2><p>Solid lines are SPIKE; dashed lines are SU2.
Negative horizontal velocity indicates the return flow inside the cavity.
Profiles use the same interior coordinates with interpolation from each solver's
native grid. Differences below are fractions of the lid speed, not percentages
of local velocity. Corners are excluded because wall velocity is discontinuous there.</p>
<h2>Comparison evidence</h2><table><thead><tr><th>Cells per solver</th><th>SPIKE status</th>
<th>SU2 status</th><th>Max |delta u| / U</th><th>Max |delta v| / U</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table><h2>Declared acceptance</h2><pre>{acceptance}</pre>
<h2>Limits</h2><ul>{limitations}</ul><p>Velocity agreement does not establish pressure,
temperature, turbulence or conjugate heat-transfer accuracy.</p>
<p><a href="comparison.json">Full comparison, diagnostics and executable/input hashes</a></p></html>'''
    destination = source.parent / 'index.html'
    destination.write_text(page, encoding='utf-8')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('comparison', type=Path)
    print(render(parser.parse_args().comparison))
