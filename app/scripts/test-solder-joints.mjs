// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import * as THREE from "three";
import { importTestTypescript } from "./import-test-typescript.mjs";
const {resolveSolderJoints,normalizeSolderJointVisual,DEFAULT_SOLDER_JOINT_VISUAL,MAX_SOLDER_JOINTS}=await importTestTypescript("solderJointModel");
const {solderJointGeometry,buildSolderJointScene}=await importTestTypescript("solderJointScene");
const {disposeScene}=await importTestTypescript("sceneResourceCache");
const {bondsForSolver}=await importTestTypescript("componentBonding");
const {createProjectPackage,parseProjectPackage}=await importTestTypescript("projectPackage");
const pad={id:"pad-u1-1",ref:"U1",name:"1",net:"VCC",at:[12,30],width:2,height:1.2,rotation:30,drill:0,layers:["F.Cu"],layer:"F.Cu"};
const board={pads:[pad]};
const bond={id:"joint",padId:pad.id,reference:"U1",pad:"1",net:"VCC",connectedLayers:["F.Cu"],status:"ready",enabled:true,solderVisual:{...DEFAULT_SOLDER_JOINT_VISUAL},searchDistanceMm:.25,electricalResistanceOhm:.001,currentLimitA:1,thermalConductivityWmK:50,contactAreaMm2:1,bondMaterial:"Solder"};
assert.equal(normalizeSolderJointVisual({...bond.solderVisual,heightMm:Infinity}),null);
assert.equal(normalizeSolderJointVisual({...bond.solderVisual,spreadMm:-1}),null);
assert.equal(normalizeSolderJointVisual({...bond.solderVisual,visible:"true"}),null);
const resolve=(patch={},scope=undefined,multi=false)=>resolveSolderJoints(board,[{...bond,...patch}],scope,multi);
assert.equal(resolve().joints.length,1);assert.equal(resolve({enabled:false}).joints.length,0);
assert.equal(resolve({solderVisual:{...bond.solderVisual,visible:false}}).joints.length,0);
for(const patch of [{padId:"other"},{reference:"U2"},{net:"GND"},{pad:"2"}])assert.equal(resolve(patch).joints.length,0);
assert.equal(resolve({},"A",true).joints.length,0);assert.equal(resolve({boardInstanceId:"A"},"A",true).joints.length,1);assert.equal(resolve({boardInstanceId:"A"},"B",true).joints.length,0);
assert.equal(resolveSolderJoints({pads:[pad,{...pad,at:[90,90]}]},[bond]).joints.length,0,"Duplicate pad IDs are ambiguous even when declared explicitly");
const duplicate={pads:[pad,{...pad,id:"duplicate"}]};assert.equal(resolveSolderJoints(duplicate,[{...bond,padId:undefined}]).joints.length,0);
const count=resolveSolderJoints(board,Array.from({length:MAX_SOLDER_JOINTS+3},(_,i)=>({...bond,id:`joint-${i}`})));assert.equal(count.joints.length,MAX_SOLDER_JOINTS);assert.ok(count.issues.some(text=>text.includes("budget")));
for(const style of ["smd-fillet","through-hole","terminal"]){
 const drilled=style==="through-hole";
 const source={pads:[{...pad,...(drilled?{drill:.6,drill_size:[.6,.4],layers:["*.Cu"],type:"thru_hole"}:{})}]};
 const result=resolveSolderJoints(source,[{...bond,connectedLayers:drilled?["F.Cu","B.Cu"]:["F.Cu"],solderVisual:{...bond.solderVisual,style}}]);assert.equal(result.joints.length,drilled?2:1);
 for(const joint of result.joints){const geometry=solderJointGeometry(joint),positions=geometry.getAttribute("position"),normals=geometry.getAttribute("normal");assert.ok(geometry.index.count<=800);for(const value of positions.array)assert.ok(Number.isFinite(value));for(const value of normals.array)assert.ok(Number.isFinite(value));if(joint.side===-1)assert.ok(geometry.boundingBox.max.z<=0);else assert.ok(geometry.boundingBox.min.z>=0);if(drilled)for(let i=0;i<positions.count;i++)assert.ok((positions.getX(i)/.3)**2+(positions.getY(i)/.2)**2>=.999,"drill bore stays open");geometry.dispose();}
}
const joint=resolve().joints[0],matrix=new THREE.Matrix4().makeTranslation(12,30,1);
const group=buildSolderJointScene([{joint,matrix,opacity:1},{joint:{...joint,id:"second"},matrix:new THREE.Matrix4().makeTranslation(100,20,1),opacity:1}]);
assert.equal(group.children.length,1,"Identical shapes batch rather than adding one draw per pin");assert.equal(group.children[0].count,2);const out=new THREE.Matrix4();group.children[0].getMatrixAt(1,out);assert.equal(out.elements[12],100);
let disposed=0;group.children[0].geometry.addEventListener("dispose",()=>disposed++);group.children[0].material.addEventListener("dispose",()=>disposed++);disposeScene(group);assert.equal(disposed,2);
const before=bondsForSolver([bond]);const after=bondsForSolver([{...bond,solderVisual:{...bond.solderVisual,heightMm:3,opacity:.5}}]);assert.deepEqual(before,after,"Visual dimensions never become solver material/contact values");
const saved=createProjectPackage({project:{name:"solder.spike"},design:{source_board:"",component_bonds:[{...bond,boardInstanceId:"A"}]},analysis:{}});const reopened=parseProjectPackage(JSON.stringify(saved)).project;assert.deepEqual(reopened.design.component_bonds,saved.design.component_bonds);
console.log("Solder joints: identity/net/occurrence safety, bounds, open bores, front/back geometry, instancing/disposal, project roundtrip and unchanged solver payload passed.");
