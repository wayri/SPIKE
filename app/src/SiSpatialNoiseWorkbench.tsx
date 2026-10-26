// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { isDesktopShell, runLocalWorker } from "./workerBridge";
import { usePanelPresentation } from "./panelPresentation";
import SiSpatialNoiseControls from "./SiSpatialNoiseControls";
import { admitSiSpatialNoise, availableSiSpatialNoiseQuantities, buildSiSpatialNoiseDisplay, defaultSiSpatialNoiseSettings } from "./siSpatialNoise";
import type { AdmittedSiSpatialNoise, SiSpatialNoiseContext, SiSpatialNoiseViewport } from "./siSpatialNoise";
import { boundedSiWorkspaceJson, coerceSpatialDeploymentWorkspace } from "./siDeploymentWorkspace";
import type { SpatialDeploymentWorkspace } from "./siDeploymentWorkspace";
import "./buttonStandard.css";
import "./SiSpatialNoiseWorkbench.css";

type RecordData = Record<string, unknown>;
const record = (value: unknown): RecordData => value && typeof value === "object" && !Array.isArray(value) ? value as RecordData : {};
const rawSamples = (data: AdmittedSiSpatialNoise) => ({ ...data,
  traceSamples: data.traceSamples.map(({ positionMm: _derivedPosition, ...sample }) => sample) });

export default function SiSpatialNoiseWorkbench({ design, occurrenceId, onDisplay, workspace, onWorkspaceChange, stagedExample }: {
  design: RecordData | null; occurrenceId: string | null; onDisplay: (value: SiSpatialNoiseViewport | null) => void;
  workspace?: SpatialDeploymentWorkspace | null; onWorkspaceChange?: (value: SpatialDeploymentWorkspace) => void;
  stagedExample?: { token: number; solverText: string; samplesText: string };
}) {
  const { ownerDocument } = usePanelPresentation();
  const [saved] = useState(() => coerceSpatialDeploymentWorkspace(workspace));
  const [candidate, setCandidate] = useState<unknown>(saved?.candidate ?? null), [fileName, setFileName] = useState(saved?.fileName ?? "");
  const [aggressor, setAggressor] = useState(saved?.aggressor ?? ""), [victim, setVictim] = useState(saved?.victim ?? ""), [requestId, setRequestId] = useState(saved?.requestId ?? "");
  const [pairDraft, setPairDraft] = useState(saved?.pairDraft ?? "");
  const [capture, setCapture] = useState<{ data: AdmittedSiSpatialNoise; design: RecordData; key: string; origin: "imported" | "supplied_pair" } | null>(null);
  const [settings, setSettings] = useState(saved?.settings ?? defaultSiSpatialNoiseSettings), [selectedSample, setSelectedSample] = useState<number | null>(null);
  const [query, setQuery] = useState(""), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [pendingExample, setPendingExample] = useState<{ solverText: string; samplesText: string } | null>(null);
  const generation = useRef(0), fileGeneration = useRef(0), alive = useRef(true), notify = useRef(onDisplay);
  const workspaceNotify = useRef(onWorkspaceChange); workspaceNotify.current = onWorkspaceChange; notify.current = onDisplay;
  const publication = useMemo(() => {
    const value = coerceSpatialDeploymentWorkspace({ contract: "spike/si-spatial-workspace/v1", candidate, fileName, aggressor, victim, requestId, pairDraft, settings });
    return { value, signature: JSON.stringify(value) };
  }, [candidate, fileName, aggressor, victim, requestId, pairDraft, settings]);
  const lastPublished = useRef(publication.signature);
  const key = JSON.stringify([occurrenceId, aggressor, victim, requestId, pairDraft]);
  const current = useRef({ design, key, candidate }); current.current = { design, key, candidate };
  const nets = Array.isArray(design?.nets) ? design.nets.map(record).filter(net => typeof net.id === "string") : [];
  const data = capture?.design === design && capture.key === key ? capture.data : null;
  const projectionSettings = useMemo(() => ({ ...settings, opacity: defaultSiSpatialNoiseSettings.opacity }),
    [settings.quantity, settings.frequencyIndex, settings.projection, settings.component, settings.phaseDeg, settings.scaleLimit]);
  const projectedDisplay = useMemo(() => data ? buildSiSpatialNoiseDisplay(data, projectionSettings) : null, [data, projectionSettings]);
  const display = useMemo(() => projectedDisplay ? { ...projectedDisplay, opacity: settings.opacity } : null, [projectedDisplay, settings.opacity]);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; generation.current++; fileGeneration.current++; notify.current(null); };
  }, []);
  useEffect(() => { generation.current++; setBusy(false); }, [design, key, candidate]);
  useEffect(() => { if (stagedExample) setPendingExample({ solverText: stagedExample.solverText, samplesText: stagedExample.samplesText }); }, [stagedExample?.token]);
  useEffect(() => {
    if (!publication.value) setError("Workspace exceeds the 24 MiB save budget or has invalid input; reduce samples or the pair draft before saving.");
    else if (lastPublished.current !== publication.signature) {
      lastPublished.current = publication.signature;
      workspaceNotify.current?.(publication.value);
    }
  }, [publication]);
  useEffect(() => {
    notify.current(display && data && design ? { display, binding: data.binding, sourceDesign: design, selectedSample, origin: capture?.origin, onSelectSample: setSelectedSample } : null);
  }, [display, data, design, selectedSample, capture?.origin]);

  const importSamples = async (file: File | undefined) => {
    if (!file) return;
    const token = ++fileGeneration.current;
    generation.current++;
    setCapture(null); setCandidate(null); setError(""); setFileName(file.name); setBusy(false);
    try {
      if (file.size > 24 * 1024 * 1024) throw new Error("Spatial sample JSON exceeds the 24 MiB import limit.");
      const value: unknown = JSON.parse(await file.text());
      if (!alive.current || token !== fileGeneration.current) return;
      if (record(value).contract !== "spike/si-spatial-noise/v1") throw new Error("Unsupported dataset. Import spike/si-spatial-noise/v1 spatial samples; channel port metrics have no spatial field.");
      const proposed = record(record(value).binding);
      setCandidate(value);
      // Proposed identities only populate editable controls. Admission requires the explicit action below.
      setAggressor(typeof proposed.aggressorNetId === "string" && proposed.aggressorNetId.length <= 512 ? proposed.aggressorNetId : "");
      setVictim(typeof proposed.victimNetId === "string" && proposed.victimNetId.length <= 512 ? proposed.victimNetId : "");
      setRequestId(typeof proposed.requestId === "string" && proposed.requestId.length <= 512 ? proposed.requestId : "");
    } catch (reason) { if (alive.current && token === fileGeneration.current) setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const bind = async () => {
    if (!design || !occurrenceId || !candidate || !aggressor || !victim || aggressor === victim || !requestId.trim()) return;
    const token = ++generation.current, sourceDesign = design, sourceKey = key, sourceCandidate = candidate;
    const isCurrent = () => alive.current && token === generation.current && current.current.design === sourceDesign && current.current.key === sourceKey && current.current.candidate === sourceCandidate;
    setBusy(true); setError(""); setCapture(null);
    try {
      const response = await runLocalWorker({ method: "inspect_si_spatial_context", params: { design: sourceDesign, occurrence_id: occurrenceId,
        aggressor_net_id: aggressor, victim_net_id: victim, request_id: requestId } });
      if (!isCurrent()) return;
      if (!response.ok || !response.result) throw new Error(response.error ?? "The current design context could not be inspected.");
      const context = response.result as unknown as SiSpatialNoiseContext;
      // Expected identity is the current user-reviewed source/request; the imported binding is never the context authority.
      if (context.designId !== sourceDesign.design_id || context.occurrenceId !== occurrenceId || context.requestId !== requestId
        || context.aggressorNetId !== aggressor || context.victimNetId !== victim) throw new Error("The context response belongs to another source or request.");
      const admitted = admitSiSpatialNoise(sourceCandidate, context);
      if (!admitted) throw new Error("Dataset rejected: revision, request, occurrence, net identities or spatial sample structure do not match the current design context.");
      setSettings(previous => ({ ...previous, quantity: availableSiSpatialNoiseQuantities(admitted).includes(previous.quantity) ? previous.quantity : availableSiSpatialNoiseQuantities(admitted)[0], frequencyIndex: Math.min(previous.frequencyIndex, admitted.frequenciesHz.length - 1) }));
      setSelectedSample(null); setQuery(""); setCapture({ data: admitted, design: sourceDesign, key: sourceKey, origin: "imported" });
    } catch (reason) { if (isCurrent()) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (isCurrent()) setBusy(false); }
  };
  const sourceReady = Boolean(design && occurrenceId && aggressor && victim && aggressor !== victim && requestId.trim() && nets.some(net => net.id === aggressor) && nets.some(net => net.id === victim));
  const ready = sourceReady && Boolean(candidate);
  const loadPairSetup = async (file: File | undefined) => {
    if (!file) return;
    const token = ++fileGeneration.current; generation.current++; setBusy(false); setError("");
    try {
      if (file.size > 2 * 1024 * 1024) throw new Error("Supplied pair setup exceeds the 2 MiB draft limit.");
      const text = await file.text();
      if (alive.current && token === fileGeneration.current) setPairDraft(text);
    } catch (reason) { if (alive.current && token === fileGeneration.current) setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const runPair = async () => {
    if (!sourceReady || !design || !occurrenceId) return;
    const token = ++generation.current, sourceDesign = design, sourceKey = key;
    const isCurrent = () => alive.current && token === generation.current && current.current.design === sourceDesign && current.current.key === sourceKey;
    setCapture(null); setError(""); setBusy(true);
    try {
      if (pairDraft.length > 2 * 1024 * 1024) throw new Error("Supplied pair setup exceeds the 2 MiB draft limit.");
      const setup = record(JSON.parse(pairDraft));
      if (Object.keys(setup).sort().join(",") !== "aggressor_segment_id,pair_request,victim_segment_id") throw new Error("Setup must contain only pair_request, aggressor_segment_id and victim_segment_id; current design and reviewed controls provide all source identities.");
      const response = await runLocalWorker({ method: "run_si_spatial_pair", params: { ...setup, design: sourceDesign, occurrence_id: occurrenceId, aggressor_net_id: aggressor, victim_net_id: victim, request_id: requestId } });
      if (!isCurrent()) return;
      if (!response.ok || !response.result) throw new Error(response.error ?? "The supplied coupled-line pair did not complete.");
      const context = response.result.context as SiSpatialNoiseContext;
      if (!context || context.designId !== sourceDesign.design_id || context.occurrenceId !== occurrenceId || context.requestId !== requestId || context.aggressorNetId !== aggressor || context.victimNetId !== victim) throw new Error("The pair response belongs to another source or request.");
      const admitted = admitSiSpatialNoise(response.result.data, context);
      if (!admitted) throw new Error("The supplied pair returned unsupported or mismatched spatial samples.");
      setCandidate(rawSamples(admitted)); setFileName("supplied-pair-result.json");
      setSettings({ ...defaultSiSpatialNoiseSettings, quantity: availableSiSpatialNoiseQuantities(admitted)[0] });
      setSelectedSample(null); setQuery(""); setCapture({ data: admitted, design: sourceDesign, key: sourceKey, origin: "supplied_pair" });
    } catch (reason) { if (isCurrent()) setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { if (isCurrent()) setBusy(false); }
  };
  const exportSamples = () => {
    if (!data || !ownerDocument) return;
    const payload = rawSamples(data);
    const blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
    if (blob.size > 24 * 1024 * 1024) { setError("Sample export exceeds the 24 MiB import budget; reduce the number of supplied frequencies or probes before exporting."); return; }
    const url = URL.createObjectURL(blob);
    const link = ownerDocument.createElement("a"); link.href = url; link.download = "si-spatial-samples.json"; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <section className="si-spatial-workbench" aria-label="Spatial SI samples">
    <header><b>Spatial SI samples</b><span>Sampled data display</span></header>
    <p>Imported source authenticity and physical qualification are unverified. Binding checks only the current design revision, reviewed identities and sample structure. Importing never runs a solver; the optional supplied-pair solve below requires an explicit Run action.</p>
    {pendingExample && <details open><summary>Review staged spatial example</summary><p>Your current samples, reviewed identities and pair draft remain until you apply. Applying requires a new explicit binding or Run action.</p>
      <label>Staged pair setup JSON<textarea rows={6} readOnly value={pendingExample.solverText} /></label>
      <label>Staged sample JSON<textarea rows={6} readOnly value={pendingExample.samplesText} /></label>
      <button type="button" disabled={busy} onClick={() => { try {
        const samples: unknown = JSON.parse(pendingExample.samplesText), setup: unknown = JSON.parse(pendingExample.solverText);
        if (pendingExample.solverText.length > 2 * 1024 * 1024 || !boundedSiWorkspaceJson(samples) || record(samples).contract !== "spike/si-spatial-noise/v1"
          || Object.keys(record(setup)).sort().join(",") !== "aggressor_segment_id,pair_request,victim_segment_id") throw new Error("Invalid staged spatial example");
        generation.current++; fileGeneration.current++; setCapture(null); setSelectedSample(null); setCandidate(samples); setFileName("staged-spatial-example.json"); setPairDraft(pendingExample.solverText); setError(""); setPendingExample(null);
      } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } }}>Apply staged spatial example</button>
      <button type="button" onClick={() => setPendingExample(null)}>Dismiss staged example</button></details>}
    <label>Import sample JSON<input type="file" accept=".json,application/json" onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; void importSamples(file); }} /></label>
    {fileName && <small title={fileName}>{fileName}</small>}
    <div className="si-spatial-binding-fields">
      <label>Aggressor net<select value={aggressor} onChange={event => setAggressor(event.target.value)}><option value="">Choose current source net</option>{nets.map(net => <option key={String(net.id)} value={String(net.id)}>{String(net.name ?? net.id)} ({String(net.id)})</option>)}</select></label>
      <label>Victim net<select value={victim} onChange={event => setVictim(event.target.value)}><option value="">Choose current victim net</option>{nets.map(net => <option key={String(net.id)} value={String(net.id)}>{String(net.name ?? net.id)} ({String(net.id)})</option>)}</select></label>
      <label>Source request ID<input value={requestId} maxLength={512} onChange={event => setRequestId(event.target.value)} /></label>
      <label>Current board occurrence<input value={occurrenceId ?? "No single board selected"} readOnly /></label>
    </div>
    <div className="si-spatial-actions"><button type="button" className="spike-control--primary" disabled={!ready || busy || !isDesktopShell()} onClick={() => void bind()}>{busy ? "Checking current design..." : "Review identities and bind samples"}</button><button type="button" disabled={!candidate && !capture && !fileName} onClick={() => { generation.current++; fileGeneration.current++; setCapture(null); setCandidate(null); setFileName(""); setError(""); setBusy(false); }}>Clear samples</button></div>
    <details><summary>Solve supplied coupled-line pair</summary>
      <p>Experimental uniform line model using supplied even/odd RLGC; no PCB parameter extraction or surrounding E-field. Choose reviewed nets and source request above. Assign two coextensive, co-directed, equal-length strokes on the same layer. Line lengths must match the strokes.</p>
      <label>Load pair setup JSON<input type="file" accept=".json,application/json" onChange={event => { const file = event.target.files?.[0]; event.target.value = ""; void loadPairSetup(file); }} /></label>
      <label>Pair setup JSON<textarea rows={8} value={pairDraft} maxLength={2 * 1024 * 1024} spellCheck={false} placeholder={'{"pair_request": {...}, "aggressor_segment_id": "...", "victim_segment_id": "..."}'} onChange={event => setPairDraft(event.target.value)} /></label>
      <div className="si-spatial-actions"><button type="button" className="spike-control--primary" disabled={!sourceReady || !pairDraft.trim() || busy || !isDesktopShell()} onClick={() => void runPair()}>{busy ? "Checking / running..." : "Run supplied pair"}</button></div>
    </details>
    <button type="button" disabled={!data} onClick={exportSamples}>Export bound sample JSON</button>
    {!isDesktopShell() && <p role="status">Open SPIKE desktop to inspect the current canonical design and admit samples.</p>}
    {!design || !occurrenceId ? <p role="status">Choose one current board design before binding spatial samples.</p> : Boolean(candidate) && !data && !error && <p role="status">Saved or imported samples are unadmitted. Review the proposed net identities and request ID, then explicitly bind to the current design.</p>}
    {data && <p role="status">{capture?.origin === "supplied_pair" ? "Executed supplied-pair model; physical qualification unverified." : "Bound imported dataset; source authenticity unverified."} {data.sourceResult.modelScope.basis}; {data.sourceResult.modelScope.extracted ? "source declares extracted parameters" : "source declares supplied parameters"}. {data.sourceResult.modelScope.limitations.join(" ")}</p>}
    <SiSpatialNoiseControls data={data} settings={settings} display={display} selectedSample={selectedSample} query={query} error={error}
      onSettings={value => { setSettings(value); setSelectedSample(null); }} onSelectSample={setSelectedSample} onQuery={setQuery} onRetry={ready && !busy ? () => void bind() : undefined} />
  </section>;
}
