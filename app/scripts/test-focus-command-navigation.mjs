// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../src/FocusCommandPanel.tsx', import.meta.url), 'utf8');
const file = ts.createSourceFile('FocusCommandPanel.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const wanted = new Set(['normalizeMenuRoute', 'sameMenuRoute', 'recordMenuRoute', 'findMenuRouteTarget']);
const declarations = [];
for (const statement of file.statements) if (ts.isFunctionDeclaration(statement) && statement.name && wanted.has(statement.name.text)) declarations.push(statement.getText(file));
const javascript = ts.transpileModule(`const MENU_ROUTE_HISTORY_LIMIT = 40;\n${declarations.join('\n').replace(/\bexport\s+/g, '')}\nreturn { normalizeMenuRoute, recordMenuRoute, findMenuRouteTarget };`, {
  compilerOptions: { module: ts.ModuleKind.None, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { normalizeMenuRoute, recordMenuRoute, findMenuRouteTarget } = Function(javascript)();

const commands = [{ id:'file', children:[{ id:'open', children:[] }, { id:'recent', children:[] }] }, { id:'view', children:[] }];
assert.deepEqual(normalizeMenuRoute(commands, ['file','open']), ['file','open']);
assert.deepEqual(normalizeMenuRoute(commands, ['file','missing']), ['file'], 'a removed child recovers to its available parent');

let history = { entries:[[]], index:0 };
history = recordMenuRoute(history, ['file']);
history = recordMenuRoute(history, ['file','open']);
let target = findMenuRouteTarget(history, commands, -1, ['file','open']);
assert.deepEqual(target.route, ['file']);
history = target.history;
target = findMenuRouteTarget(history, commands, 1, ['file']);
assert.deepEqual(target.route, ['file','open']);

history = findMenuRouteTarget(target.history, commands, -1, ['file','open']).history;
history = recordMenuRoute(history, ['view']);
assert.deepEqual(history.entries, [[], ['file'], ['view']], 'visiting after Back truncates the forward branch');
assert.equal(findMenuRouteTarget(history, commands, 1, ['view']), null);

const changed = [{ id:'file', children:[] }, { id:'view', children:[] }];
const staleHistory = { entries:[[], ['file','open'], ['view']], index:2 };
target = findMenuRouteTarget(staleHistory, changed, -1, ['view']);
assert.deepEqual(target.route, ['file'], 'history recovers a changed section to its nearest available ancestor');

history = { entries:[[]], index:0 };
for(let index=0; index<48; index+=1) history=recordMenuRoute(history, [index%2?'file':'view'], 40);
assert.equal(history.entries.length, 40, 'section history remains bounded');

for (const label of ['Go back to previous menu section','Go forward to next menu section','Go up to parent menu section','Go home to Menu']) assert.ok(source.includes(label));
assert.doesNotMatch(source, /path\.length > 0 && !term && <button[^>]+focus-command-back/, 'navigation stays in the existing header row');
console.log('Focus menu navigation preserves visit history, hierarchy, recovery, branching, and its bounded size');
