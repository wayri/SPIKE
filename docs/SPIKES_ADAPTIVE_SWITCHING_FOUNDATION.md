# SPIKES adaptive switching foundation

Source implementation and Windows validation, 2026-10-10. This is an opt-in
native transient improvement, not an ngspice-parity or converter-qualification
release. Existing fixed-step defaults and explicit backend selection remain.

## Run a switching example

From the repository root, after building the native library:

```powershell
.venv/Scripts/python.exe -m python.spikes native-run examples/spikes/adaptive_switched_rc.cir --library build-spikes-adaptive-20261010/Release/spikes_c_api.dll --method bdf2 --adaptive --minimum-time-step 1e-12 --lte-absolute-tolerance 1e-6 --lte-relative-tolerance 1e-4 --probe 'V(out)' --probe 'I(Cout)' -o artifacts/adaptive-switched-rc-20261010.json
```

`--adaptive` requires `bdf2` or `hybrid_trapezoidal`. LTE absolute/relative
tolerances and minimum timestep must be finite and positive at the project
runner boundary. `--max-rejected-steps` bounds the combined LTE and Newton
rejection count. Nondefault adaptive controls without `--adaptive`, nontransient
analyses, or a minimum exceeding the effective integration step are rejected
before loading the DLL. Python callers use the matching keyword arguments of
`python.spikes.native_runner.run_native_project`.

The `.tran` output interval is separate from internal adaptive steps. Returned
project traces are linearly interpolated to the requested reporting grid;
measurements use the original accepted solver samples. Output provenance records
these semantics, method, tolerances and timestep controls. `points` counts output
samples; `integration_points` counts retained accepted solver samples. A reporting
grid can miss narrow peaks: tighten reporting intervals for plots, and use native
measurements/probes for investigation. This path is not bounded-memory streaming.

The supplied switched-RC example completed with 2,595 integration points and
41 reporting points, including 66 LTE rejections. It uses generic smooth-switch
values and is not a manufacturer-qualified power stage.

## Numerical changes and independently derived invariants

1. Primary Newton nonconvergence or numerical direction failure in adaptive
   mode restores the previous accepted solution, halves the proposed step and
   retries. Capacitor, inductor and built-in device histories commit only after
   acceptance. Minimum-step, rejection-budget and nonadvancing-time failures
   remain explicit. Singular systems fail closed. Fixed-step behavior is not
   converted silently to adaptive recovery. OSDI remains restricted to its
   admitted fixed backward-Euler path; arbitrary callback rollback is not claimed.
2. The sparse backward-Euler companion retains its own symbolic/numeric cache.
   Full CSC row/column patterns determine symbolic reuse; exact numeric equality
   permits numeric reuse. Changed values still require full numeric LU. The
   legacy `partial_numeric_refactorizations` counter means numeric factorization
   with reused symbolic ordering, **not local/rank-update refactorization**.
   Python also exposes `symbolic_pattern_numeric_refactorizations` for clarity.
3. BDF history restarts at source corners. BDF2 is used only when the new step
   is at most twice the previous accepted step; otherwise it falls back to BE.
   Adaptive startup/restart growth is capped at two. This conservative policy
   is not a proof of stability for arbitrary variable-step DAEs or device events.
4. Ordinary capacitor/inductor nonlinear residuals use accepted-state differences
   instead of subtracting large companion-matrix history terms. For BDF
   coefficients with `a0+a1+a2=0`, independently regrouping the charge derivative
   gives `C/h * [a0*(v-vn) + a2*(vprev-vn)]`. The flux derivative uses the same
   form with `L` and current. BE has `(a0,a2)=(1,0)`. Trapezoidal capacitor
   current is `2*C/h*(v-vn)-Iprev`; the inductor branch residual is
   `vL-2*L/h*(i-in)+vLprev`. The full companion Jacobian remains unchanged.
   Reported capacitor currents and accepted histories use the same stable form.
5. Adaptive Newton convergence is scaled by independent excitation, not enormous
   storage history RHS terms. This is still one global mixed-unit tolerance,
   not proper per-row voltage/current/temperature scaling. The residual repair
   covers ordinary linear C/L within nonlinear solves; linear direct solves and
   other device-specific charge/thermal histories retain conditioning limitations.

The embedded order-two versus BE state difference is an error-control defect,
not a rigorously calibrated universal LTE estimator. Startup/corner BE steps
have no embedded estimate. Failed nonlinear companion solves produce infinite
defects for rejection; Python serializes nonfinite diagnostic ratios as `null`
with `last_lte_estimate_finite=false`, preserving strict JSON.

Method provenance: [SUNDIALS mathematical considerations, v7.5.0](https://sundials.readthedocs.io/en/v7.5.0/cvode/Mathematics_link.html)
documents nonlinear-convergence recovery and separation of nonlinear/local
error control. It informed the recovery invariant, not copied implementation.
The equations, regrouping, cache, fixtures and code here were independently
authored; no external solver implementation was used as source material.

## Verification and reproducible cache microbenchmark

The standalone harness avoids PCB/UI dependencies. Set `Eigen3_DIR` in your
environment to your Eigen 3.4 CMake package directory before running:

```powershell
cmake -S tests/native_spikes -B build-spikes-adaptive-20261010 -G "Visual Studio 18 2026" -A x64 -DEigen3_DIR="$env:Eigen3_DIR"
cmake --build build-spikes-adaptive-20261010 --config Release --parallel 4
ctest --test-dir build-spikes-adaptive-20261010 -C Release --output-on-failure
$env:SPIKES_TEST_NATIVE_LIBRARY=(Resolve-Path build-spikes-adaptive-20261010/Release/spikes_c_api.dll).Path
.venv/Scripts/python.exe -m unittest discover -s tests/python -p 'test_spikes*.py'
```

Adapt compiler and Eigen paths to the host. Eight native executables passed,
including available OSDI/BSIM fixtures; 403 SPIKES Python tests passed with
15 skips. Focused post-cleanup adaptive runner tests passed 9/9. The architecture
guard passed. Whole-repository UI/Rust/packaging suites were not run for this
native increment. Knowledgeable human numerical review is required before release.

New regression oracles cover dense/sparse agreement, diode-RC fine-step reference,
failed Newton history rollback, retry exhaustion, exact source corner landing,
bounded BDF growth and fine-grid endpoint agreement. A constant 1-V source,
1-Mohm resistor and 100-uF initialized capacitor at 1-ps steps with a reverse
diode tests exact steady state: capacitor current zero and source current about
-1 uA, KCL within 1 pA. This independently exposes cancellation at tiny steps.

[Recorded cache benchmark](validation/spikes-adaptive-sparse-20261010.json)
contains every timing, controls, source/DLL hashes and all-branch waveform
agreement across nine alternating-order warm repetitions. MSVC 19.51 Release
uses `/O2`, `/fp:strict` and the same Eigen configuration for both builds. The
control is a current-source snapshot with only the embedded cache pattern test
replaced by unconditional cache invalidation. Rebuild it through
`-DSPIKES_TRANSIENT_SOURCE=<absolute-control-source>` in a separate harness tree.
Run `scripts/benchmark_spikes_adaptive_sparse.py --help` for comparison arguments.

Observed median solve times: 16-branch dense 1.634 -> 1.616 ms; 128-branch sparse
16.972 -> 16.222 ms; switched 128-branch sparse 11.524 -> 10.785 ms. Sparse cases
improved approximately 4.6% and 6.9% in speed ratio; dense difference is noise-scale.
Accepted grids and all recorded node voltages matched exactly. These are narrow
cache-only measurements, not comparisons against a prior packaged build or other
engines. DLL loading, circuit setup, extraction, memory and thread scaling are
excluded; first solve is not process-cold timing.

## Open qualification and next implementation

The subsequent [buck conditioning repair](validation/BUCK_LOCAL_INCREMENT_RECOVERY.md)
allows `examples/spikes/adaptive_buck_stress.cir` to complete to 200 us using
the existing default 1-fs minimum, with unchanged circuit and LTE tolerances.
A user-imposed 1-ps floor still fails: the 10-uH/1-Mohm mode requires finer
resolution. The recorded cache benchmark above predates this subsequent numerical
repair and is historical, hash-bound evidence, not a new-build speed claim.

Next priorities: unit-aware residual/error weights, device-charge conditioning,
calibrated LTE with startup control, compiled CSC stamp slots, device-event root
localization and measured factorization reuse. Then qualify converter parasitics,
recovery and electrothermal models, evaluate preconditioned nonsymmetric Krylov
methods, multirate/PSS startup acceleration and EMT/phasor coupling. Ordinary CG
is not a general solver for indefinite, nonsymmetric MNA. Multicore benefit,
cross-engine parity and hardware/HIL certification remain separate evidence gates.
