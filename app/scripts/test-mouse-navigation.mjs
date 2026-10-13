// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import ts from "typescript";
import {PerspectiveCamera} from "three";
import {OrbitControls} from "three/examples/jsm/controls/OrbitControls.js";
const require=createRequire(import.meta.url);
const module={exports:{}};
const source=readFileSync(new URL("../src/viewportMouseNavigation.ts",import.meta.url),"utf8");
new Function("require","module","exports",ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(require,module,module.exports);
const {viewportMouseButtons}=module.exports;
const controls=new OrbitControls(new PerspectiveCamera());
let observed="";
controls._handleMouseDownPan=()=>{observed="pan";};
controls._handleMouseDownRotate=()=>{observed="orbit";};
for(const mode of ["orbit","pan"])for(const view of ["3D","2D"])for(const button of [0,1,2])for(const shiftKey of [false,true]){
 const event={button,shiftKey,ctrlKey:false,metaKey:false};
 controls.mouseButtons=viewportMouseButtons(mode,view,event);
 observed="";controls._onMouseDown(event);
 assert.equal(observed,shiftKey||view==="2D"||mode==="pan"||button!==0?"pan":"orbit",`${mode} ${view} button=${button} shift=${shiftKey}`);
}
for(const modifier of ["ctrlKey","metaKey"]) {
 const event={button:0,shiftKey:false,ctrlKey:false,metaKey:false,[modifier]:true};
 controls.mouseButtons=viewportMouseButtons("pan","2D",event);
 controls._onMouseDown(event);assert.equal(observed,"pan","2D modified drag must not activate disabled orbit");
}
for(const shiftKey of [true,false,true,false]){
 const event={button:0,shiftKey,ctrlKey:false,metaKey:false};
 controls.mouseButtons=viewportMouseButtons("orbit","3D",event);controls._onMouseDown(event);
 assert.equal(observed,shiftKey?"pan":"orbit","Shift only overrides the current drag");
}
const board=readFileSync(new URL("../src/BoardViewport.tsx",import.meta.url),"utf8");
assert(board.includes('addEventListener("pointerdown", prepareMouseNavigation, true)'));
assert(board.includes('removeEventListener("pointerdown", prepareMouseNavigation, true)'));
console.log("Actual OrbitControls drag dispatch: normal orbit, Shift-pan, Pan mode, 2D, all buttons and modifier release passed.");
