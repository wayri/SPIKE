import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import "./emiChamber.css";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { buildEmiChamber, disposeEmiGeometry, emiCameraCommandView, emiCameraPose, placeEmiDut, type EmiCameraView, type EmiChamberSetup } from "./emiChamber";
import { interpolateEMergePattern, type EMergeAngularPattern } from "./emergePatternInterpolation";

type BenchDisplay = "visible" | "translucent" | "hidden";

const MAX_PATTERN_SAMPLES = 4096;

function validPattern(pattern: EMergeAngularPattern | undefined) {
  return Boolean(pattern && Number.isFinite(pattern.frequency_hz) && pattern.frequency_hz > 0 &&
    pattern.theta_deg.length >= 2 && pattern.phi_deg.length >= 2 &&
    pattern.theta_deg.length * pattern.phi_deg.length === pattern.relative_amplitude_db.length && pattern.relative_amplitude_db.length <= MAX_PATTERN_SAMPLES &&
    pattern.theta_deg.every(Number.isFinite) && pattern.phi_deg.every(Number.isFinite) && pattern.relative_amplitude_db.every(Number.isFinite));
}

/** Relative display only: it deliberately has no path back into EMI setup or solver parameters. */
function createRadiationOverlay(pattern: EMergeAngularPattern) {
  if (!validPattern(pattern)) return null;
  const positions: number[] = [], colors: number[] = [], indices: number[] = [];
  const color = new THREE.Color();
  for (let thetaIndex = 0; thetaIndex < pattern.theta_deg.length; thetaIndex++) {
    const theta = THREE.MathUtils.clamp(pattern.theta_deg[thetaIndex], 0, 180);
    for (let phiIndex = 0; phiIndex < pattern.phi_deg.length; phiIndex++) {
      const phi = THREE.MathUtils.euclideanModulo(pattern.phi_deg[phiIndex], 360);
      const db = THREE.MathUtils.clamp(pattern.relative_amplitude_db[thetaIndex * pattern.phi_deg.length + phiIndex], -80, 0);
      const magnitude = THREE.MathUtils.clamp((db + 40) / 40, 0, 1);
      const radius = .26 * 10 ** (db / 20);
      const thetaRadians = THREE.MathUtils.degToRad(theta), phiRadians = THREE.MathUtils.degToRad(phi);
      positions.push(radius * Math.sin(thetaRadians) * Math.cos(phiRadians), radius * Math.sin(thetaRadians) * Math.sin(phiRadians), radius * Math.cos(thetaRadians));
      color.setHSL((1 - magnitude) * .67, .9, .52); colors.push(color.r, color.g, color.b);
    }
  }
  for (let thetaIndex = 0; thetaIndex < pattern.theta_deg.length - 1; thetaIndex++) for (let phiIndex = 0; phiIndex < pattern.phi_deg.length - 1; phiIndex++) {
    const a = thetaIndex * pattern.phi_deg.length + phiIndex;
    indices.push(a, a + pattern.phi_deg.length, a + 1, a + 1, a + pattern.phi_deg.length, a + pattern.phi_deg.length + 1);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3)); geometry.setIndex(indices); geometry.computeVertexNormals();
  const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ vertexColors: true, transparent: true, opacity: .72, side: THREE.DoubleSide, depthWrite: false, roughness: .48, metalness: .05 }));
  mesh.name = "relative EMerge radiation pattern display";
  const root = new THREE.Group(); root.name = "EMerge relative radiation overlay (display only)"; root.add(mesh);
  return root;
}

export function EmiChamberWorkspace({ source, setup, onChange, dashboard, reviewOpen, onReview, onSetup, onPrepare, onRun, busy, canRun, hasBoard, sourceNote, cameraCommand = "", navigationMode, onNavigationModeChange, emergePatterns, emergeFrequencyIndex, onEmergeFrequencyIndexChange }: {
  source: THREE.Group | null; setup: EmiChamberSetup; onChange: (setup: EmiChamberSetup) => void;
  dashboard: ReactNode; reviewOpen: boolean; onReview: (open: boolean) => void;
  onSetup: () => void; onPrepare: () => void; onRun: () => void;
  busy: boolean; canRun: boolean; hasBoard: boolean;
  sourceNote?: string; cameraCommand?: string; navigationMode?: "orbit" | "pan"; onNavigationModeChange?: (mode: "orbit" | "pan") => void;
  emergePatterns?: EMergeAngularPattern[]; emergeFrequencyIndex?: number; onEmergeFrequencyIndexChange?: (index: number) => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [layout, setLayout] = useState<"split" | "tab">("split");
  const [view, setView] = useState<"chamber" | "dut">("chamber");
  const [cameraView, setCameraView] = useState<EmiCameraView>("isometric");
  const [localNavigation, setLocalNavigation] = useState<"orbit" | "pan">("orbit");
  const [benchDisplay, setBenchDisplay] = useState<BenchDisplay>("visible");
  const [localEmergeFrequencyIndex, setLocalEmergeFrequencyIndex] = useState(0);
  const navigation = navigationMode ?? localNavigation;
  const setNavigation = onNavigationModeChange ?? setLocalNavigation;
  const patternIndex = Math.min(Math.max(emergeFrequencyIndex ?? localEmergeFrequencyIndex, 0), Math.max((emergePatterns?.length ?? 1) - 1, 0));
  const setPatternIndex = onEmergeFrequencyIndexChange ?? setLocalEmergeFrequencyIndex;
  const solvedPattern = emergePatterns?.[patternIndex];
  const displayPattern = useMemo(() => {
    if (!solvedPattern) return undefined;
    try { return interpolateEMergePattern(solvedPattern, 5); }
    catch { return undefined; }
  }, [solvedPattern]);
  const [error, setError] = useState("");
  const [size, setSize] = useState("");
  const cameraState = useRef<{ position: THREE.Vector3; target: THREE.Vector3; up: THREE.Vector3; view: string }>();
  const cameraRef = useRef<THREE.PerspectiveCamera>();
  const controlsRef = useRef<OrbitControls>();
  const renderRef = useRef<() => void>();
  const frameCameraRef = useRef<(subject: "chamber" | "dut", nextCameraView: EmiCameraView) => void>();
  const benchMeshesRef = useRef<THREE.Mesh[]>([]);
  const benchDisplayRef = useRef<BenchDisplay>(benchDisplay); benchDisplayRef.current = benchDisplay;
  const viewRef = useRef(view); viewRef.current = view;
  const cameraViewRef = useRef(cameraView); cameraViewRef.current = cameraView;
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true }); }
    catch { setError("The chamber requires a WebGL-capable graphics device."); return; }
    setError("");
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x0c1722); renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.35;
    host.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xe2eeff, 0x718598, 2.5));
    const light = new THREE.DirectionalLight(0xffecd3, 3.5); light.position.set(-3, -4, 7); scene.add(light);
    const fill = new THREE.DirectionalLight(0x91bfff, 2); fill.position.set(4, 1, 5); scene.add(fill);
    const dut = new THREE.Group(); dut.name = "placed-device-under-test";
    if (source && hasBoard) dut.add(source);
    scene.add(dut);
    const bounds = placeEmiDut(dut, setup);
    const dutSize = bounds?.getSize(new THREE.Vector3()) ?? new THREE.Vector3(.2, .15, .1);
    setSize(bounds ? `${(dutSize.x * 1000).toFixed(1)} × ${(dutSize.y * 1000).toFixed(1)} × ${(dutSize.z * 1000).toFixed(1)} mm` : "Import a board or assembly to place the DUT");
    const chamber = buildEmiChamber(setup, dutSize); scene.add(chamber.root);
    const benchNames = new Set(["turntable", "nonconductive test table", "table leg"]);
    benchMeshesRef.current = [];
    chamber.root.traverse(object => { if (object instanceof THREE.Mesh && benchNames.has(object.name)) benchMeshesRef.current.push(object); });
    for (const mesh of benchMeshesRef.current) {
      const display = benchDisplayRef.current;
      mesh.visible = display !== "hidden";
      (Array.isArray(mesh.material) ? mesh.material : [mesh.material]).forEach(material => { material.transparent = display === "translucent"; material.opacity = display === "translucent" ? .28 : 1; material.depthWrite = display !== "translucent"; material.needsUpdate = true; });
    }
    const overlay = displayPattern ? createRadiationOverlay(displayPattern) : null;
    if (overlay && bounds) { overlay.position.copy(bounds.getCenter(new THREE.Vector3())); scene.add(overlay); }
    const camera = new THREE.PerspectiveCamera(42, 1, .001, 150); camera.up.set(0, 0, 1);
    const controls = new OrbitControls(camera, renderer.domElement); controls.enableDamping = false;
    cameraRef.current = camera; controlsRef.current = controls;
    controls.enablePan = true;
    controls.mouseButtons.LEFT = navigation === "pan" ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
    controls.mouseButtons.RIGHT = navigation === "pan" ? THREE.MOUSE.ROTATE : THREE.MOUSE.PAN;
    controls.minDistance = .02; controls.maxDistance = Math.max(40, chamber.length * 4);
    const render = (subject = viewRef.current) => {
      cameraState.current = { position: camera.position.clone(), target: controls.target.clone(), up: camera.up.clone(), view: subject };
      renderer.render(scene, camera);
    };
    renderRef.current = render;
    const frameCamera = (subject: "chamber" | "dut", nextCameraView: EmiCameraView) => {
      const target = subject === "dut" ? bounds?.getCenter(new THREE.Vector3()) ?? new THREE.Vector3(0, 0, setup.table_height_m) : chamber.center;
      const span = subject === "dut" ? Math.max(dutSize.length() * 2, .25) : chamber.length * 1.15;
      const pose = emiCameraPose(target, span, nextCameraView);
      camera.position.copy(pose.position); camera.up.copy(pose.up); controls.target.copy(target); controls.update(); render(subject);
    };
    frameCameraRef.current = frameCamera;
    if (cameraState.current?.view === viewRef.current) { camera.position.copy(cameraState.current.position); camera.up.copy(cameraState.current.up); controls.target.copy(cameraState.current.target); controls.update(); }
    else frameCamera(viewRef.current, cameraViewRef.current);
    const resize = () => {
      const width = host.clientWidth, height = host.clientHeight;
      if (!width || !height) return;
      renderer.setSize(width, height); camera.aspect = width / height; camera.updateProjectionMatrix(); render();
    };
    const onControlsChange = () => render();
    controls.addEventListener("change", onControlsChange);
    const observer = new ResizeObserver(resize); observer.observe(host); resize();
    const reset = () => frameCamera(viewRef.current, cameraViewRef.current);
    host.addEventListener("dblclick", reset);
    return () => {
      observer.disconnect(); host.removeEventListener("dblclick", reset); controls.removeEventListener("change", onControlsChange); controls.dispose();
      if (cameraRef.current === camera) { cameraRef.current = undefined; controlsRef.current = undefined; renderRef.current = undefined; frameCameraRef.current = undefined; }
      if (source) dut.remove(source);
      if (overlay) disposeEmiGeometry(overlay);
      benchMeshesRef.current = [];
      disposeEmiGeometry(chamber.root); renderer.dispose(); renderer.domElement.remove();
    };
  }, [source, setup, hasBoard, displayPattern]);
  useEffect(() => {
    for (const mesh of benchMeshesRef.current) {
      mesh.visible = benchDisplay !== "hidden";
      (Array.isArray(mesh.material) ? mesh.material : [mesh.material]).forEach(material => { material.transparent = benchDisplay === "translucent"; material.opacity = benchDisplay === "translucent" ? .28 : 1; material.depthWrite = benchDisplay !== "translucent"; material.needsUpdate = true; });
    }
    renderRef.current?.();
  }, [benchDisplay]);
  useEffect(() => {
    const controls = controlsRef.current;
    if (!controls) return;
    controls.mouseButtons.LEFT = navigation === "pan" ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
    controls.mouseButtons.RIGHT = navigation === "pan" ? THREE.MOUSE.ROTATE : THREE.MOUSE.PAN;
    controls.update(); renderRef.current?.();
  }, [navigation]);
  useEffect(() => {
    if (!cameraCommand) return;
    const requestedView = emiCameraCommandView(cameraCommand);
    if (requestedView) {
      setCameraView(requestedView); frameCameraRef.current?.(viewRef.current, requestedView);
      return;
    }
    if (cameraCommand.startsWith("fit")) {
      frameCameraRef.current?.(viewRef.current, cameraViewRef.current);
      return;
    }
    const camera = cameraRef.current, controls = controlsRef.current;
    if (!camera || !controls) return;
    if (cameraCommand.startsWith("pan-")) {
      camera.updateMatrixWorld(true);
      const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
      const up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
      const step = Math.max(camera.position.distanceTo(controls.target) * .12, .025);
      const delta = new THREE.Vector3();
      if (cameraCommand.startsWith("pan-left")) delta.addScaledVector(right, -step);
      if (cameraCommand.startsWith("pan-right")) delta.addScaledVector(right, step);
      if (cameraCommand.startsWith("pan-up")) delta.addScaledVector(up, step);
      if (cameraCommand.startsWith("pan-down")) delta.addScaledVector(up, -step);
      camera.position.add(delta); controls.target.add(delta);
    } else if (cameraCommand.startsWith("zoom-in")) {
      camera.position.lerp(controls.target, .2);
    } else if (cameraCommand.startsWith("zoom-out")) {
      camera.position.sub(controls.target).multiplyScalar(1.25).add(controls.target);
    } else return;
    controls.update(); renderRef.current?.();
  }, [cameraCommand]);
  const change = (patch: Partial<EmiChamberSetup>) => { cameraState.current = undefined; onChange({ ...setup, ...patch }); };
  const hasDut = Boolean(source && hasBoard);
  const frame = (subject: "chamber" | "dut", nextCameraView = cameraView) => {
    setView(subject); setCameraView(nextCameraView); frameCameraRef.current?.(subject, nextCameraView);
  };
  return <section className="emi-chamber-workspace" aria-label="EM virtual chamber workspace">
    <nav className="emi-chamber-nav" aria-label="EM workspace views">
      <button className={!reviewOpen ? "active" : ""} onClick={() => onReview(false)}>Chamber</button>
      <button className={reviewOpen ? "active" : ""} onClick={() => onReview(true)}>Results dashboard</button>
      <button onClick={onSetup}>Board / ports setup</button>
      <span />
      <label>Results layout<select value={layout} onChange={e => setLayout(e.target.value as typeof layout)}><option value="split">Split window</option><option value="tab">Full tab</option></select></label>
    </nav>
    <div className={`emi-chamber-content ${reviewOpen ? layout : "scene-only"}`}>
      <div className="emi-chamber-scene" style={reviewOpen && layout === "tab" ? { display: "none" } : undefined}>
        <div ref={hostRef} className="emi-chamber-canvas" aria-label="3D anechoic chamber, test table, DUT and receive antenna" />
        <div className="emi-chamber-title"><b>VIRTUAL ANECHOIC CHAMBER</b><span>{setup.distance_m} m · {setup.polarization} · {setup.azimuth_deg}°</span><small>{navigation === "orbit" ? "Orbit" : "Pan"}: left drag · Zoom: wheel · Fit: double-click</small>{validPattern(displayPattern) && <small className="emi-chamber-overlay-note">Relative EMerge radiation pattern · {(displayPattern!.frequency_hz / 1e9).toFixed(3)} GHz · 5° display interpolation of solved samples</small>}</div>
        <div className="emi-chamber-view" aria-label="Chamber navigation">
          <button onClick={() => frame("chamber")}>Fit chamber</button><button disabled={!hasDut} title={hasDut ? "Focus the placed device under test" : "Import a board or assembly to focus the DUT"} onClick={() => frame("dut")}>Focus DUT</button>
          <button className={cameraView === "top" ? "active" : ""} aria-pressed={cameraView === "top"} onClick={() => frame(view, "top")}>Top</button><button className={cameraView === "bottom" ? "active" : ""} aria-pressed={cameraView === "bottom"} onClick={() => frame(view, "bottom")}>Bottom</button><button className={cameraView === "isometric" ? "active" : ""} aria-pressed={cameraView === "isometric"} onClick={() => frame(view, "isometric")}>Isometric</button>
          <button className={navigation === "orbit" ? "active" : ""} aria-pressed={navigation === "orbit"} onClick={() => setNavigation("orbit")}>Orbit</button><button className={navigation === "pan" ? "active" : ""} aria-pressed={navigation === "pan"} onClick={() => setNavigation("pan")}>Pan</button>
        </div>
        <div className="emi-chamber-caption" role="status">{error || size}{sourceNote && <small>{sourceNote}</small>}<small>Scene preview · Absorbers, receiver and table are visual fixtures. The solver uses the prepared field domain.</small></div>
      </div>
      {reviewOpen && <div className="emi-chamber-results">{dashboard}</div>}
    </div>
    <div className="emi-chamber-controls" style={reviewOpen && layout === "tab" ? { display: "none" } : undefined}>
      <label>Distance (m)<select value={setup.distance_m} onChange={e => change({ distance_m: Number(e.target.value) })}>{[1, 3, 5, 10].map(v => <option key={v}>{v}</option>)}</select></label>
      <label>Table (m)<input type="number" min=".5" max="1.5" step=".05" value={setup.table_height_m} onChange={e => { const n = Number(e.target.value); if (n >= .5 && n <= 1.5) change({ table_height_m: n }); }} /></label>
      <label>Antenna (m)<input type="number" min="1" max="4" step=".1" value={setup.antenna_height_m} onChange={e => { const n = Number(e.target.value); if (n >= 1 && n <= 4) change({ antenna_height_m: n }); }} /></label>
      <label>Polarization<select value={setup.polarization} onChange={e => change({ polarization: e.target.value as EmiChamberSetup["polarization"] })}><option value="horizontal">Horizontal</option><option value="vertical">Vertical</option></select></label>
      <label>DUT orientation<select value={setup.orientation} onChange={e => change({ orientation: e.target.value as EmiChamberSetup["orientation"] })}><option value="flat">Flat</option><option value="upright">Upright</option><option value="side">On side</option></select></label>
      <label>Turntable {setup.azimuth_deg}°<input type="range" min="0" max="360" step="5" value={setup.azimuth_deg} onChange={e => change({ azimuth_deg: Number(e.target.value) })} /></label>
      <label>Floor<select value={setup.floor} onChange={e => change({ floor: e.target.value as EmiChamberSetup["floor"] })}><option value="absorber">Absorbers</option><option value="ground_plane">Ground plane</option></select></label>
      <label>Bench display<select value={benchDisplay} onChange={e => setBenchDisplay(e.target.value as BenchDisplay)} aria-label="Bench display only"><option value="visible">Visible</option><option value="translucent">Translucent</option><option value="hidden">Hidden</option></select></label>
      {emergePatterns && emergePatterns.length > 0 && <label>EMerge pattern<select value={patternIndex} onChange={e => setPatternIndex(Number(e.target.value))} aria-label="Solved EMerge radiation pattern frequency">{emergePatterns.map((pattern, index) => <option key={`${pattern.frequency_hz}-${index}`} value={index}>Solved {(pattern.frequency_hz / 1e9).toFixed(3)} GHz</option>)}</select></label>}
      <label className="emi-chamber-check"><input type="checkbox" checked={setup.cutaway} onChange={e => change({ cutaway: e.target.checked })} />Cutaway</label>
      <button disabled={!hasDut} title={hasDut ? "Place and focus the DUT on the table" : "Import a board or assembly to place a DUT"} onClick={() => { frame("dut"); onChange({ ...setup, orientation: "flat", azimuth_deg: 0 }); }}>Auto-place DUT</button>
      <button disabled={!hasBoard || busy} onClick={onPrepare}>Prepare scan</button>
      <button disabled={!canRun || busy} onClick={onRun}>{busy ? "Working…" : "Run field scan"}</button>
    </div>
  </section>;
}
