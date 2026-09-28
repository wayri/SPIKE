# Local LLM control with MCP

SPIKE exposes a local [Model Context Protocol](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle) stdio server. It offers a fixed set of worker tools for capability inspection, design loading and validation, admitted PI and SI workflows, thermal estimates, and EM screening. Solver qualification, assumptions, and blocked preflights come from the existing SPIKE worker. The server also offers desktop tools for workspace selection, 2D/3D view, and study management when the desktop bridge is enabled.

The server does not expose a shell, generic worker dispatch, extension trust, project save, or arbitrary file write. Analysis tools may take time and return large results. A model response is guidance until a SPIKE tool reports a completed result.

## Desktop bridge

In the SPIKE desktop app, open **Settings → LLM / MCP → Enable bridge**. The bridge is off initially and listens only on `127.0.0.1`. SPIKE shows the private rendezvous file path. The MCP server discovers the newest active local bridge automatically; if several SPIKE windows are open, set `SPIKE_MCP_BRIDGE_FILE` to the path shown in the intended window. The file contains a private token and is deleted when the bridge stops or the app exits. Keep it local. GUI changes to studies remain unsaved until you save the SPIKE project.

## LM Studio as MCP host

[LM Studio supports local MCP servers](https://lmstudio.ai/docs/app/mcp). Open its **Program → Install → Edit mcp.json** and add the SPIKE entry, replacing the path with your checkout path and the Python executable with your configured SPIKE Python environment:

```json
{
  "mcpServers": {
    "spike-local": {
      "command": "python",
      "args": ["C:/path/to/SPIKE/scripts/spike_mcp.py"]
    }
  }
}
```

Load a local model with tool support in LM Studio. Ask it to call `spike_gui_status`, then `spike_gui_list_studies` or `spike_capabilities`. Desktop tools need the enabled bridge. Worker tools need the SPIKE Python runtime dependencies from `requirements.txt`. No remote MCP URL is needed.

When using a newly built packaged SPIKE worker, its executable supports `spike-worker.exe --mcp` as the MCP command. Set LM Studio's `command` to that executable and `args` to `["--mcp"]`. The current source checkout launcher remains available for development. A package built before this option was added needs rebuilding.

## Ollama or LM Studio through the local chat runner

SPIKE also includes a dependency-free client for the local [Ollama tool-calling API](https://docs.ollama.com/capabilities/tool-calling) and [LM Studio chat-completions tool API](https://lmstudio.ai/docs/developer/openai-compat/tools). Start the provider's local server and load a model that supports tools. From the SPIKE checkout:

```powershell
python scripts/spike_local_chat.py --provider ollama --list-models
python scripts/spike_local_chat.py --provider ollama --model YOUR_LOCAL_MODEL "Show SPIKE status and list studies"
python scripts/spike_local_chat.py --provider lmstudio --list-models
python scripts/spike_local_chat.py --provider lmstudio --model YOUR_LOCAL_MODEL "Which PI solvers are available?"
```

Omit the prompt for an interactive session. The default endpoints are `http://127.0.0.1:11434` for Ollama and `http://127.0.0.1:1234` for LM Studio. `--endpoint` accepts only a loopback HTTP origin with a port. The client sends the MCP tool schemas to the local model and executes only tools in SPIKE's allowlist. It caps each prompt at eight tool rounds and sixteen calls. It does not download models or start provider services.

The newly built packaged worker also supports `spike-worker.exe --local-chat --provider ollama` (or `lmstudio`) with the same options. This provides offline linking without a source checkout once that worker artifact is rebuilt.

For a GUI interaction, enable the desktop bridge first. For example, ask: “Show SPIKE status, create a study called ESP32 airflow comparisons, add thermal and EM cases, then open the Thermal run controls.” The model can prepare the study and open controls; it does not run a solver merely by opening them. Ask for a preflight before a worker analysis and inspect status and assumptions in the returned result.

## Troubleshooting

- “Connection refused” means the LM Studio or Ollama local API is not running at the selected endpoint.
- “Desktop bridge unavailable” means it is off, the app is closed, or `SPIKE_MCP_BRIDGE_FILE` points to a stale file.
- “No module named jsonschema” means the selected Python interpreter lacks the existing SPIKE worker dependencies. Install the project's requirements into that interpreter or use the bundled worker environment.
- If a small model does not produce tool calls, try a locally installed tool-capable model. Neither provider guarantees that every model will format tool calls correctly.
