// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";
const { assemblyNetLabels } = await importTestTypescript("assemblyNetLabels");
const { validAssemblyToolAction } = await importTestTypescript("assemblyToolWindowModel");
const board={bounds:{minX:0,minY:0,maxX:100,maxY:50},width:100,height:50,nets:{1:"VCC"},tracks:[{id:"t",net:"1",layer:"F.Cu",start:[5,10],end:[95,10],width:1}],zones:[]};
const a={id:"a",netIdsByName:{VCC:"net-a"},netNamesById:{"net-a":"VCC"}};
const b={...a,id:"b",netIdsByName:{VCC:"net-b"},netNamesById:{"net-b":"VCC"}};
const first=assemblyNetLabels(board,a,{}, {},.1);
assert.equal(first[0].net,"VCC"); assert.equal(first[0].occurrenceId,"a"); assert.equal(first[0].canonicalNetId,"net-a");
assert.equal(assemblyNetLabels(board,b,{}, {},.1)[0].canonicalNetId,"net-b");
assert.equal(assemblyNetLabels(board,a,{"F.Cu":false},{},.1).length,0);
assert.equal(assemblyNetLabels(board,a,{}, {"F.Cu":0},.1).length,0);
assert(assemblyNetLabels(board,a,{}, {},.1,1).length<=1);
assert(validAssemblyToolAction({type:"net-names",value:true}));
assert(!validAssemblyToolAction({type:"net-names",value:"true"}));
console.log("Assembly net label names, occurrence identities, hidden layers, budgets and toggle admission passed");
