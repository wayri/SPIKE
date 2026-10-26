// SPDX-License-Identifier: Apache-2.0
import {useEffect, useMemo, useRef, useState} from "react";
import {mechanicalMeasurementCsv, measureMechanicalPoints, parseMeasurementPoint, type MechanicalMeasurementPoints, type MeasurementPoint} from "./mechanicalMeasurement";
import "./MechanicalMeasurementControls.css";

export interface MechanicalMeasurementControlsProps {
  /** A known anchor already transformed into assembly coordinates in mm. */
  selectedPoint?: MeasurementPoint;
  selectedLabel?: string;
  onMeasure?: (points: MechanicalMeasurementPoints | null) => void;
}
type PointDraft = [string, string, string];
const emptyPoint = (): PointDraft => ["", "", ""];

export function MechanicalMeasurementControls({selectedPoint, selectedLabel, onMeasure}: MechanicalMeasurementControlsProps) {
  const [a, setA] = useState<PointDraft>(emptyPoint);
  const [b, setB] = useState<PointDraft>(emptyPoint);
  const [sourceA, setSourceA] = useState("Manual coordinates");
  const [sourceB, setSourceB] = useState("Manual coordinates");
  const result = useMemo(() => {
    const pointA = parseMeasurementPoint(a), pointB = parseMeasurementPoint(b);
    if (!pointA || !pointB) return null;
    try { return measureMechanicalPoints(pointA, pointB); } catch { return null; }
  }, [a, b]);
  const measureCallback = useRef(onMeasure);
  useEffect(() => { measureCallback.current = onMeasure; }, [onMeasure]);
  useEffect(() => { measureCallback.current?.(result ? {pointA: result.pointA, pointB: result.pointB} : null); }, [result]);
  useEffect(() => () => { measureCallback.current?.(null); }, []);
  const selectionValid = selectedPoint?.length === 3 && selectedPoint.every(Number.isFinite);
  const hasInput = [...a, ...b].some(value => value.trim());
  const capture = (endpoint: "A" | "B") => {
    if (!selectionValid || !selectedPoint) return;
    const draft = selectedPoint.map(String) as PointDraft;
    if (endpoint === "A") { setA(draft); setSourceA(selectedLabel || "Selected object anchor"); }
    else { setB(draft); setSourceB(selectedLabel || "Selected object anchor"); }
  };
  const download = (format: "json" | "csv") => {
    if (!result) return;
    const content = format === "csv" ? mechanicalMeasurementCsv(result) : JSON.stringify({...result, sourceA, sourceB}, null, 2);
    const url = URL.createObjectURL(new Blob([content], {type: format === "csv" ? "text/csv;charset=utf-8" : "application/json"}));
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `spike-measurement.${format}`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };
  return <section className="mechanical-measurement" aria-label="Mechanical measurement">
    <h4>Measure distance</h4>
    <p>Assembly coordinates (mm). Enter points or use a selected object anchor. Anchors are not surface snaps.</p>
    {(["A", "B"] as const).map(endpoint => {
      const values = endpoint === "A" ? a : b;
      return <fieldset key={endpoint}>
        <legend>Point {endpoint}</legend>
        <div className="mechanical-measurement__coordinates">
          {(["X", "Y", "Z"] as const).map((axis, index) => <label key={axis}>{axis} (mm)
            <input type="number" step="any" value={values[index]} aria-label={`Point ${endpoint} ${axis} (mm)`} onChange={event => {
              const next = [...values] as PointDraft; next[index] = event.target.value;
              if (endpoint === "A") { setA(next); setSourceA("Manual coordinates"); }
              else { setB(next); setSourceB("Manual coordinates"); }
            }} />
          </label>)}
        </div>
        <button type="button" className="spike-control--compact" disabled={!selectionValid} title={selectedLabel ? `Use anchor of ${selectedLabel}` : "Select an object with a known assembly anchor"} onClick={() => capture(endpoint)}>Set {endpoint} from selection</button>
        <small title={endpoint === "A" ? sourceA : sourceB}>{endpoint === "A" ? sourceA : sourceB}</small>
      </fieldset>;
    })}
    <div aria-live="polite">
      {result ? <dl className="mechanical-measurement__result">
        <dt>Distance</dt><dd>{result.distance.toPrecision(8)} mm</dd>
        {(["X", "Y", "Z"] as const).map((axis, index) => <div key={axis}><dt>Δ{axis} (B − A)</dt><dd>{result.delta[index].toPrecision(8)} mm</dd></div>)}
      </dl> : <p>{hasInput ? "Complete both points with finite coordinates within the supported measurement range." : "Set points A and B to measure."}</p>}
    </div>
    <div className="mechanical-measurement__actions">
      <button type="button" className="spike-control--compact" disabled={!result} onClick={() => download("json")}>JSON</button>
      <button type="button" className="spike-control--compact" disabled={!result} onClick={() => download("csv")}>CSV</button>
      <button type="button" className="spike-control--compact" onClick={() => {setA(emptyPoint()); setB(emptyPoint()); setSourceA("Manual coordinates"); setSourceB("Manual coordinates");}}>Clear</button>
    </div>
  </section>;
}

