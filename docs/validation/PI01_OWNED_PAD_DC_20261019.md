# PI01-S01 owned pad DC verification — 19 October 2026

This is a bounded geometry/contact increment, not EBrake or Marble SI/PI
qualification. The live-workspace hold was explicitly released by the
qualification owner before implementation. Frozen qualification copies were
not modified. [Method, referenced physics and limits](../OWNED_DRILLED_PAD_DC.md)
describe the independent derivation and unsupported envelope.

## Implementation and acceptance

The opt-in `owned_shared_faces` DC route now retains the actual drilled
rounded-rectangle J11.1 and resolved convex non-drilled custom SMD U2.35/U2.39
on the original EBrake 3Vin selection. No source pads, source polygons or
drills are removed. Inscribed outer/circumscribed void boundaries, union-ray
partitions, actual shared-face widths and polygon centroids preserve bounded
source support and ownership. Barrel resistance normalization is unchanged.
Custom source convexity is checked without filling a convex hull.

Default dispatch, current-density semantics, convergence thresholds, AC guards,
terminal identities and resource limits are unchanged. Unresolved, nonconvex,
holed and drilled custom pads remain unsupported. Malformed dimensions, radius,
drill, mirror metadata, inadequate ligaments and over-budget allocations fail
closed. Asymmetric mirrored custom polygons have independent area/containment
checks; native U2 source polygons each retain 4.8897876427994635 mm².

The angular annulus resistance errors at targets .5/.25/.125/.0625/.05 mm
are 7.744660/2.195461/.574669/.145556/.093312 percent. This meets the
predeclared 2% finest-error bound with monotonic refinement; the existing radial
annulus 1% bound is unchanged. Complete cell-edge containment and independent
rounded-land/drill area bounds check support separately from resistance.
Independent KiCad 10.0.6 inspection confirms J11.1 dimensions/drill/radius;
the native-IU rounding difference and 128-chord sagitta are documented separately.

## Actual EBrake run and failures retained

Pinned board SHA-256:
`d0117300c730688ce2311c2908cec041c537689f59aa4527ffa6bdec68a2edca`.
Full source design and original assumed diagnostic terminals are retained:
24 V at (165.1,116.3) B.Cu, 1 A at (149.05,116.3) B.Cu, net 3Vin.
These are fixture assumptions, not confirmed board operating requirements.

The initial retained `build/ebrake-repair-20261019/owned-final` run rejected
the two custom SMD pads. After the bounded source admission, the fresh
`owned-custom-reverified` run completes through the public CLI at 1 mm with
`model_status: approximate`. All four convergence levels [2,1,.5,.25] mm
execute. Before/after solver/importer source and board hashes match.

The final .5→.25 mm comparison has voltage-drop/loss/resistance changes about
0.050383%, passing their unchanged 3/5/5% gates. Required p95 current density
changes from about 2.5878e-11 to .9505001 A/mm², failing the unchanged 10%
gate. The report correctly records `can_sign_off: false` and `passed: false`.
Excluded undriven branches and unassigned terminal contact resistance remain
visible warnings. No passivity projection, branch-statistic substitution or
geometry clipping was used to force acceptance.

The original default EBrake acceptance was also rerun with the native runtime:
four tests executed, geometry and DC smoke passed; the original density
convergence and AC tests still fail. Default p95 changes 10.750431→7.416919
A/mm² (31.0082%, above 10%). AC retains four negative-energy modes; finite-volume
retry rejects 46 bases outside source copper, first excess .04407490138 mm².
See `build/ebrake-repair-20261019/original-ebrake-acceptance.log` and
[prior physical diagnosis](EBRAKE_FIXTURE_QUALIFICATION_20261019.md).

## Reproduction and evidence

Use the native Python 3.11 environment and a writable temporary directory:

```powershell
$env:TEMP=(Resolve-Path build/si02-s06-temp).Path
$env:TMP=$env:TEMP
build/qualification-py311/Scripts/python.exe scripts/check_ebrake_owned_dc.py --output-dir build/ebrake-repair-20261019/NEW-owned-run
```

Select a fresh output folder. The script exits nonzero when board convergence
fails, even if the CLI completes. Its retained request, output, raw convergence
results, log and source-stable report are bound by the geometry stage gate:

```powershell
build/qualification-py311/Scripts/python.exe scripts/parity_owned_pad_gate.py --output docs/validation/parity/NEW-PI01-S01.json --log docs/validation/parity/NEW-PI01-S01.log --board-dir build/ebrake-repair-20261019/owned-custom-reverified
```

Historical intermediate receipts are preserved. The backlog points only to
the final source-current receipt. This stage's passing geometry evidence never
turns a failed board-convergence result into a passing result.

## Remaining work

Full PI01, EBrake SI/PI and unrestricted Marble SI/PI remain open. The next
numerical blocker is a consistent unique-volume vector-current observable and
conforming finite contacts, followed by supported R/L field bases for AC.
The old axial-branch pseudo-volume p95 must not be silently replaced or its
gate removed. Affine rotated sheet and angular/radial annulus field oracles,
charge conservation, exact dissipation, finite terminal work and real-board
refinement must establish any replacement before default promotion.
No physical measurement, thermal feedback, arbitrary-contact accuracy or human
release review is supplied by the geometry tests.

## Executed stage and Marble checks

The final [source-bound receipt](parity/PI01-S01-bound-board-20261019.json)
records **28 tests passed, zero skips**, with stable source hashes and the
actual complete EBrake request/results bound by SHA-256. The gate additionally
checks that all four board levels executed and the original numerical
thresholds are retained. There are 67 further passing impacted geometry,
terminal, custom-pad, density/convergence and clipping regressions; two
evidence-contract tests pass. Independent review ran 22 frozen production-source
geometry/owned tests and native KiCad checks, with no remaining defect.
The later asymmetric mirror test adds coverage without production-source edits.
No full repository suite or release pass is claimed; the original four-test
EBrake run retains its two genuine failures.

Positive face widths and material conductivity produce nonnegative branch
dissipation; fixing a terminal potential removes the connected-component
constant-potential nullspace. Thin ligaments and nonorthogonal cells can still
degrade conditioning/accuracy. The 1 mm actual CLI solve reports scaled
residual about 9.64e-17 and current imbalance about -2.86e-13 A; small algebraic
errors do not repair the failed density observable or prove field accuracy.

Marble's pinned board hash is
`3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512`.
The coarse default RT0 experiment is preserved separately in
`build/ebrake-repair-20261019/marble-current-rt0.json`: resistances
4.463887/4.287492/4.197591 mΩ at .5/.25/.125 mm fail the unchanged 2% gate
(changes 4.1142%/2.1417%). This is not the previously validated mesh setting.

Replaying **exactly** the previously validated configuration, including
`--interior-edge-factor .25 --max-unknowns 250000 --max-triangles 250000`,
reproduces 4.196854930/4.140156100/4.108869814 mΩ and passing changes
1.36949%/.761433%. Evidence is retained at
`build/ebrake-repair-20261019/marble-current-refined-rt0.json`. All four audit
source hashes and the board hash match the prior corrected report; no gate
or historical resource envelope was changed. C383.1 remains connected.
This remains an experimental, explicitly refined, narrow DC result, not a
default configuration or AC/SI qualification.

The fresh public two-board audit completed all eleven requested CLI probes:
`build/ebrake-repair-20261019/board-public-reverification/readiness.json`.
Its `audit_execution_completed` is true, while `full_board_pisi_ready` and
`production_qualified` remain false. Both imports execute. EBrake VBUS DC
still fails its two-step 2% refinement gate (13.2411%/2.8250%); its separate
VBUS AC diagnostic completes approximately with capacitance disabled and no
physical return, which does not close the original /AOUT1 AC failure.
Marble routed and C383 DC probes complete; Marble AC rejects unsupported
field support/passivity. Strict SI still rejects EBrake's ambiguous reference
zone and Marble's bent path. Materials, reviewed ports and physical return
paths must be admitted rather than invented to make these requests pass.

Tracking/evidence/board-audit tests: **30 passed**, zero skips. Architecture
and reference inventory checks pass. Whole-tree whitespace checking also
reports pre-existing changes outside this increment; those files were left
untouched. This is not a clean whole-tree or release qualification claim.
