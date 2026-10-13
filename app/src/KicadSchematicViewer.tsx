// SPDX-License-Identifier: Apache-2.0
import { schematicPickBox } from "./kicadSchematicModel";
import { useEffect, useMemo, useRef, useState } from "react";
import { FolderOpen, Focus, ZoomIn, ZoomOut, Link, Search } from "./icons";
import type { SchematicAction, SchematicSnapshot } from "./kicadSchematicModel";
import "./KicadSchematicViewer.css";
export default function KicadSchematicViewer({snapshot,act,nativeWindow=false}:{snapshot:SchematicSnapshot;act:(action:SchematicAction)=>void;nativeWindow?:boolean}) {
  const doc=snapshot.document;
  const [inputKind,setInputKind]=useState("schematic");const [odbStep,setOdbStep]=useState("");
  const [pageId,setPageId]=useState("");const [query,setQuery]=useState("");const [mode,setMode]=useState<"parts"|"nets">("parts");
  const [view,setView]=useState<number[]|null>(null);const canvas=useRef<SVGSVGElement>(null);const drag=useRef<{x:number;y:number;view:number[]}|null>(null);
  const page=doc?.pages.find(p=>p.id===pageId)??doc?.pages[0];
  useEffect(()=>{setView(null);},[page?.id,doc?.source.sha256]);
  useEffect(()=>{const symbol=doc?.symbols.find(s=>s.reference===snapshot.selected.reference)||doc?.symbols.find(s=>s.nets.includes(doc.nets.find(n=>n.code===snapshot.selected.netCode)?.name??""));if(symbol)setPageId(symbol.page_id);},[doc?.source.sha256,snapshot.selected.reference,snapshot.selected.netCode]);
  const symbols=useMemo(()=>doc?.symbols.filter(s=>s.page_id===page?.id)??[],[doc,page?.id]);
  const net=doc?.nets.find(n=>n.code===snapshot.selected.netCode);const refs=new Set(net?.nodes.map(n=>n.reference)??[]);
  const bounds=view??page?.view_box??[0,0,297,210];
  const zoom=(factor:number)=>setView(current=>{const [x,y,w,h]=current??bounds;return [x+w*(1-factor)/2,y+h*(1-factor)/2,w*factor,h*factor];});
  const select=(action:Partial<SchematicAction>)=>act({type:"select",sourceSha256:doc?.source.sha256,...action});
  const entries=mode==="parts"?(doc?.symbols??[]).filter(s=>`${s.reference} ${s.value}`.toLowerCase().includes(query.toLowerCase())):(doc?.nets??[]).filter(n=>n.name.toLowerCase().includes(query.toLowerCase()));
  return <main className="kicad-schematic-viewer">
    <header><strong>{doc?.source.presentation==="generated_connectivity"?"Connectivity":"Schematic"}</strong><select aria-label="Import format" value={inputKind} disabled={snapshot.busy} onChange={e=>setInputKind(e.target.value)}><option value="schematic">KiCad schematic</option><option value="netlist">KiCad netlist (.xml/.net)</option><option value="odb++">ODB++ archive</option><option value="odb-folder">ODB++ folder</option></select><button disabled={snapshot.busy} onClick={()=>act({type:"import",inputFormat:inputKind==="odb-folder"?"odb++":inputKind as "schematic"|"netlist"|"odb++",directory:inputKind==="odb-folder",step:odbStep||undefined})} title="Import a local design or connectivity source"><FolderOpen size={15}/> Import</button>
      <select aria-label="Schematic sheet" value={page?.id??""} disabled={!doc} onChange={e=>setPageId(e.target.value)}>{doc?.pages.map(p=><option key={p.id} value={p.id}>{p.name} · {p.sheet_path}</option>)}</select>
      <button disabled={!page} onClick={()=>setView(null)} title="Fit sheet"><Focus size={15}/></button><button disabled={!page} onClick={()=>zoom(.8)} title="Zoom in"><ZoomIn size={15}/></button><button disabled={!page} onClick={()=>zoom(1.25)} title="Zoom out"><ZoomOut size={15}/></button>
      <button disabled={!doc||snapshot.busy} onClick={()=>act({type:"bind",sourceSha256:doc?.source.sha256})} title="Explicitly link this schematic to the active board"><Link size={15}/>{snapshot.linked?snapshot.boardName:"Link active board"}</button>
      {snapshot.busy&&<button onClick={()=>act({type:"cancel"})}>Cancel import</button>}{!nativeWindow&&<button onClick={()=>act({type:"close"})}>Close</button>}
    </header>
    {inputKind.startsWith("odb")&&<label className="schematic-status">ODB++ step <input aria-label="ODB++ step" value={odbStep} onChange={e=>setOdbStep(e.target.value)} placeholder="Optional for a single-step job" maxLength={96}/></label>}
    {doc?.source.presentation==="generated_connectivity"&&<p className="schematic-status" role="note">Generated connectivity diagram from {doc.source.format}. Original schematic symbols and drawing layout are not contained in this source.</p>}
    {snapshot.status&&<p className="schematic-status" role="status">{snapshot.status}</p>}
    {!doc?<div className="schematic-empty"><h2>Open a schematic or connectivity source</h2><p>Import a root .kicad_sch, KiCad netlist, or ODB++ job. Link the active board for component and pin-based net cross-selection.</p></div>:<div className="schematic-body">
      <aside><div className="schematic-search"><Search size={14}/><input aria-label="Find schematic parts or nets" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Find part or net"/></div>
        <div className="schematic-kind"><button aria-pressed={mode==="parts"} onClick={()=>setMode("parts")}>Parts</button><button aria-pressed={mode==="nets"} onClick={()=>setMode("nets")}>Nets</button></div>
        <div className="schematic-inventory">{entries.slice(0,100).map(item=>"reference" in item?<button key={item.id} className={snapshot.selected.reference===item.reference?"selected":""} onClick={()=>{setPageId(item.page_id);select({symbolId:item.id});}}><b>{item.reference}</b> {item.value}<small>{item.sheet_path}</small></button>:<button key={item.code} className={snapshot.selected.netCode===item.code?"selected":""} onClick={()=>select({netCode:item.code})}>{item.name}<small>{item.nodes.length} pins</small></button>)}{entries.length>100&&<p>Showing 100 of {entries.length}. Use search to narrow the list.</p>}</div>
      </aside>
      <svg ref={canvas} className="schematic-canvas" viewBox={bounds.join(" ")} role="img" aria-label={`${doc.source.presentation==="generated_connectivity"?"Connectivity diagram":"KiCad schematic"} ${page?.name}`} tabIndex={0}
        onWheel={e=>{e.stopPropagation();zoom(e.deltaY>0?1.1:.9);}}
        onKeyDown={e=>{if(e.key==="Escape")setView(null);if(e.key==="+"||e.key==="=")zoom(.8);if(e.key==="-")zoom(1.25);}}
        onPointerDown={e=>{if(e.button!==0||e.target!==e.currentTarget&&!(e.target instanceof SVGImageElement))return;drag.current={x:e.clientX,y:e.clientY,view:[...bounds]};e.currentTarget.setPointerCapture(e.pointerId);}}
        onPointerMove={e=>{const d=drag.current;if(!d)return;const rect=e.currentTarget.getBoundingClientRect();const scale=Math.max(d.view[2]/rect.width,d.view[3]/rect.height);setView([d.view[0]-(e.clientX-d.x)*scale,d.view[1]-(e.clientY-d.y)*scale,d.view[2],d.view[3]]);}}
        onPointerUp={e=>{drag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}} onPointerCancel={()=>{drag.current=null;}}>
        {page&&<image href={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(page.svg)}`} x={page.view_box[0]} y={page.view_box[1]} width={page.view_box[2]} height={page.view_box[3]}/>}
        {symbols.map(symbol=><rect key={symbol.id} x={schematicPickBox(doc,symbol).x} y={schematicPickBox(doc,symbol).y} width={schematicPickBox(doc,symbol).width} height={schematicPickBox(doc,symbol).height} className={`schematic-pick ${snapshot.selected.reference===symbol.reference||refs.has(symbol.reference)?"highlighted":""}`} role="button" tabIndex={0} aria-label={`Select ${symbol.reference} ${symbol.value}`} onClick={()=>select({symbolId:symbol.id})} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();select({symbolId:symbol.id});}}}><title>{`${symbol.reference} - ${symbol.value} - ${doc.source.presentation==="generated_connectivity"?"generated component connectivity region":"approximate pick region around saved symbol anchor"}`}</title></rect>)}
      </svg>
    </div>}
    {doc&&<footer><span>{doc.symbols.length} symbols · {doc.nets.length} nets · {doc.pages.length} sheets</span><details><summary>Import details</summary><p>{doc.limitations?.join(" ")}</p>{doc.diagnostics?.map((line,i)=><p key={i}>{line}</p>)}</details></footer>}
  </main>;
}
