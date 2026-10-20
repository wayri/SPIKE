<!-- SPDX-License-Identifier: Apache-2.0 -->
# Run SI and PI from this checkout

The supplied-model SI and PI workflows execute now. Routed-copper DC and
bounded AC/transient PI also execute with the compatible native runtime.
These are engineering analysis paths with explicit model limits, not a claim
of unrestricted PCB extraction, measured accuracy or commercial-tool parity.
The [readiness record](validation/PISI_RUN_READINESS_20261018.md) records actual
commands, references, results and remaining acceptance limits.

## Desktop SI

1. Open **HF / SI -> S-parameters -> Source-to-receiver workflow**.
2. Start with the RLGC channel, import a reviewed Touchstone file, or select
   the bounded geometry path. Supply the actual frequency band, reference
   impedance and physical port order. The checked-in
   [four-port example](../examples/si/analytical-coupled-rlgc.json) is a supplied
   mathematical model, not extracted copper.
3. Review Sources / receivers, source swing and output impedance, receiver
   loading, packages, aggressors, passives and clock/threshold settings.
   Ports are one-based in the UI and zero-based in saved JSON.
4. Run the loaded study in the native desktop. Inspect network traces, loaded
   receiver waveforms/eye and TDR, and each returned stage's status/limitations.
   Save the setup and result. Editing setup invalidates the displayed result.

Changing the simple default four-port through path to a two-port channel now
moves the receiver from UI port 3 to port 2, preserving its model values and
showing a review notice. Custom assignments remain intact. Invalid endpoint,
passive or reorder assignments block Run with corrective messages; switching
channels never silently deletes them. A filename port count is only a UI hint;
the backend validates actual data. Physical port meaning still needs review.

## Desktop PI

For an explicit PDN, open **Power Tree -> AC PDN / CM-DM filters**. Review the
reference/return, named nodes and ports, source small-signal output impedance,
decap C/ESR/ESL and supplied parasitics. Enter a finite-rise load waveform,
output times and timestep, then run and inspect AC driving/transfer impedance,
load voltage deviations, energy balance and assumptions. Save the setup to the
tree and retain results independently. The initial model is an example, not
automatic extraction of the loaded board. See [the complete PDN workflow](PDN_SCREENING.md#explicit-ac-pdn-and-filter-workflow).

For routed-copper PI, use the copper DC/PI or PEEC AC/transient workspaces
through **Help -> Interactive analysis guide**. Import quality, terminals,
return paths, copper/stackup and solver admission must pass first. A DC source
and load on a supply trace without an explicit return solve only that supply
path; AC R/L impedance is not a calibrated full PDN or SI channel. Review
native geometry support and model status before interpreting a plotted result.

## CLI: immediately runnable examples

From the repository root, with this checkout's `.venv` dependencies:

```powershell
.venv/Scripts/python.exe -m python.spike_core.cli --output build/my-pi.json pdn-network examples/tutorial_pi_si/rlc-pdn.request.json
.venv/Scripts/python.exe -m python.spike_core.cli --output build/my-si.json si-workflow examples/si/analytical-coupled-rlgc.json --touchstone-output build/my-si.s4p
```

The PI command uses the same owned-worker solver as the desktop. Its explicit
[RLC setup](../examples/tutorial_pi_si/rlc-pdn.request.json) has source R/L and
two decaps with ESR/ESL, an assumed 2 A finite-rise pulse, and a 4 us observation
window. Values are original modeling assumptions, not vendor or board data.
It computes small-signal voltage deviation, not an inferred regulator operating
point. The window includes ringing and remaining stored energy; it is not a
settled-state claim. The [simpler RC setup](../examples/tutorial_pi_si/rc-pdn.request.json)
provides an independent closed-form frequency/ramp reference. Both JSON requests
can also be authored in the PDN workbench.

Run all modeled checks, including a timestep-halved RLC rerun and exported
Touchstone reinspection:

```powershell
.venv/Scripts/python.exe scripts/check_pisi_readiness.py --output-dir build/my-pisi-check
```

Use a fresh output folder for every run. To add the three native routed-copper
checks in the environment verified here:

```powershell
.venv/Scripts/python.exe scripts/check_pisi_readiness.py --native-python build/qualification-py311/Scripts/python.exe --output-dir build/my-pisi-native-check
```

The optional interpreter must have the compatible built native module. A
missing native runtime is an installation/build issue, never a successful
physics result. `readiness.json`, input copies, raw result JSON, commands,
hashes and logs are retained. A nonzero exit or failed case requires action;
do not treat partial frequency results as a completed eye/transient study.

## Requirements for your board

For PI: provide the project/PCB, rail and actual return, source/load terminals,
source impedance, load current waveform, decap operating-condition models and
acceptable voltage-drop/target-impedance limits. Refine mesh and timestep at
the quantities that matter; a small linear residual alone is insufficient.

For SI: provide signal/aggressor/victim and reference nets, physical port map,
stackup/materials, source/receiver/package models, rate/edge/threshold settings,
and the channel extraction or measured network. Eye/TDR require appropriate DC,
uniform grid, bandwidth and record support. Existing geometry extraction has
bounded planar path/return coverage; arbitrary vias, branches, launches and
complex return transitions remain unqualified. Imported verified networks are
the practical path for channels beyond that geometry coverage.

No user board was supplied for the readiness run. Native visual interaction,
installed-package acceptance, protocol compliance and measured board signoff
were not established. [Solver status](SOLVER_STATUS.md) remains authoritative.

## Supplied piecewise transmission lines

For sections with explicit different RLGC values and ideal electrical junctions:

```powershell
.venv/Scripts/python.exe -m python.spike_core.cli --output build/my-cascade.json rlgc-cascade examples/rlgc_line_cascade/three-sections.request.json
```

The [cascade method](RLGC_LINE_CASCADE.md) returns external frequency-domain
S data, complete coherent section fields and conductor/dielectric heat with
checked junction/global power balance. Its sparse three-frequency example is
not an eye/TDR sweep, and ideal continuity does not infer physical launch/via
parasitics. Existing loaded SI and PDN workflows remain separate runnable paths.

## Supplied ideal branch junctions

For two through eight explicit scalar legs meeting one ideal electrical node:

```powershell
.venv/Scripts/python.exe -m python.spike_core.cli --output build/my-junction.json rlgc-junction examples/rlgc_line_junction/three-legs.request.json
```

The [junction method](RLGC_LINE_JUNCTION.md) retains ordered external ports,
coherent interior fields, separate leg losses and checked common-node/global
power balance. The example is a supplied phasor model. It does not supply
missing board materials or establish physical T-junction/return parasitics.

## EBrake1 and Marble

The [19 October actual-board audit](validation/BOARD_PISI_READINESS_20261019.md)
uses the complete pinned designs and public CLI paths. Read its admission,
material, contact/return and mesh limits before interpreting a board result.
Marble's corrected RT0 diagnostic passes the narrow DC refinement gate;
full-board SI/PI remains unqualified for both boards.

The [owned-pad DC increment](OWNED_DRILLED_PAD_DC.md) removes the actual
EBrake J11.1 and U2.35/U2.39 shape blockers when explicitly selecting
`mesh.pad_zone_coupling: owned_shared_faces`. The full 3Vin diagnostic now
executes, but its current-density convergence still fails. Use
`scripts/check_ebrake_owned_dc.py --output-dir build/NEW-owned-study` to retain
the complete CLI request/result and unchanged convergence gate. A nonzero
exit from this study remains a failed sign-off even when the CLI completed.
