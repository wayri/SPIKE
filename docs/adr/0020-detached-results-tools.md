<!-- SPDX-License-Identifier: Apache-2.0 -->
# Detached result tool windows

Status: implemented in development; native multi-monitor acceptance pending.

Results controls, probe tables, and trace plots must move outside the main
application bounds. Use Tauri WebviewWindow children with fixed allowlisted
labels, and same-origin popups in browser development. Reuse the frontend
entry point with a tool-kind query parameter; a child never mounts App or
starts another solver worker.

The main workspace owns solver results, project persistence, and edits.
Children receive bounded, validated presentation snapshots and send validated
actions referencing opaque row IDs. The parent checks row existence and
decodes IDs before applying actions. Random per-window tokens scope native
event envelopes and browser BroadcastChannels. Child capabilities allow
events only; creation, focus, and closure remain main-window capabilities.

This is a presentation boundary, not a new solver contract. It avoids sharing
mutable solver state or broad native command permissions with child views.
Closing a child retains authoritative data. The main board viewport remains
in the primary window; detached trace plots provide their own result graphs
and surface views. Payload limits and truncation must remain visible.

Validation covers snapshot limits, action validation, formula parity, source
identity, frontend compilation, and native capability compilation. Real
window movement across monitors remains a desktop acceptance check.
