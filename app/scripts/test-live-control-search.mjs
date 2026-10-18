// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {liveControlSearch} from "../src/liveControlSearch.ts";
const frames=[], events=[], reveals=[];
const document={querySelectorAll:()=>controls,getElementById:()=>null,defaultView:{requestAnimationFrame:fn=>frames.push(fn),focus(){},Event}};
function control(tag,label,{disabled=false,hidden=null,slot=null,field=false,ignore=false}={}) {
 const attrs={"aria-label":label};
 return {tagName:tag,isConnected:true,ownerDocument:document,focusCount:0,clickCount:0,
 getAttribute:key=>attrs[key]??null,getClientRects:()=>[{}],
 closest:selector=>selector.includes('data-search-ignore')?(ignore?{}:null):selector.includes('data-panel-id')?slot:hidden,
 matches:selector=>selector===":disabled"?disabled:selector.startsWith("input")?field:selector.includes("button")&&tag==="BUTTON",
 focus(){this.focusCount++;},click(){this.clickCount++;},scrollIntoView(){},dispatchEvent(event){events.push(event.type);},
 };
}
const slot={dataset:{panelId:"thermalSetup"},getAttribute:()=>"Thermal setup"};
const hidden={matches:selector=>selector.includes("floating-panel-frame")};
const button=control("BUTTON","Run heat solve");
const blocked=control("BUTTON","Blocked run",{disabled:true});
const field=control("INPUT","Ambient temperature",{slot,hidden,field:true});
const ignored=control("BUTTON","Clear search",{ignore:true});
const select=control("SELECT","Cooling model",{field:true});
select.options=[{label:"Prescribed convection",hidden:false,disabled:false,parentElement:null},{label:"Coupled airflow",hidden:false,disabled:true,parentElement:null}];
let controls=[button,blocked,field,ignored,select];
const rows=liveControlSearch(document,id=>reveals.push(id));
assert(!rows.some(row=>row.label==="Clear search"));
assert(rows.find(row=>row.label==="Blocked run").disabled);
assert(rows.find(row=>row.label==="Cooling model: Coupled airflow").disabled);
assert.equal(button.clickCount,0,"Indexing must never activate a control");
rows.find(row=>row.label==="Run heat solve").run();
assert.equal(button.clickCount,0,"Actions wait until search releases focus");frames.shift()();assert.equal(button.clickCount,1);
rows.find(row=>row.label==="Edit Ambient temperature").run();assert.deepEqual(reveals,["thermalSetup"]);frames.shift()();assert.equal(field.focusCount,1);assert.equal(field.clickCount,0);
rows.find(row=>row.label==="Cooling model: Prescribed convection").run();frames.shift()();assert.equal(select.selectedIndex,0);assert.deepEqual(events,["input","change"]);
assert.throws(()=>rows.find(row=>row.label==="Blocked run").run(),/unavailable/);
button.isConnected=false;assert.throws(()=>rows.find(row=>row.label==="Run heat solve").run(),/changed/);
console.log("Live control search: no implicit execution, retained field focus, select events, disabled and stale control admission passed.");
