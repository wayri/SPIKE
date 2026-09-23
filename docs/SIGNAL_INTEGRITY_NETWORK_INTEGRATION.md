# Signal Integrity Network Integration

## Purpose

SPIKE separates geometry extraction, field solving, and network processing. A
solver plugin receives normalized geometry and returns an inspectable network
contract. Network processors may then calculate transmission-line, S-parameter,
time-domain, and eye-diagram results without owning PCB geometry.

The current native PEEC path produces R, partial L, and driving-point Z(f). It
does not produce C or dielectric G, so capacitance-dependent transmission-line
outputs remain blocked rather than inferred.

## RLGC exchange contract

`spike/rlgc-network/v1` records:

- source and sink port identities;
- extracted R and partial L;
- C and G values or an explicit unsupported state;
- the frequency-dependent complex impedance sweep;
- model status, assumptions, supported uses, and blocked uses.

The contract is suitable for process-isolated solver adapters, SPICE export,
Touchstone generation, and independent network processors. Missing terms must
remain null and must not be silently estimated by the UI.

## Transmission-line processing

When validated per-unit-length R, L, G, and C are available, an independent
network processor can use the standard telegrapher-equation relationships:

```text
gamma(f) = sqrt((R(f) + j*w*L(f)) * (G(f) + j*w*C(f)))
Z0(f)    = sqrt((R(f) + j*w*L(f)) / (G(f) + j*w*C(f)))
```

For length `d`, the uniform-line ABCD matrix is:

```text
A = D = cosh(gamma*d)
B = Z0*sinh(gamma*d)
C = sinh(gamma*d)/Z0
```

ABCD can then be converted to Z, Y, or S matrices at an explicit reference
impedance. Coupled lines require matrix-valued RLGC terms and modal or direct
matrix propagation; scalar approximations must not be used for NEXT/FEXT or
differential channels.

## External SignalIntegrity adapter

The Nubis/Teledyne LeCroy SignalIntegrity project is GPLv3. SPIKE may use its
published workflow ideas and standard mathematics, but GPL implementation code
must not be copied into or linked with SPIKE's MIT/open-core modules.

A future optional adapter must therefore run as a separate process and exchange
only documented RLGC, Touchstone, waveform, or JSON data. The adapter manifest
must declare its license and installation source. SPIKE remains functional when
the adapter is absent.

Reference: https://github.com/Nubis-Communications/SignalIntegrity

## Validation gates

Before enabling transmission-line outputs, the producing solver must provide:

1. Frequency-dependent R and L validation, including skin and proximity effects.
2. Stackup-aware C and dielectric-loss G validation.
3. Port and return-path definitions.
4. Matrix RLGC for coupled-line analysis.
5. Analytical microstrip/stripline fixtures and measured or trusted-tool comparisons.
6. Frequency range, convergence, conditioning, and model-limit metadata.

Until those gates pass, SPIKE may display extracted R/L/Z(f) but must label
characteristic impedance, delay, S-parameters, crosstalk, and eye analysis as
unsupported.
