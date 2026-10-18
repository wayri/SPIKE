// SPDX-License-Identifier: Apache-2.0
import React from "react";
import {createRoot} from "react-dom/client";
import FileDropImport from "../src/FileDropImport";
import "../src/buttonStandard.css";
import "../src/tableTheme.css";
function Preview(){
 const [status,setStatus]=React.useState("Fixture: browser drop review; ODB++ and MCAD use the desktop app.");
 return <main style={{background:"var(--spike-table-surface)",color:"var(--spike-table-text)",minHeight:"100vh",padding:24,fontFamily:"system-ui"}}><h1>Source drop review fixture</h1><p>{status}</p><button type="button" onClick={()=>{
 const transfer=new DataTransfer();
 for(const [name,contents] of [["power-distribution-controller-revision-12-long-mechanical-reference.kicad_pcb","(kicad_pcb (version 20240108))"],["manufacturing-job.tar.gz","archive fixture"],["assembly-enclosure.step","model fixture"]])transfer.items.add(new File([contents],name));
 document.dispatchEvent(new DragEvent("drop",{dataTransfer:transfer,bubbles:true,cancelable:true}));
 }}>Stage sample dropped files</button><FileDropImport desktop={false} blocked={false} onReview={async item=>setStatus(`Review requested: ${item.fileName}`)} onError={setStatus}/></main>;
}
createRoot(document.getElementById("root")!).render(<Preview/>);
