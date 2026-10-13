// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { build } from "esbuild";
import { fileURLToPath } from "node:url";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const bundle = await build({ entryPoints:[fileURLToPath(new URL("../src/Su2ResultPanel.tsx",import.meta.url))], bundle:true, write:false, format:"esm", platform:"node", external:["react","react-dom"], loader:{".css":"empty"},
  plugins:[{name:"plot-contract-only",setup(build){build.onResolve({filter:/InteractivePlot$/},()=>({path:"plot",namespace:"stub"}));build.onLoad({filter:/.*/,namespace:"stub"},()=>({contents:"export default function Plot(){return null}"}));}}] });
const code=bundle.outputFiles[0].text.replaceAll('from "react"',`from ${JSON.stringify(new URL("../node_modules/react/index.js",import.meta.url).href)}`).replaceAll('from "react-dom"',`from ${JSON.stringify(new URL("../node_modules/react-dom/index.js",import.meta.url).href)}`).replaceAll('from "react/jsx-runtime"',`from ${JSON.stringify(new URL("../node_modules/react/jsx-runtime.js",import.meta.url).href)}`);
const {su2ResultPresentation,Su2ResultPanel}=await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
// Original presentation fixture, never claimed to be a solver accuracy oracle.
const cavity={contract:"spike/su2-cavity-result/v1",status:"completed",convergence:{converged:true,final_log10_residuals:{"rms[P]":-10}},
  fields:{x:[0,1,0,1],y:[0,0,1,1],u:[0,0,1,1],v:[0,0,0,0],p:[1,2,3,4]},
  centerlines:{coordinate:[0,.5,1],u:[0,-.2,1],v:[0,.03,0]},units:{x:"m",y:"m",u:"m/s",v:"m/s",p:"Pa"},
  provenance:{version:"8.5.0",executable_sha256:"a".repeat(64),run_directory:"retained/case"}};
const view=su2ResultPresentation({data:{result:cavity}});
assert.equal(view.error,""); assert.equal(view.plots.length,4);
assert.deepEqual(view.plots[0].data[0].marker.color,[0,0,1,1]);
assert.deepEqual(view.plots[2].data[0].y,[0,-.2,1]);
assert.deepEqual(view.residuals,[["rms[P]",-10]]);
for(const alter of [value=>value.fields.p.pop(),value=>value.fields.u[0]=NaN,value=>value.units.u="mm/s",value=>value.centerlines.coordinate.pop(),value=>value.status="failed_to_converge",value=>value.convergence.converged=false,value=>value.contract="future"]){
  const invalid=structuredClone(cavity);alter(invalid);const rejected=su2ResultPresentation(invalid);assert.equal(rejected.plots.length,0);assert.ok(rejected.error);
}
assert.equal(su2ResultPresentation({data:{status:"prepared"}}).plots.length,0);
assert.equal(su2ResultPresentation(null).plots.length,0);
const html=renderToStaticMarkup(React.createElement(Su2ResultPanel,{result:{data:{result:cavity}}}));
for(const label of ["SU2 lid-driven cavity","Not production qualified","do not represent the loaded PCB","Final log10 residuals","Run provenance","u (m/s)"]){
  if(label==="u (m/s)") assert.equal(view.plots[2].layout.yaxis.title.text,label); else assert.ok(html.includes(label),label);
}
assert.doesNotMatch(html,/<pre>/);
assert.match(html, /aria-haspopup="dialog"[^>]*>Expand results/);
assert.doesNotMatch(html, /<dialog/);
const cht={contract:"spike/su2-cht-result/v1",status:"completed",convergence:{converged:true},validation:{passed:true,violations:[]},
  zones:{fluid:{x_m:[.5,.5],y_m:[0,1],temperature_k:[309,300],u_m_s:[0,1],v_m_s:[0,0]},solid:{x_m:[.5,.5],y_m:[-.25,0],temperature_k:[310,309]}},
  interface:{x_m:[0,1],fluid_temperature_k:[309,309],solid_temperature_k:[309,309],fluid_flux_w_m2:[.09,.09],solid_flux_w_m2:[.09,.09]},
  diagnostics:{interface_temperature_jump_k:0,interface_flux_relative_error:0,global_energy_relative_error:0,heat_input_w_per_m:.09,heat_output_w_per_m:.09}};
const thermal=su2ResultPresentation({data:{result:cht}});
assert.equal(thermal.error,"");assert.equal(thermal.plots.length,4);assert.equal(thermal.metrics.length,5);
assert.deepEqual(thermal.plots[1].data[0].y,[309,300]);
assert.equal(thermal.plots[0].data[0].marker.cmin,300);assert.equal(thermal.plots[0].data[1].marker.cmax,310);
for(const alter of [value=>value.zones.solid.temperature_k[0]=Infinity,value=>value.zones.fluid.temperature_k[0]=-1,value=>value.interface.fluid_flux_w_m2.pop(),value=>value.zones.solid.x_m=[0,0],value=>value.status="executed"]){
  const invalid=structuredClone(cht);alter(invalid);const rejected=su2ResultPresentation(invalid);assert.equal(rejected.plots.length,0);assert.ok(rejected.error);
}
const threeZone=structuredClone(cht);
threeZone.zones.cold_solid={x_m:[.5,.5],y_m:[1,1.25],temperature_k:[300.2,300]};
threeZone.cold_interface={x_m:[0,1],fluid_temperature_k:[300.2,300.2],solid_temperature_k:[300.2,300.2],fluid_flux_w_m2:[.09,.09],solid_flux_w_m2:[.09,.09]};
const three=su2ResultPresentation(threeZone);
assert.equal(three.error,""); assert.equal(three.plots.length,6); assert.equal(three.plots[0].data.length,3);
assert.deepEqual(three.plots[1].data[2].y,[300.2,300]);
assert.equal(three.plots[0].data[2].marker.cmin,300); assert.equal(three.plots[0].data[2].marker.cmax,310);
assert.match(three.plots[4].title,/Cold interface/);
const mismatchedCold=structuredClone(threeZone);delete mismatchedCold.cold_interface;
assert.equal(su2ResultPresentation(mismatchedCold).plots.length,0);
const validationFailure=structuredClone(threeZone);validationFailure.status="failed_validation";
validationFailure.validation={passed:false,violations:["cold wall error exceeds 0.0001 K"]};
const withheld=su2ResultPresentation(validationFailure);
assert.equal(withheld.plots.length,0); assert.match(withheld.error,/Physical validation failed/);assert.match(withheld.error,/cold wall error/);
assert.doesNotMatch(withheld.error,/No converged solution/);
const missingValidation=structuredClone(cht);delete missingValidation.validation;
assert.equal(su2ResultPresentation(missingValidation).plots.length,0);
const preview={data:{geometry:{fluid_bounds_m:[[0,0],[1,1]],solid_bounds_m:[[0,-.25],[1,0]],cold_solid_bounds_m:[[0,1],[1,1.25]]},settings:{cells:16},runtime:{available:true,executable:"trusted/SU2_CFD"}}};
const prepared=su2ResultPresentation(preview);
assert.equal(prepared.status,"Prepared case - not solved");assert.equal(prepared.plots.length,0);assert.equal(prepared.previews[0].data.length,3);
assert.ok(prepared.details.some(([label,value])=>label==="Runtime"&&value==="Available"));
const probe=su2ResultPresentation({data:{cfd:{available:true},cht:{available:false}}});
assert.equal(probe.status,"Runtime check - no solve performed");assert.equal(probe.details.length,2);
const previewHtml=renderToStaticMarkup(React.createElement(Su2ResultPanel,{result:preview}));
assert.match(previewHtml,/Prepared case - not solved/);assert.match(previewHtml,/Cold solid bounds \(m\)/);assert.match(previewHtml,/trusted\/SU2_CFD/);
console.log("SU2 result presentation: finite SI fields, actual centreline samples, convergence gating, provenance and truthful scope passed.");
for (const path of process.argv.slice(2)) {
  const {readFile}=await import("node:fs/promises");
  const actual=su2ResultPresentation(JSON.parse(await readFile(path,"utf8")));
  assert.equal(actual.error, "", path); assert.ok(actual.plots.length>0,path);
  console.log(`Actual retained result admitted for plotting: ${path} (${actual.plots.length} figures).`);
}
