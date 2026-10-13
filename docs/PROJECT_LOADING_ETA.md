<!-- SPDX-License-Identifier: Apache-2.0 -->
# Project loading timing

The loading dialog reports elapsed time, completed stages and measured artifact
work. Time alone does not advance the progress bar. A usable scene is required
for 100 percent. Cancel loading and Escape preserve the existing cancellation
workflow; failure and cancellation stop the clock and leave a Close action.

On a first open, the package stage says Measuring and explains that worker
startup and package verification do not supply work counters. A previous open
of the same file name supplies a duration reference during startup, explicitly
pending project identity verification. The file name never authorizes a project
ETA. After manifest identity verification, only a completed open of that exact
manifest supplies stage timing estimates.

During result restoration, verified artifact bytes can estimate the current
stage after at least one second of observed work. Later stages are included only
when exact-manifest timing is available; otherwise the dialog labels the estimate
as remaining in this stage. These throughput forecasts assume future bytes take
roughly similar time. Stage overhead, changing I/O and models can change them.
Estimates use coarse seconds/minutes instead of a precise countdown. A stage that
exceeds its previous duration explains the overrun and waits for work or the next
stage to supply a new estimate.

`projectLoadProgress.ts` owns timing validation and presentation. `useProjectLoad`
retains at most eight successful complete profiles under the versioned localStorage
key `spike.project-load-timings.v1`. Entries contain manifest digest, file name,
stage durations and save time, expire after 30 days on reading, and never contain
project artifacts. Invalid or incomplete profiles are ignored. Storage failure
retains session timing hints without affecting loading. Failed or cancelled opens
do not overwrite successful timing profiles. Clearing app storage removes timing
history. The optional cache is a hint, not a promise of the next loading duration.

Focused regression check from `app`:

```powershell
node scripts/test-project-load-progress.mjs
```

The check covers cold startup, zero-duration stages, counters, stage-only versus
whole-project estimates, overruns, ready/cancelled transitions and cache rejection
and bounds. Native window layout and actual load duration remain runtime checks.
