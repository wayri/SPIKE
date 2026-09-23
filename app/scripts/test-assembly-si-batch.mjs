import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const source = readFileSync(new URL('../src/AssemblySiBatch.tsx', import.meta.url), 'utf8');
for (const token of ['run_multiboard_si_independent_batch', 'independent_board_batch', 'boards.filter(board => jobs[board.id])', 'suite_request: jobs[board.id]', 'Export batch results', 'row.namespace', 'session-only', 'disabled || busy', '2 * 1024 * 1024']) assert.ok(source.includes(token), token);
assert.ok(!source.includes('coupled_harness_network'));
const editor = readFileSync(new URL('../src/AssemblyStructureEditor.tsx', import.meta.url), 'utf8');
assert.ok(editor.includes('disabled={busy || dirty}'));
console.log('Assembly SI batch wiring checks passed. Native interactive testing remains separate.');
