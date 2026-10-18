// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { importTestTypescript } from './import-test-typescript.mjs';
const require=createRequire(import.meta.url);
const copper=await importTestTypescript('copperLayerSelection');
const iconModule={exports:{}};
new Function('require','module','exports',ts.transpileModule(readFileSync(new URL('../src/icons/index.tsx',import.meta.url),'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX},
}).outputText)(require,iconModule,iconModule.exports);
function load(name,react=React) {
  const source=readFileSync(new URL(`../src/${name}.tsx`,import.meta.url),'utf8');
  const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  const module={exports:{}};
  new Function('require','module','exports',js)(name=>name.endsWith('.css')?{}:name==='react'?react:name==='./icons'?iconModule.exports:name==='./BoardViewport'?{previewViewportTarget(){}}:name==='./copperLayerSelection'?copper:name==='./NetCatalog'?{default:load('NetCatalog',react)}:name==='./DataTable'?{default:({children})=>React.createElement('table',null,children)}:require(name),module,module.exports);
  return module.exports.default;
}
const board={nets:{'1':'GND','2':'VCC'},layers:['F.Cu','B.Cu'],tracks:[],vias:[],pads:[],zones:[]};
const selected=[],roles=[];
const props={board,selectedNet:'GND',managedNets:['VCC','GND'],setManagedNets:value=>roles.push(value),loopExtractions:[],setLoopExtractions(){},pathGroups:[],onSelectNet:value=>selected.push(value),onOpenPowerPaths(){},onOpenSeriesAnalysis(){},onStatus(){},onClose(){}};
const html=renderToStaticMarkup(React.createElement(load('NetManager'),props));
assert.match(html,/PI NET MANAGER/);assert.match(html,/Find net by name/);assert.match(html,/<th>Role<\/th>/);assert.match(html,/Role for GND/);assert.match(html,/Loop RLC/);
const hooks={useState:initial=>[typeof initial==='function'?initial():initial,()=>{}],useMemo:fn=>fn(),useEffect(){}};
const NetManager=load('NetManager',hooks);
function nodes(node) { return !node||typeof node!=='object'?[]:[node,...React.Children.toArray(node.props?.children).flatMap(nodes)]; }
const catalog=nodes(NetManager(props)).find(node=>node.props?.rows);
catalog.props.onSelect('GND');assert.deepEqual(selected,['GND'],'original manager still selects named nets through the shared catalog');
catalog.props.role('GND').props.onChange({target:{value:'source'}});assert.deepEqual(roles,[['GND','VCC']],'role assignment keeps the original analysis workflow');
const Catalog=load('NetCatalog');
const display=Catalog({rows:[{id:'internal-a',name:'GND',metrics:{layers:2,tracks:1,vias:0,pads:2,zones:0,parts:1}}],activeId:'internal-a',onSelect:id=>selected.push(id)});
const row=nodes(display).find(node=>node.type==='tr'&&node.props.className==='active');row.props.onClick();assert.equal(selected.at(-1),'internal-a','shared selection uses identity while rendering only names');
assert.doesNotMatch(renderToStaticMarkup(display),/internal-a/);
console.log('Shared net catalog preserves original PI roles, loops, named selection and canonical assembly selection');
