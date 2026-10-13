# ADR 0064: Named circuit faults and scenario event timing

Status: Accepted for bounded engineering-preview implementation; physical
failure prediction and release qualification pending.

Native persistent sessions admit additive ABI-1 setters for ordinary resistor
resistance and NMOS Level-1 VTO. Only topology-preserving bounded changes are
admitted. Factors are invalidated, physical state is retained, and integration
order restarts at the discontinuity. A checkpoint includes parameter changes and
pending discontinuity state. Compiled board packages declare immutable named
fault sites and use those same native setters; they do not embed another solver.

Python owns explicit scenario/event scheduling, separate from numerical circuit
stamps. FIT/Weibull hazard calculations schedule an already allocated failure
mode using supplied conditional quantiles. Hours and electrical seconds are
explicit, and no implicit age acceleration, mode allocation or random state is
introduced. Exposure-to-parameter mappings bind an exact part and supplied local
coefficients/conditions; missing physical evidence remains unverified.

Finite provisioned shunts approximate selected shorts. Threshold shift is an
NMOS Level-1 parameter perturbation. Neither implies universal gate rupture,
body-diode damage, radiation response, bathtub lifetime or hazardous-environment
physics. The same declared fault schedule must match native and compiled-board
behavior within numerical tolerance and preserve replay/isolation before any
capability claim. Unsupported device mutations fail explicitly.

See [scenario contracts and evidence](../SPICE_FAULT_RELIABILITY.md),
[native setter details](../INTERNAL_SPICE_FAULTS.md) and
[compiled packages](../COMPILED_BOARD_LIBRARY.md). General scalar co-simulation,
FMI, external-engine adapters, HIL and hardware correlation are separate gates.
