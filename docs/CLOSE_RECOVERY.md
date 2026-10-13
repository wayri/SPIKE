# Desktop close recovery

The main native Close button uses a host-owned request and response handshake.
A responsive workspace retains its save/discard and tool-draft checks. It sends
an immediate defer response when a save decision is needed; saving is not subject
to the recovery timeout.

If the renderer does not acknowledge a Close request within five seconds, the
native host offers **Force close SPIKE** or **Keep open**. This dialog does not
depend on JavaScript, React, or the webview. Force close may lose unsaved changes;
already saved projects and completed result files are retained. Nothing closes
automatically because a solve takes a long time. Recovery begins on a Close press.

After a close decision, assistant cleanup gets at most one second. Its failure
cannot indefinitely prevent main shutdown. Native shutdown cancels owned work
and exits the application. An independent two-second fallback terminates the host
if its event loop or shutdown hooks remain blocked. The fallback never waits for
worker locks, child windows, or process cleanup.

On Windows, child cleanup selects descendants of the current SPIKE process,
rechecks parent identity and process creation order, and terminates the specific
opened process handles. It does not kill applications by executable name or scan
for all Node/Python processes. Other-platform descendant cleanup is not implemented
by this Windows recovery path; existing cooperative worker cancellation remains.
Detached-window Close requests do not trigger main application shutdown.

Run `npm run test:desktop-close` in `app` for frontend handshake, legacy-host
compatibility, failing callbacks and bounded child-cleanup tests. Native gate
checks use `cargo test --offline --lib close_recovery` in `app/src-tauri`.
The native fix requires a rebuilt desktop runtime; an older installed executable
cannot acquire native close recovery from frontend changes alone.
