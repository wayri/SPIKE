// SPDX-License-Identifier: Apache-2.0
import {useEffect,useState} from "react";
import {createRoot} from "react-dom/client";
import * as THREE from "three";
import {GLTFExporter} from "three/examples/jsm/exporters/GLTFExporter.js";
import BoardViewport from "../src/BoardViewport";
import MechanicalObjectControls from "../src/MechanicalObjectControls";
import {DEFAULT_ASSEMBLY_SECTION,type AssemblyIr,type AssemblySceneModel} from "../src/mcadAssembly";
import {mechanicalVisual,type MechanicalVisuals} from "../src/mechanicalObjectsModel";
import {parseKicadBoard,type ParsedBoard} from "../src/boardParser";
import type {MechanicalMeasurementPoints} from "../src/mechanicalMeasurement";
import "../src/styles.css";
import "../src/WorkbenchChrome.css";
import "../src/buttonStandard.css";
const matrix=(x=0,y=0,z=0)=>[1,0,0,x,0,1,0,y,0,0,1,z,0,0,0,1];
function Preview(){
 const [board,setBoard]=useState<ParsedBoard|null>(null),[assembly,setAssembly]=useState<AssemblyIr|null>(null),[models,setModels]=useState<AssemblySceneModel[]>([]),[visuals,setVisuals]=useState<MechanicalVisuals>({}),[selected,setSelected]=useState<string|null>(null),[isolated,setIsolated]=useState<string|null>(null),[section,setSection]=useState({...DEFAULT_ASSEMBLY_SECTION}),[measurement,setMeasurement]=useState<MechanicalMeasurementPoints|null>(null),[camera,setCamera]=useState("");
 useEffect(()=>{let live=true;const urls:string[]=[];void(async()=>{
 const parsed=parseKicadBoard(await(await fetch("/demo/ebrake1.kicad_pcb")).text());
 const x=(parsed.bounds.minX+parsed.bounds.maxX)/2,y=(parsed.bounds.minY+parsed.bounds.maxY)/2;
 const parts=[{id:"housing",name:"Housing — authored visual fixture",source_id:"test",model_id:"housing-model",material_id:"",part_type:"enclosure",frame:{frame_id:"housing-frame",parent_frame_id:"assembly",units:"mm" as const,handedness:"right" as const,transform:matrix(x,y,20)},extensions:{}},{id:"bracket",name:"Mounting bracket — authored fixture",source_id:"test",model_id:"bracket-model",material_id:"",part_type:"bracket",frame:{frame_id:"bracket-frame",parent_frame_id:"assembly",units:"mm" as const,handedness:"right" as const,transform:matrix(x+25,y,10)},extensions:{}}];
 const next:AssemblySceneModel[]=[];
 for(let i=0;i<parts.length;i++){
 const scene=new THREE.Scene();scene.add(new THREE.Mesh(new THREE.BoxGeometry(i?.012:.08,i?.055:.045,i?.04:.025),new THREE.MeshStandardMaterial({color:i?0xe8aa45:0x80c9dd,side:THREE.DoubleSide})));
 const binary=await new GLTFExporter().parseAsync(scene,{binary:true});const url=URL.createObjectURL(new Blob([binary as ArrayBuffer],{type:"model/gltf-binary"}));urls.push(url);
 next.push({partId:parts[i].id,modelId:parts[i].model_id,name:parts[i].name,modelType:"glb",url,partTransform:parts[i].frame.transform,modelTransform:matrix(),visible:true,opacity:1});
 scene.traverse(o=>{if(o instanceof THREE.Mesh){o.geometry.dispose();o.material.dispose();}});
 }
 if(live){setBoard(parsed);setAssembly({contract:"spike/assembly-ir/v1",assembly_id:"authored-test",name:"Mechanical controls test",boards:[],parts});setModels(next);}
 })();return()=>{live=false;urls.forEach(url=>URL.revokeObjectURL(url));};},[]);
 return <main style={{height:"100vh",display:"flex",flexDirection:"column"}}><header style={{padding:12}}><strong>SPIKE · Mechanical viewport tools</strong><p style={{fontSize:12}}>Retained EBrake board with two authored glTF test solids · visual interaction fixture · no CAD or solver qualification</p><button type="button" onClick={()=>setCamera(`fit-${Date.now()}`)}>Fit assembly</button></header>
 <section style={{position:"relative",flex:1,minHeight:0}}>{board&&<BoardViewport board={board} viewMode="3D" visibleLayers={{}} layerOpacity={{}} layerSeparation={0} showVias showModels showSmdModels={false} showThtModels={false} navigationMode="orbit" navigationInertia={false} cameraCommand={camera} selectionFilter="all" selectedId={selected?`assembly-part:${selected}`:null} assemblyModels={models} mechanicalVisuals={visuals} mechanicalMeasurement={measurement} isolatedAssemblyPartId={isolated} assemblySection={section} onSelect={value=>setSelected(value.assemblyPartId??null)} onCamera={()=>{}}/>}
 {assembly&&<MechanicalObjectControls assembly={assembly} visuals={visuals} selectedId={selected} isolatedId={isolated} section={section} viewMode="3D" on3D={()=>{}} onMeasurement={setMeasurement} onVisual={(id,value)=>setVisuals(current=>({...current,[id]:value}))} onAll={mode=>setVisuals(mode==="reset"?{}:Object.fromEntries(assembly.parts.map(part=>[part.id,{visible:mode!=="hide",opacity:mode==="translucent"?.2:mechanicalVisual(part,visuals).opacity}])))} onSelect={part=>setSelected(part.id)} onIsolate={setIsolated} onSection={setSection} onManage={()=>{}}/>}</section>
 <output id="mechanical-state" style={{padding:8,fontSize:11}}>{JSON.stringify({visuals,selected,isolated,section,measurement})}</output></main>;
}
createRoot(document.getElementById("root")!).render(new URLSearchParams(location.search).has("narrow")?<iframe title="Narrow mechanical controls" src="./mechanical-controls-preview.html" style={{width:560,height:800,border:0,display:"block"}}/>:<Preview/>);
