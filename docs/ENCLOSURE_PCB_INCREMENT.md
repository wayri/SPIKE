# Enclosure and PCB field workflow increment

SPDX-License-Identifier: Apache-2.0
Copyright (c) 2026 SigHarmonic

## Implemented

`python/spike_core/enclosure_stokes.py` solves steady incompressible Stokes flow
on a three-dimensional Boolean voxel mask. Fluid/solid faces are impermeable,
stationary walls are no-slip, and each disconnected fluid component gets its
own pressure gauge. Spatial body forces can produce recirculation around voxel
obstacles. Results include staggered velocities, pressure, momentum residual,
divergence, force work and viscous dissipation. The direct reference solve is
limited to 4096 cells and a discrete Reynolds estimate no greater than 0.1.
Cancellation is polled outside sparse factorization; it is not an OS deadline.

`python/spike_core/pcb_entity_ports.py` lowers explicit source-entity IDs,
copper layers and attachment coordinates into axis-aligned lumped ports for
the existing openEMS process workflow. It verifies attachment to the named
source, distinct selected nets, unique IDs and exactly one excitation. The
authenticated job carries the physical geometry digest and port mapping;
runtime reconstruction checks both again. Changed geometry requires recompiling
the port binding. Straight-track endcaps not actually exported are rejected.

Rectangular copper pads now retain arbitrary rotation in both host admission
and generated worker geometry. Their vertices contribute to domain bounds;
port contact uses the same rotated contour. Curved/custom/drilled pads remain
unsupported, rather than being silently replaced with ellipses.

## Far-field units correction

The installed openEMS pulse Fourier outputs were previously passed through as
absolute V/m and W. Those raw spectra require excitation normalization. The
adapter now reevaluates the excited port at each exact far-field frequency and
uses an explicit **1 W incident-power, zero incident-voltage-phase, peak-phasor**
reference. For real reference impedance R and incident voltage spectrum U:

`E_normalized = E_spectral * sqrt(2 R) / U`

`P_normalized = P_spectral * 2 R / |U|^2`

Missing, ill-conditioned or nonfinite incident spectra are rejected. Mandatory
normalization metadata prevents old raw-spectrum results from being accepted
as corrected results. Adapter version is now 1.2.0. Existing 1.1.0 reference
evidence is preserved but not silently relabeled for the changed implementation.
Experimental process execution remains available.

Phase centers are converted from the public millimetre coordinates to the
engine's metres. Its angular power-density samples are multiplied by radius
squared to give radiation intensity (explicit `angular_units: W/sr`), so
directivity does not change with observation radius. Regression tests check
nonzero centers, inverse-radius fields and radius-invariant intensity. Maximum
directivity is the maximum on the requested angular sample grid, not a proven
continuous-sphere maximum.

## Running the examples

From the repository root:

```powershell
python scripts/run_structured_solid_thermal.py --request examples/thermal/enclosure_stokes_request.json --result build/enclosure-stokes-result.json
python examples/em/run_entity_port_patch.py --output build/my-new-pcb-case --run
python scripts/verify_enclosure_pcb_increment.py
```

The PCB example requires the installed compatible openEMS Python runtime and a
writable private case-integrity state directory. In a workspace-restricted
development shell, set `SPIKE_STATE_HOME` to a private workspace-local directory;
do not disable integrity verification. Output case directories must be new.
Without `--run`, the example only prepares a case.

The verifier runs warnings-as-errors regression tests, one warmup and five
measured forced-obstacle flow solves, and emits source hashes, a source-stability
check, diagnostics and result hashes into a new build directory. It does not
represent private CI or clean-machine qualification.

## Local execution checkpoint (2026-09-06)

- 61 focused tests passed with warnings as errors and stable tracked inputs:
  `build/enclosure-pcb-evidence-20260906T165853.110767Z/report.json`.
  Another 25 external-engine/benchmark tests and the architecture check passed.
- The forced-obstacle example had momentum relative residual `6.23e-16`, maximum
  divergence `9.57e-18 s^-1`, and force-work/dissipation agreement to roundoff.
  Five measured solves had median `0.00521 s`; this is not a performance baseline.
- Installed openEMS 0.0.36, adapter 1.2.0 completed the actual entity-bound patch
  FDTD/NF2FF example in `build/entity-port-patch-normalized-20260906`.
  The 101-point S11 sweep had a minimum of `0.06733` at `2.32 GHz`.
  At `2.45 GHz`, corrected radiated power was `0.136047 W` for `1 W` incident;
  sampled maximum directivity was `4.83575`. These are integration results,
  **not renewed mesh-convergence or measured validation**.
  The driver hash matched the prepared job after execution.
  Result SHA-256: `9540615893882bce6c7b4c82488616262c1bf67e4b89260388f8c444a475d7bf`.

The earlier unnormalized case is retained for diagnosis, not accepted as
absolute-field evidence. No archived release or historic evidence was changed.

## Remaining scope — not declared complete

- The enclosure solver handles closed constant-property creeping flow only.
  Fan curves, inlet/outlet flow, inertia, buoyancy feedback, turbulence, thermal
  advection and conjugate heat transfer are not implemented by this module.
  Staircase-mask geometry is not curved boundary-fitted CAD. Box manufactured
  convergence and forced-obstacle conservation do not prove corner accuracy.
- The PCB example is a screened planar-stackup workflow, not an arbitrary PCB
  conforming-volume mesher. Board cutouts/outlines, detailed via/antipad stacks,
  arbitrary cross-section eigenmode ports and general enclosure scattering
  still require implementation and validation.
- Native distributed backends, arbitrary-PCB field qualification, measured
  correlation and deployable general multiphysics remain unfinished.

No manager, desktop package, archived release or private native implementation
is replaced by these development components.
