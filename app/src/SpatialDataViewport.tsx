// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { SpatialSample } from "./scriptDataViews";
import { physicalMaterialColor, type PhysicalGeometry } from "./scriptResultViewportModel";
import { numericMaximum } from "./numericRange";
import { RotateCcw } from "./icons";
import "./buttonStandard.css";

const magnitude = (sample: SpatialSample) => sample.vector_real
  ? Math.hypot(...sample.vector_real, ...(sample.vector_imag ?? [0, 0, 0]))
  : Math.hypot(sample.value_real ?? 0, sample.value_imag ?? 0);

export default function SpatialDataViewport({ samples, triangles, physicalModel, selected, onSelect }: { physicalModel?: PhysicalGeometry | null; samples: SpatialSample[]; triangles?: [number,number,number][]; selected: number[]; onSelect: (indices: number[]) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const [rendererError, setRendererError] = useState(""), [retry, setRetry] = useState(0);
  const selection = useRef(selected), select = useRef(onSelect), colorsRef = useRef<THREE.BufferAttribute | null>(null), valuesRef = useRef<number[]>([]);
  useEffect(() => { selection.current = selected; select.current = onSelect; const colors = colorsRef.current, values = valuesRef.current, maximum = Math.max(numericMaximum(values), Number.EPSILON); if (!colors) return; values.forEach((value, index) => { const color = new THREE.Color().setHSL(0.72 - 0.7 * Math.min(1, value / maximum), .8, selected.includes(index) ? .72 : .5); colors.setXYZ(index, color.r, color.g, color.b); }); colors.needsUpdate = true; }, [selected, onSelect]);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const scene = new THREE.Scene(); scene.background = new THREE.Color(0x15111e);
    const camera = new THREE.PerspectiveCamera(42, 1, 1e-9, 1e9);
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true }); }
    catch (error) { setRendererError(`3D preview unavailable: ${error instanceof Error ? error.message : String(error)}. No geometry was rendered; the admitted table and exports remain available.`); return; }
    setRendererError(""); renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); element.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement); controls.enableDamping = true;
    scene.add(new THREE.AmbientLight(0xffffff, 1));
    const positions = new Float32Array(samples.length * 3), colors = new Float32Array(samples.length * 3);
    const values = samples.map(magnitude), maximum = Math.max(numericMaximum(values), Number.EPSILON), box = new THREE.Box3(); valuesRef.current = values;
    samples.forEach((sample, index) => {
      positions.set([sample.x, sample.y, sample.z], index * 3); box.expandByPoint(new THREE.Vector3(sample.x, sample.y, sample.z));
      const color = new THREE.Color().setHSL(0.72 - 0.7 * Math.min(1, values[index] / maximum), 0.8, selection.current.includes(index) ? 0.72 : 0.5);
      colors.set(color.toArray(), index * 3);
    });
    const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3)); const colorAttribute = new THREE.BufferAttribute(colors, 3); colorsRef.current = colorAttribute; geometry.setAttribute("color", colorAttribute);
    let physicalSurface: THREE.Mesh | null = null;
    const physicalMaterials: THREE.MeshStandardMaterial[] = [];
    const regionEdges: THREE.LineSegments[] = [];
    const edgeMaterial = new THREE.LineBasicMaterial({ color: 0xdce8f1, transparent: true, opacity: .65 });
    if (physicalModel) {
      const physicalGeometry = new THREE.BufferGeometry();
      const vertices = physicalModel.view.vertices ?? [];
      physicalGeometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices.flat(), 3));
      physicalGeometry.setIndex((physicalModel.view.triangles ?? []).flat());
      physicalGeometry.computeVertexNormals();
      vertices.forEach(vertex => box.expandByPoint(new THREE.Vector3(...vertex)));
      const materialIndexes = new Map<number, number>();
      for (const region of physicalModel.regions) {
        const color = physicalMaterialColor(region.material);
        let materialIndex = materialIndexes.get(color);
        if (materialIndex === undefined) {
          materialIndex = physicalMaterials.length;
          materialIndexes.set(color, materialIndex);
          physicalMaterials.push(new THREE.MeshStandardMaterial({ color, side: THREE.DoubleSide, transparent: true,
            opacity: color === 0xc88743 ? .9 : .38, depthWrite: color === 0xc88743, roughness: .65, metalness: color === 0xc88743 ? .4 : 0 }));
        }
        physicalGeometry.addGroup(region.triangle_start * 3, region.triangle_count * 3, materialIndex);
        const regionGeometry = new THREE.BufferGeometry().setAttribute("position", physicalGeometry.getAttribute("position"));
        regionGeometry.setIndex((physicalModel.view.triangles ?? []).slice(region.triangle_start, region.triangle_start + region.triangle_count).flat());
        const edges = new THREE.LineSegments(new THREE.EdgesGeometry(regionGeometry), edgeMaterial);
        regionGeometry.dispose(); regionEdges.push(edges); scene.add(edges);
      }
      physicalSurface = new THREE.Mesh(physicalGeometry, physicalMaterials);
      scene.add(physicalSurface);
    }
    const extent = Math.max(box.getSize(new THREE.Vector3()).length(), 1e-9); camera.near = extent / 10000; camera.far = extent * 100; camera.updateProjectionMatrix();
    const points = new THREE.Points(geometry, new THREE.PointsMaterial({ size: extent / 130, vertexColors: true, sizeAttenuation: true })); scene.add(points);
    let surface: THREE.Mesh | null = null;
    const standalonePhysical = !!physicalModel && triangles === physicalModel.view.triangles;
    if (triangles?.length && !standalonePhysical) { const surfaceGeometry = geometry.clone(); surfaceGeometry.setIndex(triangles.flat()); surfaceGeometry.computeVertexNormals(); surface = new THREE.Mesh(surfaceGeometry, new THREE.MeshStandardMaterial({ color:0x8463a3, emissive:0x1c1127, side:THREE.DoubleSide, transparent:true, opacity:.72, roughness:.72, metalness:.08 })); scene.add(surface); }
    const vectorPositions: number[] = [];
    const span = extent, vectorScale = span / (maximum * 18);
    for (const sample of samples) if (sample.vector_real) vectorPositions.push(sample.x, sample.y, sample.z, sample.x + sample.vector_real[0] * vectorScale, sample.y + sample.vector_real[1] * vectorScale, sample.z + sample.vector_real[2] * vectorScale);
    let vectors: THREE.LineSegments | null = null;
    if (vectorPositions.length) { const vectorGeometry = new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(vectorPositions, 3)); vectors = new THREE.LineSegments(vectorGeometry, new THREE.LineBasicMaterial({ color: 0x8cebdd })); scene.add(vectors); }
    const center = box.isEmpty() ? new THREE.Vector3() : box.getCenter(new THREE.Vector3()); camera.position.copy(center).add(new THREE.Vector3(span, span * .75, span)); controls.target.copy(center); controls.update();
    const resize = () => { const width = Math.max(1, element.clientWidth), height = Math.max(1, element.clientHeight); renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix(); };
    const observer = new ResizeObserver(resize); observer.observe(element); resize();
    const raycaster = new THREE.Raycaster(); raycaster.params.Points!.threshold = span / 70; let down: [number, number] | null = null;
    const press = (event: PointerEvent) => { down = [event.clientX, event.clientY]; };
    const pick = (event: PointerEvent) => { if (!down || Math.hypot(event.clientX - down[0], event.clientY - down[1]) > 4) { down = null; return; } down = null; const rect = renderer.domElement.getBoundingClientRect(); raycaster.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -((event.clientY - rect.top) / rect.height * 2 - 1)), camera); const pointHit = raycaster.intersectObject(points)[0], faceHit = surface ? raycaster.intersectObject(surface)[0] : standalonePhysical && physicalSurface ? raycaster.intersectObject(physicalSurface)[0] : undefined; const index = pointHit?.index ?? faceHit?.face?.a; if (index !== undefined) select.current(event.ctrlKey || event.metaKey ? [...new Set([...selection.current, index])] : [index]); };
    renderer.domElement.addEventListener("pointerdown", press); renderer.domElement.addEventListener("pointerup", pick);
    let frame = 0; const render = () => { controls.update(); renderer.render(scene, camera); frame = requestAnimationFrame(render); }; render();
    return () => { colorsRef.current = null; cancelAnimationFrame(frame); observer.disconnect(); renderer.domElement.removeEventListener("pointerdown", press); renderer.domElement.removeEventListener("pointerup", pick); controls.dispose(); geometry.dispose(); (points.material as THREE.Material).dispose(); surface?.geometry.dispose(); (surface?.material as THREE.Material | undefined)?.dispose(); vectors?.geometry.dispose(); (vectors?.material as THREE.Material | undefined)?.dispose(); physicalSurface?.geometry.dispose(); physicalMaterials.forEach(material => material.dispose()); regionEdges.forEach(edges => edges.geometry.dispose()); edgeMaterial.dispose(); renderer.dispose(); renderer.domElement.remove(); };
  }, [samples, triangles, physicalModel, retry]);
  return <div className="spatial-data-viewport-shell"><div ref={host} className="spatial-data-viewport" role="img" aria-label="Interactive 3D spatial samples" />{rendererError && <div className="spatial-renderer-error" role="alert"><p>{rendererError}</p><button type="button" className="secondary-btn" aria-label="Retry 3D" onClick={() => setRetry(value => value + 1)}><RotateCcw size={15}/><span>Retry 3D</span></button></div>}</div>;
}
