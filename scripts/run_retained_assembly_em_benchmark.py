# SPDX-License-Identifier: Apache-2.0
"""Run the original hollow-enclosure fixture at three spatial resolutions."""
import argparse
import cmath
import html
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.python.test_assembly_em import fixture
from python.spike_core.assembly_em import run_assembly_em


def write_report(directory, results, summary):
    """Present retained numerical samples without interpolation or qualification."""
    rows=[]
    for index,result in enumerate(results):
        column=result['s_parameter_column'][0]
        for frequency,real,imag in zip(result['frequency_hz'],column['real'],column['imag']):
            value=complex(real,imag)
            rows.append(f'<tr><td>{index+1}</td><td>{result["mesh"]["actual_grid"]["cell_count"]:,}</td>'
                f'<td>{frequency/1e9:.3f}</td><td>{real:.7f}</td><td>{imag:.7f}</td>'
                f'<td>{20*math.log10(max(abs(value),1e-300)):.5f}</td>'
                f'<td>{math.degrees(cmath.phase(value)):.3f}</td></tr>')
    links=''.join(f'<li>Mesh {i+1}: <a href="level-{i}/bound-result.json">numerical result and artifact hashes</a>'
        f' · <a href="level-{i}/execution.json">execution record</a>'
        f' · <a href="level-{i}/request.json">retained request</a></li>' for i in range(len(results)))
    limits=''.join(f'<li>{html.escape(item)}</li>' for item in results[-1]['limitations'])
    changes=', '.join(f'{change:.6f}' for change in summary['successive_max_s11_changes'])
    document=f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Retained assembly EM execution benchmark</title><style>
body{{font:16px/1.6 system-ui,sans-serif;color:#18313e;background:#edf2f5;margin:0}}
main{{max-width:1000px;margin:32px auto;background:white;padding:32px}}
h1,h2{{line-height:1.25}} .status{{border-left:4px solid #b57918;padding:12px;background:#fff7e6}}
.table{{overflow:auto}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
th,td{{padding:10px;border-bottom:1px solid #ced8df;text-align:right;white-space:nowrap}}
th{{background:#eef3f6}}a{{color:#075d85}}small{{color:#425963}}</style><main>
<h1>Retained assembly EM execution</h1><p class="status"><strong>Solver executed · Unvalidated</strong><br>
Original conducting plates in a hollow aluminium enclosure. This is not the routed Arduino assembly.</p>
<h2>Model and excitation</h2><p>Two 10 × 10 × 1 mm copper plates separated by 3 mm of air,
inside a hollow 16 mm cubical aluminium enclosure with 1 mm walls. One 50 Ω lumped port connects
the declared return and signal faces. Conductivities: copper 5.8 × 10⁷ S/m; aluminium 3.5 × 10⁷ S/m.
Requested spatial resolutions: 1.00, 0.75 and 0.50 mm. OpenEMS executes a Cartesian FDTD grid over
the retained polyhedral geometry; the tetrahedra identify material boundaries.</p>
<h2>Port response</h2><p>S11 is the power-normalized reflected wave divided by the incident wave at
the same port. Magnitude is 20 log₁₀|S11| in dB; phase is arg(S11) in degrees. These are three
frequency samples, not a continuous sweep or a compliance result.</p>
<div class="table"><table><thead><tr><th>Mesh</th><th>Cells</th><th>Frequency (GHz)</th>
<th>Real S11</th><th>Imaginary S11</th><th>Magnitude (dB)</th><th>Phase (°)</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<h2>Refinement diagnostic</h2><p>Maximum successive complex S11 changes: {changes} (dimensionless).
The decreasing change is a diagnostic. Independent reference correlation, boundary distance and
simulation duration convergence are still required; no quantitative accuracy claim is made.</p>
<h2>Retained data and fields</h2><ul>{links}</ul><p>The numerical result identifies the E/H HDF5
artifacts, metre coordinate axes, subsampling, frequency and file hashes. Fields are raw
Gaussian-pulse DFT samples, not calibrated steady-state 1 V or 1 W fields.</p>
<h2>Limitations</h2><ul>{limits}</ul>
<h2>Existing enclosed Arduino case</h2><p>It still requires physical stackups, filled copper,
qualified conductor/pad geometry, connector geometry and explicit source/return ports. Its mechanical
solids alone do not represent an electrically resolved device.</p></main></html>'''
    (directory/'index.html').write_text(document,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    results=[]
    for index,edge in enumerate((.001,.00075,.0005)):
        request=fixture();request['settings']['mesh_resolution_m']=edge
        result=run_assembly_em(request,args.output/f'level-{index}')
        (args.output/f'level-{index}'/'bound-result.json').write_text(
            json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
        results.append(result)
        print(f"level {index}: {result['mesh']['actual_grid']['cell_count']} cells, executed",flush=True)
    differences=[]
    for left,right in zip(results[:-1],results[1:]):
        a,b=left['s_parameter_column'][0],right['s_parameter_column'][0]
        differences.append(max(abs(complex(x,y)-complex(u,v)) for x,y,u,v in
            zip(a['real'],a['imag'],b['real'],b['imag'])))
    report={'contract':'spike/retained-assembly-em-benchmark/v1','solver_executed':True,
        'production_qualified':False,'status':'unvalidated','successive_max_s11_changes':differences,
        'cells':[r['mesh']['actual_grid']['cell_count'] for r in results],
        'model':'Original conducting plates in a hollow enclosure, not the routed Arduino assembly.',
        'limitations':['Three spatial runs are a diagnostic, not a quantitative accuracy claim.',
            'Independent reference correlation, boundary and time convergence remain required.']}
    (args.output/'summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    write_report(args.output,results,report)
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
