<!-- SPDX-License-Identifier: Apache-2.0 -->
# Study manager validation, 2026-10-03

The shared study projection and manager were integrated independently into SPIKE
and the offline SPIKE-Em checkout. Original synthetic fixtures carry no measured
hardware data or solver qualification claims.

## Focused evidence

The simulation-study lifecycle, study workspace, study-manager interaction, and
project snapshot scripts passed in both projects. They cover frozen capture
history, setup invalidation through a real save/reload merge, repeated import
identity remapping and dataset links, attachment bounds, CSV fidelity, explicit
units, result-free copies, staged editing, suspended case types, and confirmed
deletion. Independent review reproduced and verified fixes for cleared-result
resurrection, collision-related link loss, and valid export/import round trips.

The production TypeScript/Vite builds passed in both projects. SPIKE parser and
architecture gates passed. The help reference is regenerated for the SPIKE
publishing checkout. Browser verification exercised the real React component
using the synthetic study-manager fixture at 1600 x 900 and 900 x 620, dark and
light themes, recorded-result inspection and compatible comparison, filtered
navigation, names containing spaces, dataset-only studies, and CSV attachment.
Small windows retain a collapsible detail inspector and bounded scroll regions.
High contrast, dataset unlink/relink, and cancellation of dataset deletion were
also exercised. The compact inspector begins below header/status rows, keeping
messages and dismissal controls visible.

## Required gate limitations

The isolated SPIKE Python regression run completed 2,301 tests in 339.101 seconds:
14 failures, 25 errors, and 69 skips. Failures/errors include unavailable native
PEEC/SPICE engines, release-owned runtime and packaged fixture paths, and runtime
readiness/qualification checks. The full suite is **not passing**. Its complete
local log is `.tmp/study-publish-python-tests.log`; UI tests do not qualify those
engines or establish numerical accuracy.

The earlier fresh native Tauri build failed with Windows error 112 (insufficient
disk space). Native desktop acceptance stopped when the Windows desktop was
locked, under the computer-use skill's lock rule. Fresh native rendering,
dialogs, Cargo tests, and native project reopen remain unverified. Browser
screenshots are browser evidence, not native acceptance.

## Publication

SPIKE changes are isolated on `codex/ui-engines-and-ide`; the primary checkout's
unrelated work is preserved. SPIKE-Em has a local Git history on `codex/spike-em`
and no configured remote, following the owner's offline instruction. Its study
commit excludes concurrent changes to engines, icons, materials, and unrelated
App/ownership-document hunks.
