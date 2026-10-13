// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
const NAME="spike-copper-selection-boundary";
/** Selection is a display overlay, not a field value or a change in copper geometry. */
export function updateCopperSelectionBoundary(mesh:THREE.Mesh,active:boolean,color:number) {
 let outline=mesh.getObjectByName(NAME) as THREE.LineSegments | undefined;
 if(!active) {
  if(outline){mesh.remove(outline);outline.geometry.dispose();(outline.material as THREE.Material).dispose();}
  return;
 }
 if(!outline) {
  const source=mesh.material as THREE.Material;
  outline=new THREE.LineSegments(new THREE.EdgesGeometry(mesh.geometry,15),new THREE.LineBasicMaterial({color,depthTest:false,depthWrite:false,transparent:true,opacity:1,toneMapped:false,clippingPlanes:source.clippingPlanes??undefined,clipIntersection:source.clipIntersection}));
  outline.name=NAME;outline.userData.selectionBoundary=true;outline.renderOrder=392;
  // Boundaries must never become raycast targets or alter the source selection.
  outline.raycast=()=>{};mesh.add(outline);
 }
 (outline.material as THREE.LineBasicMaterial).color.setHex(color);
}
export function copperSelectionOpacity(type:string|undefined,exact:boolean,resultActive:boolean) {
 if(resultActive)return exact?.18:.08;
 if(type==="zone")return exact?.52:.28;
 return exact?.96:.88;
}
