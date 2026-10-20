# MCP and SpiDeR interfaces

SPIKE exposes one application contract across its worker, Python automation,
CLI, local stdio MCP and the opt-in desktop bridge. Capability discovery and
schema validation never establish solver qualification.

## Discover and inspect

Legacy MCP hosts retain the 2025-11-25 initialize handshake. Modern 2026-07-28
hosts use per-request protocol/client-capability metadata and server/discover.
See [protocol details](MCP_PROTOCOL_UPGRADE.md). Both use the same fixed tool
registry. Tools include operation hints, input schemas and typed SpiDeR outputs.
Tools/resources lists are deterministic and paginated; follow nextCursor until
absent. Cursors are bound to the catalog revision and must be restarted after
an update. Notifications do not execute tools.

Installed schemas are read-only MCP resources under spike://schemas/NAME.
Schema discovery includes title, contract IDs, byte counts and SHA-256 hashes.
Validation resolves references offline, bounds documents and reported issues,
and reports when issue counts are incomplete. No URI is an arbitrary file path.

The tools spike_spider_capabilities, spike_validate_spider,
spike_normalize_spider, spike_query_spider and spike_compare_spider inspect
inline v1/v2 designs. Queries retain canonical/source IDs, entity records and
reference identities. Use expected_revision to detect changed input between
pages. Revision comparisons report added/removed/changed entities and source
or coordinate-frame drift; they never apply edits. See
[SpiDeR interoperability](SPIDER_INTEROPERABILITY.md).

## Loaded-board and simulation interfaces

With the desktop bridge enabled, spike_gui_spider_context returns current
validation/revision evidence, spike_gui_spider_query reads bounded entities,
and spike_gui_spider_compare compares a supplied prior document to the loaded
board. These calls use the canonical loaded design where present, reject caller
context overrides and recheck the loaded-board binding after worker execution.
They do not mutate studies or saved geometry.

spike_validate_spice_workspace and spike_compose_spice_workspace expose explicit
circuit model/pin validation and deterministic netlist aliases. For Studio
feedback, use spike_studio_board_context, spike_validate_studio_feedback and
spike_run_studio_feedback with an inline board. Loaded-board users call
spike_gui_studio_board_context, then the existing analysis_prepare/preflight/run
job workflow with kind studio_feedback and active_board scope. Its published
input schema is studio-board-feedback-request-v1.schema.json. Supply all
physical parameters; no package thermal data or semiconductor losses are inferred.
Only accepted approximate coupled results become evidence; no spatial field is
manufactured. See [board Studio](SPIKES_BOARD_STUDIO.md).

Selected established v1 worker operations also accept v2 documents through a
shared lossless projection gate. Nonidentity frames, dropped typed fields,
stale legacy geometry snapshots and other projection losses are rejected before
solver dispatch. Native-v2 SI operations keep their existing v2 contract.
Worker response metadata records input/normalized revisions and projection
issues; MCP exposes it as metadata and as a separate input-binding text record,
without changing solver result schemas or their qualification.

## Human and Python usage

The CLI offers spider-capabilities, spider-validate, spider-normalize,
spider-query and spider-compare. All except capabilities take --request pointing
to a JSON object containing the same operation arguments. Validation failure
returns the existing validation exit code. CLI argument files are bounded to
16 MiB; per-document service limits still apply. Existing output and quiet flags apply.
For example:

```powershell
python -m python.spike_core.cli spider-capabilities
python -m python.spike_core.cli spider-query --request query.json
```

query.json contains document, optional entity_types/IDs/name filter, offset,
limit and optional expected_revision. Python uses
SpikeAutomation().call("query_spider", arguments); call_response retains outer
worker revision metadata when needed. Transport limits are 2 MiB per MCP
request and 16 MiB per complete response; a loaded-board query avoids resending
the entire design. Larger caller data needs a smaller page or a direct worker
workflow, not silent truncation.

## Recovery and evidence

Malformed JSON, duplicate keys, nonfinite values, unsupported contracts,
invalid references, stale revisions/cursors and unsafe schema URIs fail
explicitly. Schema validation is not physical admission. Existing extension
trust and assembly scope remain enforced. This stdio server processes calls
sequentially; it does not advertise tasks, subscriptions or asynchronous
cancellation. GUI simulation jobs retain existing polling/admission behavior.
No shell, arbitrary worker method, executable path, extension trust grant or
Studio process launcher is added to MCP.

Focused evidence lives in test_mcp_protocol.py, test_mcp_spider_integration.py,
test_spider_api.py and the desktop test-mcp-spider-interfaces.mjs. Native bridge
allowlist checks cover the new commands. Installed-package/GUI launch checks
are separate from these source and protocol tests.
