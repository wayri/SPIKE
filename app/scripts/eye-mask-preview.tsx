// SPDX-License-Identifier: Apache-2.0
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import SiChannelResultPanel from "../src/SiChannelResultPanel";
import fixture from "../.tmp/eye-masks/usb2-template1.json";
import passing from "../.tmp/eye-masks/usb2-template1-pass.json";
import "../src/styles.css";
import "../src/buttonStandard.css";
function Preview() {
const [selected,setSelected]=useState(false);
const lane=(selected?fixture:passing).lanes[0];
return <main style={{maxWidth:1000,margin:"auto",padding:16,height:"100vh",overflow:"auto",boxSizing:"border-box"}}><h1>Executed USB HS inner-mask verification</h1><p>Numerical fixture; explicit 0.8 V scale. Retained polylines only; hardware compliance not evaluated.</p><button onClick={()=>setSelected(false)}>Zero offset case</button><button onClick={()=>setSelected(true)}>Shifted voltage case</button><SiChannelResultPanel result={lane.channel_result as unknown as Record<string,unknown>} eyeMaskResult={lane.eye_mask_result as unknown as Record<string,unknown>} onStatus={()=>{}} /></main>;
}
createRoot(document.getElementById("root")!).render(<Preview />);
