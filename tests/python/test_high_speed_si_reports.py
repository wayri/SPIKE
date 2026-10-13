# SPDX-License-Identifier: Apache-2.0
"""Report layout contracts: unit titles, probes and honest evidence states."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('si_report_renderer', ROOT / 'examples/high_speed_si/render_reports.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class HighSpeedReportTests(unittest.TestCase):
    def test_unavailable_evidence_is_not_passed(self):
        harness, field = renderer.report_guides({})
        self.assertIn('Unavailable', harness)
        self.assertIn('has not passed', field)
        self.assertNotIn('Sanity checks passed', field)

    def test_board_context_preserves_section_and_projection(self):
        geometry = [{'name': 'A.substrate', 'kind': 'dielectric',
                     'start_mm': [-20, -10, -1], 'stop_mm': [20, 10, 0]}]
        section = renderer.projected_field_geometry(geometry, 0, 2, 1, 0)[0]
        self.assertEqual((section['x'], section['y'], section['width'], section['height']),
                         (-20, -1, 40, 1))
        self.assertTrue(section['cut'])
        projection = renderer.projected_field_geometry(geometry, 0, 1, 2, 5)[0]
        self.assertFalse(projection['cut'])
        self.assertEqual((projection['width'], projection['height']), (40, 20))

    def test_native_grid_order_and_shape(self):
        capture = {'shape': [2, 2, 2], 'positions': {'x': [0, 1], 'y': [0, 1], 'z': [0, 1]},
                   'electric_field': [{'real': [[i, 0, 0] for i in range(1, 9)],
                                       'imag': [[0, 0, 0] for _ in range(8)]}]}
        grid = renderer.field_grid(capture, 'electric_field', 0)
        self.assertEqual(grid[:, :, 1].tolist(), [[2, 4], [6, 8]])
        self.assertEqual(grid[:, 1, :].tolist(), [[3, 4], [7, 8]])
        capture['shape'] = [8, 1, 1]
        with self.assertRaisesRegex(ValueError, 'shape'):
            renderer.field_grid(capture, 'electric_field', 0)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for report JavaScript contracts')
    def test_units_layout_and_exact_probe(self):
        frame = {'frequency_hz': 1e9, 'real': [[1., 2., 3.] for _ in range(8)], 'imag': [[0., 0., 0.] for _ in range(8)]}
        wire = {'id': 'pwr', 'color': '#ff0000', 'properties': {'cross_section_position_mm': [0, 1]}}
        data = {
            'protocols': [{'id': 'case', 'label': 'Reference', 'metrics': [['Status', 'pass']],
                           'frequency_ghz': [1], 'gain_db': [-6], 'eye': [{'phase_ui': [0, 1], 'voltage_v': [0, 1]}]}],
            'geometry': [{'name': 'A.substrate', 'kind': 'dielectric', 'start_mm': [0, 0, 0], 'stop_mm': [1, 1, 1]}],
            'field_samples': {'points_mm': [[x,y,z] for x in (1,2) for y in (2,3) for z in (3,4)], 'electric_field': [frame, {**frame, 'frequency_hz': 2e9, 'real': [[10., 20., 30.] for _ in range(8)]}], 'magnetic_field': [frame]},
            'harness': {}, 'screen': {},
            'harness_assembly': {'harnesses': [{'extensions': {'spike.harness-conductors': {'wires': [wire]}}}]},
            'harness_pi': {'native_result': {'data': {'element_current_a': {}, 'element_power_w': {}}}},
            'harness_validation': {'pi': {'load_voltage_v': 12}, 'si': {'frequency_response': [
                {'frequency_hz': 1e9, 'differential_next_db': -40, 'differential_fext_db': -50}]}},
            'field': {'frequency_hz': [1e9], 's_real': [[[0] * 4 for _ in range(4)]],
                      's_imag': [[[0] * 4 for _ in range(4)]]},
        }
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with patch.object(renderer, 'OUT', out), patch.object(renderer.shutil, 'copyfile'):
                renderer.write_html(data, [('Reference', 'Bounded fixture', [], [])])
            html = (out / 'index.html').read_text(encoding='utf-8')
            self.assertIn('How to read the captured field', html)
            self.assertIn('Receiver eye diagram', html)
            self.assertIn('mesh/duration convergence', html)
            script = html.split('<script>')[1].split('</script>')[0]
            harness = r'''
const assert = require('node:assert/strict');
const plots = new Map(), elements = new Map();
const defaults = {'#boards':'both','#field-quantity':'electric_field','#field-frequency':'0','#sample-index':'0','#wire-choice':'pwr','#field-view':'volume','#slice-plane':'xy','#slice-index':'1','#field-smoothing':'smooth','#field-scale':'frequency'};
global.document = {querySelector(id) {if(!elements.has(id))elements.set(id,{value:defaults[id],handlers:{},on(name,callback){this.handlers[name]=callback;}});return elements.get(id);}};
global.Plotly = {newPlot(id,traces,layout,config){plots.set(id,{traces,layout,config});}};
'''
            checks = r'''
for (const [id,p] of plots) {
  const axes = p.layout.scene || p.layout;
  for(const key of (p.layout.scene?['xaxis','yaxis','zaxis']:['xaxis','yaxis'])) {
    assert.equal(typeof axes[key].title.text,'string',id+' '+key);
    assert.match(axes[key].title.text,/\((GHz|V|UI|dB|dB V\/V|mm)\)/);
    assert.equal(axes[key].automargin,true);
  }
  assert.equal(p.config.responsive,true);
}
assert.equal(plots.size,6);
const field = plots.get('scene').traces.find(t=>t.name==='Raw field samples');
assert.equal(field.marker.colorbar.orientation,'h');
assert.equal(field.marker.colorbar.title.text,'Raw E (V/m)');
assert.equal(field.showlegend,false);
assert.equal(field.customdata[0].complex_vector_norm,Math.sqrt(14));
document.querySelector('#probe-sample').onclick();
assert.equal(JSON.parse(document.querySelector('#probe').textContent).units,'V/m');
document.querySelector('#field-quantity').value='magnetic_field';
document.querySelector('#field-quantity').onchange();
assert.equal(plots.get('scene').traces.find(t=>t.name==='Raw field samples').marker.colorbar.title.text,'Raw H (A/m)');
document.querySelector('#probe-sample').onclick();
assert.equal(JSON.parse(document.querySelector('#probe').textContent).units,'A/m');
document.querySelector('#sample-index').value='-1';
document.querySelector('#probe-sample').onclick();
assert.match(document.querySelector('#probe').textContent,/valid saved index/);
document.querySelector('#slice-index').value='1';
document.querySelector('#field-view').value='slice';
document.querySelector('#field-view').onchange();
let slice = plots.get('scene').traces[0];
assert.equal(slice.type,'heatmap');
assert.equal(slice.zsmooth,'best');
assert.equal(plots.get('scene').layout.shapes.length,1);
assert.equal(plots.get('scene').layout.shapes[0].line.dash,'dash');
assert.match(document.querySelector('#field-resolution').textContent,/2 × 2 × 2/);
document.querySelector('#field-smoothing').value='native';
document.querySelector('#field-smoothing').onchange();
assert.equal(plots.get('scene').traces[0].zsmooth,false);
assert.deepEqual(slice.customdata.map(row=>row.map(v=>v.sample_index)),[[1,5],[3,7]]);
assert.equal(slice.colorbar.title.text,'Raw H (A/m)');
assert.match(document.querySelector('#slice-position').textContent,/Z = 4.000 mm/);
assert.equal(plots.get('scene').layout.xaxis.title.text,'X (mm)');
assert.equal(plots.get('scene').layout.yaxis.title.text,'Y (mm)');
document.querySelector('#slice-prev').onclick();
assert.equal(document.querySelector('#slice-index').value,'0');
document.querySelector('#slice-prev').onclick();
assert.equal(document.querySelector('#slice-index').value,'0');
document.querySelector('#slice-next').onclick();
assert.equal(document.querySelector('#slice-index').value,'1');
for(const [plane,expected,axis] of [['xz',[[2,6],[3,7]],'Z (mm)'],['yz',[[4,6],[5,7]],'Z (mm)']]){
 document.querySelector('#slice-plane').value=plane;
 document.querySelector('#slice-plane').onchange();
 const p=plots.get('scene');
 assert.deepEqual(p.traces[0].customdata.map(row=>row.map(v=>v.sample_index)),expected);
 assert.equal(p.layout.yaxis.title.text,axis);
}
document.querySelector('#slice-peak').onclick();
assert.equal(document.querySelector('#slice-index').value,'0');
assert.equal(document.querySelector('#field-view').value,'slice');
document.querySelector('#field-quantity').value='electric_field';
document.querySelector('#field-quantity').onchange();
document.querySelector('#field-scale').value='all';
document.querySelector('#field-scale').onchange();
const sharedMax=plots.get('scene').traces[0].zmax;
assert.equal(sharedMax,Math.sqrt(1400));
inspectSample(7,true);
assert.match(document.querySelector('#probe-inspector').innerHTML,/2.000 \/ 3.000 \/ 4.000/);
assert.equal(plots.get('scene').traces[1].name,'Selected native sample');
document.querySelector('#field-frequency').value='1';
document.querySelector('#field-frequency').onchange();
assert.equal(plots.get('scene').traces[0].zmax,sharedMax);
assert.equal(JSON.parse(document.querySelector('#probe').textContent).complex_vector_norm,Math.sqrt(1400));
assert.equal(JSON.parse(document.querySelector('#probe').textContent).frequency_hz,2e9);
document.querySelector('#field-scale').value='frequency';
document.querySelector('#field-frequency').value='0';
document.querySelector('#field-frequency').onchange();
assert.equal(plots.get('scene').traces[0].zmax,Math.sqrt(14));
document.querySelector('#scene').handlers.plotly_click({points:[{customdata:{sample_index:0}}]});
assert.equal(JSON.parse(document.querySelector('#probe').textContent).sample_index,0);
document.querySelector('#coupling').handlers.plotly_click({points:[{x:1.5,y:-32,data:{name:'S31 near'}}]});
assert.match(document.querySelector('#readout-coupling').textContent,/S31 near.*1.50000 GHz.*-32.0000 dB/);
assert.equal(plots.get('coupling').layout.hovermode,'x unified');
assert.equal(plots.get('coupling').layout.xaxis.showspikes,true);


'''
            result = subprocess.run(['node', '-e', harness + script + checks], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
