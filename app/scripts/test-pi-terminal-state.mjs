// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import ts from 'typescript';
import { piTerminalPosition, removePiTerminal } from '../src/piTerminalState.ts';
assert.equal(piTerminalPosition({ x: '', y: '' }), null);
assert.equal(piTerminalPosition({ x: ' ', y: '10' }), null);
assert.equal(piTerminalPosition({ x: 'NaN', y: '10' }), null);
assert.deepEqual(piTerminalPosition({ x: '0', y: '0' }), [0, 0]);
assert.deepEqual(piTerminalPosition({ x: '-12.5', y: ' 10 ' }), [-12.5, 10]);
const setup = { sources: [{ id: 'same' }], loads: [{ id: 'same' }],
  returnPath: { sources: [{ id: 'same' }], loads: [{ id: 'same' }] }, batchJobs: [{ id: 'batch' }] };
for (const role of ['source', 'load', 'source_return', 'load_return']) {
  const next = removePiTerminal(setup, role, 'same');
  const values = [next.sources, next.loads, next.returnPath.sources, next.returnPath.loads];
  assert.equal(values.filter(items => !items.length).length, 1, 'only the clicked role is deleted');
  assert.equal(next.batchJobs, setup.batchJobs);
  assert.equal(setup.sources.length, 1, 'original snapshot remains usable for undo');
}
assert.equal(removePiTerminal(setup, 'source', 'missing').sources.length, 1);
const app = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const ast=ts.createSourceFile('App.tsx',app,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
let actionSource;
function visit(node){
 if(ts.isObjectLiteralExpression(node) && node.properties.some(prop=>ts.isPropertyAssignment(prop) && prop.name.getText(ast)==='id' && ts.isStringLiteral(prop.initializer) && prop.initializer.text==='delete-terminal')) actionSource=node.getText(ast);
 ts.forEachChild(node,visit);
}
visit(ast);assert.ok(actionSource,'the actual terminal deletion action remains in the workspace context catalog');
const compiled=ts.transpileModule(`export function action(deps){const {clickedObject,recordChange,setPiSetup,setSelected,removePiTerminal,smartContext}=deps;return (${actionSource});}`,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const module={exports:{}};
new Function('module','exports',compiled)(module,module.exports);
for(const role of ['source','load','source_return','load_return']){
 let changes=0,selected='terminal',next=setup;
 const action=module.exports.action({clickedObject:{id:'analysis-terminal:same',type:'terminal',terminalRole:role},smartContext:{},recordChange:()=>changes++,setPiSetup:update=>next=update(next),setSelected:value=>selected=value,removePiTerminal});
 action.run();assert.equal(changes,1);assert.equal(selected,null);
 const lists=[next.sources,next.loads,next.returnPath.sources,next.returnPath.loads];
 assert.equal(lists.filter(items=>!items.length).length,1,'context action removes only its terminal role');
 assert.equal(lists[['source','load','source_return','load_return'].indexOf(role)].length,0);
 assert.equal(next.batchJobs,setup.batchJobs);
}
console.log('PI terminal coordinates and production context role-scoped deletion passed.');
