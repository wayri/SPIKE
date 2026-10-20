# Board repair contact audit and unchanged replay — 19 October 2026

This record separates native input facts, numerical repair checks and physical
qualification. No gate, original fixture, production solver, stage status or
existing receipt is changed by the work described here. The coordinating chat
owns density/AC repairs; this chat owns only new independent audit scripts,
tests and this record. The owner explicitly keeps original EBrake contact
areas unspecified; no replacement electrode or sensitivity model is authorized.

## Independent native contact facts

`scripts/audit_board_terminal_contacts.py` reads native board expressions
directly, without importing SPIKE's board adapter, contact mapper or solver.
It pins the same source hashes as the actual board studies and records them
before and after reading. It preserves quoted parentheses and transforms pad
centres using native footprint position/angle. Backside local coordinates are
not mirrored a second time. This is a bounded audit of these pinned files,
not a general KiCad parser or a replacement importer.

The retained `build/ebrake-contact-review-20261019/native-contact-facts.json`
records both board hashes unchanged:

| Board | SHA-256 |
| --- | --- |
| EBrake | `d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca` |
| Marble | `3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512` |

The original 3Vin DC fixture sets 24 V at (165.1,116.3) B.Cu and a 1 A load
at (149.05,116.3) B.Cu. Neither record specifies a finite electrode footprint.
The source point overlaps three 0.7 mm track primitive envelopes near a
junction. The load point overlaps one such primitive, whose native endpoint
is (149.075,116.275). Neither input is exactly that native track junction.

The load point is strictly inside J7.2's circular through-drill void. Native
J7.2 centre is (149.075,116.275), drill diameter 0.95 mm; the point's distance
from the centre is `sqrt(.025²+.025²) = .0353553390593 mm`, well below the
0.475 mm radius. A track drawn to a plated-hole centre does not establish
planar metal inside the open drill. No barrel-wall current distribution,
solder fill, pad electrode or different terminal location is inferred here.
The original /AOUT1 AC fixture also provides no explicit source/load electrode
records. Its geometry/passivity checks remain required numerical tests.

Marble has finite native pad geometry, which is separate from an independently
confirmed external electrode/current distribution:

| Pad | Centre (mm) | Native size (mm) | Copper layer |
| --- | --- | --- | --- |
| U37.18 | (232.9726,159.4734) | 1.05 × .35, roundrect | B.Cu |
| R195.1 | (233.0832,159.385) | .62 × .58, rect | F.Cu |
| C383.1 | (234.4784,157.988) | .62 × .62, rect | B.Cu |

The existing RT0 probe states its uniform finite-pad injection and conjugate
area-average terminal voltage assumptions. This audit does not turn them into
measured contact evidence or reinterpret the original EBrake coordinates.
Native distances and transforms here are independent Euclidean calculations;
no external implementation or dataset was copied. Governing steady-conduction
physics and finite-contact work are recorded separately in
[the existing method evidence](../OWNED_DRILLED_PAD_DC.md).

Five focused tests passed, including both pinned native boards, malformed
expressions, a rotated footprint, backside coordinates, segment endpoints and
degenerate segments, and the fact that drawn-track overlap cannot override a
drill void. These verify source facts, not simulated physical performance.

## Source-bound unchanged repair replay

`scripts/verify_board_repair_acceptance.py` prepares and executes the following
unchanged checks with their complete original inputs:

1. Independent native contact audit above.
2. All four original `tests.python.test_kicad_fixture` EBrake tests, with
   `SPIKE_FIXTURE_BOARD` set explicitly. All four original identities must
   execute and pass; a missing native runtime, skip, substituted test, failure
   or incomplete log cannot pass.
3. Full EBrake owned 3Vin CLI/DC convergence through
   `scripts/check_ebrake_owned_dc.py`, retaining its original terminal values,
   four mesh levels and thresholds. Its failure is not waived by this audit.
4. Marble RT0 replay with the previously validated .5/.25/.125 mm levels,
   interior-edge factor .25 and original 250000 unknown/triangle caps.
5. Eleven public EBrake/Marble import/DC/AC/SI diagnostic probes. Their raw
   rejection states remain visible; diagnostic execution is distinct from
   successful SI/PI admission.

Before/after hashes cover all Python core/solver package helpers (including
new files), PEEC C++/header files and Python binding source, the exact runners,
original EBrake fixture and both board files. Python/dependency identities and
the loaded native extension path/hash are recorded before and after execution.
This describes the recorded source coverage; it is not proof that a binary
was built from those sources, a complete dependency/build provenance chain,
the full repository suite or package/release qualification. Those remain the
coordinating chat's separate checks. Source changes stop further replay and
prevent a passing acceptance report.

Every command and raw output is retained and hashed. A fresh workspace build
folder holds logs, requests, results, report and writable temporary files;
qualification-owned directories are rejected as output targets. Failures and
timeouts remain explicit, including partial process logs. Overall audit
execution also requires the public probes to finish. A passing repair-test
report still leaves `full_board_pisi_ready` and `production_qualified` false;
it cannot resolve the unspecified physical contact model or broader SI limits.
The script never edits stage statuses or old receipts.

Four focused harness tests pass: exact original-test identity/no-skip checks,
required-case and source/native drift rejection, unchanged Marble settings,
and detection of newly added or edited numerical helpers. These are evidence
contract checks, not substitutes for actual board reruns.

The preparation run at `build/board-repair-prepared-20261019/report.json` is
explicitly `prepared_not_executed`, with `repair_acceptance_passed: false`.
It supplies a concrete source snapshot and command plan, with **no simulation
or stage-completion claim**. Actual repair replay awaits the producers' source
freeze; original failures must remain failures when the unchanged runs fail.

```powershell
build/qualification-py311/Scripts/python.exe scripts/verify_board_repair_acceptance.py --output-dir build/board-repair-NEW-final
```

Use a fresh folder after confirming the repair freeze. Existing historical
EBrake failures, Marble refined-DC results, PI01-S01 receipts and frozen
qualification snapshots remain preserved. No new parity stage is marked done
by this contact audit or prepared replay.
