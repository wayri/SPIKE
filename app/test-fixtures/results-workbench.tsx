// SPDX-License-Identifier: Apache-2.0
// Synthetic presentation fixture: these values are not a solver validation.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import BoardViewport from '../src/BoardViewport';
import ProbeResultsTable from '../src/ProbeResultsTable';
import { parseKicadBoard } from '../src/boardParser';
import { normalizeSolverResult, defaultResultVisualization } from '../src/analysisResults';
import type { ProbeFormulaRow } from '../src/probeCalculations';
import { DetachedToolContent } from '../src/detachedToolWindows';
import { decodeDetachedRowId } from '../src/detachedToolWindowModel';
import { buildDetachedProbeSnapshot } from '../src/resultsToolSnapshots';
import '../src/styles.css';
const board=parseKicadBoard(`(kicad_pcb (version 20240108) (generator "regression-fixture")
 (general (thickness 1.6)) (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))
 (net 1 "VDD") (gr_rect (start 0 0) (end 30 20) (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts"))`);
board.zones=[{id:'surface',net:'VDD',layer:'F.Cu',points:[[2,2],[28,2],[28,18],[2,18]],holes:[]}];
const voltage=Array.from({length:26*16},(_,index)=>{
  const x=2+index%26, y=2+Math.floor(index/26);
  return {element_id:`cell-${index}`,net:'VDD',layer:'F.Cu',x_mm:x+.5,y_mm:y+.5,value:1+(x-2)/26,
    vertices_mm:[[x,y,.8],[x+1,y,.8],[x+1,y+1,.8],[x,y+1,.8]]};
});
const result=normalizeSolverResult({status:'completed',analysis_id:'synthetic-display-regression',model_status:'synthetic',mode:'dc',
  summary:{},fields:{visualization:{scalar_fields:{voltage_v:voltage}}},
  probes:[{id:'probe/1',status:'mapped',net:'VDD',layer:'F.Cu',voltage_v:2,peak_adjacent_current_a:.5},
    {id:'probe/2',status:'mapped',net:'VDD',layer:'F.Cu',voltage_v:1,peak_adjacent_current_a:0}]})!;
function Fixture(){
 const [mode,setMode]=useState<'2D'|'3D'>('3D');
 const [visual,setVisual]=useState({...defaultResultVisualization(),mode:'voltage' as const,fieldStyle:'smooth' as const});
 const [cursor,setCursor]=useState(true);
 const [rows,setRows]=useState<ProbeFormulaRow[]>([{id:'C1',name:'Voltage difference',formula:'P1.voltage-P2.voltage'}]);
 const [target,setTarget]=useState('none');
 if (new URLSearchParams(location.search).get('tool') === 'probes') return <DetachedToolContent kind="probes"
 snapshot={buildDetachedProbeSnapshot([{id:'probe/1',name:'Source',type:'pad',net:'VDD',layer:'F.Cu'},
 {id:'probe/2',name:'Load',type:'pad',net:'VDD',layer:'F.Cu'}],result,rows,{'probe/1':'P1','probe/2':'P2'})}
 onAction={action=>{
   const id=action.rowId ? decodeDetachedRowId(action.rowId) : null;
   if(action.actionId==='edit-formula') setRows(current=>current.map(row=>row.id===id?{...row,formula:String(action.value)}:row));
   if(action.actionId==='rename-formula') setRows(current=>current.map(row=>row.id===id?{...row,name:String(action.value)}:row));
   if(action.actionId==='delete-formula') setRows(current=>current.filter(row=>row.id!==id));
   if(action.controlId==='add-formula') setRows(current=>[...current,{id:`C${current.length+1}`,name:'Synthetic calculation',formula:'2+3'}]);
   if(action.type==='redock') location.search='';
 }} />;
 return <div style={{height:'100vh',display:'grid',gridTemplateRows:'48px 1fr 250px'}}>
 <header style={{display:'flex',alignItems:'center',gap:16,padding:8}}><strong>Synthetic display regression</strong>
 <button onClick={()=>setMode(mode==='3D'?'2D':'3D')}>{mode}</button>
 <button onClick={()=>setVisual(v=>({...v,fieldStyle:v.fieldStyle==='smooth'?'cells':'smooth'}))}>{visual.fieldStyle}</button>
 <button onClick={()=>setVisual(v=>({...v,plotStyle:v.plotStyle==='flat'?'contour':'flat'}))}>{visual.plotStyle}</button>
 <button onClick={()=>setVisual(v=>({...v,sceneMode:v.sceneMode==='opaque'?'results_only':'opaque'}))}>{visual.sceneMode}</button>
 <button onClick={()=>setCursor(!cursor)}>Cursor {cursor?'on':'off'}</button><output aria-label="cursor sample">{target}</output></header>
 <div style={{position:'relative',minHeight:0}}><BoardViewport board={board} viewMode={mode}
 visibleLayers={{'F.Cu':true,'B.Cu':true}} layerOpacity={{}} layerSeparation={0} showVias={true}
 showModels={false} showSmdModels={false} showThtModels={false} showAxes={true}
 navigationMode="orbit" navigationInertia={false} cameraCommand="fit-fixture" selectionFilter="all" selectedId={null}
 analysisResult={result} resultVisualization={visual} hoverProbeEnabled={cursor} onHoverProbe={value=>setTarget(value?.resultSample?.element_id??'none')}
 onSelect={()=>{}} onCamera={()=>{}} /></div>
 <div style={{overflow:'auto'}}><ProbeResultsTable probes={[{id:'probe/1',name:'Source',type:'pad',net:'VDD',layer:'F.Cu'},
 {id:'probe/2',name:'Load',type:'pad',net:'VDD',layer:'F.Cu'}]} result={result} calculatedRows={rows}
 onCalculatedRowsChange={setRows} probeReferenceIds={{'probe/1':'P1','probe/2':'P2'}} onRemoveProbe={()=>{}} /></div></div>;
}
const root = createRoot(document.getElementById('root')!);
root.render(<Fixture/>);
if (import.meta.hot) import.meta.hot.dispose(() => root.unmount());
