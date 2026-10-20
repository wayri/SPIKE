// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { createRoot } from "react-dom/client";
import PartLimitsPanel from "../src/PartLimitsPanel";
import type { PartLimitRule, PartLimitReport } from "../src/partLimitsModel";
import fixture from "../.tmp/part-limits-review.json";
import "../src/styles.css";
import "../src/buttonStandard.css";
import "../src/EngineeringReview.css";
function Preview() {
  const [rules,setRules]=useState(fixture.request.part_limits as PartLimitRule[]),[valid,setValid]=useState(true);
  return <main className="engineering-review" style={{margin:"12px auto",maxHeight:"none",boxSizing:"border-box"}}><header><h2>Part limits & stress</h2><small>Synthetic inputs · real cached backend report · no live solver</small><button type="button" onClick={()=>{setRules(fixture.request.part_limits as PartLimitRule[]);setValid(true);}}>Restore verified fixture</button></header><PartLimitsPanel components={[{occurrence_id:"board-a",component_id:"u1",reference:"U1"}]} rules={rules} report={valid?fixture.result.part_limit_report as PartLimitReport:undefined} disabled={false} onChange={next=>{setRules(next);setValid(false);}}/></main>;
}
const root=createRoot(document.getElementById("root")!);root.render(<Preview/>);
if(import.meta.hot)import.meta.hot.dispose(()=>root.unmount());
