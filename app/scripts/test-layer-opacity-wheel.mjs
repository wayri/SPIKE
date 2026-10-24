// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
let harness;
const react = {
  useRef: initial => { const i=harness.index++; return harness.slots[i] ??= {current:initial}; },
  useState: initial => { const h=harness,i=h.index++; if(!(i in h.slots))h.slots[i]=initial; return [h.slots[i],next=>{h.slots[i]=typeof next==="function"?next(h.slots[i]):next;}]; },
  useId: ()=>"choices",
  useEffect: (fn,deps)=>{const h=harness,i=h.index++,old=h.effects[i]; if(!old||deps.some((x,k)=>x!==old.deps[k]))h.pending.push(()=>{old?.cleanup?.();h.effects[i]={deps,cleanup:fn()};});},
};
const jsx=(type,props)=>({type,props:props??{}}), module={exports:{}};
const code=ts.transpileModule(readFileSync(new URL("../src/ViewportLayerSelector.tsx",import.meta.url),"utf8"),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
new Function("require","module","exports",code)(name=>name==="react"?react:name==="react/jsx-runtime"?{jsx,jsxs:jsx}:name==="./icons"?{}:name==="./layerPalette"?{layerCssColor:()=>"red"}:{},module,module.exports);
const {default:Selector,wheelLayerOpacity}=module.exports;
const nodes=n=>!n||typeof n!=="object"?[]:[n,...[n.props?.children].flat(Infinity).flatMap(nodes)];
const text=n=>typeof n==="string"||typeof n==="number"?String(n):Array.isArray(n)?n.map(text).join(""):n?text(n.props?.children):"";
const nativeTimeout=globalThis.setTimeout,nativeClear=globalThis.clearTimeout;
let now=0,nextId=0;const clock=new Map();
globalThis.setTimeout=(fn,ms)=>{const id=++nextId;clock.set(id,{fn,at:now+ms});return id;};
globalThis.clearTimeout=id=>clock.delete(id);
const advance=ms=>{now+=ms;for(const [id,t]of [...clock])if(t.at<=now){clock.delete(id);t.fn();}};
try {
  harness={index:0,slots:[],effects:[],pending:[]};
  const calls=[],listeners=new Map();let rendered=[],boundRootRef;
  const root={addEventListener:(name,fn,options)=>{assert.equal(options.passive,false,"wheel must cancel browser zoom/scroll");listeners.set(name,fn);},removeEventListener:(name,fn)=>{if(listeners.get(name)===fn)listeners.delete(name);},contains:button=>rendered.includes(button)};
  let props={board:{id:"A",name:"Board A",layers:["F.Cu","B.Cu","Board body"],visibility:{"B.Cu":false},opacity:{"F.Cu":1,"B.Cu":.3,"Board body":.8}},selectedBoardIds:["A"],onToggle(){},onShowAll(){},onManage(){},onOpacity:(...a)=>calls.push(["one",...a]),onAllOpacity:(...a)=>calls.push(["all",...a])};
  const render=()=>{harness.index=0;const tree=Selector(props);if(tree?.props.ref){boundRootRef=tree.props.ref;boundRootRef.current=root;}else if(boundRootRef)boundRootRef.current=null;rendered=nodes(tree).filter(n=>n.type==="button");for(const fn of harness.pending.splice(0))fn();return tree;};
  const button=layer=>rendered.find(n=>n.props["data-layer-opacity"]===(layer==="All"?"all":"layer")&&(layer==="All"||n.props["data-layer-name"]===layer));
  const wheel=(layer,deltaY,extra={})=>{const node=button(layer);assert.ok(node);node.dataset={layerOpacity:node.props["data-layer-opacity"],layerName:node.props["data-layer-name"]};node.disabled=node.props.disabled;let prevented=false,stopped=false;listeners.get("wheel")?.({target:{closest:()=>node},deltaY,preventDefault(){prevented=true;},stopPropagation(){stopped=true;},...extra});return {prevented,stopped};};
  render().props.onMouseEnter();render();
  assert.deepEqual(wheel("F.Cu",100),{prevented:true,stopped:true});render();assert.deepEqual(calls.at(-1),["one","A","F.Cu",.95]);
  assert.ok(text(button("F.Cu")).includes("95"));advance(500);
  wheel("F.Cu",100);render();assert.deepEqual(calls.at(-1),["one","A","F.Cu",.9],"rapid wheels accumulate before owner props catch up");
  props={...props,board:{...props.board,opacity:{...props.board.opacity,"F.Cu":.9}}};render();
  advance(999);render();assert.ok(nodes(button("F.Cu")).some(n=>n.props.className==="viewport-layer-percent"));advance(1);render();assert.ok(!nodes(button("F.Cu")).some(n=>n.props.className==="viewport-layer-percent"),"name restored exactly one second after final wheel");
  wheel("All",100);render();assert.deepEqual(calls.at(-1),["all","A",.95],"mixed opacities reset to the All master");
  wheel("B.Cu",100);render();assert.deepEqual(calls.at(-1),["one","A","B.Cu",.9],"hidden layer uses immediately applied All value without changing visibility");
  wheel("All",-100);render();assert.deepEqual(calls.at(-1),["all","A",1]);
  const count=calls.length;for(const extra of [{ctrlKey:true},{metaKey:true}])assert.equal(wheel("All",-100,extra).prevented,false);wheel("All",0);wheel("All",NaN);assert.equal(calls.length,count);
  props={...props,disabled:true};render();wheel("All",100);assert.equal(calls.length,count,"read-only selector cannot change opacity");
  props={...props,disabled:false,board:{...props.board,id:"B",name:"Board B",opacity:{"F.Cu":.2}},selectedBoardIds:["B"]};render().props.onMouseEnter();render();assert.equal(clock.size,0,"board switch cancels old feedback timers");
  wheel("F.Cu",-100);render();assert.deepEqual(calls.at(-1),["one","B","F.Cu",.25]);
  assert.deepEqual(props.board.visibility,{"B.Cu":false});
  props={...props,selectedBoardIds:["A","B"]};assert.equal(render(),null);assert.equal(listeners.size,0,"multiselect removes wheel listener");
  for(const effect of harness.effects)effect?.cleanup?.();assert.equal(clock.size,0,"unmount cancels feedback timers");
  assert.equal(wheelLayerOpacity(1,-1),1);assert.equal(wheelLayerOpacity(0,1),0);assert.equal(wheelLayerOpacity(.05,1),0);assert.equal(wheelLayerOpacity(.95,-1),1);
  console.log("Layer wheel: direction, 0–100 bounds, rapid accumulation, exact 1s debounce, All reset, disabled/modifier guards, scope switch and cleanup passed.");
} finally {globalThis.setTimeout=nativeTimeout;globalThis.clearTimeout=nativeClear;}
