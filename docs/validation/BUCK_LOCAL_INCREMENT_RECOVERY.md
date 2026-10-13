# Buck local-increment conditioning repair

Source validation: 2026-10-10. Not manufacturer or hardware qualification.

## Diagnosis and repair

The unchanged generic asynchronous buck has a 10-uH inductor and 1-Mohm
off-state switch, giving a 10-ps extinction mode. Two separate issues occurred:

- Ordinary storage residuals still subtracted rounded absolute candidate
  voltages. At tiny steps, `C/h` amplified voltage quantization into a residual
  floor and the BE companion failed Newton convergence.
- After removing that floor, a user-imposed 1-ps minimum still prevented the
  all-coordinate BE/BDF2 defect test from passing. Tightening Newton to 1e-14
  confirmed a finite defect above one at that floor. Removing algebraic voltage
  error tests would change accuracy semantics and was rejected.

Primary and embedded Newton now retain separate increments relative to a common
local origin, materializing absolute states only for other device/static terms.
Ordinary C/L storage and capacitor current reporting use these increments;
embedded defects compare the increments directly. Accepted physical C/L changes
are retained for BDF history and source checkpoints. Fresh UIC capacitors shift
the local origin toward their initial voltage; this is a guess, not an extra
equation. Predictor-only convergence still checks Jacobian rank, and invalid
model-envelope predictions fall back to the pre-predictor origin.

Direct workspace continuation restores current C/L values from the accepted
solution rather than reusing old circuit ICs. New C++ checkpoint fields are
additive at source level; old empty fields use rounded-history fallback. Rebuild
C++ consumers after the header change. Public C ABI layouts remain unchanged.

Independent derivation: `x = anchor + dx`; capacitor change is
`(anchor_p-anchor_n-v_history)+(dx_p-dx_n)`. BDF current is
`C/h*(a0*delta-a2*last_delta)` because `a0+a1+a2=0`. Inductor flux uses the
analogous branch-current change. Both discrete systems retain the original
equations/Jacobians. Rejected candidates commit neither storage changes nor
currents. This is not full compensated arithmetic: accepted absolute trajectories
still round to double, and generic compact-model charges/thermal states and
linear direct solves are outside this repair.

## Reproduction

Build and test with the standalone harness in
[adaptive switching foundation](../SPIKES_ADAPTIVE_SWITCHING_FOUNDATION.md).
Then run from the repository root:

```powershell
.venv/Scripts/python.exe -m python.spikes native-run examples/spikes/adaptive_buck_stress.cir --library build-spikes-adaptive-20261010/Release/spikes_c_api.dll --method bdf2 --adaptive --minimum-time-step 1e-15 --lte-absolute-tolerance 1e-6 --lte-relative-tolerance 1e-4 --probe 'V(out)' --probe 'V(sw)' --probe 'I(L1)' -o artifacts/adaptive-buck-repaired-20261010.json
```

The original 200-ns maximum-step circuit completes to 200 us. The recorded run
used about 7,186 accepted steps, including a minimum around 1.48 fs. Its mean
output from 100 to 200 us was 7.90383 V, with peak inductor current 1.70012 A
over that interval. These are computed generic-model results, not measured data.
Keeping `--minimum-time-step 1e-12` deliberately fails rather than silently
changing accuracy or model parameters.

## Regression evidence and accuracy boundary

- Initialized 1-V, 100-uF capacitor charged at 1 mA with a reverse diode, 1-ps
  steps: independent KCL within 1 pA. Voltage follows `1+10*t` within 20 fV.
  Dense/sparse BE, BDF2 and trapezoidal paths and accumulated continuation are
  checked. A floating singular subsystem cannot be hidden by UIC prediction.
- Original buck completes through diode extinction in dense and sparse paths;
  endpoint comparison gates are 20 mV and 10 mA. All algebraic coordinate defect
  tests remain enabled and circuit values/LTE tolerances are unchanged.
- Coarse 200-ns versus refined 100-ns/fourfold-tightened-LTE comparison showed
  approximately 17.1 mV / 49.3 mA maximum differences on a 1-us reporting grid.
  Thus coarse-step completion is not a high-accuracy claim. Startup/corner BE
  steps still lack embedded error estimates.
- An explicitly finer configuration (20-ns maximum step versus 10 ns with
  fourfold tighter LTE, allowing a 0.01-fs minimum) meets the original 20-mV /
  20-mA trajectory gates: observed maximum differences were 0.474 mV / 3.72 mA
  on the same grid. This is refinement evidence, not an analytical switching
  waveform oracle or cross-engine/hardware correlation.

Eight native suites passed; 403 SPIKES Python tests completed successfully with
15 skips against the final DLL. Final transient-source SHA256:
`6c61b45f7fd077bcc33c102e969a856c093b97b079fe776813fd43eecb661f50`.
Final built-DLL SHA256:
`013443b0c64af6d6ca157750738c87d9e2d1942f9344687de1938806cb8a2033`.
The architecture guard currently fails on an
unrelated concurrent UI change in `app/src/SiChannelResultPanel.tsx` (spread
extrema over large arrays); this solver patch does not change that file.
Knowledgeable human numerical review remains mandatory before release;
this software repair cannot replace it or establish ngspice parity.
