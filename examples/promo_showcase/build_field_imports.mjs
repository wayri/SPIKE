// SPDX-License-Identifier: Apache-2.0
// Presentation adapters only: exact solved samples; no field/time interpolation.
import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {importTestTypescript} from '../../app/scripts/import-test-typescript.mjs';
const root=new URL('../../',import.meta.url);
const out=new URL('output/promo-showcase-20261023/field-imports/',root);
await fs.mkdir(out,{recursive:true});
const read=async p=>JSON.parse(await fs.readFile(new URL(p,root),'utf8'));
const {nativeCavityFieldVolume}=await importTestTypescript('fieldVolumeAdapters');
const {admitFieldVolume}=await importTestTypescript('fieldVolumeModel');
const records=[];
async function save(name,data,source,scope){
 const admitted=admitFieldVolume(data);assert.equal(admitted.frames.length,data.frames.length);
 for(let i=0;i<data.frames.length;i++)for(const q of data.quantities)assert.deepEqual(admitted.frames[i].scalars[q.id],data.frames[i].scalars[q.id]);
 await fs.writeFile(new URL(name,out),JSON.stringify(data));
 records.push({file:name,cells:data.cells.centers.length,frames:data.frames.length,times_s:data.frames.map(f=>f.timeS),source,source_sha256:createHash('sha256').update(await fs.readFile(new URL(source,root))).digest('hex'),scope,native_field_admission:'passed',physical_time_interpolation:false});
}
const cavitySource='output/promo-showcase-20261023/thermal_flow/native-cavity.result.json';
const cavity=await read(cavitySource);const cavityView=nativeCavityFieldVolume(cavity);assert(cavityView);
await save('native-cavity.field.json',cavityView,cavitySource,'Actual steady 2D CFD cells. Display-only Z thickness; no enclosure/CAD association.');
const chtSource='output/promo-showcase-20261023/thermal_flow/channel-cht.result.json';
const cr=await read(chtSource),cq=await read('output/promo-showcase-20261023/thermal_flow/channel-cht.request.json');
const [nx,ny]=cr.shape,g=cq.geometry,grid=cq.grid;
const edges=[];
for(let j=0;j<=grid.lower_wall_cells;j++)edges.push(-g.lower_wall_thickness_m+j*g.lower_wall_thickness_m/grid.lower_wall_cells);
for(let j=1;j<=grid.fluid_cells;j++)edges.push(j*g.fluid_height_m/grid.fluid_cells);
for(let j=1;j<=grid.upper_wall_cells;j++)edges.push(g.fluid_height_m+j*g.upper_wall_thickness_m/grid.upper_wall_cells);
assert.equal(edges.length,ny+1);assert.equal(cr.temperature_k.length,nx*ny);
const centers=[],sizes=[];
for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){centers.push([(i+.5)*g.length_m/nx,(edges[j]+edges[j+1])/2,0]);sizes.push([g.length_m/nx,edges[j+1]-edges[j],g.width_m]);}
await save('channel-cht-temperature.field.json',{contract:'spike/field-volume-view/v1',id:'promo-channel-cht',label:'Solved bounded channel CHT - steady',lengthUnit:'m',geometryNote:'Actual returned solid/fluid finite-volume temperatures. Channel cells are extruded through the declared uniform span for presentation, not a general 3D CFD solve. One steady frame, no invented time evolution.',cells:{centers,sizes},quantities:[{id:'temperature_k',label:'Temperature',unit:'K'}],frames:[{timeS:0,scalars:{temperature_k:cr.temperature_k}}]},chtSource,'Exact CHT temperatures; native Fields import for presentation. Research API rerun, not a native CHT setup importer.');
const magSource='output/promo-showcase-20261023/electrical/planar_solenoid_fem-result.json';
const mr=await read(magSource),nodes=mr.field.nodes_m,history=mr.coupled.history;
assert(history.length>1);for(const f of history){assert.equal(f.temperature_k.length,nodes.length);assert.equal(f.potential_a_wb_per_m.length,nodes.length);}
await save('solenoid-potential-temperature-transient.field.json',{contract:'spike/field-volume-view/v1',id:'promo-solenoid-retained-transient',label:'Computed 2D solenoid nodal A_z and temperature',lengthUnit:'m',geometryNote:'Exact solved nodal magnetic vector potential A_z and temperature at three physical times (0, 1, 2 ms). Planar nodal points, not PCB coil geometry or B-vector animation. Scrub saved frames: minimum playback speed is too fast for a visible 2 ms history. No interpolated time samples.',cells:{centers:nodes.map(([x,y])=>[x,y,0])},quantities:[{id:'potential_a',label:'Magnetic vector potential A_z',unit:'Wb/m'},{id:'temperature_k',label:'Temperature',unit:'K'}],frames:history.map(f=>({timeS:f.time_s,scalars:{potential_a:f.potential_a_wb_per_m,temperature_k:f.temperature_k}}))},magSource,'Actual transient scalar nodal samples; no fabricated magnetic B fields, no time remapping.');
await fs.writeFile(new URL('verification.json',out),JSON.stringify({status:'passed',generator:fileURLToPath(import.meta.url),records},null,2)+'\n');
console.log(JSON.stringify(records.map(r=>({file:r.file,cells:r.cells,frames:r.frames})),null,2));
