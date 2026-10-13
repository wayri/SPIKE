// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import ts from 'typescript';
const require = createRequire(import.meta.url), cache = new Map();
function load(name) {
 if (cache.has(name)) return cache.get(name).exports;
 const base = new URL(`../src/${name}`, import.meta.url), file = existsSync(base.pathname.replace(/^\/(\w:)/,'$1')+'.ts') ? new URL(base+'.ts') : new URL(base+'.tsx');
 const module = {exports:{}};cache.set(name,module);
 const code=ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 new Function('require','module','exports',code)(dep=>dep.startsWith('./')?load(dep.slice(2)):require(dep),module,module.exports);return module.exports;
}
const {mutateAssistantAssembly,assistantAssemblyContext}=load('assistantAssemblyTools');
const {validateAssistantToolCall}=load('assistantSkills');
const matrix=x=>[1,0,0,x,0,1,0,0,0,0,1,0,0,0,0,1];
const frame=(id,x=0)=>({frame_id:id,parent_frame_id:'root',units:'mm',handedness:'right',transform:matrix(x)});
const assembly={contract:'spike/assembly-ir/v1',assembly_id:'assembly',name:'Test',frame:{...frame('root'),parent_frame_id:null},boards:[{id:'A',design_id:'d',frame:frame('A')},{id:'B',design_id:'d',frame:frame('B',100)}],parts:[],harnesses:[],connector_mappings:[{id:'a-j',data:{board_id:'A',connector_id:'J1',pins:{1:'v'}}},{id:'b-j',data:{board_id:'B',connector_id:'J1',pins:{1:'v'}}}]};
const designs={contract:'spike/assembly-designs/v1',active_design_id:'d',designs:[{design_id:'d',nets:[{id:'v',name:'VCC'}]}]};
const original=JSON.stringify(assembly);
const added=mutateAssistantAssembly("assembly_add_occurrence",{designId:"d"},assembly,designs);assert.equal(added.assembly.boards.length,3);assert.equal(added.assembly.boards[2].design_id,"d");
assert.throws(()=>mutateAssistantAssembly("assembly_add_occurrence",{designId:"missing"},assembly,designs),/retained design/);
const dup=mutateAssistantAssembly('assembly_duplicate_occurrence',{boardId:'A'},assembly,designs);
assert.equal(dup.assembly.boards.length,3);assert.notEqual(dup.evidence.occurrenceId,'A');assert.equal(dup.assembly.boards[2].design_id,'d');assert.equal(JSON.stringify(assembly),original);
const placed=mutateAssistantAssembly('assembly_set_transform',{boardId:'A',transform:matrix(25)},assembly,designs);
assert.equal(placed.assembly.boards[0].frame.transform[3],25);assert.deepEqual(placed.assembly.boards[1],assembly.boards[1]);
const scale=matrix(0);scale[0]=2;assert.throws(()=>mutateAssistantAssembly('assembly_set_transform',{boardId:'A',transform:scale},assembly,designs),/Scale/);
const mirror=matrix(0);mirror[0]=-1;assert.throws(()=>mutateAssistantAssembly('assembly_set_transform',{boardId:'A',transform:mirror},assembly,designs),/Reflections/);
assert.throws(()=>mutateAssistantAssembly('assembly_set_transform',{boardId:'A',transform:matrix(1100)},assembly,designs),/1 m/);
const linked=mutateAssistantAssembly('assembly_link_connectors',{endpointA:'A::J1',pinA:'1',endpointB:'B::J1',pinB:'1'},assembly,designs);
assert.equal(linked.assembly.connector_mappings.length,3);
assert.throws(()=>mutateAssistantAssembly('assembly_link_connectors',{endpointA:'A::J1',pinA:'99',endpointB:'B::J1',pinB:'1'},assembly,designs),/retained pins/);
const removed=mutateAssistantAssembly('assembly_remove_occurrence',{boardId:'A'},linked.assembly,designs);assert.equal(removed.assembly.boards.length,1);assert.equal(removed.evidence.removedLinks,2);
assert.throws(()=>mutateAssistantAssembly('assembly_remove_occurrence',{boardId:'A'},{...assembly,thermal_contacts:[{id:'contact'}]},designs),/thermal contacts/);
const context=assistantAssemblyContext(assembly,designs,{offset:0,limit:1});assert.equal(context.boards.items.length,1);assert.equal(context.boards.more,true);
validateAssistantToolCall('spike_place_board',{boardId:'A',transform:matrix(0)});assert.throws(()=>validateAssistantToolCall('spike_place_board',{boardId:'A',transform:scale,path:'x'}),/unknown/);
assert.throws(()=>validateAssistantToolCall('spike_assembly',{limit:101}),/Invalid/);
console.log('Assistant assembly tools: occurrence identity, placement, links, dependencies and bounds passed.');
