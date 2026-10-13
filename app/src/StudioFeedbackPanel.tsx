// SPDX-License-Identifier: Apache-2.0
import { studioBindingFingerprint } from "./studioBoardCircuit";
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { Play, Square, ListChecks, FileOutput, Thermometer } from "./icons";
import type { ParsedBoard } from "./boardParser";
import type { SpiceWorkspace, SpiceNetlistPreview } from "./spiceWorkspace";
import type { AssemblyAnalysisScope, AssemblyWorkload } from "./assemblyAdmission";
import { isDesktopShell, runLocalWorker, cancelLocalWorker, cancelLocalWorkerCleanup, subscribeWorkerProgress, saveNativeTextFile } from "./workerBridge";
import { buildStudioFeedbackRequest, defaultStudioFeedback, type StudioFeedbackSetup, type StudioThermalBinding, type StudioFeedbackFrame, type StudioFeedbackResult } from "./studioFeedback";
import InteractivePlot from "./InteractivePlot";
import "./StudioFeedbackPanel.css";
type Props = {
    board: ParsedBoard | null;
    design: Record<string, unknown> | null;
    workspace: SpiceWorkspace;
    onWorkspace: (workspace: SpiceWorkspace) => void;
    onBusy: (busy: boolean) => void;
    onRequireAdmission: (workload: AssemblyWorkload) => Promise<AssemblyAnalysisScope | null>;
    onStatus: (message: string) => void;
    onFrame?: (frame: StudioFeedbackFrame | null) => void;
};
export default function StudioFeedbackPanel({ board, design, workspace, onWorkspace, onBusy, onRequireAdmission, onStatus, onFrame }: Props) {
    const setup = workspace.studio_feedback ?? defaultStudioFeedback(), [busy, setBusy] = useState(false), [notice, setNotice] = useState("Enter measured or documented thermal parameters for each assigned resistor. Geometry feedback is optional and explicit."), [frames, setFrames] = useState<StudioFeedbackFrame[]>([]), [result, setResult] = useState<StudioFeedbackResult | null>(null);
    const active = useRef<string | null>(null), current = useRef({ design, workspace }), mounted = useRef(true);
    current.current = { design, workspace };
    useEffect(() => { mounted.current = true; return () => { mounted.current = false; if (active.current)
        void cancelLocalWorkerCleanup(active.current); }; }, []);
    useEffect(() => { if (active.current) {
        void cancelLocalWorkerCleanup(active.current);
        active.current = null;
        setBusy(false);
        onBusy(false);
        setNotice("Board or model changed: previous run cancelled and its results discarded.");
    } setFrames([]); setResult(null); onFrame?.(null); }, [design, workspace]);
    const set = (patch: Partial<StudioFeedbackSetup>) => { if (busy)
        return; onWorkspace({ ...workspace, studio_feedback: { ...setup, ...patch } }); };
    const resistors = workspace.assignments.filter(row => row.enabled && workspace.models.find(model => model.id === row.model_id)?.primitive === "resistor");
    const rowFor = (reference: string): StudioThermalBinding => setup.bindings.find(row => row.reference === reference) ?? { reference, capacitance: "", thermalResistance: "", tcr: "", referenceTemperature: "", initialTemperature: "", minimumTemperature: "", maximumTemperature: "", confirmed: false };
    const patch = (reference: string, changes: Partial<StudioThermalBinding>) => set({ bindings: [...setup.bindings.filter(row => row.reference !== reference), { ...rowFor(reference), ...changes }] });
    const run = async (execute: boolean) => {
        if (!design || !board || busy)
            return;
        const id = crypto.randomUUID(), source = { design, workspace };
        active.current = id;
        setBusy(true);
        onBusy(true);
        setResult(null);
        setFrames([]);
        let unsubscribe: (() => void) | undefined;
        try {
            const scope = await onRequireAdmission(setup.mode === "steady_state" ? "pi_dc" : "pi_ac");
            if (!scope)
                throw new Error("Board analysis admission was not granted");
            const context = await runLocalWorker({ method: "prepare_studio_board_context", params: { design } });
            if (!context.ok)
                throw new Error(context.error ?? "Board context failed");
            const couplingWorkspace: SpiceWorkspace = { ...workspace, analysis: setup.mode === "steady_state" ? { mode: "operating_point" } : { mode: "transient", time_step_s: Number(setup.electricalStep), stop_time_s: Number(setup.stopTime) } };
            const composed = await runLocalWorker({ method: "compose_spice_workspace", params: { design, workspace: couplingWorkspace, assembly_scope: scope } });
            if (!composed.ok)
                throw new Error(composed.error ?? "Circuit composition failed");
            const request = buildStudioFeedbackRequest(board, workspace, composed.result as unknown as SpiceNetlistPreview, String(context.result?.board_revision ?? ""), setup);
            if (active.current !== id || current.current.design !== source.design || current.current.workspace !== source.workspace)
                return;
            if (execute)
                unsubscribe = await subscribeWorkerProgress(progress => { if (progress.operationId !== id || active.current !== id || !mounted.current)
                    return; const frame = (progress.frame.accepted_frame ?? progress.frame) as unknown as StudioFeedbackFrame; if (typeof frame.time_s === "number" && frame.temperature_k && frame.electrical) {
                    setFrames(previous => [...previous.slice(-1999), frame]);
                    onFrame?.(frame);
                } });
            setNotice(execute ? "Running coupled electrical and thermal windows…" : "Validating feedback contract…");
            const response = await runLocalWorker({ id, method: execute ? "run_studio_board_cosimulation" : "validate_studio_board_cosimulation", params: { design, request, assembly_scope: scope } });
            if (active.current !== id || !mounted.current)
                return;
            if (!response.ok)
                throw new Error(response.error ?? "Feedback worker failed");
            if (execute) {
                const next = response.result as unknown as StudioFeedbackResult;
                setResult(next);
                setFrames(next.frames ?? []);
                onFrame?.(next.frames?.[next.frames.length - 1] ?? null);
                setNotice(`Feedback run: ${next.status} (${next.model_status}). Only accepted windows are shown.`);
                onStatus(`Studio feedback: ${next.status}`);
            }
            else {
                const admission = response.result as {
                    status?: string;
                    issues?: {
                        message: string;
                    }[];
                };
                setNotice(`${admission.status ?? "Unknown admission"}: ${(admission.issues ?? []).map(issue => issue.message).join("; ") || "Circuit, board bindings and supplied model ranges accepted."}`);
            }
        }
        catch (error) {
            if (active.current === id && mounted.current)
                setNotice(String(error));
        }
        finally {
            unsubscribe?.();
            if (active.current === id) {
                active.current = null;
                if (mounted.current)
                    setBusy(false);
                onBusy(false);
            }
        }
    };
    const stop = async () => { const id = active.current; if (!id)
        return; setNotice("Stopping feedback worker…"); await cancelLocalWorker(id); };
    const latest = frames[frames.length - 1], times = frames.map(frame => frame.time_s), nodeIds = Object.keys(latest?.temperature_k ?? {}), elements = Object.keys(latest?.electrical.resistance_ohm ?? {});
    return <section className="studio-feedback" aria-label="Studio thermal and geometry feedback"><header><Thermometer size={16}/><b>Electrical / thermal feedback</b><span>Board-bound lumped model</span></header>
 <fieldset disabled={busy}><div className="studio-feedback-controls"><label>Behavior<select value={setup.mode} onChange={event => set({ mode: event.target.value as StudioFeedbackSetup["mode"] })}><option value="transient">Transient electrical + thermal</option><option value="steady_state">Coupled steady state</option></select></label><label>Ambient (K)<input type="number" value={setup.ambient} onChange={event => set({ ambient: event.target.value })}/></label><label>Stop time (s)<input type="number" value={setup.stopTime} onChange={event => set({ stopTime: event.target.value })}/></label><label>Coupling window (s)<input type="number" value={setup.window} onChange={event => set({ window: event.target.value })}/></label><label>Electrical step (s)<input type="number" value={setup.electricalStep} onChange={event => set({ electricalStep: event.target.value })}/></label></div>
 <p>Resistor losses heat the assigned thermal nodes. Temperature updates resistance before the next accepted window. Optional conductor expansion updates its dimensions and resistance; nominal geometry resistance must match the circuit.</p>
 <div className="studio-feedback-bindings">{resistors.map(assignment => { const row = rowFor(assignment.component_ref); return <article key={assignment.id}><b>{assignment.component_ref}</b><div className="studio-feedback-controls">{([["capacitance", "Heat capacity (J/K)"], ["thermalResistance", "To ambient (K/W)"], ["tcr", "TCR (1/K)"], ["referenceTemperature", "Reference (K)"], ["initialTemperature", "Initial (K)"], ["minimumTemperature", "Model minimum (K)"], ["maximumTemperature", "Model maximum (K)"]] as const).map(([key, label]) => <label key={key}>{label}<input type="number" value={row[key]} onChange={event => patch(row.reference, { [key]: event.target.value, confirmed: false })}/></label>)}</div><label><input type="checkbox" checked={Boolean(row.geometry)} onChange={event => patch(row.reference, { geometry: event.target.checked ? { length: "", width: "", thickness: "", resistivity: "", expansion: "" } : undefined, confirmed: false })}/>Explicit conductor geometry feedback</label>{row.geometry && <div className="studio-feedback-controls">{([["length", "Length (m)"], ["width", "Width (m)"], ["thickness", "Thickness (m)"], ["resistivity", "Resistivity (ohm m)"], ["expansion", "Expansion (1/K)"]] as const).map(([key, label]) => <label key={key}>{label}<input type="number" value={row.geometry![key]} onChange={event => patch(row.reference, { geometry: { ...row.geometry!, [key]: event.target.value }, confirmed: false })}/></label>)}</div>}<label><input type="checkbox" checked={row.confirmed && row.confirmation === studioBindingFingerprint(workspace, row.reference)} onChange={event => patch(row.reference, { confirmed: event.target.checked, confirmation: studioBindingFingerprint(workspace, row.reference) })}/>I reviewed this part's model, pins and thermal/material values</label></article>; })}</div>
 {!resistors.length && <p>Assign resistor models under Parts &amp; pins to create board thermal bindings.</p>}<label><input type="checkbox" checked={setup.losslessConfirmed} onChange={event => set({ losslessConfirmed: event.target.checked })}/>I accept ideal R/L/C and source model coverage: only resistor dissipation is thermally coupled; no inferred semiconductor, switching, core or dielectric losses.</label></fieldset>
 <div className="studio-feedback-actions"><button type="button" disabled={busy || !design || !isDesktopShell()} onClick={() => void run(false)}><ListChecks size={14}/>Validate</button><button type="button" disabled={busy || !design || !isDesktopShell()} onClick={() => void run(true)}><Play size={14}/>Run feedback</button><button type="button" disabled={!busy} onClick={() => void stop()}><Square size={14}/>Stop</button><button type="button" disabled={!result || busy || !isDesktopShell()} onClick={() => void saveNativeTextFile("studio-feedback.json", JSON.stringify({ setup, result }, null, 2), "result")}><FileOutput size={14}/>Save results</button></div><pre className="studio-feedback-notice" role="status">{notice}</pre>
 {frames.length > 0 && <><div className="studio-feedback-metrics"><span>Accepted time: {latest?.time_s.toPrecision(5)} s</span><span>Thermal residual: {latest?.temperature_residual_k?.toExponential(2)} K</span><span>Power residual: {latest?.power_residual_w?.toExponential(2)} W</span><span>Balance: {latest?.balance_residual_w?.toExponential(2)} W</span></div><div className="studio-feedback-plots"><InteractivePlot title="Part temperature" revision={`thermal-${frames.length}`} data={nodeIds.map(id => ({ type: "scatter", mode: "lines", name: id, x: times, y: frames.map(frame => (frame.temperature_k[id] ?? NaN) - 273.15) }))} layout={{ xaxis: { title: "Time (s)" }, yaxis: { title: "Temperature (°C)" }, height: 320 }}/><InteractivePlot title="Coupled resistance" revision={`resistance-${frames.length}`} data={elements.map(id => ({ type: "scatter", mode: "lines", name: id, x: times, y: frames.map(frame => frame.electrical.resistance_ohm[id] ?? NaN) }))} layout={{ xaxis: { title: "Time (s)" }, yaxis: { title: "Resistance (ohm)" }, height: 320 }}/><InteractivePlot title="Part heating power" revision={`power-${frames.length}`} data={nodeIds.map(id => ({ type: "scatter", mode: "lines", name: id, x: times, y: frames.map(frame => frame.node_power_w[id] ?? NaN) }))} layout={{ xaxis: { title: "Time (s)" }, yaxis: { title: "Power (W)" }, height: 320 }}/><InteractivePlot title="Element current" revision={`current-${frames.length}`} data={Object.keys(latest?.electrical.element_current_a ?? {}).map(id => ({ type: "scatter", mode: "lines", name: id, x: times, y: frames.map(frame => frame.electrical.element_current_a[id] ?? NaN) }))} layout={{ xaxis: { title: "Time (s)" }, yaxis: { title: "Current (A)" }, height: 320 }}/></div></>}
 {Array.isArray(result?.issues) && result.issues.map((issue, index) => <p key={`issue-${index}`}>{String((issue as {
        message?: string;
    }).message ?? issue)}</p>)}
 {result?.limitations?.map((text, index) => <p key={index}>{text}</p>)}<footer>Parameters are saved with the circuit workspace. This feedback model does not create a board temperature field or a structural deformation solve. A native worker is required.</footer></section>;
}
