# Native transistor charge update — development engine

The owned C++ solver now stamps conservative terminal charge alongside its existing
NPN Ebers–Moll and NMOS Level-1 conduction equations for backward Euler and BDF2.
Hybrid trapezoidal remains explicitly rejected for these models. Select `--method be`
or `--method bdf2` in `native-run`, or Backward Euler/BDF2 in Studio's run profile.
The development DLL is rebuilt; installed beta.5 and its installers are unchanged.

## Explicit bounded charge parameters

* NMOS `.model`: `CGS`, `CGD`, `CDS` are constant total capacitances in farads.
  They are SPIKES extensions, not a claim to implement SPICE Meyer/BSIM charge.
  They do not scale with W/L. Charge on each pair is C*(Va−Vb), added to one
  terminal and subtracted from the other.
* NPN `.model`: `CBE`, `CBC` are constant pair capacitances; `TF` and `TR` add
  forward/reverse junction diffusion charge Q=tau*Ijunction, with analytic
  differential capacitance tau*dI/dV. The exponential continuation is shared with
  the native conduction evaluator. These are not Gummel–Poon high-injection,
  voltage-dependent depletion-capacitance or avalanche models. `CJE/CJC` remain
  rejected rather than treated as constant capacitances.
* Omitted charge parameters are zero; no hidden manufacturer defaults are inferred.

The nonlinear residual includes dQ/dt, and the Jacobian includes the integration
coefficient times dQ/dV. Previous accepted voltages define prior charges, using the
existing transient history and timestep-rejection machinery. Net terminal charge is
zero by construction. Tests check integrated MOS gate charge, drain KCL, BJT
incremental base charge, BE/BDF2 execution and native WBG turn-on/thermal-rise traces.
This is limited equation-level qualification, not manufacturer qualification or a
complete convergence/accuracy validation across all bias regions.

I(M) / I(Q) reports total drain/collector current including displacement current.
P(M) / P(Q) is the existing two-terminal branch power convention, not total
multi-terminal dissipation. Probe terminal supply currents to audit electrical power;
do not feed P(M)/P(Q) into a thermal model as validated heat loss.

## Five-terminal native WBG bindings

```
Z1 drain gate source bulk thermal_rise modelname
.model modelname SPK_GAN(GATE_SOURCE_CAPACITANCE_F=1n)
```

`SPK_SIC` selects the existing SiC branch. These names are explicit SPIKES native
extensions, not manufacturer SPICE model syntax. Parameters use uppercase names
of the public WBG ABI's double fields, including thermal and capacitance terms.
The fifth node is temperature rise in kelvin, not absolute temperature; do not
ground it. The existing model supplies its thermal network. BE/BDF2 are required.
This binds the bounded model's existing charge/thermal/breakdown equations, not a
universal GaN or SiC compact model. No vendor part is certified by this binding.

Examples are in `examples/spikes/compact_charge`. Run, for example:

```
python -m python.spikes native-run examples/spikes/compact_charge/nmos_charge.cir --library build-spikes-current-vs18-20260906/Release/spikes_c_api.dll --method be -o nmos.json
```

Still open: arbitrary native nonlinear B execution, BSIM, IGBT/thyristor families,
full vendor-model compatibility and manufacturer-specific evidence. Transient FRA
is still a transfer experiment; automatic return-ratio/loop-gain extraction and
closed-loop stability qualification are not supplied by this charge update.
