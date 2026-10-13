<!-- SPDX-License-Identifier: Apache-2.0 -->
# SMPS design and stability scope

SPIKES targets lumped-circuit design of isolated and non-isolated converters.
There is no universal wattage checkbox that validates a design: a few-watt supply,
a kilowatt inverter and a megawatt converter require applicable device, magnetic,
thermal, interconnect and control models, each with declared operating envelopes.
Power-scaled analytical fixtures establish equation scaling, not hardware ratings.

## Available analytical design increment

The explicit ideal CCM voltage-mode workspace covers buck, boost, inverting
buck-boost output magnitude and flyback with an Ns/Np turns ratio. It accepts
power-stage parameters, operating duty, load, PWM/feedback gain and PI/Type-II/
Type-III compensation. The model is independent of the current schematic:
changing its parameters never silently changes the circuit.

Read [the numerical derivation and limits](SPIKES_SMPS_STABILITY.md). The
frequency window presents plant/loop Bode plots, a sampled Nyquist locus, actual
rational-model closed-loop poles, plant poles/zeros and crossover margins.
Positive margins alone are not a general stability proof. An averaged model
cannot establish switching-cycle or physical-system stability.

## Completion work, not implemented capability claims

1. Add reviewed DCR/ESR, nonlinear capacitance, controller dynamics and isolated
   feedback; compare against switched circuits with identical applicable models.
2. Extend conduction/control regimes: DCM, boundary/critical conduction,
   peak/valley/average current mode, slope compensation, sampled digital control,
   frequency control, pulse skipping and burst operation.
3. Qualify isolated forward, push-pull, half/full bridge, phase-shift full bridge,
   LLC/CLLC, dual-active bridge, SEPIC/Cuk/Zeta, multiphase/interleaved, PFC and
   multilevel converter workflows. Topology names are not interchangeable plants.
4. Provide settling-checked switched return-ratio experiments, injection-impedance
   validity checks, amplitude/linearity checks and periodic/Floquet analysis.
5. Support nested/multiloop systems, source/load impedance interactions, constant-
   power loads, robust tolerance/temperature/corner stability and sensitivity.
6. Co-qualify losses, saturation, leakage, gate ringing, Miller behavior, dead
   time, recovery, insulation and electrothermal/protection dynamics.
7. Publish equal-model circuit/reference/hardware evidence across relevant power
   ranges. Obtain knowledgeable numerical review before release; physical safety,
   EMC, insulation and hard-real-time claims need their own evidence.

Existing native transient FRA remains transfer measurement unless a reviewed
return-ratio fixture and assumptions establish loop gain. Existing linear
voltage-injection analysis is unilateral and not a periodic-switching solution.
