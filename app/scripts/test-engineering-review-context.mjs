// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
const require = createRequire(import.meta.url), module = {exports:{}};
let slots=[],cursor=0,effects=[],pending=[];
const hooks={
  useState(initial){const i=cursor++;if(!(i in slots))slots[i]=typeof initial==="function"?initial():initial;return[slots[i],value=>{slots[i]=typeof value==="function"?value(slots[i]):value;}];},
  useRef(initial){const i=cursor++;return slots[i]??={current:initial};},
  useEffect(fn,deps){const i=cursor++;const old=effects[i];if(!old||deps.some((v,j)=>v!==old.deps[j]))pending.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}
};
const hashing=[];
const code=ts.transpileModule(readFileSync(new URL("../src/EngineeringReview.tsx",import.meta.url),"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
new Function("require","module","exports",code)(name=>{
  if(name==="react")return hooks;
  if(name.endsWith(".css"))return{};
  if(name==="./workerBridge")return{};
  if(name==="./panelPresentation")return{usePanelPresentation:()=>({})};
  if(name==="./PartLimitsPanel")return{default:()=>null};
  if(name==="./engineeringReviewWorkspace")return{engineeringReviewScope:()=>new Promise(resolve=>hashing.push(resolve)),restoreEngineeringReviewWorkspace:value=>value};
  return require(name);
},module,module.exports);
const context=name=>({boards:[{id:"same-occurrence",design:{components:[{id:"same-part",reference:"U1"}],name}}]});
let calls=0,complete,publications=[];
const execute=()=>{calls++;return new Promise(resolve=>complete=resolve);};
const props={open:true,onClose:()=>{},onWorkspaceChange:value=>publications.push(value),execute};
function find(element,predicate){if(!element||typeof element!=="object")return null;if(predicate(element))return element;for(const child of [element.props?.children].flat(Infinity)){const found=find(child,predicate);if(found)return found;}return null;}
function render(board){cursor=0;const tree=module.exports.default({...props,context:board});return find(tree,node=>node.type==="button"&&node.props.title==="Review current board occurrences");}
function flush(){pending.splice(0).forEach(effect=>effect());}
const a=context("A"),b=context("B");
assert.equal(render(a).props.disabled,true);flush();hashing.shift()("a".repeat(64));await Promise.resolve();await Promise.resolve();
let run=render(a);assert.equal(run.props.disabled,false);run.props.onClick();assert.equal(calls,1);
// New source render, deliberately before effects clean up the old request.
run=render(b);assert.equal(run.props.disabled,true);run.props.onClick();assert.equal(calls,1,"new design cannot run under the prior hash");
complete({ok:true,result:{contract:"spike/engineering-review-result/v1"}});await Promise.resolve();await Promise.resolve();
assert.equal(publications.length,0,"old result cannot publish in the pre-effect context-switch window");
flush();effects.forEach(effect=>effect?.cleanup?.());
console.log("Engineering review rejects pre-effect source-scope races and stale result publication");
