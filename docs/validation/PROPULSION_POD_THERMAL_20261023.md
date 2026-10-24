# Eleven-node electrothermal feedback — 23 October 2026

## Method, identity and units

Original Apache-2.0 implementation `python/spike_core/propulsion_pod_thermal.py`, class `ThermalNetwork`, and its dedicated tests are experimental lumped thermal feedback. Nodes 0..2 are phase A/B/C windings; nodes 3..8 are phase-major MOSFET junctions A-high,A-low,B-high,B-low,C-high,C-low; node 9 motor case; node 10 board case. No actual board reference designator or calibrated motor identity is inferred. Kelvin is used throughout; temperature differences in kelvin equal differences in degrees Celsius. Capacity C is J/K, symmetric pairwise conductance g is W/K, resistance ohm, temperature coefficient K^-1, power W, time s, energy J.

`validate_thermal_spec` returns a fresh normalized bounded specification. Positive capacities and reference resistances, nonnegative conductances and temperature coefficients, exactly symmetric zero-diagonal links, finite scalar/vector shapes and ordered admissible temperature bounds are checked. Resistances remain strictly positive over the full admitted interval. Zero ambient conductance or absent links are valid adiabatic limits. `spec` returns a deep copy. Supplied initial temperatures are retained in specification; every stateless step explicitly receives T0.

## Independently stated mathematical reduction

For each node, conservation of internal energy gives Cj*dTj/dt = pj + sum_k gjk*(Tk-Tj) - gj,ambient*(Tj-Ta). Define G=diag(sum_k gjk+gj,ambient)-g; symmetric links imply G is positive semidefinite and internal exchange cancels under multiplication by the all-ones vector. G has W/K units.

For the winding phases Rj(T)=Rj,ref*(1+alphaCu*(T-Tref)); phase heat is ij^2*Rj. Each phase high MOSFET receives dutyj*ij^2*Rhigh(T), and its low MOSFET receives (1-dutyj)*ij^2*Rlow(T). Leg resistance is dutyj*Rhigh+(1-dutyj)*Rlow, exactly matching the sum of that phase's junction heat. Duty is in [0,1]. This is averaged conduction heating, excluding switching, diode, gate, reverse recovery and magnetic/core losses. Signed currents yield nonnegative heat. Nonnegative bearing heat is deposited only in motor-case node 9.

Let w be these nine nonnegative squared-current duty weights. Then pj(T)=p0j+betaj*Tj with p0j=wj*Rrefj*(1-alphaj*Tref), betaj=wj*Rrefj*alphaj. Cases have beta=0; motor-case p0 includes bearing heat. An individual algebraic p0 can be negative, but the actual admitted p(T)=wR(T) remains nonnegative.

With h=dt and Tbar=(T1+T0)/2, midpoint balance is

`[diag(2C/h)+G-diag(beta)]*Tbar = diag(2C/h)*T0+p0+gambient*Ta`.

The code solves this 11x11 linear system, then T1=2*Tbar-T0. This is an exact solve of the admitted midpoint discretization, not an exact continuous trajectory. It uses the same Tbar for resistance and heat. A must be positive definite with lambda_min > 1e-12*max(1,lambda_max) and condition number <=1e12; failure rejects the step, rather than accepting an ill-conditioned positive-feedback branch. This is a numerical time-step/feedback gate, not proof that the continuous heated network has a stable equilibrium. Both endpoints and midpoint resistances must remain in the admitted temperature interval. Midpoint is second order for smooth solutions but not unconditionally monotone. A conservative additional gate requires diag(2C/h)-diag(G)+beta >= 0, making the old-state propagation matrix entrywise nonnegative because off-diagonal links are nonnegative. This prevents the usual large-step passive RC undershoot; the caller reduces h on rejection. This gate does not replace the SPD, endpoint or equilibrium-stability checks.

Summing the actual midpoint equations yields exactly (up to floating point residual)

`storage_j + ambient_heat_j = generated_heat_j`,

where storage=sum Cj*(T1j-T0j), ambient=h*sum gj,ambient*(Tbarj-Ta), generated=h*sum pj(Tbar). Ambient heat is signed, so a warmer ambient supplies negative outward heat. Pairwise exchanges cancel. Returned `electrical_loss_j` is only the winding plus MOS conduction heat; bearing heat is reported separately. In a coupled electrical/magnetic/mechanical/thermal ledger these losses transfer internally into thermal storage/outward heat. They must not be counted again as external supplied heat. Neither this identity nor SPD alone establishes realistic component temperature predictions.

## Teaching defaults and primary source boundaries

[COMSOL 6.4, Theory for the Thermal Capacitor and Thermal Mass Components](https://doc.comsol.com/6.4/doc/com.comsol.help.heat/heat_ug_theory.07.039.html) states the homogeneous-temperature lumped-capacitance approximation and its applicability conditions. Node isothermality is an assumption here; no Biot-number or spatial-temperature validation is inferred from using a network.

Defaults: winding capacities 8 J/K each; MOS junction capacities .4 J/K each; motor and board case capacities 80 and 30 J/K. Winding-to-motor links .5 W/K each; junction-to-board links 2.5 W/K each; motor/board ambient conductances .8/.5 W/K. Tref=Ta=Tinitial=298.15 K; admitted interval 200..450 K. Winding Rref=.08 ohm, alphaCu=.00393/K; MOS Rref=.002 ohm, alphaMOS=.004/K. These are explicitly supplied illustrative coefficients, not a fitted copper law, device transient impedance, cooling CFD, actual PCB spreading network or measured pod model.

The [official Infineon/International Rectifier IRFS7530 datasheet, November 7 2014](https://www.infineon.com/assets/row/public/documents/24/49/infineon-irfs7530-datasheet-en.pdf), page 2, states maximum Rds(on)=2 milliohm at Vgs=10 V, Id=100 A, Tj=25 C; junction-to-case maximum .40 K/W. Its 40 K/W D2Pak junction-to-ambient condition uses a one-inch-square PCB. These numbers do not characterize the actual VESC assembly. The illustrative 2.5 W/K junction link is numerically reciprocal to .40 K/W but its attachment to a shared board node is an approximation, not package/board qualification. The linear alphaMOS is not fitted to that datasheet. No PDF or third-party implementation was copied.

## Executed verification and limitations

`.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_thermal -q`

Eight tests passed: independent scalar RC midpoint closed form and second-order refinement; independently solved linear resistance-feedback scalar equation; exact nine-channel winding/high-low loss allocation and no duplicated heat; passive internal-link cancellation and ambient balance; phase-major resistance mapping and temperature feedback; malformed/nonfinite/bool/negative/overtemperature/runaway rejection; specification mutation isolation; and rejection of a large passive RC step that would undershoot ambient. Dedicated tests use isolated/adiabatic limits as analytical references rather than copying the matrix implementation.

The network does not calculate convection coefficients, CFD energy transfer, spreading resistance from PCB copper, thermal radiation, nonlinear heat capacity, semiconductor dynamic losses, saturation or physical temperature qualification. Current and duty are step-supplied midpoint/averaged quantities. Coupled iterations must use these same midpoint resistances and heat; lagged resistance feedback is the integrator owner's approximation to disclose. This authoring derivation is not its own independent approval. Knowledgeable human numerical review remains required before release.
