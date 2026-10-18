// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import ts from "typescript";
const require=createRequire(import.meta.url),cache=new Map();
let slots=[],cursor=0,effects=[];
const hooks={useState(initial){const i=cursor++;if(!(i in slots))slots[i]=typeof initial==="function"?initial():initial;return [slots[i],next=>slots[i]=typeof next==="function"?next(slots[i]):next];}};
function load(name){if(name.endsWith(".css"))return {};if(name==="react")return hooks;if(name==="./icons")return new Proxy({},{get:()=>()=>null});if(!name.startsWith("./"))return require(name);if(cache.has(name))return cache.get(name);const file=new URL(`../src/${name.slice(2)}${name.endsWith("Panel")?".tsx":".ts"}`,import.meta.url);const module={exports:{}};const code=ts.transpileModule(readFileSync(file,"utf8"),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX}}).outputText;new Function("require","module","exports",code)(load,module,module.exports);cache.set(name,module.exports);return module.exports;}
const {suggestWorkspaceIntents:suggest}=load("./workspaceIntentModel"),{default:Panel}=load("./WorkspaceIntentReviewPanel"),{canonicalIntentNet,thermalIntentScenario,studioIntentFeedback}=load("./workspaceIntentAdapters");
const context={version:"v1",nets:[{id:"s",name:"TX"},{id:"g",name:"GND"}],components:[{id:"u",name:"U1"},{id:"v",name:"U2"}],occurrences:[{id:"a",name:"Main"},{id:"b",name:"Shield"}]};
const nodes=tree=>!tree||typeof tree!=="object"?[]:[tree,...[tree.props?.children].flat(Infinity).flatMap(nodes)];
let props,applied;
function start(query,staleReason=""){slots=[];applied=null;props={suggestion:suggest(query,context)[0],context,staleReason,onApply:request=>applied=request,onClose(){}};assert.ok(props.suggestion,query);return render();}
function render(){cursor=0;return Panel(props);}
function field(tree,label){return nodes(tree).find(row=>row.props?.["aria-label"]===label);}
function apply(tree){const button=nodes(tree).filter(row=>row.type==="button").at(-1);assert.ok(button);if(!button.props.disabled)button.props.onClick();return button;}
let tree=start("run SI fstart=0Hz fstop=1GHz");assert.ok(apply(tree).props.disabled);
// Select exact roles: no need to add the same net again in the object chip list.
for(const [label,value]of [["Signal net","s"],["Return/reference net","g"]]){const select=nodes(tree).find(row=>row.type==="label"&&row.props.children?.[0]===label)?.props.children[1];assert.ok(select,label);select.props.onChange({target:{value}});tree=render();}
assert.equal(apply(tree).props.disabled,false);assert.deepEqual(applied.draft.bindings.netIds,["s","g"]);
tree=start("import touchstone");assert.equal(apply(tree).props.disabled,false);assert.equal(applied.choices.importKind,"touchstone");
tree=start("open assembly");assert.equal(apply(tree).props.disabled,false);
tree=start("run assembly CHT");assert.ok(apply(tree).props.disabled);assert.equal(applied,null);
tree=start("import step","Workspace changed");assert.ok(apply(tree).props.disabled);
tree=start("run thermal on U1 power=2W ambient=30C");assert.equal(apply(tree).props.disabled,false);assert.equal(applied.draft.parameters.powerW,2);
const component=id=>({id,ref:id==="u"?"U1":"U2",width:2,height:2,at:[3,4],layer:"F.Cu",value:"fixture"});
const board={nets:{s:"TX",g:"GND"},components:[component("u"),component("v")],stackup:[],bounds:{minX:0,minY:0}};
assert.equal(canonicalIntentNet("s",board,[{id:"canonical-s",name:"TX"}]),"canonical-s");
assert.throws(()=>canonicalIntentNet("s",board,[{id:"one",name:"TX"},{id:"two",name:"TX"}]),/ambiguous/);
const previous={heat_sources:[{id:"board-total",source_type:"board",power_w:8,theta_top_c_per_w:12,theta_bottom_c_per_w:14,thermal_capacitance_j_per_c:99}],thermal_elements:[{id:"saved-u",object_id:"u",reference:"U1",kind:"pcb_component",material_id:"copper",enabled:false,power_w:8}],thermal_links:[{id:"contact"}],result:{old:true},board_thermal_result:{old:true}};
const scenario=thermalIntentScenario(board,previous,applied);
assert.equal(scenario.heat_sources[0].theta_top_c_per_w,12);assert.equal(scenario.heat_sources[0].thermal_capacitance_j_per_c,99);assert.equal(scenario.heat_sources[0].power_w,0);assert.equal(scenario.board_fallback_power_w,0);assert.equal(scenario.ambient_temperature_c,30);assert.equal(scenario.result,undefined);assert.equal(scenario.board_thermal_result,undefined);assert.deepEqual(scenario.thermal_links,previous.thermal_links);
const heat=scenario.thermal_elements.find(row=>row.object_id==="u");assert.equal(heat.power_w,2);assert.equal(heat.enabled,true);assert.equal(heat.material_id,"copper");assert.equal(scenario.thermal_elements.find(row=>row.object_id==="v").power_w,0);assert.equal(previous.thermal_elements[0].power_w,8);
const multi={...applied,draft:{...applied.draft,bindings:{...applied.draft.bindings,componentIds:["u","v"]}},choices:{...applied.choices,componentPowersW:{u:1,v:2}}};assert.throws(()=>thermalIntentScenario(board,null,multi),/conserve/);
console.log("Workspace review: exact role selection, missing/stale/unsupported admission, importer routing, canonical identity, explicit thermal allocation and invalidation passed.");

const feedback={ambient:"",mode:"steady_state",stopTime:"1",window:"0.01",electricalStep:"0.001",bindings:[{reference:"R1",confirmed:true,confirmation:"old"}],losslessConfirmed:false};
const feedbackNext=studioIntentFeedback(feedback,{ambientC:25,durationS:2},false);assert.equal(feedbackNext.ambient,"298.15");assert.equal(feedbackNext.stopTime,"2");assert.equal(feedbackNext.mode,"transient");assert.equal(feedbackNext.bindings[0].confirmed,false);assert.equal(feedback.bindings[0].confirmed,true);assert.throws(()=>studioIntentFeedback(feedback,{ambientC:-274},false),/ambient/);

tree=start("run EM on net TX return GND fstart=1MHz fstop=1GHz");
const groundChip=nodes(tree).find(row=>row.type==="button"&&row.props.title==="GND");assert.ok(groundChip);groundChip.props.onClick();tree=render();assert.equal(apply(tree).props.disabled,false);assert.equal(applied.draft.roles.referenceNetId,undefined);assert.ok(!applied.draft.bindings.netIds.includes("g"));

tree=start("run RF on assembly fstart=0Hz fstop=1GHz");assert.ok(apply(tree).props.disabled);assert.equal(applied,null);
