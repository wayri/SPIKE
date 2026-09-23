# Shared Mesh and Solve workspace

## User workflow

Select **Mesh** in the persistent ribbon to review discretization, via settings,
resource planning, preview and convergence. Select **Solve** for terminals,
return-path setup and execution. The existing PI setup instance is retained;
changing stages does not create another mesh configuration or discard edits.
Local PI run shortcuts route through shared Solve controls. G and U are the
default configurable Mesh/Solve keyboard shortcuts.

Select the PI or SI domain in the shared workspace. SI opens its existing
extraction/loaded-channel controls and retains its mounted setup between tabs;
it does not inherit PI mesh numbers or fabricate a mesh for a supplied network.
Specialized SI/model editors remain separate domain editors, not replacement
solver implementations. This increment does not claim every legacy dialog has
been removed, nor that all physics use one mesh representation.

## Running and Stop

Heavy worker operations share admission control and operation-ID-scoped state.
Unrelated health calls and rejected competing requests cannot dismiss an active
run indicator. Stop acknowledges immediately as **Stopping**, targets the exact
active operation, and remains pending until native execution settles. Late
results are rejected after cancellation; an accepted Stop is not a solved result.
Native project/MCAD operations use the same lifecycle as analysis calls.

Request writes run off the supervising thread, so a child that does not read
stdin cannot prevent the host checking cancellation. Native polling uses 50 ms
intervals; the Windows tree-termination helper has a 750 ms bound before direct
child termination. These are implementation bounds, not a guarantee of total
end-to-end UI latency under arbitrary OS/resource pressure. Output drainage is
also bounded. Stop discards work; it does not save a numerical checkpoint.

## Verification (2026-09-20)

- Full Python regression run: 1752 tests, nine skipped, successful.
- Rust lifecycle tests include a real child that leaves a 16 MiB stdin write
  blocked; owned termination releases that writer within the test's two seconds.
- Frontend mocked-invoke tests cover duplicate admission, late success after
  Stop, overlapping cancellation, and false/unknown cancellation responses.
- Shared-workspace rendering tests cover control separation and preserved state.
- Browser preview interaction confirmed Mesh/Solve stage changes, absence of Run
  in the Mesh panel, terminal tables in Solve, and retention of a 0.75 mm mesh
  input after Mesh -> Solve -> Mesh. No numerical solve was run in the browser.
- Production frontend build passed. No installer was produced by this change.

Remaining acceptance includes packaged real-board run/cancel stress testing,
large-result render profiling and broader responsive-window interaction checks.
These fixes do not establish that all large-board hangs or solver failures are
resolved. Numerical model validity and the PI release gate are unchanged.
