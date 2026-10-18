// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { unlinkSync } from "node:fs";
import { fileURLToPath,pathToFileURL } from "node:url";
const output=fileURLToPath(new URL(".floating-panel-test.mjs",import.meta.url));
try {
 await build({entryPoints:[fileURLToPath(new URL("../src/FloatingPanel.tsx",import.meta.url))],outfile:output,bundle:true,platform:"node",format:"esm",external:["react","react-dom","lucide-react"],logLevel:"silent"});
 const {normalizePanelScale,panelDragLeavesWindow}=await import(pathToFileURL(output).href);
 assert.equal(normalizePanelScale(NaN),1);assert.equal(normalizePanelScale(Infinity),1);
 assert.equal(normalizePanelScale(.1),.65);assert.equal(normalizePanelScale(10),1.5);assert.equal(normalizePanelScale(1.25),1.25);
 const viewport={width:1440,height:900};
 assert.equal(panelDragLeavesWindow({x:800,y:100},viewport),false);
 for(const point of [{x:-1,y:100},{x:1441,y:100},{x:100,y:-1},{x:100,y:901}])assert.equal(panelDragLeavesWindow(point,viewport),true);
 console.log("Panel scale bounds and drag-to-detach boundary checks passed.");
}finally{try{unlinkSync(output);}catch{}}
