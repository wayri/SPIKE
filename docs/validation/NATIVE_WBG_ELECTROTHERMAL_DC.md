# Native WBG electrothermal DC slice

SPIKES now contains a native five-terminal `wbg_fet_electrothermal` element.
The drain, gate, source, bulk, and junction-temperature-rise terminals are
stamped directly into the existing sparse Newton MNA system. The thermal-node
residual is:

```text
T_rise / Rth - Pdevice = 0
```

The Jacobian includes electrical derivatives with respect to temperature and
the power derivatives with respect to all electrical terminals and
temperature. Thus the DC operating point is a genuinely coupled
electrothermal solve rather than a post-processing temperature estimate.

The two bounded technology branches are:

- `gan_hemt`: bidirectional channel current plus thresholded third-quadrant
  reverse conduction, leakage, and symmetric avalanche;
- `sic_mosfet`: bidirectional channel current, bulk junction diodes, leakage,
  and symmetric avalanche.

Both branches implement temperature-dependent mobility and threshold,
temperature-dependent breakdown voltage, finite model validity limits, and
charge-conserving Cgs/Cgd/Cds terminal charges. The constitutive API returns
D/G/S/B currents, a 4-by-5 current Jacobian, conserved terminal charges, a
4-by-4 charge Jacobian, dissipated power, and its five derivatives.

The additive ABI-v1 C boundary uses the versioned and size-checked
`spikes_wbg_fet_electrothermal_model` structure. The Python bridge exposes
`NativeCircuit.add_wbg_fet_electrothermal(...)` with explicit `gan_hemt` and
`sic_mosfet` choices.

## Qualification in this slice

Native tests cover:

- terminal-current and terminal-charge conservation;
- current-Jacobian conservation;
- hot-channel mobility reduction;
- SiC body-diode reverse conduction versus the GaN branch;
- avalanche conduction above breakdown;
- sparse-MNA electrothermal convergence and `T_rise = Pdevice * Rth`;
- invalid-model rejection;
- end-to-end C ABI and Python execution.

## Explicit production gaps

This is not BSIM, ASM-HEMT, HiSIM-HV, or a vendor-qualified compact model. The
current/charge Jacobians are bounded numerical derivatives, not generated
analytic derivatives. Charge conservation is executable, but transient charge
history is not stamped yet; transient construction must reject this DC-only
element. The model does not yet include trapping/dynamic Rds(on), nonlinear
capacitance surfaces, reverse-recovery state, short-circuit degradation,
thermal capacitance, mutual thermal coupling, package inductance, statistical
corners, aging, or measurement correlation. It therefore does not qualify
production GaN/SiC accuracy, converter transient accuracy, hard real time,
HIL, or competitive superiority.
