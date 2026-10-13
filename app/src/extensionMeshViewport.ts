// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
export type ExtensionMesh = Record<string, unknown>;
/** Mesh display is a bounded subset of returned topology, never solver input. */
export function buildExtensionMeshScene(mesh: ExtensionMesh, transform: { centerX: number; centerY: number; scale: number; zOffsetMm: number }): THREE.Group {
  const group = new THREE.Group();
  group.name = "Extension mesh preview";
  if (!mesh || typeof mesh !== "object" || Array.isArray(mesh) || !transform || typeof transform !== "object") return group;
  const admission = mesh.admission as Record<string, unknown> | undefined;
  if (mesh.status !== "completed" || mesh.solved !== false || mesh.units !== "mm" || !(mesh.contract === "spike/gmsh-mesh/v1" ? mesh.coordinate_frame === "normalized_board_local_mm" : mesh.coordinate_frame === "design_top_copper")
      || !["unvalidated", "experimental"].includes(String(mesh.model_status))
      || admission?.contract !== "spike/extension-mesh-admission/v1" || admission.design_bound !== true
      || admission.complete_connectivity !== true || admission.physics_validated !== false || admission.cross_engine_reuse !== false
      || ![transform.centerX, transform.centerY, transform.scale, transform.zOffsetMm].every(Number.isFinite) || transform.scale <= 0) return group;
  const point = (p: number[]) => [(p[0]-transform.centerX)*transform.scale, (transform.centerY-p[1])*transform.scale, (p[2]+(mesh.contract === "spike/gmsh-mesh/v1" ? 0 : transform.zOffsetMm))*transform.scale];
  const representable = (p: number[]) => point(p).every(value => Number.isFinite(value) && Math.abs(value) <= 3.4e38);
  const vertices: number[] = [];
  let total = 0, shown = 0;
  if (["spike/emerge-mesh/v1", "spike/gmsh-mesh/v1"].includes(String(mesh.contract))) {
    const nodes = mesh.nodes_mm as number[][], tets = mesh.tetrahedra as number[][];
    if (!Array.isArray(nodes) || !Array.isArray(tets) || nodes.length < 4 || !tets.length || nodes.length > 100000 || tets.length > 200000
        || nodes.some(node => !Array.isArray(node) || node.length !== 3 || !node.every(Number.isFinite) || !representable(node))
        || tets.some(cell => !Array.isArray(cell) || cell.length !== 4 || new Set(cell).size !== 4 || cell.some(id => !Number.isInteger(id) || id < 0 || id >= nodes.length))) return group;
    total = tets.length;
    const stride = Math.max(1, Math.ceil(total/5000));
    for (let i=0; i<tets.length; i+=stride) {
      const cell=tets[i];
      for (const [a,b] of [[0,1],[0,2],[0,3],[1,2],[1,3],[2,3]]) vertices.push(...point(nodes[cell[a]]),...point(nodes[cell[b]]));
      shown++;
    }
  } else if (mesh.contract === "spike/openems-grid/v1") {
    const grid=mesh.lines_mm as Record<string,number[]>;
    if (!grid || ![grid.x,grid.y,grid.z].every(axis=>Array.isArray(axis)&&axis.length>=2&&axis.length<=100000&&axis.every(Number.isFinite)&&axis.every((value,i)=>i===0 || value>axis[i-1]))) return group;
    if (![0,grid.x.length-1].every(x=>[0,grid.y.length-1].every(y=>[0,grid.z.length-1].every(z=>representable([grid.x[x],grid.y[y],grid.z[z]]))))) return group;
    total=grid.x.length+grid.y.length+grid.z.length;
    const sample=(axis:number[])=>axis.filter((_,i)=>i%Math.max(1,Math.ceil(axis.length/128))===0 || i===axis.length-1);
    const [x,y,z]=[sample(grid.x),sample(grid.y),sample(grid.z)];
    const ends=(axis:number[])=>[axis[0],axis[axis.length-1]];
    // Returned Cartesian lines on domain faces; interior cells remain in full payload.
    for (const a of x) for (const b of ends(grid.y)) vertices.push(...point([a,b,grid.z[0]]),...point([a,b,grid.z[grid.z.length-1]]));
    for (const a of y) for (const b of ends(grid.z)) vertices.push(...point([grid.x[0],a,b]),...point([grid.x[grid.x.length-1],a,b]));
    for (const a of z) for (const b of ends(grid.x)) vertices.push(...point([b,grid.y[0],a]),...point([b,grid.y[grid.y.length-1],a]));
    shown=x.length+y.length+z.length;
  } else return group;
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute("position",new THREE.Float32BufferAttribute(vertices,3));
  group.add(new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:0xe6bc50,transparent:true,opacity:.4,depthWrite:false})));
  group.userData={extensionMesh:true,total,shown,displaySubset:true,solverInput:false};
  return group;
}
