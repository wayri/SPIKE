# Executed controller / FEM / hover-propeller loop

This is one coupled numerical run. The actual SPIKES persistent compiled C
controller observes current, rotor speed and field-derived flux-angle derivatives,
then applies ideal averaged winding voltages. The coupled solve finds current
from `v=Ri+d(lambda)/dt`, uses reciprocal field-derived torque, advances the
shaft against calculated BEM propeller reaction, and returns speed/sensing to
the next controller tick. There is no prescribed current, speed trajectory,
thrust signal or fitted torque coefficient driving this demonstration.

The field owner uses four actual P1 solves spanning a linear fixed-mesh PM
reference exactly. All saved fields are recovered from those FE basis solutions
and accepted current/angle states. This is not a nonlinear 3-D rotor CAD solve.
The uniform PM remanence rotates in a polygonal circular recoil-linear domain.
Normalized signed winding functions excite and extract the same terminal flux.

The two-blade propeller uses declared radial chord/twist and an illustrative
attached linear lift/constant drag polar. Each annulus solves blade axial force
against momentum to obtain induced velocity; lift/drag projections yield
shaft reaction and thrust. It is quasi-steady no-swirl hover BEM, not resolved
blade CFD, a turbulent wake or interaction with the stand/enclosure.

## Actual source-workspace execution

The registered `run_propulsion_pod` route ran inside the same isolated Python
Workspace child runtime used by SPIKE. The native C source was compiled and
executed, not emulated in Python. Retained `python-workspace-execution.json`
reports completed execution and eight admitted views. The earlier failed view
publication attempt is retained separately; its field/shaft solve completed,
but that script failure is not described as a successful Workspace run.

| Quantity | Executed default result |
| --- | --- |
| Simulation span | 0–0.25 s |
| Accepted step / controller period | 100 µs / 500 µs |
| Accepted steps / compiled controller ticks | 2,500 / 500 |
| Saved field states | 26, from actual accepted states |
| Final speed / target | 106.584812976 rad/s / 100 rad/s |
| Final thrust / propeller shaft power | 0.092186542 N / 0.100679214 W |
| Total source work | 0.670439126 J |
| Total energy defect | approximately 4.18e-15 J |

The final overshoot is reported, not called settled or tuned. Energy closure
does not establish accuracy: component mesh/radial refinement, independent
analytical/PDE checks and fixed-controller-period transient step halving are
separate evidence. The 4 A `current_limit_a` caps the controller request; it is
not a hard clamp on simulated phase current or hardware protection.

`restrained-propulsion-pod-coupled.spike` retains the exact result and admitted
views under report members referenced by `spike.propulsion-pod-coupled-study`.
Native save/read, source-board byte identity and four STEP tessellations passed.
The adjacent full KiCad project remains CC BY-SA 4.0 VESC source/context, with
no inferred physical connection to the synthetic two-phase winding. The board's
three physical phase terminals are not silently assigned to two virtual ports.

## Reproduce

From the SPIKE source root with the existing dependencies, use:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod tests.python.test_propulsion_pod_review tests.python.test_propulsion_pod_field tests.python.test_propulsion_pod_propeller -v
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/coupled/run_from_workspace.py
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/coupled/build_benchmark_geometry.py
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/coupled/build_native_project.py
.venv/Scripts/python.exe examples/promo_showcase/propulsion_pod/package.py
```

The execution-evidence capture refuses to overwrite an existing actual result:
select a fresh capture path before rerunning it. The in-app runner can rerun
normally; set RESULT_FILE only when a new export is desired. No solver DLL,
compiler or external runtime binary is redistributed in the project ZIP.

Primary references, independently authored derivations, exact source hashes
and independent review are in the three `PROPULSION_POD_*_DERIVATION_20261023.md`
records. Frozen-worker release, interactive desktop visual acceptance,
knowledgeable human numerical review, real motor/propeller data, VESC switching,
thermal feedback, blade CFD and flight remain outside this completed reference.
