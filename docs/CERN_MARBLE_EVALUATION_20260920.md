# CERN White Rabbit and Berkeley Lab Marble evaluation inputs

User-authorized local hardware-data evaluation, 2026-09-20. These are third-party
hardware fixtures, not SPIKE implementation code or measured solver references.
Original files remain unmodified and outside source control under `build/`.
No upstream firmware, scripts or build instructions are executed.

## Source identity and licenses

The CERN collaboration's [official technology page](https://white-rabbit-collaboration-website.web.cern.ch/wr-technology/)
links the [White Rabbit hardware repository](https://gitlab.com/ohwr/project/wr-switch-hw).
The selected historical v3 files declare **CERN OHL v1.2**, not the newer
license described for current collaboration technology. The actual downloaded
README and full license are retained. This partial fixture selection is not a
complete fabrication package and has not been approved for redistribution.

- Commit: `54f8a604978bdc65bbde5b1f4c7ec9bee3505a44`.
- Core: `circuit_board/wrs_v3/SCB_SAM9G45/uTCA_MCH_PCB3.pcbdoc`,
  SHA-256 `f74bcabd7d073327e4236173cea4d2490bf661333d93c88d9bc052d482e82673`.
- 18-SFP backplane: `circuit_board/wrs_v3/mini_backplane_18SFP/miniBackplane.PcbDoc`,
  SHA-256 `0ddfe75d79cde08138734d538c19a9f22c591d5263f1805332057e6c52e3e715`.
- Local root: `build/white-rabbit-qualification-20260920`.
- Its `manifest.json` records each URL, hash and byte count, with qualification
  and redistribution flags false. The downloader checks the immutable-ref API
  response's member path, size and SHA-256 and enforces bounded responses.

[BerkeleyLab/Marble](https://github.com/BerkeleyLab/Marble) already exists locally:

- v1.4.4, commit `a426777d92c0f22a546d4740b419a3937e0c1f90`, CERN OHL v1.2.
- `build/marble-qualification/sources/Marble-v1.4.4/design/Marble.kicad_pcb`.
- SHA-256 `3304ba37c2bd891849fc36b500cd940934aaf1f2013a95639c03564fb925c512`.
- The board hash matches the earlier provenance. The checkout's project-local
  settings file has user changes, so the checkout is not described as clean and
  is neither reset nor replaced.

The installed KiCad CLI exported this board to an ODB++ archive for a local
SPIKE import comparison. The actual JSON-lines worker response was 252,676,698
bytes, below the 256 MiB desktop response limit. The import produced 12 copper
layers, 1,374 nets, 37,379 tracks, 122 zones, 7,246 pads, 3,664 vias, 3,871
drills, and 994 components. Rounded-rectangle copper flashes and all EDA copper
references resolved. The report retains 1,118 technical-artwork warnings. It
linked 3,664 holes to vias and 188 holes to component pads through exact ODB EDA
references; 19 mechanical holes lack an EDA owner and remain unresolved. The
export contains no complete physical stackup or component 3D model assignments,
so parsing and display do not establish solver readiness or model completeness.

## Executed evaluation and limitations

Marble validation was rerun using the repaired CPython 3.11 environment:
`build/marble-qualification/marble-validate-rerun-20260920.json`.
It reports `valid: true`, zero errors and two summary warnings: 22 recoverable
import-object diagnostics and one ambiguous component reference. This does not
establish complete geometry, connectivity, PI/SI/thermal accuracy or compliance.
Earlier synthetic SI/thermal smoke results are NOT results from this board.

Direct CLI validation of the CERN Altium core fails at UTF-8 JSON decoding:
`build/white-rabbit-qualification-20260920/core-validation.json`. The current
CLI does not import this native binary Altium board. Do not label this a valid
or solved board. KiCad conversion is a separately recorded experiment; even a
successful conversion requires independent geometry/material/connectivity checks.

The first sandboxed core/backplane conversions stalled and were terminated;
their originals were untouched. A 90-second-bounded retry outside the restrictive
sandbox successfully converted the core using installed KiCad 10.0.5:
`core-converted-bounded/conversion.json`. Native counts: 774 components, 4,550
pads, 27,699 straight tracks, 2,819 vias, 635 zones and 12 copper layers.
Converted board SHA-256:
`6ae6d75d44c89200ec358ad9f43403ff6b8bea4a3580758f160588fa91502aff`.

SPIKE inspection (`core-spike-inspect.json`) completed: 905 nets, 82,579
normalized tracks, 2,819 vias, 4,550 pads, 130 zones and 770 components.
These counts are NOT all one-to-one equivalent categories and have not been
reconciled. In particular, the report contains 505 recoverable object diagnostics
and no extracted explicit stackup. AC/HF qualification is blocked until geometry
loss and material/stackup completeness are resolved; successful parsing is not
successful physical extraction. No default dielectric constants are fabricated.

The matching backplane's bounded KiCad retry exceeded 90 seconds and returned
`conversion_timeout`; its worker was killed by the supervisor. No backplane
conversion or SPIKE import is claimed. The downloaded original remains intact.
Further work needs native-import diagnosis or an independently checked export,
not repeated unbounded retries. Conversion is an optional evaluation tool, not
an installed SPIKE Altium importer or production worker-sandbox implementation.

The downloader's integrity regression passes (altered path, encoding, size and
digest rejected). The architecture guard passes after adding the fixture tools.

Next evaluation gates: compare KiCad-native and SPIKE object/geometry inventories,
resolve import diagnostics, bind explicit real nets/terminals/return conductors,
obtain passing resource and model admission, run mesh/frequency convergence, and
compare against independent or measured references. Downloaded layouts alone
cannot establish 10GbE compliance, measured SI correlation or actuator accuracy.
