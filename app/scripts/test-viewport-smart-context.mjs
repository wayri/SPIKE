// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {importTestTypescript} from "./import-test-typescript.mjs";
const {viewportSmartContext,viewportObjectSnapshot}=await importTestTypescript("viewportSmartContext");
const board={nets:{"1":"VCC"},tracks:[{id:"track",net:"VCC",layer:"F.Cu",start:[0,0],end:[3,4]}],pads:[{id:"pad",net:"VCC"}],vias:[],zones:[],components:[]};
const result={mode:"DC IR Drop",status:"ok",model_status:"approximate",provenance:{board_occurrence_id:"A"},scalar_fields:{voltage_v:[{value:3.2}],voltage_drop_v:[],current_a:[],current_density_a_mm2:[],power_loss_w:[],via_current_density_a_mm2:[],operating_point_impedance_ohm:[]},vector_fields:{electric_field:[],magnetic_field:[]},mesh:[]};
const base={object:{id:"track",type:"trace",name:"VCC",net:"VCC",layer:"F.Cu"},board,boardName:"board.kicad_pcb",workspace:"PI",mode:"DC IR Drop",solver:"auto",activeDesignId:"design",occurrences:[],result};
let context=viewportSmartContext(base);assert(context.ownsObject&&context.hasNet&&context.resultScoped);assert.match(context.summary.join(" "),/5.00 mm/);assert.deepEqual(context.modes,["voltage"]);
const occurrences=[{id:"A",designId:"design"},{id:"B",designId:"other-design"},{id:"C",designId:"design"}];
context=viewportSmartContext({...base,occurrences,object:{...base.object,occurrenceId:"B"}});assert(!context.ownsObject&&!context.hasNet&&!context.resultScoped);assert(context.boardReason);
context=viewportSmartContext({...base,occurrences,object:{...base.object,occurrenceId:"C"}});assert(context.ownsObject&&context.hasNet);assert(!context.resultScoped);assert.deepEqual(context.modes,[]);
context=viewportSmartContext({...base,occurrences,object:{...base.object,occurrenceId:"A"}});assert(context.resultScoped);
context=viewportSmartContext({...base,object:{...base.object,id:"stale-object"}});assert(!context.ownsObject&&!context.hasNet&&!context.resultScoped);
context=viewportSmartContext({...base,object:null,occurrences});assert(!context.hasNet&&!context.resultScoped);
context=viewportSmartContext({...base,board:null,result:null});assert(!context.ownsObject&&!context.hasNet&&!context.resultScoped);assert(context.boardReason&&context.resultReason);
console.log("Workspace context gates stale objects, cross-design edits and unbound assembly results; retains route units and actual result availability.");

const exactResult={...result,scalar_fields:{...result.scalar_fields,voltage_v:[{element_id:"track",net:"other",layer:"F.Cu",value:999},{element_id:"track",net:"VCC",layer:"F.Cu",x_mm:1,y_mm:2,value:3.2}]}};
const snapshot=viewportObjectSnapshot(base.object,board,exactResult,true);assert.equal(snapshot.geometry.length,5);assert.equal(snapshot.saved_base_samples[0].value,3.2);assert.equal(snapshot.saved_base_samples[0].unit,"V");assert.equal(viewportObjectSnapshot(base.object,board,exactResult,false).saved_base_samples.length,0);
