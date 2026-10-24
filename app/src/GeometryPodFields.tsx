// SPDX-License-Identifier: Apache-2.0
import {type GeometryPodField,type GeometryPodResult} from "./geometryPodStudy";
import {numericExtent,numericMaximum} from "./numericRange";
export default function GeometryPodFields({result,index,onSelect}:{result:GeometryPodResult;index:number;onSelect:(index:number)=>void}) {
  const frames=result.field_snapshots;
  if(!frames?.length)return <p>No retained spatial magnetic snapshots in this capture.</p>;
  const selected=frames.find(f=>f.history_index===index);
  const max=numericMaximum(frames.flatMap(f=>Object.values(f.snapshot.domains).flatMap(d=>d.element_b_t.map(v=>Math.hypot(...v)))),1)||1;
  return <section><h3>Saved spatial magnetic field</h3><label>Actual solved endpoint<select aria-label="Saved spatial magnetic state" value={selected?index:""} onChange={e=>onSelect(Number(e.target.value))}><option value="" disabled>Select a retained spatial state</option>{frames.map(f=><option key={f.history_index} value={f.history_index}>{result.history[f.history_index].time_s.toPrecision(6)} s</option>)}</select></label>
    {selected?<Field frame={selected} maximum={max}/>:<p>No spatial field was retained at this accepted state. Select a saved spatial state.</p>}
    <small>Shared |B| scale: 0-{max.toPrecision(4)} T. Display patches sample actual P2 fields at centroids; they are not solver elements or exact material boundaries. Replay uses retained states only.</small>
  </section>;
}
function Field({frame,maximum}:{frame:GeometryPodField;maximum:number}) {
  const domains=Object.values(frame.snapshot.domains),points=domains.flatMap(d=>d.nodes_m),x=numericExtent(points.map(p=>p[0])),y=numericExtent(points.map(p=>p[1]));
  return <svg className="pod-field" viewBox={`${x.minimum} ${y.minimum} ${x.maximum-x.minimum} ${y.maximum-y.minimum}`} role="img" aria-label="Actual retained motor magnetic flux density samples">
    {domains.map((mesh,j)=>mesh.triangles.map((tri,k)=><polygon key={`${j}-${k}`} points={tri.map(i=>mesh.nodes_m[i].join(",")).join(" ")} fill={`hsl(${240-240*Math.hypot(...mesh.element_b_t[k])/maximum} 75% 48%)`}/>))}
  </svg>;
}
