# Dependent sources and linear FRA — development build

The updated native C ABI adds E/G/F/H source stamps to DC and transient assembly,
including sparse matrices and embedded transient matrices. Both positive and negative
gains are allowed. Current is positive from the positive to the negative terminal;
negative current represents sourcing in the opposite direction, not a separate sink
device family.

```
E1 out 0 control 0 10
G1 out 0 control 0 0.001
F1 out 0 Vsense 2
H1 out 0 Vsense 1000
B1 out 0 V={3*V(control)}
B2 out 0 I={0.001*V(control)}
```

E is VCVS (V/V), G is VCCS (A/V), F is CCCS (A/A), H is CCVS (V/A).
F/H control a voltage-defined branch, commonly a zero-volt sensing source. The
control source may appear later in the deck. The tested linear B expressions lower
to these stamps. This does not implement all BV/BI expressions, nonlinear equations,
Laplace, POLY, TABLE or arbitrary multi-signal behavioral callbacks.

Select the rebuilt `build-spikes-current-vs18-20260906/Release/spikes_c_api.dll` for
native dependent sources. Older DLLs return a missing-ABI error instead of using a
different solver. Existing installed beta.5 does not have this new ABI.

## FRA

```
python -m python.spikes fra examples/spikes/studio_tutorials/02_rc_startup.cir --source V1 --output-probe "V(out)" --start-hz 1 --stop-hz 100000 --points 301 -o fra.json
```

FRA computes output divided by an explicitly selected ideal excitation source using
the existing Python linear complex-MNA backend. It is not native C++ AC, nonlinear
biased AC, periodic switching FRA or automatic loop-gain measurement. Other sources
have zero AC excitation. It is bounded to 256 MNA unknowns and 10,000 sweep points.

In the frequency workspace, configure source/output/range, then **Save FRA block**.
**Run saved FRA block** executes a named configuration against the current circuit,
with existing Bode, Nyquist and pole/zero views. These are persisted analysis blocks,
not new electrical components or automatically inserted loop-breaking fixtures.
Captured frequency results retain their settings and backend provenance.

## Semiconductor status

C++/ABI-level static BJT, Level-1 MOSFET and WBG functions exist, but the netlist
project representation and native runner do not yet connect those families. Their
presence is not universal BSIM/vendor support. Detailed manufacturer qualification,
charge-model coverage, all behavioral sources and switching-loop FRA remain open.
