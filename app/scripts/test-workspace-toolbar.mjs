// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const states=[],refs=[],effectSlots=[],pendingEffects=[];let stateIndex=0,refIndex=0,effectIndex=0;
const useState=initial=>{const index=stateIndex++;if(!(index in states))states[index]=initial;return[states[index],value=>{states[index]=typeof value==="function"?value(states[index]):value;}];};
const useRef=initial=>{const index=refIndex++;return refs[index]??=( {current:initial} );};
const useEffect=(effect,deps)=>{const index=effectIndex++,previous=effectSlots[index],changed=!previous||!deps||deps.some((value,at)=>!Object.is(value,previous.deps?.[at]));if(changed)pendingEffects.push(()=>{previous?.cleanup?.();effectSlots[index]={deps,cleanup:effect()};});};
const listeners=new Map();
globalThis.document={addEventListener:(type,listener)=>listeners.set(type,listener),removeEventListener:(type,listener)=>{if(listeners.get(type)===listener)listeners.delete(type);}};
globalThis.requestAnimationFrame=callback=>{callback(0);return 1;};
let id=0;
const jsx=(type,props)=>({type,props:props??{}}),module={exports:{}};
const source=readFileSync(new URL("../src/WorkspaceToolbar.tsx",import.meta.url),"utf8");
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
new Function("require","module","exports",compiled)(name=>name==="react/jsx-runtime"?{jsx,jsxs:jsx}:name==="react"?{useState,useRef,useEffect,useId:()=>`workspace-${++id}`}:name==="./icons"?{Grid3X3:"Grid3X3",ArrowLeft:"ArrowLeft",ChevronRight:"ChevronRight",MousePointer2:"MousePointer2"}:{},module,module.exports);

const calls=[],Icon="Icon",content={type:"existing-form",props:{id:"solver-form"}};
const props={workspaces:[{name:"PCB",icon:Icon},{name:"Thermal",icon:Icon},{name:"Results",icon:Icon}],activeWorkspace:"Thermal",onWorkspace:name=>calls.push(["workspace",name]),actions:[
  {id:"setup",label:"Setup",content},
  {id:"run",label:"Run",icon:Icon,run:()=>calls.push(["action","run"])},
  {id:"advanced",label:"Advanced",icon:Icon,onEnter:()=>calls.push(["enter","advanced"]),children:[
    {id:"advanced-setup",label:"Advanced setup",content:{type:"advanced-form",props:{id:"advanced-form"}}},
    {id:"overlay",label:"Overlay",icon:Icon,checked:true,run:()=>calls.push(["action","overlay"])},
    {id:"disabled",label:"Disabled",icon:Icon,disabled:true,run:()=>calls.push(["action","disabled"])}
  ]}
]};
const flatten=node=>!node||typeof node!=="object"?[]:[node,...[node.props?.children].flat(Infinity).flatMap(flatten)];
const insideTarget={},focusCount=new Map(),domButtons=new Map();
const focused=label=>focusCount.set(label,(focusCount.get(label)??0)+1);
const rootElement={contains:target=>target===insideTarget,querySelector:selector=>selector.includes("workspace-toolbar-command")?[...domButtons.values()].find(item=>item.command&&!item.back&&!item.disabled)??null:null,querySelectorAll:()=>[...domButtons.values()].filter(item=>item.command&&!item.disabled)};
const mountRefs=tree=>{domButtons.clear();for(const node of flatten(tree)){const ref=node.props?.ref;if(!ref)continue;if(node===tree){ref.current=rootElement;continue;}const label=node.props?.["aria-label"]??"unknown",classes=(node.props.className??"").split(/\s+/),element={focus:()=>focused(label),command:classes.includes("workspace-toolbar-command"),back:classes.includes("workspace-toolbar-back"),disabled:Boolean(node.props.disabled)};domButtons.set(label,element);if(typeof ref==="function")ref(element);else ref.current=element;}};
const render=()=>{stateIndex=0;refIndex=0;effectIndex=0;const tree=module.exports.default(props);mountRefs(tree);pendingEffects.splice(0).forEach(run=>run());return tree;};

let tree=render(),nodes=flatten(tree),trigger=nodes.find(node=>node.props?.["aria-label"]==="Switch workspace");
assert.equal(trigger.props["aria-expanded"],false);assert.equal(trigger.props["aria-pressed"],false);
tree.props.onMouseEnter();tree=render();nodes=flatten(tree);
assert.ok(nodes.find(node=>node.props?.["aria-label"]==="Workspace switcher"),"hover opens the horizontal flyout");
const workspaceButtons=nodes.filter(node=>(node.props?.className??"").split(/\s+/).includes("workspace-toolbar-workspace"));
assert.deepEqual(workspaceButtons.map(button=>[button.props["aria-label"],button.props["aria-pressed"],button.props.tabIndex]),[["PCB workspace",false,-1],["Thermal workspace",true,0],["Results workspace",false,-1]]);
workspaceButtons[2].props.onClick();assert.deepEqual(calls,[["workspace","Results"]]);
assert.equal(nodes.find(node=>node===content),content,"existing command content is retained in the flyout");
nodes.find(node=>node.props?.["aria-label"]==="Run").props.onClick();await Promise.resolve();assert.deepEqual(calls.at(-1),["action","run"]);
const advanced=nodes.find(node=>node.props?.["aria-label"]==="Advanced");assert.equal(advanced.props["aria-haspopup"],"menu");advanced.props.onClick();await Promise.resolve();tree=render();nodes=flatten(tree);
assert.deepEqual(calls.at(-1),["enter","advanced"],"submenu invokes its existing onEnter handler");
assert.equal(focusCount.get("Overlay"),1,"entering a submenu focuses its first enabled action");
assert.ok(nodes.find(node=>node.props?.["aria-label"]==="Back to previous actions"));
assert.equal(nodes.find(node=>node.props?.["aria-label"]==="Overlay").props["aria-pressed"],true);
assert.equal(nodes.find(node=>node.props?.["aria-label"]==="Disabled").props.disabled,true);
assert.ok(nodes.find(node=>node.type==="advanced-form"),"nested existing content renders in place");
props.actions=[...props.actions];tree=render();nodes=flatten(tree);
assert.ok(nodes.find(node=>node.props?.["aria-label"]==="Overlay"),"a parent rerender with a new action-array identity preserves the open submenu");
assert.ok(nodes.find(node=>node.type==="advanced-form"),"existing nested content stays mounted after the parent rerender");
nodes.find(node=>node.props?.["aria-label"]==="Overlay").props.onClick();await Promise.resolve();assert.deepEqual(calls.at(-1),["action","overlay"]);
let nestedPrevented=false;nodes.find(node=>node.props?.["aria-label"]==="Overlay").props.onKeyDown({key:"Escape",currentTarget:domButtons.get("Overlay"),preventDefault:()=>{nestedPrevented=true;}});tree=render();assert.ok(flatten(tree).find(node=>node.props?.["aria-label"]==="Advanced"));assert.equal(nestedPrevented,true);assert.equal(focusCount.get("Advanced"),1,"Escape from nested actions restores focus to their parent command");

tree.props.onMouseLeave();tree=render();assert.equal(flatten(tree).some(node=>node.props?.["aria-label"]==="Workspace switcher"),false,"un-pinned flyout closes on boundary leave");
nodes=flatten(tree);trigger=nodes.find(node=>node.props?.["aria-label"]==="Switch workspace");trigger.props.onClick();tree=render();nodes=flatten(tree);trigger=nodes.find(node=>node.props?.["aria-label"]==="Switch workspace");
assert.equal(trigger.props["aria-pressed"],true,"click pins the flyout");tree.props.onMouseLeave();tree=render();assert.ok(flatten(tree).find(node=>node.props?.["aria-label"]==="Workspace switcher"),"pinned flyout survives pointer leave");
assert.equal(typeof listeners.get("pointerdown"),"function","pinned state installs its outside-pointer listener");
listeners.get("pointerdown")({target:insideTarget});tree=render();assert.ok(flatten(tree).find(node=>node.props?.["aria-label"]==="Workspace switcher"),"pointer input inside the pinned boundary keeps it open");
listeners.get("pointerdown")({target:{}});tree=render();assert.equal(flatten(tree).some(node=>node.props?.["aria-label"]==="Workspace switcher"),false,"outside pointer closes pinned state");

nodes=flatten(tree);trigger=nodes.find(node=>node.props?.["aria-label"]==="Switch workspace");let prevented=false;
trigger.props.onKeyDown({key:"ArrowDown",preventDefault:()=>{prevented=true;}});tree=render();nodes=flatten(tree);
assert.equal(prevented,true);assert.equal(nodes.find(node=>node.props?.["aria-label"]==="Switch workspace").props["aria-pressed"],true,"keyboard opening pins the flyout");
assert.equal(typeof listeners.get("keydown"),"function","keyboard-open pinned state installs its Escape listener");
listeners.get("keydown")({key:"Escape"});tree=render();assert.equal(flatten(tree).some(node=>node.props?.["aria-label"]==="Workspace switcher"),false,"document Escape closes a keyboard-open pinned flyout");
assert.ok((focusCount.get("Switch workspace")??0)>0,"document Escape restores focus to the workspace trigger");
nodes=flatten(tree);trigger=nodes.find(node=>node.props?.["aria-label"]==="Switch workspace");trigger.props.onClick();tree=render();nodes=flatten(tree);nodes.find(node=>node.props?.["aria-label"]==="Switch workspace").props.onClick();tree=render();assert.equal(flatten(tree).some(node=>node.props?.["aria-label"]==="Workspace switcher"),false,"a second trigger click closes pinned state");

const css=readFileSync(new URL("../src/WorkspaceToolbar.css",import.meta.url),"utf8");assert.match(css,/max-width:min\(1040px,calc\(100vw - 16px\)\)/);assert.match(css,/var\(--spike-popup-surface\)/);assert.match(css,/@media\(max-width:720px\)/);
console.log("Workspace toolbar: hover/pin, outside pointer and Escape dismissal, routing, stable command nesting/content, disabled/current states and responsive token styling passed.");
