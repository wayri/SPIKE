# Closing SPIKE

Use the main window Close button or Alt+F4. Closing SPIKE ends its native
report, result, probe and assembly windows as well as its owned local workers.
Closing a detached tool alone leaves the main workspace open.

## Unsaved work

- If the main project is dirty, choose Save and continue, Discard changes, or
  Cancel. A canceled or failed save keeps the project open. Repeated Save clicks start
  only one write for that decision. Cancel invalidates any pending save-and-close
  decision; its eventual completion cannot close the application. Newer unsaved
  edits also keep the application open until saved or explicitly discarded.
- If an assembly tool holds a draft, SPIKE shows a review dialog. Review draft
  restores its minimized window. Save or discard there, then close SPIKE again.
  Cancel closing keeps both the application and the draft open.
- Desktop closing uses this application decision rather than a second browser
  before-unload prompt. Browser previews retain browser before-unload protection.

An unavailable draft window is reported without silently discarding its state.
Reopen the assembly tool and review it. If native close IPC fails, the main
workspace remains open and the status message invites another close attempt.

## Unresponsive workspace

If the renderer cannot acknowledge a close request within five seconds, a
native dialog offers to close anyway and warns that unsaved work may be lost.
Choose Keep open to retain SPIKE. Choose Force close SPIKE only when you accept that loss.
Repeated close clicks cannot stack recovery dialogs. If the renderer recovers
while this dialog is open, its save/draft guard takes ownership and a stale Force close
response cannot bypass that guard.

## Worker shutdown

After the main workspace admits closing, the native host rejects new worker
requests and asks running requests to terminate. Resident and one-shot workers,
including lightweight operations, observe the same shutdown flag. Resident
cleanup uses a nonblocking mutex attempt outside the UI event loop.

Cooperative worker draining has a two-second budget. Descendant retirement runs
after that drain and normal exit waits for retirement completion, with a total
four-second cleanup limit. Bridge shutdown runs independently so a locked bridge
cannot block child retirement. A five-second committed-close fallback exits the
host process if the
native event loop is stuck. These deadlines start after save/discard admission,
not while a user is deciding or saving. Owned worker process termination and
reaping have bounded waits. No unrelated process is selected for termination.

Closing during an analysis cancels that work. It does not mark partial output
as a completed result. Saved project and result files are not deleted by closing.

## Verification

`npm run test:desktop-close` exercises clean/repeated close, detached draft
protection, dirty project decisions, failed save, cancel and native dispatch.
The Rust desktop lifecycle tests exercise admission, bounded cleanup and owned
process handling. Windows packaging now requires a real native close after its
startup check and fails if the installed process remains alive for ten seconds;
a forced cleanup after failure is not acceptance evidence.

These checks do not prove every external engine responds to cancellation. Native
visual acceptance and the full release gates remain separate evidence.

## 27 October close reliability correction

The old cleanup thread could spend the entire three-second exit timeout draining
workers, then start descendant retirement just as another thread exited the app.
It also called bridge shutdown before beginning its drain timer. Cleanup now has
separate drain and total budgets, and bridge shutdown cannot hold up retirement.
The renderer also invalidates canceled save decisions and checks for edits made
after the saved snapshot before admitting close.

Executed checks: desktop-close behavior tests (including deferred-save Cancel,
newer edits, duplicate Save and fresh decisions after cancellation), all six Rust
lifecycle tests, TypeScript, architecture, button standard and UI hotfix checks
pass. The production frontend build passes with the existing large-chunk and
Plotly import warnings. The full host test run is 83 passed, 1 failed, 1 ignored: the failing
packaged-worker session test requires the absent packaged worker executable in
this source checkout. A native debug verification executable builds successfully
using a test-only empty bundle-resource override; this is not an installer.
Interactive native Close verification is pending desktop availability. No
installed-app update or newly qualified release is established by these checks.
