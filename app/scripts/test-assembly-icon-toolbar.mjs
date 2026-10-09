// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import ts from 'typescript';
const require=createRequire(import.meta.url);
const source=readFileSync(new URL('../src/AssemblyIconToolbar.tsx',import.meta.url),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const module={exports:{}};
new Function('require','module','exports',js)(name=>name.endsWith('.css')?{}:require(name),module,module.exports);
const Toolbar=module.exports.default;
const events=[];
const Icon=props=>React.createElement('svg',props);
const actions=[{id:'fit',label:'Fit the visible assembly',text:'Fit',icon:Icon,onClick:()=>events.push('fit')},
  {id:'orbit',label:'Orbit the camera',text:'Orbit',icon:Icon,pressed:true,onClick:()=>events.push('orbit')},
  {id:'focus',label:'Focus selected board',text:'Focus',icon:Icon,disabled:true,onClick:()=>events.push('focus')}];
const element=Toolbar({actions});
const buttons=element.props.children;
assert.equal(element.props.role,'toolbar');
assert.equal(buttons.length,3);
for(let index=0;index<buttons.length;index++){
  const button=buttons[index];
  assert.equal(button.type,'button');
  assert.equal(button.props.type,'button');
  assert.equal(button.props['aria-label'],actions[index].label);
  assert.equal(button.props.title,actions[index].label);
  assert.equal(button.props.children[0].props['aria-hidden'],'true');
}
buttons[0].props.onClick();buttons[1].props.onClick();
assert.deepEqual(events,['fit','orbit'],'actions retain distinct command callbacks');
assert.equal(buttons[1].props['aria-pressed'],true);
assert.equal(buttons[2].props.disabled,true);
const html=renderToStaticMarkup(element);
assert.match(html,/>Fit<\/span>/,'mini labels remain visible');
assert.match(html,/aria-pressed="true"/);
assert.match(html,/disabled=""/,'native disabled buttons block keyboard and pointer activation');
console.log('Assembly icon toolbar names, tooltips, mini labels, commands and toggle states passed.');
