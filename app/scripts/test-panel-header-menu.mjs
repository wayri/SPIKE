// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { unlinkSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
const output=fileURLToPath(new URL(".panel-header-menu-test.mjs",import.meta.url));
try {
  await build({entryPoints:[fileURLToPath(new URL("../src/PanelHeaderMenu.tsx",import.meta.url))],outfile:output,bundle:true,jsx:"transform",jsxFactory:"globalThis.testCreateElement",tsconfigRaw:{compilerOptions:{jsx:"react"}},platform:"node",format:"esm",logLevel:"silent",plugins:[{name:"hook-harness",setup(builder){
    builder.onResolve({filter:/^react$/},()=>({path:"react",namespace:"harness"}));
    builder.onLoad({filter:/.*/,namespace:"harness"},()=>({contents:'export const createContext=value=>({value}); export const useContext=context=>globalThis.inheritedActions??context.value; export const useState=()=>[globalThis.menuPoint??null,value=>globalThis.menuPoint=value]; export default {createElement:()=>null};'}));
    builder.onResolve({filter:/ActionContextMenu$/},()=>({path:"menu",namespace:"menu"}));
    builder.onLoad({filter:/.*/,namespace:"menu"},()=>({contents:'export default function Menu(){return null;}'}));
  }}]});
  globalThis.testCreateElement=(_type,props)=>({props});
  const {usePanelHeaderMenu}=await import(pathToFileURL(output).href);
  let runs=0;
  const {headerProps}=usePanelHeaderMenu("Study",[{label:"Close",run:()=>runs++}]);
  assert.equal(headerProps.tabIndex,0,"headers are keyboard reachable");
  const event={preventDefault(){this.prevented=true;},stopPropagation(){this.stopped=true;},currentTarget:{getBoundingClientRect:()=>({left:30,bottom:70})}};
  headerProps.onContextMenu({...event,clientX:90,clientY:120});
  assert.deepEqual(globalThis.menuPoint,{x:90,y:120},"right click anchors in the owning header's viewport");
  for(const keys of [{key:"ContextMenu"},{key:"F10",shiftKey:true}]){
    const input={...event,...keys};headerProps.onKeyDown(input);
    assert.deepEqual(globalThis.menuPoint,{x:42,y:70},"keyboard context menu anchors at header");
    assert.equal(input.prevented,true);assert.equal(input.stopped,true);
  }
  globalThis.menuPoint=null;headerProps.onKeyDown({...event,key:"F10",shiftKey:false});
  assert.equal(globalThis.menuPoint,null,"unmodified F10 keeps its existing behavior");
  assert.equal(runs,0,"opening the header menu never invokes an action");
  globalThis.menuPoint={x:10,y:20};
  const ownerClose={label:"Close",run:()=>runs++};
  globalThis.inheritedActions=[{label:"Hide",run:()=>{}},ownerClose];
  const merged=usePanelHeaderMenu("Inner Study",[{label:"Close",run:()=>{throw new Error("duplicate owner must not run");}},{label:"Export",run:()=>{}}]).menu.props.actions;
  assert.deepEqual(merged.map(action=>action.label),["Hide","Close","Export"],"inner headers inherit window actions without duplicate labels");
  assert.equal(merged[1],ownerClose,"inherited Close retains its owning cleanup workflow");
  merged[1].run();assert.equal(runs,1);
  delete globalThis.inheritedActions;delete globalThis.testCreateElement;
  delete globalThis.menuPoint;
  console.log("Panel header pointer and keyboard context menu activation passed.");
}finally{try{unlinkSync(output);}catch{}}


