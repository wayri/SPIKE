// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {spawnSync} from "node:child_process";
import {resolve} from "node:path";
import {importTestTypescript} from "./import-test-typescript.mjs";
const {extractStudioBoardCircuit,studioBindingFingerprint}=await importTestTypescript("studioBoardCircuit");
const board={width:20,height:10,components:[{id:"r1",ref:"R1",value:"10k",at:[5,5],rotation:90,layer:"F.Cu"},{id:"h1",ref:"H1",value:"Mount",at:[15,5],rotation:0,layer:"B.Cu"}],pads:[{id:"p1",ref:"R1",name:"1",at:[4,5],net:"1",type:"smd"},{id:"p2",ref:"R1",name:"2",at:[6,5],net:"2",type:"smd"}],nets:{1:"Supply rail",2:"GND"},tracks:[]};
const workspace={name:"Boundary fixture",ground_node:"GND",models:[{id:"r",kind:"primitive",primitive:"resistor",value:"10k",pins:["1","2"]}],assignments:[{id:"a",component_ref:"R1",model_id:"r",enabled:true,pin_bindings:[{model_pin:"2",pad_id:"p2",board_net:"GND",circuit_node:"GND"},{model_pin:"1",pad_id:"p1",board_net:"Supply rail",circuit_node:"Supply rail"}]}]};
const graph=extractStudioBoardCircuit(board,workspace,"a".repeat(64),"board-a",{R1:studioBindingFingerprint(workspace,"R1")});
const repository=resolve(import.meta.dirname,"../..");
const code=`import sys,json
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/"standalone/spikes_project/studio/python"))
from spikes_studio.studio_handoff import document_from_handoff
doc=document_from_handoff(json.load(sys.stdin))
print(json.dumps({"source":doc.data["source"],"parts":doc.data["components"]}))`;
const result=spawnSync(resolve(repository,process.platform==="win32"?".venv/Scripts/python.exe":".venv/bin/python"),["-B","-c",code],{cwd:repository,input:JSON.stringify(graph),encoding:"utf8",timeout:30000});
assert.equal(result.status,0,result.stderr);const document=JSON.parse(result.stdout);
assert.match(document.source,/R1 N_[a-f0-9]+ 0 10k/);assert.doesNotMatch(document.source,/H1 /);
const resistor=document.parts.find(part=>part.ref==="R1"),mount=document.parts.find(part=>part.ref==="H1");
assert.equal(resistor.execution.available,true);assert.equal(mount.execution.available,false);assert.deepEqual(resistor.board_placement,graph.components[0].placement);assert.equal(resistor.cross_selection_id,graph.components[0].cross_selection_id);
console.log("Actual frontend graph → Studio document: pin order, ground, unsafe label alias, placements and inert parts passed");
