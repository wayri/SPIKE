// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import {importTestTypescript} from './import-test-typescript.mjs';
const optionSearch=await importTestTypescript('optionSearch');
let cursor=0,states=[],refs=[],effects=[],pending=[];
const react={useState(initial){let i=cursor++;if(!(i in states))states[i]=initial;return[states[i],v=>states[i]=typeof v==='function'?v(states[i]):v];},useRef(value){return refs[cursor++]??={current:value};},useEffect(fn,deps){let i=cursor++;if(!effects[i]||deps.some((v,k)=>v!==effects[i].deps[k]))pending.push(()=>{effects[i]?.cleanup?.();effects[i]={deps,cleanup:fn()};});}};
let requests=[],updated=0,fail=false,resolvePending;
const digest='a'.repeat(64),changed='b'.repeat(64);
const bridge={selectNativeImportFile:async()=>({path:'C:/boards/main.kicad_pcb'}),selectNativeMcadFile:async()=>({path:'C:/cad/case.glb'}),runNativeProjectWorker:async request=>{requests.push(request);if(fail)return{ok:false,error:'Source changed after review'};if(resolvePending)return new Promise(resolve=>{resolvePending.resolve=resolve;});return{ok:true,result:request.method==='linked_source_status'?{status:'changed',sha256:changed}:request.method==='prepare_linked_source_update'?{source:{sha256:changed},outcome:{design:{components:[{}],tracks:[{},{}]}}}:{manifest:{}}};}};
const jsx=(type,props)=>({type,props:props??{}}),module={exports:{}};
const compiled=ts.transpileModule(readFileSync(new URL('../src/LinkedSourcesPanel.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
new Function('require','module','exports',compiled)(name=>name==='react'?react:name==='react/jsx-runtime'?{jsx,jsxs:jsx}:name==='./workerBridge'?bridge:name==='./optionSearch'?optionSearch:{},module,module.exports);
let props={projectPath:'C:/test.spike',manifest:digest,targets:[{kind:'board',id:'board',name:'Controller',instances:2},{kind:'model',id:'case',name:'Enclosure',instances:1}],links:[{target_kind:'board',target_id:'board',path:'C:/boards/main.kicad_pcb',sha256:digest}],disabledReason:'',onUpdated:async()=>updated++,onStatus(){}};
const nodes=node=>!node||typeof node!=='object'?[]:[node,...[node.props?.children].flat(Infinity).flatMap(nodes)];
const text=node=>node==null||typeof node==='boolean'?'':typeof node==='number'?String(node):typeof node==='string'?node:[node?.props?.children].flat(Infinity).map(value=>typeof value==='string'?value:text(value)).join('');
let tree;
function render(){cursor=0;pending=[];tree=module.exports.default(props);pending.forEach(fn=>fn());return nodes(tree);}
const button=label=>render().find(n=>n.type==='button'&&text(n).includes(label));
const settle=async()=>{await new Promise(resolve=>setImmediate(resolve));render();};
render();button('Controller').props.onClick();render();
button('Check changes').props.onClick();await settle();
assert.equal(requests.at(-1).method,'linked_source_status');assert.equal(requests.at(-1).params.target_id,'board');assert.ok(!('path' in requests.at(-1).params));
button('Review update').props.onClick();await settle();assert.ok(button('Apply update and invalidate results'));
fail=true;button('Apply update and invalidate results').props.onClick();await settle();assert.equal(updated,0);assert.ok(button('Apply update and invalidate results'));assert.ok(render().some(n=>n.props.role==='alert'&&text(n).includes('Source changed')));
fail=false;button('Apply update and invalidate results').props.onClick();await settle();assert.equal(updated,1);assert.equal(requests.at(-1).params.expected_sha256,changed);assert.equal(requests.at(-1).params.invalidate_results,true);
button('Relocate source').props.onClick();await settle();assert.equal(requests.at(-1).method,'link_project_source');assert.equal(requests.at(-1).params.path,'C:/boards/main.kicad_pcb');
button('Unlink').props.onClick();await settle();assert.equal(requests.at(-1).params.unlink,true);assert.ok(!('path' in requests.at(-1).params));
props={...props,disabledReason:'Save current changes'};assert.equal(button('Review update').props.disabled,true);
props={...props,disabledReason:''};resolvePending={};button('Review update').props.onClick();await settle();props={...props,manifest:changed};render();resolvePending.resolve({ok:true,result:{source:{sha256:changed},outcome:{}}});resolvePending=null;await settle();assert.equal(button('Apply update and invalidate results'),undefined,'A preview from an old project revision must be discarded');
const normal=module.exports.normalizeLinkedSources;assert.equal(normal([{},...props.links,{...props.links[0],sha256:'invalid'}]).length,1);
console.log('Linked source UI: scoped requests, reviewed hashes, failure recovery, dirty locks and stale response rejection passed');

