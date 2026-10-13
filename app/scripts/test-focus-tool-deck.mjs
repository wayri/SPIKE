// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { unlinkSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
const output=fileURLToPath(new URL(".focus-tool-deck-test.mjs",import.meta.url));
try {
  await build({entryPoints:[fileURLToPath(new URL("../src/FocusToolDeck.tsx",import.meta.url))],outfile:output,bundle:true,platform:"node",format:"esm",external:["react","react-dom","lucide-react"],logLevel:"silent"});
  const {default:Deck,activeFocusPanel}=await import(pathToFileURL(output).href);
  const panels=[
    {id:"layers",title:"Layers",open:true,content:React.createElement("input",{defaultValue:"retained layer draft"})},
    {id:"study",title:"Study",open:true,content:React.createElement("input",{defaultValue:"retained study draft"})},
    {id:"closed",title:"Closed",open:false,content:"closed tool"},
    {id:"managers",aliases:["nets","links"],title:"Managers",open:true,content:"occurrence controls"},
  ];
  assert.equal(activeFocusPanel(panels,null),undefined,"hiding returns the full viewport rather than resurrecting a previous panel");
  assert.equal(activeFocusPanel(panels,"closed"),undefined,"closed tools cannot remain visible");
  assert.equal(activeFocusPanel(panels,"links").id,"managers","an occurrence manager is activated by any of its domain routes");
  assert.equal(activeFocusPanel(panels,"study").title,"Study");
  for(const id of ["layers","study",null]) {
    const html=renderToStaticMarkup(React.createElement(Deck,{panels,activeId:id,commandsOpen:false,onActivate:()=>{}}));
    assert.ok(html.includes("retained layer draft")&&html.includes("retained study draft"),"switching or hiding tools retains mounted editor inputs");
    assert.ok(!html.includes("closed tool"),"closed tools are unmounted normally");
    const sections=[...html.matchAll(/<section[^>]*class="focus-tool-content"([^>]*)>/g)];
    assert.equal(sections.filter(match=>!match[1].includes("hidden")).length,id?1:0,"only one tool surface is visible");
  }
  const menu=renderToStaticMarkup(React.createElement(Deck,{panels,activeId:"layers",commandsOpen:true,onActivate:()=>{}}));
  assert.match(menu,/<aside[^>]+hidden=""/,"commands reserve the same slot and hide the active tool");
  console.log("Focus panel admission, one-visible-slot, hidden input retention and manager aliases passed");
} finally { try { unlinkSync(output); } catch {} }
