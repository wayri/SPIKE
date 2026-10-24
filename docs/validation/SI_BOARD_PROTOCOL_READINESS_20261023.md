<!-- SPDX-License-Identifier: Apache-2.0 -->
# Actual SERDES pair admission: Marble and WREN-Ie

## Scope and result boundary

This experiment addresses actual high-speed PCB nets, not the clock traces in
[the earlier material diagnostics](SI_BOARD_SCENARIOS_20261023.md). The script
`scripts/verify_si_board_protocol_readiness.py` invokes the unchanged
`extract_coupled_path_rlgc` on all 16 Marble QSFP-side TX/RX pairs and the two
native WREN-Ie SFP pairs in separate strict and piecewise-planar requests.
It does not qualify 10GbE, a complete board channel,
hardware, a vendor model, or the protocol runner. Admission failures are
preserved, not converted into synthetic passing channels.

The pinned native boards and third-party ownership remain those of the earlier
diagnostic record; no external board, standard, solver code or model is added
to the distributed repository. The original script, tests and this account
were independently authored. Public specifications were reviewed for interface
applicability, not to adapt their example code or implement an unreviewed
compliance algorithm. This changes orchestration and evidence only, with no
new physical equations or numerical gates.

## Physical identities actually inspected

Native KiCad 10.0.6 `pcbnew.LoadBoard` read both original files without saving
them. The following source net assignments agree with the SPIKE import. They
are package-pad and connector contacts, not measured compliance reference
planes or proof of native ratsnest closure.

| Board / pair | Positive / negative package contacts | Positive / negative connector contacts |
| --- | --- | --- |
| Marble QSFP1 TX1 | U1 D2 / D1 | J17 36 / 37 |
| Marble QSFP1 RX1 | U1 E4 / E3 | J17 17 / 18 |
| Marble QSFP2 TX1 segment | U46 13 / 12 | J8 36 / 37 |
| Marble QSFP2 RX1 segment | U48 19 / 18 | J8 17 / 18 |
| WREN SFP0 TX | IC20 R4 / R3 | J16 18 / 19 |
| WREN SFP0 RX | IC20 T2 / T1 | J16 13 / 12 |

Marble's U1 is `XC7K160T-2FFG676C` in FFG676; J8/J17 are
`SAMTEC_QSFP8-038-01-L-D-RA1`. QSFP2-side lanes terminate at
`PI3DBS16212ZBBEX` switches, so those named nets are only channel segments.
The pinned v1.4.4 `Marble_User_Guide.tex`, sections GTX Routing and QSFP,
identifies the direct bank-116 QSFP1 connection and switched bank-115 QSFP2
connection. The actual switch control state and its S-parameters remain
unbound. See the [official Marble project](https://github.com/BerkeleyLab/Marble)
and its [documentation](https://berkeleylab.github.io/Marble/manuals.html).

WREN IC20 is `XCZU4CG-1SFVC784E` in SFVC784; J16 is
`TYCO_1888247-1`. The exact nets are `/SFP0.TX_P`, `/SFP0.TX_N`,
`/SFP0.RX_P` and `/SFP0.RX_N`. This is the native CERN WREN-Ie source,
not the converted older White Rabbit switch board. Public project context is
the [WREN hardware repository](https://gitlab.cern.ch/be-cem-edl/chronos/wren/wren-hw)
and [WREN project](https://gitlab.com/ohwr/project/wren/-/wikis/White-Rabbit-Event-Node).
The online hardware page returned HTTP 403 during this review; local source
identity is pinned by the previously obtained file hash, not inferred from a
different online schematic revision.

## Applicable public requirements, not invented limits

Reviewed 23 October 2026:

- [SFF-8418 Rev 1.4, 30 July 2015](https://members.snia.org/document/dl/25879),
  sections 3.2-3.5, pages 15-22: 10GBASE-R SFI is 10.3125 GBd; host B/C test
  points include compliance fixtures. The differential/common-mode references
  are 100/25 ohm and instrument ports are 50 ohm. Section 3.3 specifies 12 GHz
  measurement bandwidth unless otherwise stated. The host output reflection
  requirement in Table 5 is defined at B, not a bare PCB trace port. It cannot
  be applied to the earlier DC-64 MHz two-port clock results.
- [SFF-8431 Rev 4.1 + Addendum](https://members.snia.org/document/dl/25891),
  archive cover: high-speed content moved to SFF-8418. The archived document
  is not silently represented as a current independent standard.
- [SFF-8436 Rev 4.9, 31 August 2018](https://members.snia.org/document/dl/25896),
  sections 3-4, pages 11-20: QSFP+ accommodates multiple applications; above
  6 Gb/s the specified protocol's compliance-board method and fixture-loss
  correction apply. Its 10G Ethernet references point to SFF-8431, while
  40G applications reference IEEE 802.3ba. The connector alone does not select
  4x10G breakout versus a four-lane 40G application.

Therefore WREN's SFP+ path is a candidate for an explicitly selected SFI
10GBASE-R study, not proof that the installed firmware/module operates in that
mode. Marble's QSFP path requires a declared module, lane mapping and firmware
mode before choosing its test procedure. Neither board identifies a 10GBASE-KR
backplane or 10GBASE-T copper PHY merely by containing FPGA SERDES. No optical
SR/LR/ER reach, BER, COM or normative loss-margin result is asserted here.

## Execution contract and reproduction

```powershell
.venv/Scripts/python.exe scripts/verify_si_board_protocol_readiness.py --output build/si-board-protocol-readiness-new.json
.venv/Scripts/python.exe -m unittest tests.python.test_si_board_protocol_readiness -v
```

Each board hash is verified before import and again after evaluation. The
import's source identity must match. Relevant implementation hashes are checked
before/after the complete run. A fresh output is mandatory; CLI exit 2 means
protocol qualification remains blocked even if some extraction prerequisite
eventually succeeds. An unexpected runtime error is not swallowed as an
engineering rejection.

The only override is the separately labelled **assumed** 58,000,000 S/m bulk
copper at 293.15 K scenario already documented in the earlier board record.
Only explicit copper-class materials are eligible. Original geometry, dielectric
properties, conductor thickness, stackup and source identity remain intact.
Each request names both polarities, GND and In1.Cu. Both `strict_uniform` and
`piecewise_planar` are attempted and reported separately. The latter explicitly
sets separation/skew tolerances to zero: it asks for an exact matched-segment
prerequisite, not tolerances fitted to a desired result. It does not select an
arbitrary reference zone, remove vias/arcs or switch to a clock trace. No frequency sweep is
executed when geometric admission fails, and no rejected pair has S-parameters,
loss, eye or BER evidence.

The output records all paired net IDs, track/arc/via counts, layers, widths,
component values, footprints and assigned package/connector pads. Marble QSFP2
records remain partial switch-to-connector segments, never a complete FPGA link.

## Executed real-board outcome

The final artifact is `build/si-board-protocol-readiness-both-modes-20261023.json`
(97,133 bytes), SHA-256
`3b18963b76e34e6a853db0bca565af49c75315c024cf4f25d67e1e575c092d11`.
All nine recorded implementation hashes matched current source after execution.
Both original board hashes also matched their pins. There were 36 actual
extractor calls (18 pairs times two modes), all rejected. The command returned
nonzero as intended. The preceding strict-only artifact remains at
`build/si-board-protocol-readiness-20261023.json`; its script hash belongs to
that earlier version, not the final both-mode verifier.

| Board / pair group | Strict first failure | Piecewise first failure |
| --- | --- | --- |
| Marble QSFP1 TX1-4 | Bends | Unequal paired segment counts |
| Marble QSFP1 RX1-4 | Vias | Vias |
| Marble QSFP2 TX1, TX3 | Bends | Unequal paired segment counts |
| Marble QSFP2 TX2, TX4, RX1-4 | Vias | Vias |
| WREN SFP0 TX | Vias | Vias |
| WREN SFP0 RX | Bends | Unequal paired segment counts |

For example, WREN TX retains 30/35 positive/negative straight tracks plus two
vias per polarity, spanning F.Cu and B.Cu. WREN RX retains 28/29 tracks on
F.Cu and no vias. Marble QSFP1 TX1 retains 12/96 tracks on F.Cu and no vias.
The segment-count rejection occurs before separation/skew tolerances are
evaluated, so choosing larger tolerances would not address that failure.
Its remedy would require a separately reviewed nonconformal path-pairing and
electromagnetic/discontinuity treatment, not trimming or merging source tracks
until the current gate passes. The via cases require three-dimensional return
and transition evidence. Reference-zone and dielectric gates were not reached;
this result does not claim they would pass afterward.

### WREN RX subdivision discrimination

A subsequent read-only diagnostic used the existing `_ordered_open_path` and
`_ordered_points` helpers on the complete retained RX paths. Coordinates were
expressed in native integer nanometres. Consecutive segments were considered
coalescible only when their integer cross product was exactly zero and their
dot product positive. This was a diagnostic list operation, not a design
mutation or another admitted solver run. The original board hash was rechecked.

No segment could be removed: P remained **28 -> 28**, N **29 -> 29**. Their
27 and 28 internal turns are all signed 45-degree bends, respectively. Both
widths are constant at 0.115 mm. Complete centerline lengths are
132.97084254510216 mm (P) and 133.07102784457635 mm (N), making N longer by
0.10018529947419 mm. This is geometric length skew, not an inferred delay.

With paths oriented from the low-x endpoints, corresponding main-run segments
2 through 20 (zero-based) are co-directed and parallel. Their perpendicular
centerline spacing is 0.214999999999975 to 0.215000059460479 mm; the tiny spread
reflects native-coordinate quantization on diagonals. In contrast, initial
track endpoints are 0.8 mm apart and terminal track endpoints 0.94231 mm apart.
The second segments head at +45 degrees and -45 degrees, and terminal breakout
turn sequences differ. These distances describe track geometry, not new package
models or a complete minimum-clearance/field calculation.

Thus the 28/29 mismatch is not redundant collinear CAD subdivision. The long
coupled middle run does not make the entire fan-in/fan-out paths conformal;
removing their differing portions would discard physical coverage. No automatic
coalescing, fitted tolerances or partial-route substitution is justified by
this check. The existing rejection remains appropriate.

## Verification and remaining work

Nine focused tests passed with zero skips. The positive case genuinely executes
the existing coupled extractor on the authored straight-pair fixture and checks
its per-unit-length resistance independently using `R'=1/(sigma*w*t)` in SI
units. Negative cases cover actual via/bend and piecewise-segment rejection with retained geometry,
missing polarity, missing copper classification, source-hash mismatch,
unexpected runtime errors and overwrite refusal. Material preparation is checked
for immutability and unchanged dielectric/source records. Architecture validation
passed. The fixture is not a measured PCB or vendor reference.

Completion requires an exact operating configuration and applicable test
procedure; full broadband package/via/connector/switch/return-path networks;
board-specific frequency-dependent material evidence; independently correlated
Tx/Rx/CDR/jitter/BER models; fixture/reference-plane transformations and executed
normative comparisons with uncertainty. Native DRC/ratsnest closure, production
hardware measurement, human release review and installer qualification are not
provided by this experiment. The RF-network and KiCad skills enforced explicit
port/source identity and the separation between native parsing, numerical
admission and physical qualification.
