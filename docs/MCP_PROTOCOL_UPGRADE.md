# MCP protocol and schema resources

SPIKE's local stdio boundary supports the legacy `2025-11-25` initialize
handshake and the `2026-07-28` per-request metadata form. Existing direct
`McpServer.call_tool` consumers retain their ordinary CallToolResult dictionaries.
Modern RPC results include `resultType: complete` and server identity metadata.

## Client workflow

Legacy clients send `initialize` and then `notifications/initialized`. The
server selects `2025-11-25`, including when a legacy client proposes a different
revision; a client that cannot use the selected version must disconnect.
Modern clients may send `server/discover` or directly invoke a method. Each
request includes these fields inside `params._meta`:

- `io.modelcontextprotocol/protocolVersion`: `2026-07-28`.
- `io.modelcontextprotocol/clientCapabilities`: an object, empty if unused.
- Optional `io.modelcontextprotocol/clientInfo`: client `name` and `version`.

Identity metadata is descriptive; it never grants permission. An unsupported
modern revision returns `-32022` with the requested and supported versions.
Malformed metadata returns `-32602`. Notifications receive no response and
never invoke an application tool. A modern request does not initialize or
change the legacy session. The server advertises only tools and resources;
there are no tasks, subscriptions, prompts, sampling or elicitation handlers.

`tools/list` and `resources/list` return at most 128 descriptors, sorted by
name and URI respectively. Pass `nextCursor` as the next request's `cursor`
until it is absent. Cursors are opaque deterministic position tokens bound
to the full listed descriptors, method namespace and page size. A changed
catalog or invalid cursor returns `-32602`; restart without a cursor. Cursors
are not authorization credentials. Resource descriptors carry installed-schema
SHA-256 metadata, so a schema content change invalidates resource cursors too.

`resources/read` accepts only exact `spike://schemas/<filename>.schema.json`
URIs enumerated by `resources/list`. The returned text is the installed schema
JSON with MIME type `application/schema+json`. Query strings, fragments,
percent-encoded aliases, alternate schemes and arbitrary paths are rejected.
The underlying schema service owns installed-file confinement and offline
reference resolution. Schema validity does not establish numerical admission.

## Integration and bounds

`mcp_protocol.McpProtocol.gate(request)` returns `(handled, response)`.
Return that response if handled; otherwise dispatch only the existing method
allowlist. Use `protocol.result(request, payload)` for every successful RPC
and `protocol.error(request, code, message, data)` for errors. The protocol
helper consumes lifecycle, ping and discovery. `initialized` records only the
legacy handshake. Tools and resource handlers remain separate from admission.

`mcp_protocol_catalog.CatalogPager.page(items, params, namespace, key)` owns
listing. `mcp_resources.SchemaResources.list(params)` and `.read(params)` own
resources. `ProtocolError.code` is the JSON-RPC code for rejected parameters
or internal catalog bounds. Application tool failures remain CallToolResult
values with `isError: true`; a completed modern invocation still has
`resultType: complete` when the invoked tool reports failure.

`decode_request` accepts a complete UTF-8 newline-delimited frame, at most
2 MiB, with unique JSON keys, finite numbers, maximum depth 64 and 100,000
values. `encode_response` bounds the entire serialized response including
both structured and text content at 16 MiB. Listings admit at most 8192 items
and 8 MiB of descriptors. An individual serialized schema resource is limited
to 1 MiB. The existing supervised worker owns execution timeouts. This is a
sequential transport; cancellation notifications cannot interrupt a tool
already executing. Clients should use the existing GUI analysis job API for
pollable work. There is no HTTP transport or generic shell/file mutation API.

## Evidence and provenance

Native-free checks: `python -m unittest tests.python.test_mcp_protocol -v`.
The integration owner also runs the MCP server regression tests and the
repository architecture gate. These helpers do not independently certify a
complete transport implementation before their server integration is tested.

This implementation is independently authored from official protocol
requirements, without copying external implementation source or fixtures:

- [Versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning)
- [Message envelopes and metadata](https://modelcontextprotocol.io/specification/2026-07-28/basic)
- [Discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover)
- [stdio framing](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)
- [Tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [Resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources)
