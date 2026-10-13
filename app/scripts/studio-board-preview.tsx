// SPDX-License-Identifier: Apache-2.0
import React,{useState} from "react";
import {createRoot} from "react-dom/client";
import StudioBoardCircuitView from "../src/BoardCircuitStudioPanel";
import StudioFeedbackPanel from "../src/StudioFeedbackPanel";
import {defaultSpiceWorkspace} from "../src/spiceWorkspace";
import type {ParsedBoard} from "../src/boardParser";
import "../src/styles.css";
import "../src/buttonStandard.css";
const components=[{id:"r1",ref:"R1",value:"10 ohm",at:[10,12],width:3,height:1,rotation:0,layer:"F.Cu"},{id:"c1",ref:"C1",value:"1 uF",at:[30,12],width:3,height:1,rotation:90,layer:"F.Cu"},{id:"j1",ref:"J1",value:"Supply",at:[10,30],width:3,height:1,rotation:0,layer:"F.Cu"}];
const pads=components.flatMap(part=>[1,2].map((pin,index)=>({id:`${part.id}-${pin}`,ref:part.ref,name:String(pin),at:[part.at[0]+index*2-1,part.at[1]],net:pin===1?"1":"2",type:"smd",layer:"F.Cu",width:1,height:1})));
const board={components,pads,nets:{1:"SUPPLY",2:"GND"},tracks:[{id:"t1",start:[9,12],end:[29,12],net:"1",width:.5,layer:"F.Cu"}],zones:[],width:45,height:40,bounds:{minX:0,minY:0,maxX:45,maxY:40}} as unknown as ParsedBoard;
function Preview(){const [workspace,setWorkspace]=useState(defaultSpiceWorkspace("pi",board)),[tab,setTab]=useState("board"),[status,setStatus]=useState("Synthetic UI fixture: no solver results");return <main style={{height:"100vh",display:"flex",flexDirection:"column",background:"var(--spike-table-surface)",color:"var(--spike-table-text)"}}><header style={{display:"flex",gap:8,padding:8}}><button type="button" onClick={()=>setTab("board")}>Board circuit</button><button type="button" onClick={()=>setTab("feedback")}>Feedback</button><span>{status}</span></header><div style={{flex:1,minHeight:0}}>{tab==="board"?<StudioBoardCircuitView board={board} design={{components}} workspace={workspace} onWorkspace={setWorkspace} onSelect={part=>setStatus(`Selected ${part.ref}`)} onEditPins={ref=>setStatus(`Pin editor: ${ref}`)} onStatus={setStatus}/>:<StudioFeedbackPanel board={board} design={null} workspace={workspace} onWorkspace={setWorkspace} onBusy={()=>{}} onRequireAdmission={async()=>null} onStatus={setStatus}/>}</div></main>;}
createRoot(document.getElementById("root")!).render(<Preview/>);
