// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const compile = name => ts.transpileModule(readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8"), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText;
const helper = {exports:{}};
new Function("module", "exports", compile("siSearchDraft.ts"))(helper, helper.exports);
const {siSearchDraftError: validate} = helper.exports;
assert.equal(validate({id:"a",signalNetId:"s",referenceNetId:"g",frequencyStopHz:1e9}, ["s","g"]), "");
assert.match(validate({id:"a",signalNetId:"unknown"}, ["s","g"]), /no longer exists/);
assert.match(validate({id:"a",signalNetId:"s",referenceNetId:"s"}, ["s"]), /distinct/);
assert.match(validate({id:"a",frequencyStartHz:2,frequencyStopHz:1}, []), /greater/);
assert.match(validate({id:"a",bitRateHz:NaN}, []), /positive/);
assert.match(validate({id:"a",impedanceOhm:0}, []), /impedance/);
assert.match(validate({id:"a",impedanceOhm:Infinity}, []), /impedance/);
assert.match(validate({id:"a",riseTimeS:-1}, []), /Rise time/);

// Exercise the component's effects with persistent hook state across renders.
// External solvers are fail-fast stubs: reviewed input must never execute them.
let slots=[], cursor=0, effects=[], changed=false;
const same = (a,b) => a && b && a.length===b.length && a.every((v,i)=>Object.is(v,b[i]));
const hooks = {
 useState(initial){const i=cursor++; if(!(i in slots))slots[i]=typeof initial==="function"?initial():initial; return [slots[i], value=>{const next=typeof value==="function"?value(slots[i]):value;if(!Object.is(next,slots[i])){slots[i]=next;changed=true;}}];},
 useRef(initial){const i=cursor++;return slots[i]??(slots[i]={current:initial});},
 useMemo(fn,deps){const i=cursor++;if(!same(slots[i]?.deps,deps))slots[i]={deps,value:fn()};return slots[i].value;},
 useEffect(fn,deps){const i=cursor++;if(!same(slots[i],deps)){slots[i]=deps;effects.push(fn);}},
};
const jsx=(type,props)=>({type,props});
let allowRequestCapture=false, capturedRequest=null;
const worker=new Proxy({isDesktopShell:()=>false,runSiUniformChannel:async(_design,request)=>{assert.ok(allowRequestCapture,"Review must not run a solver");capturedRequest=request;return {ok:false,error:"Request capture only"};}},{get:(o,k)=>o[k]??(()=>{throw Error(`Unexpected solver call ${String(k)}`);})});
const module={exports:{}};
new Function("require","module","exports",compile("SParameterWorkbench.tsx"))(name=>{
 if(name==="react")return hooks;
 if(name==="react/jsx-runtime")return {jsx,jsxs:jsx};
 if(name==="./siSearchDraft")return helper.exports;
 if(name==="./numericRange"){const range={exports:{}};new Function("module","exports",compile("numericRange.ts"))(range,range.exports);return range.exports;}
 if(name==="./workerBridge")return worker;
 if(name==="./panelPresentation")return {usePanelPresentation:()=>({})};
 return {};
},module,module.exports);
const design={contract:"spike/design-ir/v2",design_id:"board",nets:[{id:"s",name:"SIGNAL"},{id:"g",name:"GND"}],layers:[{id:"l",name:"B.Cu",layer_type:"copper"}]};
const draft={id:"first",signalNetId:"s",referenceNetId:"g",frequencyStopHz:2e9,bitRateHz:3e9,impedanceOhm:75,riseTimeS:2e-9,componentRefs:["U1","J1"]};
let props={assemblyDesigns:null,canonicalDesign:design,onClose(){},onStatus(){},initialResult:{contract:"spike/si-channel-result/v1"},searchDraft:draft};
function render(){let tree;for(let i=0;i<8;i++){cursor=0;effects=[];changed=false;tree=module.exports.default(props);effects.forEach(fn=>fn());if(!changed)return tree;}throw Error("Effects did not settle");}
function nodes(tree){if(!tree||typeof tree!=="object")return [];return [tree,...[tree.props?.children].flat(Infinity).flatMap(nodes)];}
function text(tree){if(typeof tree==="string")return tree;if(!tree||typeof tree!=="object")return "";return [tree.props?.children].flat(Infinity).map(text).join("");}
let tree=render();
assert.match(text(tree), /U1, J1 do not define source\/receiver pin endpoints/);
assert.match(text(tree), /Select the reference copper layer/);
assert.match(text(tree), /Requested rise time 2e-9 s remains pending review/);
assert.match(text(tree), /No waveform is inferred/);
assert.equal(capturedRequest,null,"Applying search must not execute a request");
const values=nodes(tree).filter(n=>n.type==="select"||n.type==="input").map(n=>n.props.value);
assert.ok(values.includes("s")&&values.includes("g")&&values.includes("2000000000")&&values.includes("3000000000"));
assert.ok(!nodes(tree).some(n=>n.type==="select"&&n.props.value==="l"), "Reference layer requires explicit review");
assert.ok(!text(tree).includes("Export experimental channel result"), "Prior result must be invalidated");
const stopInput=nodes(tree).find(n=>n.type==="input"&&n.props.value==="2000000000");
stopInput.props.onChange({target:{value:"2500000000"}});
tree=render();
assert.ok(nodes(tree).some(n=>n.type==="input"&&n.props.value==="2500000000"), "Same draft must preserve later user edits");
const layerLabel=nodes(tree).find(n=>n.type==="label"&&text(n).startsWith("Reference layer"));
nodes(layerLabel).find(n=>n.type==="select").props.onChange({target:{value:"l"}});
tree=render();
const impedanceLabel=nodes(tree).find(n=>n.type==="label"&&text(n)==="Reference impedance (ohm)");
const impedanceInput=nodes(impedanceLabel).find(n=>n.type==="input");
assert.equal(impedanceInput.props.value,"75");
impedanceInput.props.onChange({target:{value:"0"}});
tree=render();
nodes(tree).find(n=>n.type==="button"&&text(n)==="Run experimental SI channel").props.onClick();
tree=render();
assert.match(text(tree),/Reference impedance must be positive/);
assert.equal(capturedRequest,null,"Invalid impedance must block execution");
nodes(nodes(tree).find(n=>n.type==="label"&&text(n)==="Reference impedance (ohm)")).find(n=>n.type==="input").props.onChange({target:{value:"80"}});
tree=render();allowRequestCapture=true;
nodes(tree).find(n=>n.type==="button"&&text(n)==="Run experimental SI channel").props.onClick();
await Promise.resolve();
assert.equal(capturedRequest.reference_impedance_ohm,80,"Edited impedance must reach the actual request");
assert.ok(!("rise_time_s" in capturedRequest),"Pending rise time must not invent a waveform input");
props={...props,searchDraft:{id:"bad",signalNetId:"missing"}};
tree=render();assert.match(text(tree), /requested SI net no longer exists/);
assert.ok(!nodes(tree).some(n=>n.type==="select"&&["s","g"].includes(n.props.value)), "Rejected IDs cannot silently choose defaults");
props={...props,canonicalDesign:{...design,design_id:"other"}};
tree=render();assert.match(text(tree), /Board context changed/);
assert.ok(!nodes(tree).some(n=>n.type==="select"&&["s","g"].includes(n.props.value)));
console.log("SI reviewed draft: identity, frequencies, explicit layer/endpoints, rejected IDs, board changes and no solver execution passed.");
