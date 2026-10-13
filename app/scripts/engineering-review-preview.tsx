// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { createRoot } from "react-dom/client";
import EngineeringReview from "../src/EngineeringReview";
import fixture from "../.tmp/engineering-review.json";
import "../src/styles.css";
import "../src/buttonStandard.css";
function Preview() {
  const [open,setOpen]=useState(true);
  const context={boards:fixture.request.boards.map(board=>({id:board.occurrence_id,name:board.occurrence_id,design_id:board.occurrence_id,design:board.design})),selected_board_id:null,assembly:null};
  return <><p>Visual verification only · cached outputs from an original backend fixture · no native worker</p><button type="button" onClick={()=>setOpen(true)}>Open review</button><EngineeringReview open={open} context={context} onClose={()=>setOpen(false)} execute={async request=>{
    const input=(request.params as {request:unknown}).request;
    const quick=request.method==="quick_engineering_tool";
    if(JSON.stringify(input)!==JSON.stringify(quick?fixture.quick_request:fixture.request))return{ok:false,error:"This visual fixture supports its original inputs only. Use the desktop for new calculations."};
    return{ok:true,result:quick?fixture.quick_result:fixture.result};
  }}/></>;
}
createRoot(document.getElementById("root")!).render(<Preview/>);
