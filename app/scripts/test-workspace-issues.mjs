import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { workspaceIssues } from '../src/workspaceIssues.ts';
const base = { hasBoard: false, workspace: 'EM', mode: 'DC IR Drop', stackupComplete: false,
  components: 0, nets: 0, copperLayers: 0, stackRows: 0 };
const empty = workspaceIssues(base);
assert.equal(empty.length, 1);
assert.equal(empty[0].kind, 'info');
assert.equal(empty[0].title, 'No design loaded');
assert.equal(empty.filter(x => x.kind === 'warning').length, 0);
for (const workspace of ['EM', 'EMI', 'Thermal', 'HF / SI']) {
  assert.ok(!workspaceIssues({ ...base, hasBoard: true, workspace }).some(x => /DC convergence|Mesh convergence/.test(x.title)));
}
assert.ok(!workspaceIssues({ ...base, hasBoard: true, workspace: 'PI', mode: 'AC Impedance Sweep' }).some(x => /DC convergence/.test(x.title)));
const dc = workspaceIssues({ ...base, hasBoard: true, workspace: 'PI', convergence: 'passed', convergenceLevels: 3 });
assert.equal(dc[0].title, 'Mesh convergence passed');
assert.equal(dc[1].kind, 'warning', 'real incomplete stackup remains actionable');
assert.ok(!dc.some(x => x.title === 'Import completed'));
const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
assert.match(app, /activeWorkspaceIssues\.map\(issue => <Issue/);
assert.doesNotMatch(app, /<CheckCircle2 size=\{14\} \/> Contract valid/);
assert.doesNotMatch(app, /Issues <b>\{stackupComplete \? 1 : 2\}/);
console.log('empty workspace, active analysis and evidence-based issue states passed');
