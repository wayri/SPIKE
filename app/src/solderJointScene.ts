// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import type { ResolvedSolderJoint } from "./solderJointModel";
/** Authored low-poly display profiles; these are not reflow/contact solutions. */
export function solderJointGeometry(joint:ResolvedSolderJoint):THREE.BufferGeometry {
  const {pad,visual}=joint,n=24,h=visual.heightMm;
  const rx=pad.width/2+visual.spreadMm,ry=pad.height/2+visual.spreadMm;
  const drilled=pad.drill>0;
  const holeX=drilled?Math.max(pad.drill_size?.[0]??pad.drill,0)/2:0;
  const holeY=drilled?Math.max(pad.drill_size?.[1]??pad.drill,0)/2:0;
  const tipX=drilled?holeX+.04:Math.max(.02,pad.width*.20);
  const tipY=drilled?holeY+.04:Math.max(.02,pad.height*.20);
  const rings=drilled?[[rx,ry,0],[rx*.75+tipX*.25,ry*.75+tipY*.25,h*.16],[tipX,tipY,h],[holeX,holeY,h],[holeX,holeY,0]]:[[rx,ry,0],[rx*.76,ry*.76,h*.18],[tipX,tipY,h],[0,0,h],[0,0,0]];
  const positions:number[]=[],indices:number[]=[];
  rings.forEach(([x,y,z])=>{for(let i=0;i<n;i++){const angle=i*2*Math.PI/n,c=Math.cos(angle),s=Math.sin(angle);const exponent=visual.style==="smd-fillet"?.45:1;positions.push(Math.sign(c)*Math.abs(c)**exponent*x,Math.sign(s)*Math.abs(s)**exponent*y,z);}});
  for(let ring=0;ring<rings.length;ring++){const next=(ring+1)%rings.length;for(let i=0;i<n;i++){const j=(i+1)%n,a=ring*n+i,b=ring*n+j,c=next*n+i,d=next*n+j;indices.push(a,b,c,b,d,c);}}
  const geometry=new THREE.BufferGeometry();geometry.setAttribute("position",new THREE.Float32BufferAttribute(positions,3));geometry.setIndex(indices);if(joint.side<0){geometry.scale(1,1,-1);const index=geometry.getIndex()!;for(let i=0;i<index.count;i+=3){const b=index.getX(i+1);index.setX(i+1,index.getX(i+2));index.setX(i+2,b);}}geometry.computeVertexNormals();geometry.computeBoundingBox();return geometry;
}
export type SolderJointPlacement={joint:ResolvedSolderJoint;matrix:THREE.Matrix4;opacity:number};
/** Instanced by authored shape and opacity; owned resources are released by disposeScene. */
export function buildSolderJointScene(placements:readonly SolderJointPlacement[]):THREE.Group {
  const group=new THREE.Group();group.name="solder-connections";
  const batches=new Map<string,SolderJointPlacement[]>();
  for(const row of placements){const {pad,visual}=row.joint;const key=JSON.stringify([pad.width,pad.height,pad.drill,pad.drill_size,row.joint.side,visual.style,visual.heightMm,visual.spreadMm,row.opacity]);const batch=batches.get(key)??[];batch.push(row);batches.set(key,batch);}
  for(const rows of batches.values()){
    const material=new THREE.MeshStandardMaterial({color:0xb6bbc0,metalness:.78,roughness:.27,opacity:rows[0].opacity,transparent:rows[0].opacity<1,depthWrite:rows[0].opacity>=1,side:THREE.DoubleSide});
    const mesh=new THREE.InstancedMesh(solderJointGeometry(rows[0].joint),material,rows.length);
    rows.forEach((row,index)=>mesh.setMatrixAt(index,row.matrix));mesh.instanceMatrix.needsUpdate=true;
    mesh.userData={solderJointIds:rows.map(row=>row.joint.id),presentationOnly:true};
    // Pad selection remains on the authoritative board geometry underneath.
    mesh.raycast=()=>{};mesh.castShadow=true;group.add(mesh);
  }
  return group;
}
