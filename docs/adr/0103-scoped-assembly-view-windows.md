# Scoped assembly view windows

Status: implemented for gamma; native multi-window acceptance pending.

The project owner remains the sole authority for undo, project persistence,
worker execution and assembly identity. A tab describes one retained board
occurrence or mechanical part; switching the main selection does not retarget it.

`useWorkspaceViews` projects only that scope into a renderer. Inactive docked
renderers unmount, retaining bounded camera, filter and selection presentation.
At most eight scoped views may be open. Detaching creates a presentation-only
root through `workspaceViewWindows`, the approved desktop bridge. Child actions
carry a random session token, view identity, project session and revision;
stale or cross-scope actions are rejected. A lease disables owner-dependent
controls after disconnect. Closing/redocking preserves the tab descriptor;
project replacement retires all previous views. No renderer or GPU object crosses
window boundaries. There is no project or solver authority in a child window.

This reuses the existing board viewport and parent layer/selection/analysis
callbacks. Geometry placement and solver setup remain in their existing tools;
these tabs do not create independent copies of a project or run concurrent
writes to a saved project. Browser fallback uses same-origin token-bound
BroadcastChannel sessions and reports blocked popup creation.

The architecture guard explicitly permits the new bridge. Native window event
permissions are restricted to the generated `spike-assembly-view-*` labels under
the existing assembly tool capability. No new dependency or physics method is
introduced. Validation is recorded in the gamma workspace validation report.
