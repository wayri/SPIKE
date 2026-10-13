// SPDX-License-Identifier: Apache-2.0
import type { StudioFeedbackFrame } from "./studioFeedback";
import StudioCircuitSymbol from "./StudioCircuitSymbol";
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { CircuitBoard, ExternalLink, Focus, Link2, Search, ShieldCheck, ZoomIn, ZoomOut } from "./icons";
import type { ParsedBoard } from "./boardParser";
import type { BoardObject } from "./BoardViewport";
import { createSpiceAssignment, type SpiceWorkspace } from "./spiceWorkspace";
import { extractStudioBoardCircuit, studioBindingFingerprint, studioDesignDigest, type StudioBoardCircuit } from "./studioBoardCircuit";
import { isDesktopShell, runLocalWorker } from "./workerBridge";
import "./buttonStandard.css";
import "./StudioBoardCircuit.css";
export default function StudioBoardCircuitView({ board, design, workspace, onWorkspace, onSelect, onEditPins, onStatus, occurrenceId = "active-board", feedbackFrame }: {
    board: ParsedBoard | null;
    design: Record<string, unknown> | null;
    workspace: SpiceWorkspace;
    onWorkspace: (value: SpiceWorkspace) => void;
    onSelect?: (value: BoardObject) => void;
    onEditPins: (ref: string) => void;
    onStatus: (message: string) => void;
    occurrenceId?: string;
    feedbackFrame?: StudioFeedbackFrame | null;
}) {
    const [graph, setGraph] = useState<StudioBoardCircuit | null>(null), [digest, setDigest] = useState(""), [selected, setSelected] = useState(""), [query, setQuery] = useState(""), [modelId, setModelId] = useState(workspace.models[0]?.id ?? ""), [reviewed, setReviewed] = useState<Record<string, string>>({}), [busy, setBusy] = useState(false), [notice, setNotice] = useState("Auto-extract creates a placement-preserving connectivity drawing. Models and pin maps remain explicit."), [zoom, setZoom] = useState(1), [pan, setPan] = useState({ x: 0, y: 0 });
    const mounted = useRef(true), boardRef = useRef(board);
    boardRef.current = board;
    useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
    useEffect(() => { setGraph(null); setDigest(""); setReviewed({}); setSelected(""); }, [board, occurrenceId]);
    useEffect(() => { if (board && digest) {
        try {
            setGraph(extractStudioBoardCircuit(board, workspace, digest, occurrenceId, reviewed));
        }
        catch (error) {
            setNotice(String(error));
        }
    } }, [board, workspace, digest, reviewed, occurrenceId]);
    const extract = async () => { if (!board || !design || busy)
        return; setBusy(true); const source = board; try {
        let revision = await studioDesignDigest(design);
        if (isDesktopShell()) {
            const response = await runLocalWorker({ method: "prepare_studio_board_context", params: { design } });
            if (!response.ok)
                throw new Error(response.error ?? "Cannot bind this board revision");
            const context = response.result as {
                board_revision?: string;
            };
            if (!context.board_revision)
                throw new Error("Board context returned no revision");
            revision = context.board_revision;
        }
        if (!mounted.current || source !== boardRef.current)
            return;
        const result = extractStudioBoardCircuit(source, workspace, revision, occurrenceId, reviewed);
        setGraph(result);
        setDigest(revision);
        setZoom(1);
        setPan({ x: 0, y: 0 });
        setNotice(`${result.components.length} parts, ${result.nets.length} nets extracted. Positions are unchanged; wires are diagram routes, not extracted impedances.`);
    }
    catch (error) {
        setNotice(String(error));
    }
    finally {
        if (mounted.current)
            setBusy(false);
    } };
    const choose = (id: string) => { setSelected(id); const part = board?.components.find(row => row.id === id); if (part)
        onSelect?.({ id: part.id, type: "component", name: part.ref, ref: part.ref, position: part.at, layer: part.layer, occurrenceId }); };
    const part = graph?.components.find(row => row.id === selected), component = board?.components.find(row => row.id === selected), assignment = workspace.assignments.find(row => row.enabled && row.component_ref === part?.ref);
    const assign = () => { const model = workspace.models.find(row => row.id === modelId); if (!board || !component || !model)
        return; const created = createSpiceAssignment(board, component, model); onWorkspace({ ...workspace, assignments: [...workspace.assignments.filter(row => row.component_ref !== component.ref), created] }); setNotice("Assignment created. Review model values and every pin mapping before confirming this part."); };
    const handoff = async (launch: boolean) => { if (!graph || busy)
        return; setBusy(true); try {
        const response = await runLocalWorker({ method: launch ? "launch_spikes_studio" : "prepare_spikes_studio_handoff", params: { request: graph } });
        if (!response.ok)
            throw new Error(response.error ?? "Studio handoff failed");
        const result = response.result as {
            message?: string;
            path?: string; handoff_path?:string;
            status?: string;
        };
        setNotice(result.message ?? `${result.status ?? "Prepared"}: ${result.path ?? result.handoff_path ?? "Studio board circuit"}`);
        onStatus(result.message ?? "SPIKES Studio handoff prepared");
    }
    catch (error) {
        setNotice(String(error));
    }
    finally {
        if (mounted.current)
            setBusy(false);
    } };
    const width = Math.max(board?.width ?? 100, 1), height = Math.max(board?.height ?? 60, 1), unit = Math.max(width, height) / 400, extent = { x: (zoom > 1 && part ? part.placement.x_mm : (board?.bounds.minX ?? 0) + width / 2) - width * .55 / zoom + pan.x, y: (zoom > 1 && part ? part.placement.y_mm : (board?.bounds.minY ?? 0) + height / 2) - height * .55 / zoom + pan.y, width: width * 1.1 / zoom, height: height * 1.1 / zoom };
    const parts = graph?.components.filter(row => `${row.ref} ${row.value}`.toLowerCase().includes(query.toLowerCase())) ?? [];
    return <section className="studio-board-circuit" aria-label="Board circuit Studio">
  <div className="studio-circuit-toolbar"><button type="button" onClick={() => void extract()} disabled={!board || !design || busy}><CircuitBoard size={15}/>{busy ? "Preparing…" : "Auto-extract board"}</button><button type="button" disabled={!graph} onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}><Focus size={14}/>Fit</button><button type="button" disabled={!graph} aria-label="Zoom circuit in" onClick={() => setZoom(value => Math.min(12, value * 1.3))}><ZoomIn size={14}/></button><button type="button" disabled={!graph} aria-label="Zoom circuit out" onClick={() => setZoom(value => Math.max(.5, value / 1.3))}><ZoomOut size={14}/></button><button type="button" disabled={!graph || busy || !isDesktopShell()} onClick={() => void handoff(true)}><ExternalLink size={14}/>Open SPIKES Studio</button><button type="button" disabled={!graph || busy || !isDesktopShell()} onClick={() => void handoff(false)}>Prepare Studio file</button></div>
  <p className="studio-circuit-notice" role="status">{notice}</p>
  <div className="studio-circuit-grid"><aside><label className="studio-part-search"><Search size={14}/><input aria-label="Find board circuit part" placeholder="Find part…" value={query} onChange={event => setQuery(event.target.value)}/></label><div className="studio-part-list">{parts.slice(0, 1000).map(row => <button type="button" key={row.id} aria-pressed={row.id === selected} onClick={() => choose(row.id)}><b>{row.ref}</b><span>{row.value}</span><small>{row.model_binding.status === "reviewed" ? "Confirmed" : "Needs model / pin review"}</small></button>)}</div></aside>
   <div className="studio-circuit-drawing">{graph ? <svg onPointerDown={event => { if ((event.target as Element).closest("[role=button]"))
            return; event.currentTarget.setPointerCapture(event.pointerId); event.currentTarget.dataset.panX = String(event.clientX); event.currentTarget.dataset.panY = String(event.clientY); }} onPointerMove={event => { if (!event.currentTarget.hasPointerCapture(event.pointerId))
            return; const bounds = event.currentTarget.getBoundingClientRect(); const dx = event.clientX - Number(event.currentTarget.dataset.panX), dy = event.clientY - Number(event.currentTarget.dataset.panY); event.currentTarget.dataset.panX = String(event.clientX); event.currentTarget.dataset.panY = String(event.clientY); const scale = Math.max(extent.width / Math.max(bounds.width, 1), extent.height / Math.max(bounds.height, 1)); setPan(current => ({ x: current.x - dx * scale, y: current.y - dy * scale })); }} onPointerUp={event => { if (event.currentTarget.hasPointerCapture(event.pointerId))
            event.currentTarget.releasePointerCapture(event.pointerId); }} viewBox={`${extent.x} ${extent.y} ${extent.width} ${extent.height}`} role="img" aria-label="Circuit at original board component positions">
    {graph.wires.map((wire, index) => wire.style === "wire" ? <polyline key={index} points={wire.points_mm.map(point => point.join(",")).join(" ")} fill="none" stroke="var(--spike-table-choice)" strokeWidth={unit * .8}><title>{wire.label}</title></polyline> : <text key={index} x={wire.points_mm[0][0] + unit} y={wire.points_mm[0][1] - unit} fontSize={unit * 3.5} fill="var(--spike-table-edit)"><title>{wire.label}</title>{wire.label}</text>)}
    {graph.components.flatMap(row => row.pins.map(pin => <g key={`pin-${row.id}-${pin.id}`}><circle cx={pin.x_mm} cy={pin.y_mm} r={unit * .7} fill="var(--spike-table-choice)"><title>{`${row.ref}.${pin.pin}: ${pin.net_name}`}</title></circle>{selected === row.id && <text x={pin.x_mm + unit} y={pin.y_mm + unit * 2.5} fontSize={unit * 2.8} fill="var(--spike-table-text)">{pin.pin}</text>}</g>))}
    {graph.components.map(row => <g key={row.id} data-board-component={row.id} transform={`translate(${row.placement.x_mm} ${row.placement.y_mm})`} role="button" tabIndex={0} aria-label={`Select ${row.ref}: ${row.value}`} onClick={() => choose(row.id)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            choose(row.id);
        } }}><rect x={-unit * 6} y={-unit * 8} width={unit * 12} height={unit * 16} rx={unit} fill={selected === row.id ? "var(--spike-table-choice-bg)" : "var(--spike-table-surface)"} stroke={row.model_binding.status === "reviewed" ? "var(--spike-table-edit)" : "var(--spike-table-focus)"} strokeWidth={unit}/><StudioCircuitSymbol part={row} unit={unit}/>{feedbackFrame?.temperature_k[`thermal_${row.id}`] !== undefined && <text x={unit * 7} y={0} fill="var(--spike-table-focus)" fontSize={unit * 3.5}>{(feedbackFrame.temperature_k[`thermal_${row.id}`] - 273.15).toFixed(2)} °C lumped</text>}<title>{`${row.ref} ${row.value}; ${row.placement.x_mm}, ${row.placement.y_mm} mm; ${row.pins.length} pins`}</title></g>)}
   </svg> : <p>Load a board and choose Auto-extract board.</p>}</div>
   <aside className="studio-part-inspector">{part ? <><h3>{part.ref}</h3><p>{part.value}</p><small>{part.placement.x_mm.toFixed(3)}, {part.placement.y_mm.toFixed(3)} mm · {part.placement.side}</small><label>Simulation model<select aria-label="Board part simulation model" value={modelId} onChange={event => setModelId(event.target.value)}>{workspace.models.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label><button type="button" onClick={assign}><Link2 size={14}/>Assign model</button><button type="button" disabled={!assignment} onClick={() => onEditPins(part.ref)}>Edit model and pins</button><label><input type="checkbox" checked={part.model_binding.status === "reviewed"} disabled={!assignment} onChange={event => setReviewed(current => { const next = { ...current }; if (event.target.checked)
        next[part.ref] = studioBindingFingerprint(workspace, part.ref);
    else
        delete next[part.ref]; return next; })}/><ShieldCheck size={14}/>I checked this model and its pin map</label><table><thead><tr><th>Pin</th><th>Board net</th></tr></thead><tbody>{part.pins.map(pin => <tr key={pin.id}><td>{pin.pin}</td><td>{pin.net_name}</td></tr>)}</tbody></table></> : <p>Select a board part to bind its model and inspect pins.</p>}</aside>
  </div><footer>Exact component centers and connectivity are retained. Display wires are simplified; crossings do not establish connections. Unreviewed parts are context only and cannot become executable Studio devices.</footer>
 </section>;
}
