<!-- SPDX-License-Identifier: Apache-2.0 -->
# Qualification disk-exhaustion incident — 25 October 2026

## Outcome and ownership

An agent delegated by the integrating owner made a command-construction error
while preparing an additional Linux full-suite snapshot. This is an execution
error in our qualification work, not a solver numerical failure or a user error.
The copy exhausted host C: space. The second Windows full-suite attempt was
stopped and is **not qualification evidence**. No thresholds were changed.

Ubuntu starts again after narrowly verified space recovery. Its previously
qualified worker, manifest and native CHT hashes still match their pre-incident
records. The 6,475 guarded Windows input files also match their pre-attempt
hashes, with zero changes. These checks do not establish the integrity of every
unrelated host file or every other Linux workload.

## Cause and containment

A Bash loop variable was embedded in an interpolating PowerShell command. The
outer shell expanded it before Bash received it, changing the intended rsync
source to `/`. The destination was the newly created task directory:

`/home/gulkak/spike-linux-worker-20261024/src-moving-lid-fullsuite-r2`

It was not the repository or the retained Linux candidate. The failed copy
occupied 2,364,010,496 allocated bytes. Host C: reached zero free bytes and WSL
reported startup/filesystem I/O errors. The delegated worker terminated Ubuntu
before the integrating owner received the incident report. Such termination can
interrupt other jobs in that shared distribution; no absence of collateral
effects is inferred.

The Linux workstream was interrupted. The exact Windows qualification launcher
PID 230776 was revalidated by its command line before its task-owned process tree
was stopped. Its partial log is retained but is not used for acceptance. No
other Windows process was targeted. A subsequent Linux process check found no
running rsync.

## Verified recovery

Using the verified-project-cleanup procedure, the owner inventoried only two
completed task-owned worker staging copies under `build/`. Each candidate file
was matched by relative path, size and SHA-256 against the retained final worker
on D:. A fixture tested admission/rejection controls; tracked files, linked
paths, unknown classes and retention intersections were rejected. Source and
retained hashes were rechecked before file-only removal; retained guards were
rechecked afterward. No recursive directory deletion was used.

- Removed duplicate files: 2,956.
- Removed logical bytes: 557,585,078.
- Immediately observed C: free space after recovery: 586,977,280 bytes.
- Subsequent observations remained below 0.6 GB; heavy qualification is paused.
- Retained worker: `D:/SPIKE-moving-lid-qualification-20261025/compatible-v1-r2/worker/resources/spike-worker`.
- Cleanup manifest SHA-256:
  `33c37b9e1cfc466cf643fbac69c9e1a896f68104cac8588c71492c8d7623eb94`.
- Removal receipt SHA-256:
  `cd4696f1af995bcd47894eee97762bf680ec49a12d70b15e22ded43dfe0fe8e0`.

The task's installer files, native outputs, source, environments and saved results
were not removal candidates. The deleted staging copies can be reconstructed
from the retained worker; the old generated staging configs must not be reused
without restaging. Both original and corrected installer cohorts and their
extraction images remain retained.

After Ubuntu restarted, the following exact hashes were checked again:

| Retained Linux artifact | SHA-256 |
| --- | --- |
| Frozen worker | `6e85e12820fb4547f4bd337d4b7156f03bfdfaec3b974c501774e7463280df4d` |
| Worker manifest | `15fe1a9a21cd2fd857632d7dbc8f558788c167ee06e1e20b1bf6d1ca2a3c1631` |
| Native CHT executable | `bdb99e5c166f8a86ccbe5af798dc45765bab8115882de0048a03c57f57c7714a` |

The failed copy remains quarantined, not admitted as source or deleted. Ubuntu
was not unregistered, reset or reinstalled. No virtual-disk compaction or
relocation was attempted.

## Evidence and qualification state

Incident report, copied before/after input hashes, partial log and their digest
ledger are retained under
`D:/SPIKE-moving-lid-qualification-20261025/disk-incident/`.
The incident report SHA-256 is
`b8584b7560031db760a1de6a8399e8c86a18b819bb1b9d87dce918847bd4ffc0`.
The completed earlier full run remains a failed baseline; focused fixes and
successful frozen-worker/installer-payload checks do not replace the interrupted
full run. A fresh complete suite remains required after capacity is restored.

## Prevention and proposed next action

Future source transfers must use fixed argument arrays rather than shell-text
loops spanning PowerShell/Bash. Validate the source's exact canonical repository
root and required fingerprints, reject empty sources and filesystem/mount roots,
assert a fresh contained destination, perform a bounded dry run, and reserve
host capacity before copying. Independent source/target manifests must be checked
before executing qualification. No raw interpolating rsync retry is authorized
by this record.

The installed WSL 2.6.3.0 local help lists `--manage` / `--move`. The existing
Ubuntu VHD is 41,815,113,728 bytes; D: had approximately 285 GB free. A proposed
recovery is to coordinate all Ubuntu users, stop that distribution, make and
hash-verify a fresh backup on D:, then use the supported distribution move to a
fresh D: location. Verify registration, default UID and the retained artifact
hashes before resuming. Do not unregister the original distribution, delete a
backup, compact a live disk, or substitute an unverified copy. Microsoft documents
[WSL backup/export facilities](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)
and their scope. Relocating a shared development environment requires explicit
owner approval; this is a plan, not an executed recovery action.
