// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {withoutSavedResults} from '../src/projectSnapshotState.ts';
const b=await build({entryPoints:['src/emViewportResults.ts'],bundle:true,platform:'node',format:'esm',write:false});
const api=await import(`data:text/javascript;base64,${Buffer.from(b.outputFiles[0].text).toString('base64')}`);
const dataset={positions_m:[[.001,.002,.003],[.004,.005,.006]],vectors:[[[3,0],[0,4],[0,0]],[[1,0],[0,0],[0,0]]],native_indices:[1,9],source_sample_count:10,units:'V/m'};
const preview={contract:'spike/assembly-em-preview/v1',coordinate_frame:'assembly',coordinate_units:'m',normalization:'1V_peak_incident',frequency_hz:1e9,datasets:{'electric-field':dataset,'magnetic-field':{...dataset,units:'A/m'}}};
const record={id:'volume',label:'volume',result:{status:'completed',fields:{retained_volume:preview}}};
const s={...api.defaultEMViewportSettings,quantity:'volume_e',style:'samples'};
let d=api.buildEMViewportData(record,s);
assert.equal(d.values[0],5);assert.deepEqual(d.positionsMm[0],[1,2,3]);assert.deepEqual(d.nativeSampleIndices,[1,9]);
assert.equal(d.assemblyFrame,true);assert.match(d.unit,/1 V peak incident/);assert.equal(d.indices.length,0,'no fabricated surface across volume samples');
d=api.buildEMViewportData(record,{...s,quantity:'volume_h',component:'y',projection:'imaginary'});
assert.equal(d.values[0],4);assert.match(d.unit,/A\/m/);
assert.equal(api.buildEMViewportData(record,{...s,frequencyIndex:1}),null);
for(const key of ['coordinate_frame','coordinate_units','normalization']){
  const bad=structuredClone(record);bad.result.fields.retained_volume[key]='wrong';assert.equal(api.buildEMViewportData(bad,s),null);
}
const bad=structuredClone(record);bad.result.fields.retained_volume.datasets['electric-field'].vectors[0][0][0]=NaN;
assert.equal(api.buildEMViewportData(bad,s),null);
const saved={analysis:{retained_assembly_em:{request:{geometry:'retained'},result:record.result}}};
assert.equal(withoutSavedResults(saved).analysis.retained_assembly_em.result,null);assert.ok(saved.analysis.retained_assembly_em.result);
console.log('Retained assembly field units, coordinates, native probes, admission and result-free saves passed.');
