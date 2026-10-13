# Runtime resource ownership

SPIKE's installed desktop serves bundled frontend assets. Node/npm and Vite
are development tools, not required background services for an installed release.
A browser preview keeps its development server running while the preview is used.
Codex may separately run Node-based tools; their processes are not SPIKE workers.

## Inspect on Windows

Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_runtime_processes.ps1`
from the repository. This invocation sets the execution policy for this process
only; it does not change the machine policy.
Use `-Detailed` for process rows or `-Json` for a structured snapshot. The script is read-only, does not print
command arguments, and never terminates processes. It identifies desktop
process trees through parent IDs and creation times, distinguishes Codex Node
executables, and labels other Node processes conservatively. An npm launcher
without a repository path remains unclassified. Separate SPIKE instances can
each have their own worker and WebView processes.

Working-set sums include shared pages and are not private-memory measurements.
Use SPIKE's resource monitor for desktop-tree and system memory observations.
A single snapshot cannot establish a leak. Compare the same workload after
repeated open/run/close cycles and allow completed loaders to settle.

## Release behavior

The viewport cache has a retention budget for reusable decoded geometry and
textures. Closing a viewport releases idle sources. Active shared clones and
pending loaders remain pinned until their final user releases them. Teardown
invalidates asynchronous board/assembly generations so late loads cannot attach
to a disposed viewport. Already-running asset loaders are not forcibly aborted.

The desktop host tracks successfully admitted resident simulation sessions.
Closing one session preserves other sessions; a matching successful final close
retires the Python worker and its imported runtime. Failed or malformed replies
do not authorize retirement. Application exit retains the existing worker-tree
cleanup. The MCP bridge is a separate bounded service owned by the host.

## Recovery and limits

Close projects and sessions normally before closing the application. An idle
process with a large working set is a reason to inspect ownership and lifecycle,
not proof that it is safe to kill. Do not terminate every Node/Python process:
other applications, development servers, and unsaved sessions may own them.

Cache cleanup does not cap an active assembly's GPU allocation or an active
solver's memory. It does not guarantee that OS working-set counters immediately
decrease. The regression checks cover resource ownership and worker retirement;
a long-duration installed workload memory benchmark remains separate evidence.
