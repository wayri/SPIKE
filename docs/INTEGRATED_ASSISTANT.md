# Integrated SPIKE Assistant

Open **Tools > SPIKE Assistant** (also Settings > Assistant or command search).
The assistant opens in its own resizable desktop window, which can move outside
the main SPIKE window or minimize to the Windows taskbar. Reopening Assistant
restores that same window. **New chat** adds an independent conversation with its
own provider, model, draft, sharing consent and tool evidence (up to 32 chats).
Chats remain in memory while the window is open; closing asks before discarding
them and cancels owned model requests. Closing the main workspace also asks
before discarding open assistant chats and destroys its owned chat window. They are not saved in `.spike` files.
Switching the loaded project blocks the old chat session: close and reopen it.

**External LLM handoff** provides a selectable transcript for manual copy to an
external assistant. Inspect it before sharing: tool evidence may appear in model
responses. It excludes automatic project context and credentials. For complex
workflows, use the external CLI/MCP interfaces; export their actual tool catalog
with `spike assistant-tools`. No external application is contacted by handoff.

This source feature connects a model to bounded SPIKE tools. It is not yet in an
installed release. A model's explanation is not numerical validation.

## Connections

| Provider | Connection | Requirements |
| --- | --- | --- |
| OpenAI / ChatGPT models | Official Responses API | OpenAI API key and API access; a ChatGPT subscription alone is not API access |
| Anthropic Claude | Official Messages API | Anthropic API key and API access |
| LM Studio | Local OpenAI-compatible server | Start server, default `http://127.0.0.1:1234`, load a tool-capable model |
| Ollama | Local chat API | Start server, default `http://127.0.0.1:11434`, install a tool-capable model |

Select the provider, enter or probe its model, then send a message. No model name
is assumed to be available. Local endpoints must be numeric loopback HTTP with
an explicit port; remote LAN servers are not admitted by this connection UI.
Cloud hosts are fixed, TLS is verified, and redirects/proxies are not followed.
Windows cloud credentials use Windows Credential Manager. Other platforms have
no plaintext fallback and currently cannot configure cloud credentials here.
Keys and conversations are excluded from `.spike` project persistence.

## Consent and context

Cloud conversation consent and project evidence sharing are separate, unchecked
settings. Without project sharing the assistant provides advisory conversation
and cannot use SPIKE tools. Sharing exposes the current summary and subsequent
requested tool evidence, including board nets, connections and analysis inputs.
Review the context preview before enabling it. Provider or consent changes clear
conversation history and evidence so prior local evidence is not silently reused
by another provider. Clear conversation cancels the active model request.

The initial summary contains project name, selected workspace, board/design
identities, study count and retained result IDs. Typed tools retrieve more detail;
assembly lists and board pads support explicit paging. Oversized context is
rejected, not silently truncated. Project labels, imported text and tool outputs
are treated as untrusted data rather than commands. Cloud provider retention is
subject to that provider's policy; `store:false` is requested for OpenAI Responses.

## Skills and available actions

The panel lists its exact skill/tool catalog. Workflows include:

- Inspect board nets/layers/pads, retained studies and actual analysis capabilities.
- Create and activate PI/SI/EM/thermal study cases; prepare/patch typed cases,
  preflight, request execution, poll jobs and inspect bounded result evidence.
- List retained PI/SI/EM/thermal results, read their actual fields with array paging, display them in the viewport and open the engineering report preview.
- Inspect board occurrences, STEP part identities, connector pins, harness links,
  materials, thermal contacts and electrical bonds, plus paged harness document wires.
- Add an occurrence of an already retained design, duplicate an occurrence locally, remove an occurrence and dependent explicit
  links, apply a rigid placement in mm, and link retained connector pins.
- Open assembly/import, mechanical attachment and detailed harness editors.
  Opening these controls does not itself import a file or edit STEP geometry.

Edits and runs require **Apply once** or **Reject** with visible typed arguments.
Prepared-case review includes the exact setup and preflight evidence. The reviewed project and prepared-case revisions must still match at execution.
A changed project invalidates model-proposed tools until it replans. Draft locks,
missing references, unsupported scopes and failed preflights remain errors.
Removal with mechanical children, thermal contacts or electrical bonds requires
resolving those dependencies in the assembly editor first. Saving modified project
state and exporting reports use the existing user controls.

Example prompts:

1. "Inspect this assembly and list the explicit power and return connections."
2. "Show saved studies and display the retained thermal result."
3. "Describe supported multiboard PI inputs and ask me for missing values."
4. "Propose duplicating board A and moving the copy; show me the changes first."
5. "Review this result's model status and open its engineering report."

The assistant cannot run arbitrary code, infer missing electrical/thermal models,
qualify a solver, or edit native CAD solids. Harness wire authoring and STEP import
remain dedicated editor workflows. See [solver status](SOLVER_STATUS.md) for actual
physics limits and [external MCP tools](LOCAL_LLM_MCP.md) for headless integration.

## Developer boundaries and verification

`assistantSkills.ts` owns the version-controlled catalog and engineering guidance;
`assistantConversation.ts` owns consent, budgets, tool validation and review.
`assistantAssemblyTools.ts` reuses existing occurrence/placement/link operations.
Python owns provider transports and Windows credentials. Rust only supervises
worker processes. Provider tool calls remain inert until the frontend broker
validates and applies them. Requests are bounded to 2 MiB/128 messages; responses
4 MiB, eight calls per response, eight rounds/16 calls per turn and 120-second
provider deadline. Cancel stops the owned heavy worker; completed analyses are
independent SPIKE jobs and are not silently killed by closing chat.

Focused tests cover actual local HTTP exchanges, mocked cloud payloads, malformed
JSON, bounds, consent, stale revisions, rejected actions, cancellation and occurrence
identity. Live cloud accounts, actual account credential persistence and native
window visual checks require separate acceptance. No paid request is made by tests.

Primary interface references: [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling),
[Claude Messages](https://platform.claude.com/docs/en/api/python/messages/create),
[LM Studio tools](https://lmstudio.ai/docs/developer/openai-compat/tools),
[Ollama chat](https://docs.ollama.com/api/chat).

### Detached window boundary

`assistantWindow.ts` is the desktop IPC bridge. A random per-window session token,
request IDs, typed command allowlist, owned worker cancellation and current
project revision bind each request to the main workspace. The child receives no
filesystem or direct worker permission. `AssistantWindowRoot.tsx` owns in-memory
chat tabs and explicit close/handoff controls. The main workspace remains the
project authority. Provider workers stay supervised by its existing broker.

Run `npm run test:assistant` and `npm run test:button-standard`; the detached
broker test exercises stale revisions, unsupported methods, invalid schemas,
foreign sessions, project switches and listener cleanup. A native verification copy opened the standalone window and a second independent
chat at 1000 x 800. Desktop input routing prevented reliable minimize/restore and
narrow-window checks; those remain pending. Live provider accounts were not used.
