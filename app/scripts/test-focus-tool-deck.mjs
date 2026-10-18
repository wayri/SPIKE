// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { readFileSync, unlinkSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
const output=fileURLToPath(new URL(".focus-tool-deck-test.mjs",import.meta.url));
try {
  await build({entryPoints:[fileURLToPath(new URL("../src/FocusToolDeck.tsx",import.meta.url))],outfile:output,bundle:true,platform:"node",format:"esm",external:["react","react-dom","lucide-react"],logLevel:"silent"});
  const {default:Deck,activeFocusPanel,normalizeFocusPanelWidth,FOCUS_PANEL_DEFAULT_WIDTH}=await import(pathToFileURL(output).href);
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
  assert.equal(normalizeFocusPanelWidth("not-a-width"),FOCUS_PANEL_DEFAULT_WIDTH,"invalid saved widths recover to the compact default");
  assert.equal(normalizeFocusPanelWidth(40),280,"tool panels cannot collapse below an editable width");
  assert.equal(normalizeFocusPanelWidth(2400),720,"tool panels cannot consume an unbounded workspace width");
  for(const id of ["layers","study",null]) {
    const html=renderToStaticMarkup(React.createElement(Deck,{panels,activeId:id,commandsOpen:false,onActivate:()=>{}}));
    assert.ok(html.includes("retained layer draft")&&html.includes("retained study draft"),"switching or hiding tools retains mounted editor inputs");
    assert.ok(!html.includes("closed tool"),"closed tools are unmounted normally");
    const sections=[...html.matchAll(/<div[^>]*class="floating-panel-frame"([^>]*)>/g)];
    assert.equal(sections.filter(match=>!match[1].includes("hidden")).length,id?1:0,"only one tool surface is visible");
  }
  const menu=renderToStaticMarkup(React.createElement(Deck,{panels,activeId:"layers",commandsOpen:true,onActivate:()=>{}}));
  assert.match(menu,/<aside[^>]+hidden=""/,"commands reserve the same slot and hide the active tool");
  const active=renderToStaticMarkup(React.createElement(Deck,{panels,activeId:"layers",commandsOpen:false,onActivate:()=>{}}));
  assert.match(active,/aria-label="Resize tool panel"/,"the panel edge exposes a named resize control");
  assert.match(active,/lucide-grip-vertical/,"the resize edge has a visible affordance");
  assert.match(active,/aria-label="Expand tool panel"/,"workspace expansion stays in the panel header");
  assert.match(active,/aria-label="Hide panel"/,"the panel can be dismissed without using an embedded editor control");
  const layout=readFileSync(fileURLToPath(new URL("../src/FocusWorkspace.css",import.meta.url)),"utf8");
  assert.match(layout,/focus-panel-open\s*\{[^}]*grid-template-columns:[^;]*clamp\(280px,[^;]*720px/s,"the dock keeps an editable minimum while bounding its share of the viewport");
  assert.match(layout,/\.focus-panel-resizer\s*\{[^}]*width:\s*14px;[^}]*transform:\s*translate\(-50%,-50%\)/s,"the resize handle is visible on the panel boundary");
  assert.match(layout,/\.focus-tool-content\s+:is\(input,select,textarea\):focus-visible\s*\{[^}]*outline:/s,"embedded editors retain an explicit keyboard focus indication");
  console.log("Focus panel admission, bounded width, visible panel controls, one-visible-slot, hidden input retention and manager aliases passed");
} finally { try { unlinkSync(output); } catch {} }
