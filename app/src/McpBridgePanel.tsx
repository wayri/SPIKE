// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { mcpBridgeStatus, startMcpBridge, stopMcpBridge, type McpBridgeStatus } from "./workerBridge";

export default function McpBridgePanel({ onClose, latestEvidence }: { onClose: () => void; latestEvidence?: Record<string, unknown> | null }) {
  const [status, setStatus] = useState<McpBridgeStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { void mcpBridgeStatus().then(setStatus).catch(cause => setError(String(cause))); }, []);
  const change = async (enable: boolean) => {
    setBusy(true); setError("");
    try { setStatus(await (enable ? startMcpBridge() : stopMcpBridge())); }
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  };

  const object = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const payload = object(object(latestEvidence?.data).analysis_result ?? latestEvidence?.analysis_result ?? latestEvidence);
  const provenance = object(payload.provenance), meta = object(latestEvidence?.mcp);
  const evidenceSummary = latestEvidence ? { contract: payload.contract, status: payload.status, model_status: payload.model_status,
    analysis_id: payload.analysis_id, returnedKeys: Object.keys(payload).slice(0, 100),
    provenance: Object.fromEntries(["solver", "design_id", "design_digest", "case_sha256", "script_sha256"].map(key => [key, typeof provenance[key] === "string" ? provenance[key].slice(0, 512) : undefined])),
    job: Object.fromEntries(["kind", "caseId", "jobId", "scope"].map(key => [key, meta[key]])),
  } : null;
  return <div className="modal-shade" role="presentation" onKeyDown={event => { if (event.key === "Escape") onClose(); }}>
    <section className="floating-panel mcp-bridge-panel" role="dialog" aria-modal="true" aria-labelledby="mcp-bridge-title" tabIndex={-1}>
      <div className="floating-heading"><b id="mcp-bridge-title">LOCAL LLM / MCP</b><button onClick={onClose} aria-label="Close local LLM panel">×</button></div>
      <div className="mcp-bridge-body">
        <p>Connect LM Studio or an Ollama model to SPIKE through the local MCP server. Enable the desktop bridge to let a model inspect the loaded board, configure studies, prepare supported analyses, and inspect actual results.</p>
        <p><b>Desktop bridge:</b> {status?.enabled ? "Enabled" : "Off"}</p>
        {status?.enabled && <><p><b>Local endpoint:</b> 127.0.0.1:{status.port}</p><p><b>Connection file:</b> <code>{status.rendezvousPath}</code></p></>}
        <p>The connection file contains a private token. Keep it on this machine. SPIKE's MCP server reads it through <code>SPIKE_MCP_BRIDGE_FILE</code>.</p>
        <p>Discover capabilities and contract schemas first. SpiDeR tools inspect loaded parts, nets, copper and their references in bounded pages and compare revisions without changing the board. Prepare explicit inputs, preflight the bound case, then run and poll its job. Missing inputs and unsupported physics stay blocked. Supported results appear in SPIKE; retained EM results offer linked graphs and probes in the main viewport, followed by engineering report preview.</p>
        <p>Extension analyses require existing trust. Reduced multi-board models have their own admission. Full assembly coupled field solving, arbitrary scripts, shell commands, and granting extension trust are unavailable through this bridge.</p>
        {latestEvidence && <details><summary>Latest MCP analysis evidence</summary><p>Returned contract and provenance summary. Retrieve full actual arrays through paginated analysis evidence queries.</p><pre style={{ maxHeight: 260, overflow: "auto", whiteSpace: "pre-wrap" }}>{JSON.stringify(evidenceSummary, null, 2)}</pre></details>}
        {error && <p role="alert" className="mcp-bridge-error">{error}</p>}
        <div className="mcp-bridge-actions"><button disabled={busy || status?.enabled === true} onClick={() => void change(true)}>Enable bridge</button><button disabled={busy || status?.enabled !== true} onClick={() => void change(false)}>Disable bridge</button></div>
        <p className="mcp-bridge-help">For LM Studio, register <code>scripts/spike_mcp.py</code> as a local MCP server. For Ollama, run <code>scripts/spike_local_chat.py --provider ollama</code>. Both paths use locally hosted models.</p>
      </div>
    </section>
  </div>;
}
