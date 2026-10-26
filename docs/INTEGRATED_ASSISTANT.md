# Integrated SPIKE Assistant

Start with the [Assistant user guide](ASSISTANT_USER_GUIDE.md) for complete local
setup, connection tests, file/attachment handling, staged analysis prompts, data
calculations, script drafting/execution and troubleshooting. This document records
the integrated interface and developer boundaries.

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

## Conversation layout and attachments

The conversation is the main surface. A compact header shows the provider and
model; its **settings** icon opens connection, credentials, project sharing and
the tool catalog without reserving space above the chat. Close settings with its
close icon or Escape. Tool calls appear in a collapsed **SPIKE activity** summary;
expand an individual action for its exact evidence. Proposed edits and runs
still require explicit review.

Use the composer paperclip, drop files onto the composer, or paste a screenshot.
Review thumbnails and filenames, remove unwanted attachments, then **Send**.
Attaching does not upload anything. Sending to a cloud provider requires its
separate conversation consent; the composer identifies that destination.

| Input/output | Current behavior |
| --- | --- |
| Image input | PNG, JPEG or WebP; up to 5 MiB each and four per conversation |
| Text input | UTF-8 `.txt`, `.md`, `.csv`, `.json`, `.log`, `.py`, `.spice`, `.cir`, `.net`; 256 KiB each, treated only as untrusted evidence |
| Conversation budget | Eight attachments and 20 MiB decoded content across the full history; earlier evidence is never silently removed |
| Rich responses | Formatted text, tables, lists and copyable code; raw HTML is escaped and arbitrary image URLs are not fetched |
| Engineering visuals | Existing result/report tools display actual retained solver output in SPIKE's viewport and report preview |
| Generated image, audio or video responses | Not supported by these chat transports; unsupported provider media is rejected explicitly |
| Audio, video, PDF or CAD input | Not admitted by chat; use the corresponding project importer where available |

Every attachment has a SHA-256 content fingerprint and is checked again by the
worker. Images require a vision-capable model: Ollama must report vision support
for the exact selected model; LM Studio must identify it as a VLM. Missing
capability metadata blocks image inference with a recovery message. Cloud APIs
also reject incompatible models; model discovery alone does not prove vision or
inference quality. Text files are never executed. Attachments and chats remain
in memory, and attachments are included in manually copied handoffs.

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
Selecting a local provider automatically checks its model list and selects a
loaded model when identified, otherwise the first reported model. Discovery has
a ten-second deadline; a connected server
with no models is reported separately from a failed connection. Changing the
endpoint clears the selected model and conversation; probe the new server before
continuing. Model discovery confirms the API connection, not tool support or
successful inference. For Ollama, start the installed service with `ollama serve`;
for LM Studio, load a model and start its local API server. No model is downloaded
by SPIKE. HTTP failures include local recovery guidance without exposing provider
response bodies.
LM Studio discovery prefers an already loaded model, retaining the complete
model list for manual selection. Older compatible servers fall back to the
standard OpenAI model list when loaded-state metadata is unavailable.
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

The [task harness](ASSISTANT_TASK_HARNESS.md) adds bounded read-only access to a
user-selected work folder, source-bound complete-file CSV summaries and reviewed
staging of unsaved Python drafts. Choose the folder in Assistant settings; models
cannot inject a filesystem root. The Python workspace retains explicit Run/Save.

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

Read-only tools in the same reply may verify the exact revision produced by an
approved action. Further edits/runs still require a fresh plan after a revision
change; an unrelated project change also blocks the follow-up read. Tool progress
is shown while the model continues, and the conversation follows new evidence.

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
validates and applies them. Text requests are bounded to 2 MiB/128 messages;
attachment-bearing request envelopes are bounded to 30 MiB. Responses are limited to
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
