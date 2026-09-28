// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { mcpBridgeStatus, startMcpBridge, stopMcpBridge, type McpBridgeStatus } from "./workerBridge";

export default function McpBridgePanel({ onClose }: { onClose: () => void }) {
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

  return <div className="modal-shade" role="presentation" onKeyDown={event => { if (event.key === "Escape") onClose(); }}>
    <section className="floating-panel mcp-bridge-panel" role="dialog" aria-modal="true" aria-labelledby="mcp-bridge-title" tabIndex={-1}>
      <div className="floating-heading"><b id="mcp-bridge-title">LOCAL LLM / MCP</b><button onClick={onClose} aria-label="Close local LLM panel">×</button></div>
      <div className="mcp-bridge-body">
        <p>Connect LM Studio or an Ollama model to SPIKE through the local MCP server. Enable the desktop bridge to let a model navigate this open window and organize studies.</p>
        <p><b>Desktop bridge:</b> {status?.enabled ? "Enabled" : "Off"}</p>
        {status?.enabled && <><p><b>Local endpoint:</b> 127.0.0.1:{status.port}</p><p><b>Connection file:</b> <code>{status.rendezvousPath}</code></p></>}
        <p>The connection file contains a private token. Keep it on this machine. SPIKE's MCP server reads it through <code>SPIKE_MCP_BRIDGE_FILE</code>.</p>
        {error && <p role="alert" className="mcp-bridge-error">{error}</p>}
        <div className="mcp-bridge-actions"><button disabled={busy || status?.enabled === true} onClick={() => void change(true)}>Enable bridge</button><button disabled={busy || status?.enabled !== true} onClick={() => void change(false)}>Disable bridge</button></div>
        <p className="mcp-bridge-help">For LM Studio, register <code>scripts/spike_mcp.py</code> as a local MCP server. For Ollama, run <code>scripts/spike_local_chat.py --provider ollama</code>. Both paths use locally hosted models.</p>
      </div>
    </section>
  </div>;
}
