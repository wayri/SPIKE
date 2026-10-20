// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { nativeCavityFieldVolume, assemblyAirflowFieldVolume } = await importTestTypescript("fieldVolumeAdapters");
const cavity = { status:"converged", settings:{n:2,reynolds:100}, diagnostics:{time:3}, fields:{
  x_m:[.25,.75,.25,.75], y_m:[.25,.25,.75,.75], u_m_s:[1,0,0,-1], v_m_s:[0,2,0,0], pressure_pa:[1,2,3,4] } };
const sheet = nativeCavityFieldVolume(cavity);
assert.equal(sheet.cells.centers.length,4);
assert.deepEqual(sheet.cells.sizes[0],[.5,.5,.5]);
assert.deepEqual(sheet.frames[0].scalars.speed_m_s,[1,2,0,1]);
assert.match(sheet.geometryNote,/no physical 3D meaning/);
assert.equal(nativeCavityFieldVolume({...cavity,status:"failed_to_converge",fields:null}),null);

const airflow = { contract:"spike/thermal-field-result/v1", status:"completed", model_status:"experimental",
  qualification:{production_qualified:false}, job_id:"job", fields:{
    temperature_k:{unit:"K",samples:[{point_mm:[1,2,3],value:300,region:"air"}]},
    velocity_m_s:{unit:"m/s",samples:[{point_mm:[1,2,3],value:[3,4,0],region:"air"}]}}};
const points = assemblyAirflowFieldVolume(airflow);
assert.deepEqual(points.cells,{centers:[[1,2,3]]});
assert.deepEqual(points.frames[0].scalars,{temperature_k:[300],speed_m_s:[5]});
assert.deepEqual(points.frames[0].vectors,[[3,4,0]]);
assert.equal(assemblyAirflowFieldVolume({...airflow,fields:{...airflow.fields,velocity_m_s:{unit:"m/s",samples:[{point_mm:[9,9,9],value:[1,0,0],region:"air"}]}}}),null);
console.log("field volume CFD adapters preserve returned coordinates, vectors, values, and geometry limits");
