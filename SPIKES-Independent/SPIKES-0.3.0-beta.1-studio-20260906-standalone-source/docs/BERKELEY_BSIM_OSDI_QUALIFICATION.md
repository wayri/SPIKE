# Berkeley BSIM through native OSDI

SPIKES compiles the official Berkeley BSIM-BULK 107.2.1 and BSIM-CMG
112.1.0 Verilog-A releases with the pinned OpenVAF-reloaded 20260616 build.
The resulting OSDI 0.4 modules execute directly in the owned C++ device path.

The loader now implements scalar real, integer and string parameter metadata,
aliases, case-insensitive SPICE parameter lookup, model/instance assignment,
`$simparam` values, the required Verilog-A log callback, reference-node noise
sentinels, DC residual/Jacobian callbacks, reactive charge callbacks, and OSDI
0.4 noise type/power/exponent callbacks. Qualification sets `TNOIMOD=1` and
requires an active `corl` source from both BSIM families.

Evidence is in
`artifacts/models/berkeley-bsim-osdi-qualification-2026-08-31.json`. The
source archives, extracted license/notice files, compiled modules and exact
hashes are retained together under `tools/models/berkeley` and
`artifacts/models`.

This is a native compact-model execution qualification, not a foundry-card or
silicon-correlation claim. “Production BSIM” still requires selected process
cards, geometry/binning suites, DC/CV/RF/noise/transient golden data and a
versioned validity envelope. Vendor IGBT, thyristor, GaN and SiC packages
require separately licensed artifacts and vendor or laboratory correlation;
they are not represented by SPIKES' generic bounded power-device equations.
