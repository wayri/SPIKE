<!-- SPDX-License-Identifier: Apache-2.0 -->
# ESC promotion examples

See [START_HERE.md](START_HERE.md) for the manual SPIKE/Studio recording sequence
and [ATTRIBUTION.md](ATTRIBUTION.md) for redistribution boundaries. This supplements
the broader `examples/promo_showcase` pack with a source-pinned VESC hardware
example, Python workspace templates and executable native Studio projects.

The downloaded hardware is staged under `output/promo-esc-20261023/source`.
Scripts intentionally use existing registered SPIKE solvers and native Studio
execution; they add no numerical method. Each area documents exact inputs,
executed evidence, approximation and unsupported coupling. Native board packages
are generated under `output/promo-esc-20261023/thermal`. Original Studio projects
are under `studio`; actual board-derived phase dividers are under
`analytics/studio` and retain that area's hardware license boundary.

After each area's verification, `package.py` collects ready projects, source
notices and raw evidence in `output/promo-esc-20261023/READY_TO_OPEN`, makes a ZIP
and checks every archived file hash. It does not record UI footage or claim
three-phase firmware/controller/field coupling.
