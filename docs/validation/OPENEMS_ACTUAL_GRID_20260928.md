<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# openEMS actual-grid admission (2026-09-28)

Status: experimental PCB FDTD adapter improvement and local Windows reference
test. It is **not** arbitrary-PCB EM, calibrated multiport, EMI-compliance, or
native `spike.fullwave_3d` qualification.

## Change and bounded admission

CSXCAD receives the same continuous pad polygons and ports retain their exact
coordinates. The established conductor-edge `AddEdges2Grid` policy remains the
default. An explicit `experimental_compact_edge_grid: true` option omits those
automatic sheet-edge lines, avoiding curved-pad facet proliferation; it changes
the *rasterized* FDTD geometry and requires fresh mesh-convergence checks for
each application. It does not repair missing vias, antipads, cutouts, or
material interfaces. A real setup-only patch case confirmed the opt-in
`experimental_compact` policy is reported; default cases report
`conductor_edges`.
`examples/em/run_entity_port_patch.py --experimental-compact-edge-grid`
demonstrates the opt-in without changing the default.

Before `Run`, the isolated worker reads the **final CSXCAD grid** and rejects
non-finite or non-increasing axes and actual cell/memory budget violations. It
reports per-axis cell count and minimum/maximum spacings. For spacings
`dx,dy,dz` in metres it computes a vacuum Yee CFL reference timestep

`dt_CFL,ref = 1 / (c0 * sqrt(dx^-2 + dy^-2 + dz^-2))`.

This global-minimum-spacing value is a conservative **reference**, not
openEMS's actual timestep or a rigorous upper bound on its nonuniform-grid
Rennings2 method. The explicit resource policy requires
`max_timesteps * dt_CFL,ref` to span at least one cycle at the lowest
requested positive frequency. It can reject a runnable case and passing does
not guarantee sufficient decay, frequency resolution, passivity, or accuracy.
The host validates the reported grid/time metrics again. [The openEMS mesh
documentation](https://docs.openems.de/en/latest/concepts/mesh.html)
distinguishes the textbook CFL expression from its default timestep method.

## Executed evidence

On the pinned Marble provisional PI slice at 0.25 mm requested resolution,
the real setup produced a 69×67×49-cell grid (226,527 cells). Its minimum XY
spacing is 0.0078 mm due to distinct required port planes. The vacuum CFL
reference is 1.8175e-14 s. With 30,000 permitted steps, its reference window
is 5.4525e-10 s, below one 100 MHz cycle (1e-8 s). The adapter now fails
the configured policy before FDTD with
`OPENEMS_ACTUAL_GRID_TIME_WINDOW_POLICY_INSUFFICIENT`; it does not
snap the ports or claim a Marble S-parameter result. The older setup had
approximately 3.8 µm minimum XY gaps and advanced only 0.167 ns in 300 s;
removing those unnecessary facet lines alone is insufficient because the port
gap remains. Local ignored setup/error records are under
`build/validation/openems-marble-actual-grid-20260928*` and
`build/validation/openems-marble-time-window-20260928*`.
With the final 1.3.4 default conductor-edge policy and a diagnostic one-million
step allowance, the same Marble case still produced 226,527 cells and 7.8 µm
minimum XY spacing; it passed the *screen* with an 18.18 ns CFL reference
window but was **not** run. This confirms that raising the step allowance only
removes the preliminary screen, not the impractical-workload concern. The
ignored setup record is under
`build/validation/openems-marble-default-134-highsteps/`.

The installed openEMS 0.0.36 runtime completed an entity-port patch smoke
with 101 frequency points and 37×73 far-field samples. The current 1.3.4
default edge policy then passed the official
[simple-patch reference](https://docs.openems.de/python/openEMS/Tutorials/Simple_Patch_Antenna.html)
at all three real 5/4/3 mm runs and the existing convergence gate:

| Mesh (mm) | Resonance (GHz) | Min. abs(S11) | Peak directivity |
| ---: | ---: | ---: | ---: |
| 5 | 2.20 | 0.13346 | 4.70804 |
| 4 | 2.28 | 0.18444 | 4.82881 |
| 3 | 2.32 | 0.13141 | 4.84563 |

The finest-pair resonance and peak-directivity changes were 1.724% and
0.347%, below the fixture's 3% and 10% limits. All three runs had finite
normalized S11, positive radiated power, and positive directivity. These
checks are narrower than complex multiport S-parameter, reciprocity,
passivity, or measured-correlation qualification. The local result JSONs are
`build/validation/openems-patch-adapter-134/mesh-{5,4,3}mm/engine-output/normalized-result.json`;
their respective SHA-256 digests are:

- 5 mm: `aa8d450898f70fa7f09d5c0b43bdf7925bac61741f4e880be55829ea28c6b39b`
- 4 mm: `ad06b150c995b901a2cabf3423c4995bec79e311cf451fcadf6420abc2d9a0cc`
- 3 mm: `891fd040b6e05851fac8a4837f0278d01361ff8f2175da001aa56a42ae93ad2d`

Source SHA-256 at this run: adapter
`8464f6728bf593ae238933a50e059e4f2be2fa064389c661b1dfd83cbc792e58`,
mesh policy
`99c5f726ba0a7ef2d3e112a7f2244706ac99860f58b532141a4f683842cb45ea`,
and engine at the reference run
`9dc77f88f41af8f6d02e631e8308b6dc1ad32b9f7836db3c470722d5f5b6ac5b`.
Subsequent host-only validation hardening binds reported timestep, edge policy,
and actual cell/memory values to authenticated job options. It did not change
the FDTD geometry/solve source; both default and compact setup-only cases
passed the hardened import path. Current engine and host-validator SHA-256 are
`fe596450e304538d556fc13cf65e0e57082bb981f610aacfab5b9ff1272d132c`
and `f0cfdc9b850f4835463f2aaaa2e9d56a9aebac04924c48867445ca37440e76a8`.

Run with the pinned local runtime from the repository root:

```powershell
$env:SPIKE_STATE_HOME=(Resolve-Path build).Path + '\openems-private-state'
build\qualification-py311\Scripts\python.exe -m python.spike_core.cli openems-benchmark --mesh-resolution-mm 5 4 3 --max-timesteps 50000 --timeout-seconds 180 --case-root build\validation\openems-patch-reproduction
```

The earlier 1.3.2/1.3.3 compact-policy prototypes also passed this narrow
fixture gate, but the table and hashes above belong to the current
default-preserving **1.3.4** adapter. The previously packaged simple-patch
evidence binds **1.1.0**. The catalog correctly remains
`experimental`/`unvalidated` until this new local evidence is independently
reviewed, captured in a durable version-bound record, and packaged. The
result files are ignored local artifacts, not a portable release bundle.

## Remaining EM gates

Qualify conforming PCB stackups, padstacks/vias/antipads, copper holes and
board outlines; calibrated arbitrary cross-section wave ports and reference
planes; complex multiport S over three mesh levels; reciprocity, passivity,
field-energy balance, and independent/measurement correlation. The native
H(curl)/MoM and distributed production backends remain separate unfinished
work. No regulatory EMI/EMC conclusion follows from this reference fixture.
