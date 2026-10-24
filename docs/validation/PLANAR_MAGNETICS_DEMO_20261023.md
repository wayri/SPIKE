<!-- SPDX-License-Identifier: Apache-2.0 -->
# Independent review: planar magnetics demonstration — 23 October 2026

Status: **pass for the stated reduced model's algebraic and discrete energy conservation; not release or hardware qualification**. Reviewer did not author the converter circuit/generator. This review covers the exact artifacts below, not general solver implementation or a physical 50 W converter design.

## Reviewed identity and execution boundary

SHA-256 of files read on 23 October 2026:

| Repository-relative artifact | SHA-256 |
| --- | --- |
| examples/promo_showcase/planar_magnetics/converter/converter-refined.cir | cc085431533fa04f2a94f83d50d0e90155244c19050e9edb6a557d8cc11c0381 |
| examples/promo_showcase/planar_magnetics/converter/run_converter.py | 0b6e4e16a1f1bc1141e6667330f2989d7c2ed9e7253c0650efd013551e825f88 |
| output/promo-planar-magnetics-20261023/converter/checks.json | de27fd77a77da386c4dfdaa3dcc0074ae6c532a1a852aaddccfb471a55d26602 |
| output/promo-planar-magnetics-20261023/converter/base-result.json | 9200cb7ea524e102b11d21706955e80a220c957c525210098a88991ab2682aa8 |
| output/promo-planar-magnetics-20261023/converter/refined-result.json | 971ac41f0576ae2ba281e202a4da0405979240121bd15981c6028544479eb3be |

The author-executed records report the native library hash `6b9014073366d7f43b003aa93a6ee740c3f750fbc978074b83c784320122ca5d`, 100 ns and 50 ns requested steps, and backward Euler. This reviewer **did not rerun the native solver** or reproduce that runtime binary hash. The reviewer did execute independently written NumPy arithmetic over both complete retained result files: dependent-source pair power residuals, right-endpoint source/resistor energies, L/C stored-energy changes, backward-Euler dissipation and final balance. Exact reported balances were reproduced. This distinguishes inspected upstream solver execution from independently executed postprocessing.

## Assumptions and governing identities

The excitation is a prescribed bipolar 48 V PWL bridge, 100 kHz period, fixed duty parameter approximately 0.306062. It is not a solved MOSFET bridge. At review, the code comment saying 20 ns edges was stale: the executed generator sets `edge=100e-9` s and the deck has 100 ns drive ramps. The author subsequently corrected only that comment to 100 ns, with new script SHA-256 `13146948c99e7ed48b74670363003f72f985afa2cd29a746b2b61f61784a4d27`. CIR and raw-result hashes remain unchanged; the reviewed identity table above preserves the pre-correction script hash. No new solver execution was claimed for the comment correction.

The transformer ratio is supplied `a=Ns/Np=1/8`. With primary voltage `vp=V(pri,0)`, secondary voltage `vs=V(sec_b,sec_a)`, and E-source current `iE` positive sec_b→sec_a, the E element imposes `vs=a vp`. The F element imposes current `iF=-a iE` positive pri→0. Consequently absorbed powers satisfy `vp iF + vs iE = 0` pointwise. The negative F gain is essential: replacing it by a positive value would create an active, nonconserving pair. The stated dot convention P1↔S2 is consistent with sec_b positive. This is an ideal transformer constraint, not a K-coupled-inductor or CAD-extracted model.

The magnetizing branch is a separate supplied linear `Lm=364.8 µH`. The nominal arithmetic `5700 nH/turn² × 8² = 364.8 µH` agrees with the EELP32 N97 set AL value; it ignores ±25% AL tolerance, mating gaps, amplitude/frequency dependence and saturation. It does not establish an actual wound-transformer inductance. The circuit's 1 GΩ secondary reference prevents a floating numerical node; it is not evidence of insulation/leakage-current performance or a safety isolation rating.

For the ideal behavioral rectifier, let dimensionless prescribed polarity signal be `s=V(pol)` and voltage-source current `iB` positive rect→0. The sources impose `vr=s vs` and secondary current `is=-s iB`; hence `vr iB + vs is=0`, including ramps and `s=0` freewheel intervals. This algebra is power conserving for arbitrary finite s, but does not model switch body diodes, dead time, reverse recovery, gate drive, switching loss or semiconductor thermal behavior. V(pol) is an abstract control quantity, not gate-power accounting.

The load is a resistor `R=0.0648 Ω = (1.8 V)²/(50 W)`, not a processor/CPU workload or constant-power load. Lout=1 µH, Cout=1 mF, Rprimary=0.05 Ω and Rlout=0.001 Ω are supplied lumped values. The duty is tuned at this one resistive operating case; no feedback regulator, load-step rejection, soft start, current limit or robustness to input/load variation is present. No efficiency or physical loss qualification follows from the 50 W operating-point match.

## Independently derived discrete energy check

For each retained interval h>0, backward Euler uses inductor voltage `v_n=L(i_n−i_prev)/h` and capacitor current `i_n=C(v_n−v_prev)/h`. Multiplying by the current endpoint state gives

`h v_n i_n = Δ(½ L i²) + ½ L(Δi)²`,

and analogously `h v_n i_n = Δ(½ C v²) + ½ C(Δv)²` for capacitors. Thus KCL power conservation requires

`E_source = E_resistors + ΔU_LC + D_BE`,

where `D_BE=Σ[½ L(Δi)² + ½ C(Δv)²] ≥ 0`. Terms are joules (H·A² or F·V²); resistor powers are watts and multiply actual interval seconds. D_BE is **numerical dissipation, not physical copper/core heat**. The implementation's use of actual saved dt and right-endpoint powers is appropriate to this identity, even where source breakpoints perturb the nominal time grid. A trapezoidal mean-power difference is a different quadrature and must not be presented as the exact discrete balance or attributed wholly to physical loss.

Independent recomputation on the retained approximately 0.8–1.0 ms window:

| Quantity | 100 ns request | 50 ns request |
| --- | ---: | ---: |
| Maximum transformer pair residual, W | 1.137e−13 | 1.137e−13 |
| Maximum rectifier pair residual, W | 1.137e−13 | 1.137e−13 |
| Source energy, J | 0.010299786949 | 0.010252562626 |
| Resistor energy, J | 0.010200417194 | 0.010200979680 |
| L/C stored-energy change, J | 5.262072746e−6 | 5.338388779e−6 |
| Numerical backward-Euler dissipation, J | 9.410768222e−5 | 4.624455694e−5 |
| Final energy residual, J | −4.310e−18 | 1.184e−17 |

These pass the unchanged author thresholds 1e−7 W for source pairs and 1e−7 J for energy balance. Numerical dissipation roughly halves under refinement. Inspected results give mean output 1.79992068→1.80005129 V and ripple 6.64851→6.70607 mV; this two-step comparison supports only bounded time-discretization consistency of these metrics. It is not a convergence-order proof, spatial refinement, physical validation or regulation test. The average output/load-power checks pass their stated tolerances (±25 mV and 48–52 W).

## Primary references and separation from core thermal evidence

Reviewed primary [TI, Power Transformer Design, SLUP126](https://www.ti.com/lit/ml/slup126/slup126.pdf), section4, displayed pp4-1 and4-3: magnetizing energy/flux depends on applied volt-seconds per turn; load transfer and leakage effects are distinct. Independently, Faraday's integral law gives `ΔB=(1/(Np Ae))∫vp dt` for an assumed uniform effective core section. Load-current matching alone cannot establish flux, core loss or thermal rise. No flux or arbitrary-waveform core-loss evaluation is added by this review.

The source-traceable ELP32/N97 inventory is in `examples/promo_showcase/planar_magnetics/core/n97-core-material.json`: [TDK ELP32/6/20, October2022,p2](https://www.tdk-electronics.tdk.com/inf/80/db/fer/elp_32_6_20.pdf) and [TDK N97, June2025,p2](https://www.tdk-electronics.tdk.com/inf/80/db/fer/n97.pdf). The set-loss limit <2.60 W is conditioned on 100 kHz/200 mT/100°C, not a loss law for this converter waveform. Material initial permeability is not a nonlinear B-H/hysteresis model. Separate generic ferrite thermal estimates retain their own provenance and status.

The reviewed converter deck/generator contains no thermal solve or electrical→core heat transfer. Core-only transient examples use explicitly supplied 1 W/2.6 W heating with generic thermal estimates; those are **separate illustrative solid-conduction studies**, not calculated converter core losses or coupled winding/core temperatures. This reviewer authored that core/CAD subpack, so this document is independent review of the converter algebra/retained numerical results only, not independent validation of its own thermal examples.

No 3D electromagnetic field/circuit/thermal co-simulation, CAD-derived leakage, skin/proximity loss, nonlinear core saturation/hysteresis, parasitic capacitance, insulation qualification, measured component characterization or whole-system thermal closure is established. Knowledgeable human numerical/hardware review and the existing project release gates remain required. No capability status is promoted by this record.
