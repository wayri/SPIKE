// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {importTestTypescript} from "./import-test-typescript.mjs";
const {buildStudioFeedbackRequest,defaultStudioFeedback}=await importTestTypescript("studioFeedback");
const {studioBindingFingerprint}=await importTestTypescript("studioBoardCircuit");
const workspace={models:[{id:"r",kind:"primitive",primitive:"resistor",value:"10",pins:["1","2"]}],assignments:[{id:"a",component_ref:"R1",model_id:"r",enabled:true,pin_bindings:[]}]},board={components:[{id:"component-1",ref:"R1"}]},preview={status:"ready",netlist:"Rload a 0 10",element_aliases:{R1:"Rload"}};
const binding={reference:"R1",capacitance:"2",thermalResistance:"4",tcr:"0.004",referenceTemperature:"293.15",initialTemperature:"298.15",minimumTemperature:"273.15",maximumTemperature:"423.15",confirmed:true,confirmation:studioBindingFingerprint(workspace,"R1")};
const setup={...defaultStudioFeedback(),ambient:"298.15",bindings:[binding],losslessConfirmed:true},revision="a".repeat(64);
const request=buildStudioFeedbackRequest(board,workspace,preview,revision,setup);
assert.equal(request.bindings[0].element_id,"Rload");assert.equal(request.bindings[0].component_id,"component-1");assert.equal(request.thermal.links[0].to_id,"ambient");assert.equal(request.thermal.nodes[0].capacitance_j_per_k,2);
assert.throws(()=>buildStudioFeedbackRequest(board,workspace,preview,revision,{...setup,ambient:""}),/required/);
assert.throws(()=>buildStudioFeedbackRequest(board,workspace,preview,revision,{...setup,losslessConfirmed:false}),/Confirm/);
assert.throws(()=>buildStudioFeedbackRequest(board,{...workspace,models:[{...workspace.models[0],value:"20"}]},preview,revision,setup),/Confirm/);
assert.throws(()=>buildStudioFeedbackRequest(board,workspace,{...preview,element_aliases:{}},revision,setup),/Confirm/);
const geom={length:"0.02",width:"0.001",thickness:"0.000035",resistivity:"1.7e-8",expansion:"0.000017"};
assert.equal(buildStudioFeedbackRequest(board,workspace,preview,revision,{...setup,bindings:[{...binding,geometry:geom}]}).bindings[0].geometry.thickness_m,0.000035);
assert.throws(()=>buildStudioFeedbackRequest(board,workspace,preview,revision,{...setup,bindings:[{...binding,capacitance:"-1"}]}),/positive/);
console.log("Studio feedback board identity, aliases, units, explicit confirmations, invalidation and geometry request checks passed");
