<!-- SPDX-License-Identifier: Apache-2.0 -->

# Original classic IBIS driver and receiver fixture

Original synthetic classic-IBIS fixture, authored for SPIKE under Apache-2.0.
No vendor data, external implementation, specification sample or measured data
was copied. It models an arithmetic 1 V / 50 ohm CMOS driver with zero die
capacitance and a capacitive receiver. It is an experimental compiler oracle,
not a qualified device model.

The two rising fixtures have 50 ohm loads to 0 V and 1 V. With f equal to
0, 0, 0.5, 1, 1 at 0, 1, 2, 3, 4 ns, their voltages are f/2 and (f+1)/2.
Falling fixtures use reversed f. Direct KCL gives k_pullup=f and
k_pulldown=1-f. Current is positive into the die. Thus the signed pullup
table has negative current for positive Vcc-minus-die voltage.

`request.json` contains the complete inline-source request for an inert compile.
No native engine is loaded by compilation. Execution requires the separately
admitted trusted ngspice executable and explicit consent. Physical device
validation and external fixture replay remain separate gates.

The two recorded supervised executions in `execution_evidence.json` completed
at 20 ps and 10 ps maximum steps. Their pad and driver-die differences exceed
the strict 0.5 mV refinement criterion; convergence qualification remains open.
Both runs used the recorded exact runtime hash and Windows Job Object limits.
