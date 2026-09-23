// SPDX-License-Identifier: MIT
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import TraceResultsWorkbench from "../src/TraceResultsWorkbench";
import type { ScalarSample, SolverResultBundle } from "../src/analysisResults";
const samples: ScalarSample[] = [];
for (const [net, offset] of [["3V3", 0], ["1V8", 8]] as const) for (let trace = 0; trace < 3; trace++) for (let step = 0; step < 50; step++) {
  const x = step * .5, y = offset + trace * 2;
  samples.push({ net, layer: "F.Cu", element_id: `trace-${trace}`, x_mm: x+.25,y_mm:y+.25,z_mm:0,value:(step+trace*5)*.0002,
    vertices_mm:[[x,y,0],[x+.5,y,0],[x+.5,y+.5,0],[x,y+.5,0]] });
}
const result = { analysis_id:"synthetic-trace-visual-regression",model_status:"synthetic display fixture",status:"completed",mode:"dc",scalar_fields:{voltage_drop_v:samples,voltage_v:samples.map(sample=>({...sample,value:3.3-sample.value}))},mesh:[],parasitics:[{net:"DATA+",model_status:"synthetic display fixture",impedance:Array.from({length:50},(_,i)=>({frequency_hz:1e4*1.2**i,magnitude_ohm:50+5*Math.sin(i*.1),phase_deg:i*.1}))}], vector_fields:{} } as unknown as SolverResultBundle;
function Preview(){const [domain,setDomain]=useState<"pi"|"si">("pi");return <><div style={{color:'#fff',padding:8,font:'14px sans-serif'}}>Synthetic rendering fixture — not a board simulation. <button onClick={()=>setDomain(domain==='pi'?'si':'pi')}>Switch to {domain==='pi'?'SI':'PI'}</button></div><TraceResultsWorkbench domain={domain} result={result}/></>}
createRoot(document.getElementById('root')!).render(<Preview/>);
