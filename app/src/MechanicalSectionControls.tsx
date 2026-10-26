// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useState } from "react";
import type { AssemblySection } from "./mcadAssembly";
import { MECHANICAL_SECTION_PRESETS, mechanicalSectionThroughPoint, primaryMechanicalSectionPlane, sectionAnglesFromNormal, sectionNormalFromAngles, updateMechanicalSectionPlane } from "./mechanicalSectionModel";
import "./buttonStandard.css";
import "./MechanicalSectionControls.css";

export interface MechanicalSectionControlsProps {
  expanded?: boolean;
  section: AssemblySection;
  onChange: (section: AssemblySection) => void;
  onManage?: () => void;
  /** Selected part origin in assembly mm; absent when no reliable origin is available. */
  anchorPoint?: readonly [number, number, number];
}

export default function MechanicalSectionControls({ section, onChange, onManage, anchorPoint, expanded=false }: MechanicalSectionControlsProps) {
  const plane = primaryMechanicalSectionPlane(section);
  const angles = sectionAnglesFromNormal(plane.normal);
  const throughSelection = anchorPoint ? mechanicalSectionThroughPoint(section, anchorPoint) : null;
  const [azimuth, setAzimuth] = useState(String(angles.azimuth));
  const [elevation, setElevation] = useState(String(angles.elevation));
  const [offset, setOffset] = useState(String(plane.offsetMm));
  const [error, setError] = useState("");
  const helpId = useId();
  useEffect(() => { setAzimuth(String(angles.azimuth)); setElevation(String(angles.elevation)); setOffset(String(plane.offsetMm)); setError(""); }, [angles.azimuth, angles.elevation, plane.offsetMm]);
  const apply = () => {
    if (![azimuth, elevation, offset].every(value => value.trim() && Number.isFinite(Number(value)))) { setError("Enter finite angles and an offset in mm."); return; }
    try { onChange(updateMechanicalSectionPlane(section, { normal: sectionNormalFromAngles(Number(azimuth), Number(elevation)), offsetMm: Number(offset) })); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Check the section angles."); }
  };
  return <details className="mechanical-section-controls" open={expanded||undefined}>
    <summary hidden={expanded}>Cross section <span>{section.enabled ? section.mode === "box" ? "Box" : section.mode === "planes" && section.planes.length > 1 ? `${section.planes.length} planes` : "On" : "Off"}</span></summary>
    <div className="mechanical-section-body">
      <div className="mechanical-section-actions">
        <label><input type="checkbox" checked={section.enabled} onChange={event => onChange({ ...section, enabled: event.target.checked })} /> Enable section</label>
        {onManage && <button type="button" className="spike-control--compact" onClick={onManage}>Box / multiple planes</button>}
      </div>
      {section.mode === "box" && <p>Box clipping is active. Editing a plane control switches to plane clipping.</p>}
      {section.mode === "planes" && section.planes.length > 1 && <p>Editing first plane; other planes remain active according to their manager settings.</p>}
      <div className="mechanical-section-presets" role="group" aria-label="Section orientation presets">
        {MECHANICAL_SECTION_PRESETS.map(preset => <button type="button" className="spike-control--compact" key={preset.label} title={`Set section normal: ${preset.normal.map(value => value.toFixed(3)).join(", ")}`} onClick={() => onChange(updateMechanicalSectionPlane(section, { normal: preset.normal }))}>{preset.label}</button>)}
      </div>
      <div className="mechanical-section-fields" aria-describedby={helpId}>
        <label>Azimuth (deg)<input type="number" step="any" value={azimuth} onChange={event => setAzimuth(event.target.value)} /></label>
        <label>Elevation (deg)<input type="number" step="any" min={-90} max={90} value={elevation} onChange={event => setElevation(event.target.value)} /></label>
        <label>Offset (mm)<input type="number" step="any" value={offset} onChange={event => setOffset(event.target.value)} /></label>
      </div>
      <div className="mechanical-section-actions">
        <label><input type="checkbox" checked={plane.enabled} onChange={event => onChange(updateMechanicalSectionPlane(section, { enabled: event.target.checked }))} /> First plane enabled</label>
        <label><input type="checkbox" checked={plane.flipped} onChange={event => onChange(updateMechanicalSectionPlane(section, { flipped: event.target.checked }))} /> Flip retained side</label>
        <button type="button" className="spike-control--compact" onClick={apply}>Apply angles / offset</button>
        <button type="button" className="spike-control--compact" disabled={!throughSelection} title="Move the applied first plane through the selected part origin and enable clipping" onClick={() => { if (throughSelection) { onChange(throughSelection); setError(""); } }}>Through selection</button>
      </div>
      {error && <p role="alert">{error}</p>}
      <p id={helpId}>Normal angles: azimuth +X toward +Y; elevation XY toward +Z. Offset is signed distance from the assembly origin along the normal. The 45 presets bisect the named axes.</p>
      <p>Viewport clipping only; cuts are uncapped and do not create an exact BREP section.</p>
    </div>
  </details>;
}


