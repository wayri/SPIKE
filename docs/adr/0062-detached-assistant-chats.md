# ADR 0062: Detached assistant chats

Status: Accepted for source implementation; native opening and multiple chats
observed, narrow layout and minimize/restore acceptance pending.

SPIKE's assistant uses a separately movable native webview, with independent
in-memory conversations. It does not own project state. A session-bound event
bridge routes a fixed provider-worker allowlist and catalog-validated project
actions through the main workspace. Revision checks reject stale actions;
switching projects invalidates the session. Secrets remain in the existing OS
credential boundary and chats remain outside portable projects.

Minimization preserves the conversation. Closing explicitly discards histories
and cancels owned provider requests without canceling previously started analysis
jobs. Complex work is handed to external CLI/MCP assistants via a manually
reviewed transcript and the exact machine-readable `assistant-tools` catalog.
No arbitrary code or shell execution capability is added. Existing typed tool
review and numerical validation requirements remain authoritative.
