// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { readFileSync, unlinkSync } from "node:fs";
import { fileURLToPath,pathToFileURL } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import postcss from "postcss";
const output=fileURLToPath(new URL(".floating-panel-test.mjs",import.meta.url));
try {
 await build({entryPoints:[fileURLToPath(new URL("../src/FloatingPanel.tsx",import.meta.url))],outfile:output,bundle:true,platform:"node",format:"esm",external:["react","react-dom","lucide-react"],logLevel:"silent"});
 const {default:FloatingPanel,FloatingPanelControls,normalizePanelScale,panelDragLeavesWindow}=await import(pathToFileURL(output).href);
 assert.equal(normalizePanelScale(NaN),1);assert.equal(normalizePanelScale(Infinity),1);
 assert.equal(normalizePanelScale(.1),.65);assert.equal(normalizePanelScale(10),1.5);assert.equal(normalizePanelScale(1.25),1.25);
 const viewport={width:1440,height:900};
 assert.equal(panelDragLeavesWindow({x:800,y:100},viewport),false);
 for(const point of [{x:-1,y:100},{x:1441,y:100},{x:100,y:-1},{x:100,y:901}])assert.equal(panelDragLeavesWindow(point,viewport),true);
 const originalStorage=Object.getOwnPropertyDescriptor(globalThis,"localStorage");
 try {
   for(const scale of [.65,.75,.9,1,1.1,1.25,1.5]) {
     Object.defineProperty(globalThis,"localStorage",{configurable:true,value:{getItem:()=>String(scale)}});
     const html=renderToStaticMarkup(React.createElement(FloatingPanel,{id:"scale-test",title:"Scale test",active:true},React.createElement(FloatingPanelControls)));
     assert.ok(html.includes(`<option value="${scale}" selected="">${Math.round(scale*100)}%</option>`),"every saved scale retains its complete selected percentage label");
     assert.match(html,/Choose 100% for the default size/,"the control explains how to restore the default scale");
   }
 } finally {
   if(originalStorage)Object.defineProperty(globalThis,"localStorage",originalStorage);else delete globalThis.localStorage;
 }
 const layout=postcss.parse(readFileSync(new URL("../src/FocusWorkspace.css",import.meta.url),"utf8"));
 // At the explicit 12px font, reserve a conservative 8px per label character,
 // 16px horizontal padding, 20px for the native chevron and 2px for borders.
 const minimumLabelWidth="150%".length*8+16+20+2;
 let scaleRules=0;
 layout.walkRules(rule=>{
   if(rule.selector!==".focus-panel-scale select")return;
   scaleRules++;
   rule.walkDecls(/^(?:width|min-width|max-width)$/,decl=>{
     if(decl.value==="none")return;
     assert.ok(Number.parseFloat(decl.value)>=minimumLabelWidth,"scale width cannot clip percentages or the native chevron, including narrow overrides");
   });
   assert.ok(rule.nodes.some(decl=>decl.prop==="appearance"&&decl.value==="auto"),"keep the native select chevron");
 });
 assert.ok(scaleRules>0,"the scale control has scoped sizing");
 console.log("Panel scale bounds and drag-to-detach boundary checks passed.");
 console.log("Panel scale selected labels, reset guidance and native-chevron width budget passed.");
}finally{try{unlinkSync(output);}catch{}}
