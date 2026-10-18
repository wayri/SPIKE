// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { Copy, FileOutput, Layers3, Spline, X } from "./icons";
import type { ParsedBoard, ParsedBendLine } from "./boardParser";
import PlotlyChart from "./PlotlyChart";
import DataTable from "./DataTable";
import { usePanelPresentation } from "./panelPresentation";
import "./FlexBoardManager.css";

const number = (value?: number) => value === undefined ? "Unspecified" : `${Number(value.toPrecision(7))}`;
export function kikakukaBendAnnotation(bend: ParsedBendLine): string | null {
  if (bend.angleDeg === undefined || !Number.isFinite(bend.angleDeg)) return null;
  if (bend.radiusMm === undefined || !Number.isFinite(bend.radiusMm) || bend.radiusMm < 0) return null;
  if (bend.annotation?.trim()) return bend.annotation.trim();
  return `a=${bend.angleDeg} r=${bend.radiusMm}mm`;
}
type Props = { board: ParsedBoard | null; onClose: () => void; onStatus: (message: string) => void; onShowLayers: (layers: string[]) => void; onOpenFolding?:()=>void };
export default function FlexBoardManager({ board, onClose, onStatus, onShowLayers, onOpenFolding }: Props) {
  const { ownerDocument, ownerWindow } = usePanelPresentation();
  const [selected, setSelected] = useState(0), [notice, setNotice] = useState("");
  const close = useRef<HTMLButtonElement>(null), dialog = useRef<HTMLElement>(null);
  useEffect(() => { const previous = ownerDocument?.activeElement as HTMLElement | null; close.current?.focus(); return () => { if (previous?.isConnected) previous.focus(); }; }, [ownerDocument]);
  const bends = board?.bendLines ?? [], regions = board?.regions ?? [], bend = bends[selected], annotation = bend ? kikakukaBendAnnotation(bend) : null;
  const { data, curveBends } = useMemo(() => {
    const traces: Record<string, unknown>[] = [], ids: (number | null)[] = [];
    for (const [index, loop] of (board?.outlineLoops ?? []).entries()) { const points = loop.length ? [...loop, loop[0]] : [];
      traces.push({ type: "scatter", mode: "lines", name: `Board outline ${index + 1}`, x: points.map(point => point[0]), y: points.map(point => point[1]), line: { color: "#8597a8", width: 1.5 }, hovertemplate: "X %{x:.6g} mm<br>Y %{y:.6g} mm<extra>Outline</extra>" }); ids.push(null); }
    for (const [index, item] of bends.entries()) {
      traces.push({ type: "scatter", mode: "lines+markers", name: `Bend ${index + 1}`, x: item.points.map(point => point[0]), y: item.points.map(point => point[1]), line: { color: index === selected ? "#d9a5fa" : "#80bcc0", width: index === selected ? 3 : 1.5, dash: "dash" }, hovertemplate: "X %{x:.6g} mm<br>Y %{y:.6g} mm<extra>Bend definition</extra>" }); ids.push(index);
    }
    return { data: traces, curveBends: ids };
  }, [board, selected]);
  const copy = async () => {
    if (!annotation) return;
    try { await navigator.clipboard.writeText(annotation); setNotice("Annotation copied. Place KiCad text within 0.1 mm of the bend line endpoint on the FreekiCAD layer."); }
    catch { setNotice(`Clipboard unavailable. Copy this annotation: ${annotation}`); }
  };
  const exportDefinition = () => {
    if (!board) return;
    const packet = { contract: "spike/flex-review/v1", technology: board.technology ?? "rigid", coordinate_frame: "flat_fabrication_reference", units: "mm", regions, bends, issues: board.flexIssues ?? [], deformed_geometry: false };
    if (!ownerDocument) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(packet, null, 2)], { type: "application/json" })), link = ownerDocument.createElement("a");
    link.href = url; link.download = "flex-board-review.json"; link.click(); if (ownerWindow) ownerWindow.setTimeout(() => URL.revokeObjectURL(url), 1000); else setTimeout(() => URL.revokeObjectURL(url), 1000); onStatus("Flex definitions exported with their flat-reference coordinate frame.");
  };
  return <div className="modal-shade"><section ref={dialog} className="flex-board-manager" role="dialog" aria-modal="true" aria-labelledby="flex-board-title" onKeyDown={event => { event.stopPropagation(); if (event.key === "Escape") onClose();
    if (event.key === "Tab") { const items = [...(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled),select,input,textarea,[tabindex='0']") ?? [])], index = items.indexOf(ownerDocument?.activeElement as HTMLElement); if (event.shiftKey && index <= 0 || !event.shiftKey && index === items.length - 1) { event.preventDefault(); items[event.shiftKey ? items.length - 1 : 0]?.focus(); } }
  }}>
    <header><div><Spline size={22}/><h2 id="flex-board-title">Flex PCB manager</h2></div><button ref={close} onClick={onClose} aria-label="Close flex PCB manager"><X size={18}/></button></header>
    <p>Review imported flex regions and bend definitions. KiKakuka boards use a user layer named <b>FreekiCAD</b>, with line segments and nearby <code>a=angle r=radius</code> or <code>a=angle s=span</code> text.</p>
    {onOpenFolding && <button type="button" onClick={onOpenFolding}><Spline size={15}/>Open sheet and flex folding</button>}
    <div className="flex-board-actions"><button onClick={() => onShowLayers([...new Set([...bends.map(item => item.sourceLayer), ...regions.map(item => item.sourceLayer)])])} disabled={!board || !bends.length && !regions.length}><Layers3 size={15}/>Show definition layers</button><button onClick={exportDefinition} disabled={!board}><FileOutput size={15}/>Export definitions</button><span>{board ? `${board.technology ?? "rigid"} · ${bends.length} bends · ${regions.length} regions` : "Import a board to review its flex definitions."}</span></div>
    <div className="flex-board-content"><div className="flex-board-plan">{board ? <PlotlyChart title="Flat fabrication reference and bend definitions" data={data} revision={`flex-plan:${board.width}:${board.height}:${bends.map(item => item.id).join(",")}`} layout={{ xaxis: { title: "Board X (mm)" }, yaxis: { title: "Board Y (mm)", autorange: "reversed" }, margin: { l: 58, r: 20, t: 32, b: 48 }, showlegend: false }} onPointClick={point => { const index = curveBends[point.curveNumber]; if (index !== null && index !== undefined) setSelected(index); }}/>: <p>No board is loaded.</p>}</div>
    <div className="flex-board-details"><h3>Bend definitions</h3>{bends.length ? <DataTable label="Imported flex bend definitions"><thead><tr><th>Bend</th><th>Angle (deg)</th><th>Radius (mm)</th><th>Span (mm)</th><th>Layer</th></tr></thead><tbody>{bends.map((item, index) => <tr key={item.id} aria-selected={index === selected}><td><button aria-pressed={index === selected} onClick={() => setSelected(index)} title={item.name}>Bend {index + 1}</button></td><td>{number(item.angleDeg)}</td><td>{number(item.radiusMm)}</td><td>{number(item.spanMm)}</td><td title={item.sourceLayerUserName ?? item.sourceLayer}>{item.sourceLayerUserName ?? item.sourceLayer}</td></tr>)}</tbody></DataTable>:<p>No bend lines were imported. A line on FreekiCAD can be retained without an annotation and configured in KiKakuka.</p>}
      {bend && <div className="flex-board-bend"><b>{bend.name}</b><p>{bend.points.map(point => `(${number(point[0])}, ${number(point[1])}) mm`).join(" → ")}</p><code>{annotation ?? "Angle and radius are not both specified."}</code><button onClick={() => void copy()} disabled={!annotation}><Copy size={14}/>Copy KiKakuka annotation</button></div>}
      {bend?.issues?.length ? <ul aria-label="Bend import diagnostics">{bend.issues.map((issue, index) => <li key={index}>{issue.message}</li>)}</ul> : null}
      <h3>Regions and stiffeners</h3>{regions.length ? <ul>{regions.map(item => <li key={item.id}><b>{item.name}</b> · {item.kind} · {item.sourceLayer}</li>)}</ul>:<p>No explicit regions were imported.</p>}
      {!!board?.flexIssues?.length && <details><summary>All flex import diagnostics ({board.flexIssues.length})</summary><ul aria-label="All flex import diagnostics">{board.flexIssues.map((issue, index) => <li key={index}><b>{issue.severity}</b> · {issue.message}</li>)}</ul></details>}
    </div></div>
    <p className="flex-board-boundary">The board view and solver geometry remain the flat fabrication reference. Bend definitions do not establish folded MCAD geometry or validate an RF solve on a bent board. Use the native KiKakuka/FreeCAD workflow for a folded model and review the solver’s geometry support before analysis.</p>
    {notice && <p role="status">{notice}</p>}
  </section></div>;
}
