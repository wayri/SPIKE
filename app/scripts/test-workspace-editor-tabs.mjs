// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {build} from "esbuild";
import {unlinkSync} from "node:fs";
import {fileURLToPath,pathToFileURL} from "node:url";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
const output=fileURLToPath(new URL(".workspace-editor-tabs-test.mjs",import.meta.url));
try {
  await build({entryPoints:[fileURLToPath(new URL("../src/WorkspaceEditorTabs.tsx",import.meta.url))],outfile:output,bundle:true,platform:"node",format:"esm",external:["react","react-dom","lucide-react"],logLevel:"silent"});
  const {default:Tabs,workspaceEditorPanels}=await import(pathToFileURL(output).href);
  const panels=workspaceEditorPanels([
    {id:"topologyEditor",title:"Power & signal paths",open:true,content:"draft"},
    {id:"spiceOpen",title:"Circuit workspace",open:true,content:"circuit draft"},
    {id:"thermalOpen",title:"Thermal setup",open:false,content:"closed"},
    {id:"rightOpen",title:"Spatial selection",open:true,content:"selection"},
    {id:"assemblyManagers",aliases:["netManagerOpen"],title:"Board inputs",open:true,content:"draft"},
  ]);
  assert.equal(panels[0].presentation,"document");assert.equal(panels[3].presentation,"panel");
  const markup=renderToStaticMarkup(React.createElement(Tabs,{panels,activeId:"topologyEditor",onActivate:()=>{}}));
  assert.match(markup,/role="tab"[^>]*aria-selected="true"[^>]*>.*Power &amp; signal paths/);
  assert.ok(markup.includes("Circuit workspace"));assert.ok(!markup.includes("Thermal setup"));assert.ok(!markup.includes("Spatial selection"));
  const activated=[];const tree=Tabs({panels,activeId:"netManagerOpen",onActivate:id=>activated.push(id)});
  const list=tree.props.children,buttons=[list.props.children[0],...list.props.children[1]];
  assert.equal(buttons.at(-1).props["aria-selected"],true,"aliases select the existing document");
  buttons[0].props.onClick();buttons[2].props.onClick();assert.deepEqual(activated,[null,"spiceOpen"]);
  let focused=-1;const targets=buttons.map((button,index)=>({focus:()=>focused=index,click:button.props.onClick}));
  list.props.onKeyDown({key:"ArrowRight",target:targets.at(-1),currentTarget:{querySelectorAll:()=>targets},preventDefault(){}});
  assert.equal(focused,0,"arrow navigation wraps to the viewport tab");
  assert.equal(activated.at(-1),null);
  assert.equal(Tabs({panels:[],activeId:null,onActivate(){}}),null,"no empty document strip");
  assert.equal(panels[0].content,"draft","tab projection preserves original editor content");
  console.log("Workspace editor tabs: document/inspector routing, aliases, closed tabs, draft preservation, keyboard navigation and viewport return passed.");
} finally {for(const generated of [output,output.replace(/\.mjs$/, ".css")]){try{unlinkSync(generated);}catch{}}}
