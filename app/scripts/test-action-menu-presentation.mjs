// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import ts from "typescript";
const module={exports:{}};
globalThis.document={activeElement:null,body:{id:"main-body"},addEventListener(){},removeEventListener(){}};
globalThis.window={innerWidth:800,innerHeight:600,addEventListener(){},removeEventListener(){}};
const detachedDocument={activeElement:null,body:{id:"detached-body"},addEventListener(){},removeEventListener(){}};
const detachedWindow={innerWidth:640,innerHeight:480,addEventListener(){},removeEventListener(){}};
let portalTarget;
const jsx={jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
const source=readFileSync(new URL("../src/ActionContextMenu.tsx",import.meta.url),"utf8");
new Function("require","module","exports",ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText)(
 name=>name==="react"?{useRef:x=>({current:x}),useEffect(){}}:name==="react-dom"?{createPortal:(x,target)=>{portalTarget=target;return x;}}:name==="./panelPresentation"?{usePanelPresentation:()=>({ownerDocument:detachedDocument,ownerWindow:detachedWindow,detached:true})}:name==="react/jsx-runtime"?jsx:{Check:"Check",MousePointer2:"Pointer"},module,module.exports);
let chosen=0,closed=0;
const tree=module.exports.default({x:1,y:1,title:"Navigate",actions:[
 {label:"Orbit",icon:"OrbitIcon",description:"Left drag · Shift + left drag to pan",section:"Drag mode",checked:true,radio:true,run:()=>chosen++},
 {label:"Pan",icon:"HandIcon",section:"Drag mode",checked:false,radio:true,run(){}},
 {label:"Axes",icon:"GridIcon",section:"View options",checked:false,run(){}},
],onClose:()=>closed++});
const nodes=tree=>!tree||typeof tree!=="object"?[]:[tree,...[tree.props?.children].flat(Infinity).flatMap(nodes)];
const buttons=nodes(tree).filter(x=>x.type==="button");
const actionButton=(role,label)=>buttons.find(button=>button.props.role===role&&nodes(button).some(node=>node.props?.children===label));
const orbit=actionButton("menuitemradio","Orbit"),pan=actionButton("menuitemradio","Pan"),axes=actionButton("menuitemcheckbox","Axes");
const closeButton=buttons.find(button=>button.props["aria-label"]==="Close Navigate");
assert.equal(portalTarget,detachedDocument.body,"context menu portal follows its detached panel document");
assert.ok(orbit,"Orbit is a named radio menu item");assert.equal(orbit.props["aria-checked"],true);
assert.ok(pan,"Pan is a named radio menu item");assert.equal(pan.props["aria-checked"],false);
assert.ok(axes,"Axes is a named checkbox menu item");assert.equal(axes.props["aria-checked"],false);
assert.ok(closeButton,"menu has a named close control");closeButton.props.onClick();assert.equal(closed,1);assert.equal(chosen,0);
assert(nodes(tree).some(x=>x.type==="OrbitIcon"));assert(nodes(tree).some(x=>x.type==="HandIcon"));assert(nodes(tree).some(x=>x.type==="GridIcon"));
assert.equal(nodes(tree).filter(x=>x.props?.className==="action-menu-section").length,2);
assert(nodes(tree).some(x=>x.type==="small"&&x.props.children.includes("Shift")));
orbit.props.onClick();assert.equal(chosen,1);assert.equal(closed,2);
console.log("Navigation menu icons, radio/checkbox states, grouped actions, gesture hints and callbacks passed.");
