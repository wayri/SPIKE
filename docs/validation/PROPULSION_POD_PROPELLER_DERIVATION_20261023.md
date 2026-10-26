<!-- SPDX-License-Identifier: Apache-2.0 -->
# Geometry-derived hover BEM propeller reaction — 23 October 2026

Status: experimental in-process reference, `production_qualified:false`. This adds an actual blade-element/annular-momentum calculation for a **quasi-steady hover reaction port**, not rotating-blade CFD, a solved swirl field, measured propeller performance, or complete propulsion qualification. A motor/controller owner may call `evaluate_propeller(spec, omega_rad_s)` with its current accepted shaft speed and subtract the returned positive resisting `torque_nm`. This module does not itself advance the motor or implement the time master.

## Reviewed primary foundations and implementation provenance

Reviewed 23 October 2026:

- NASA Glenn, [Propeller Thrust](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/propeller-thrust/), Simple Momentum Theory: disk mass flux, momentum/pressure jump and disk velocity midway between upstream/downstream velocity. Its ideal disk treatment excludes detailed tip losses.
- Franklin D. Harris, NASA/CR-20205001147, **May 2020**, [Model Rotor Hover Performance at Low Reynolds Number](https://rotorcraft.arc.nasa.gov/Publications/files/Harris%20CR-20205001147_Final.pdf), displayed p7, equations2–7 (PDF p15) and AppendixB heading/equations at displayed pp57–58 (PDF pp65–66): blade-element pitch/inflow relation, supplied linear lift/drag coefficients and radial integration. The report also documents optimistic BEM hover power predictions and uncertainty at low Reynolds number; it does not qualify this example polar.

These sources inform established equations. No external source implementation, mesh, airfoil table or experimental dataset was copied. The scalar root method, exact force/power derivation below, API and analytical tests were authored for SPIKE. This is a deliberately narrower constant-profile-drag, no-swirl branch rather than a claim to reproduce every model in the NASA report. Independent review of the derivation/implementation and knowledgeable human numerical review remain required before release.

## Explicit request, units and restricted validity

`python/spike_core/propulsion_pod_propeller.py` exposes `evaluate_propeller(spec, omega_rad_s)`. Required spec fields:

- `contract: spike/hover-bem-propeller/v1`, positive integer `blade_count`;
- equal-length `radial_stations_m`, `chord_m`, `twist_rad` arrays; positive strictly increasing radii from nonzero hub cutout to tip; piecewise-linear chord/twist interpolation;
- `density_kg_m3`, `dynamic_viscosity_pa_s`, `speed_of_sound_m_s`;
- `polar`: positive `lift_slope_per_rad`, nonnegative **constant** `drag_coefficient`, `alpha_valid_rad:[0,upper]`, nonnegative ordered `reynolds_valid` interval and a nonempty `source`/assumption declaration;
- bounded `radial_cells`, `relative_tolerance`, `max_iterations`.

All geometry is SI metres, pitch/inflow/angle of attack radians, speed rad/s, density kg/m³ and viscosity Pa·s. Forces are N, torque N·m, power W. `torque_nm` is positive resistance to positive shaft rotation; motor reaction is its negative. Positive thrust is along a separately declared installation axis. Negative rotation is rejected; reversing geometry/axis requires a separate physically defined request. Nonzero axial advance, yaw, crossflow, inflow history and chamber/ground effects have no accepted input and are not silently ignored.

The numerical branch requires `0<theta<=0.3 rad`, the whole root-search angle span inside the declared attached polar, maximum linear Cl<=1.5 and local solidity Bc/(2πr)<=0.3. These are explicit conservative experimental gates, **not universal physical stall criteria**. Caller-declared alpha/Re validity is not manufacturer authentication or measured airfoil validation. Every positive-speed evaluation checks each annulus against that interval and Mach<=0.3. The exact stopped state returns zero forces, velocity, mass flux and power even though a positive minimum-Re polar cannot characterize zero flow. Negative/nonfinite speed, nonrepresentable forces, unknown fields, failed roots or regime violations raise ValueError without returning partial successful loads. No clipping, torque coefficient, fallback flow or stall extrapolation is substituted.

## Independent governing derivation

Let B be blade count, c(r) chord, theta(r) pitch, rho density, omega>=0 and vi(r)>=0 hover disk axial velocity. On an annulus of radial width dr:

```
U = omega*r
W = sqrt(U² + vi²)
phi = atan2(vi,U)
alpha = theta-phi
Cl = a*alpha
Cd = supplied constant Cd0
q = rho*W²/2
L = q*B*c*Cl*dr
D = q*B*c*Cd*dr
```

L and D here are integrated blade-element lift/drag forces across all B blades on that annulus. Project their vector components, without replacing sin/cos by a small-angle approximation:

```
dT = L*cos(phi) - D*sin(phi)
dQ = r*(L*sin(phi) + D*cos(phi))
```

For a still upstream fluid, ideal annular momentum assumes far-wake axial speed2vi and disk area `dA=2πr dr`. Therefore `dm=rho*vi*dA`, `dT_m=dm*(2vi)=2rho*vi²*dA=4πrho*r*vi² dr`. BEM solves **dT=dT_m** at each radius, using supplied radial geometry/polar and instantaneous speed. No `Q=k omega²` coefficient is an input. The familiar squared-speed scaling emerges from these explicit constant-property hover equations; it is verified as a consequence, not used as a fitted load replacement.

For nonzero omega, solve x=vi/U. Cancelling positive rho U² dr gives the dimensionally consistent root (each term has units metres):

```
f(x) = (B*c/2)*sqrt(1+x²)*[a*(theta-atan(x))-Cd*x] - 4πr*x² = 0.
```

At x=0, f>0. At x=tan(theta), alpha=0 and f<0 even if Cd=0. Its blade term derivative is

```
(B*c/2)/sqrt(1+x²) * [a*(x*alpha-1)-Cd*(1+2x²)].
```

Over the admitted branch, `x*alpha<=tan(0.3)*0.3<1`; hence this derivative is strictly negative and the momentum subtraction is nonincreasing. There is exactly one root in `[0,tan(theta)]`. Bisection admits only a residual within the caller's unchanged relative tolerance; maximum-iteration failure rejects the evaluation. Exact canonical spec strings cache the immutable dimensionless radial root solution for repeated speed calls. Geometry/polar/fluid/control changes invalidate that identity. No cached force replaces a new instantaneous speed/Re/Mach evaluation, and returned mutable radial records cannot modify the cache.

## Energy, airflow evidence and limits of the no-swirl approximation

From the exact force projections:

```
omega*dQ - vi*dT
= L*(U*sin(phi)-vi*cos(phi)) + D*(U*cos(phi)+vi*sin(phi))
= D*W >= 0.
```

Thus the model accounts for `Pshaft=omega*Q = sum(vi*dT)+sum(D*W)`. The first term equals the annular ideal far-wake kinetic-energy flux `0.5*dm*(2vi)²` after momentum closure. The second is modeled profile-drag aerodynamic dissipation; it is **not automatically deposited as motor/structure heat** and is not a resolved air sensible-heat calculation. The model's energy identity is independently testable even with a nonzero supplied profile drag.

The ideal uniform induced-power lower bound is defined on the **active annular area**, `A=π(R²-Rhub²)`, matching the modeled support. Since `T=∑2rho*vi²*dA` and `Pi=∑2rho*vi³*dA`, the weighted power-mean inequality gives `Pi>=T*sqrt(T/(2rho*A))`. Root residual tolerance is included in admitting that bound. Profile dissipation ensures Pshaft>=Pi. Neither bound proves a physical propeller efficiency or real thrust rating.

`radial_airflow` retains disk/far-wake axial speeds, actual annulus mass flux, Reynolds/Mach, local forces, torque, momentum thrust, induced/profile/far-wake power and root residual/iterations. These are annular actuator-disk quantities, **not XYZ CFD cells, a pressure/shear field on a blade, or flow around the actual stand**. Swirl, wake angular-momentum closure, tip/root-loss correction, finite-blade wake interactions, transient inflow and stall are omitted. The rotor reaction torque is a quasi-steady blade-force model; it must not be described as a resolved angular-momentum CFD transfer. The output explicitly marks `wake_swirl_resolved:false` and `angular_momentum_wake_verified:false`. Completing blade-resolved CFD and actual rotor/fluid work interfaces remains a separate stage under the existing solver-status gates.

## Executed verification and nominal example

Executed on local Python3.12.9:

```
.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_propeller -v
```

**7 test methods passed**. They include: exact stopped state/reverse rejection; an independently manufactured blade giving uniform vi=1.5m/s at300rad/s, recovering `T=2rho*A*vi²` and `P=T*vi` with zero Cd; annular momentum, mass-flux and far-wake energy checks; exact shaft/profile/induced power identity and actuator-disk bound; geometry/density/speed scaling and changed chord reaction; positive profile drag; radial quadrature refinement; invalid geometry, unsupported advance, stall/polar, Re/Mach, nonfinite/underflow and failed-root rejection; and cache/result mutation isolation. The analytical manufactured blade includes every integration midpoint in its station data, separating the root/momentum oracle from interpolation error.

Illustrative, unmeasured nominal spec:2 blades; root/tip0.03/0.15m; chord0.018→0.012m; twist0.18→0.12rad; slope6/rad, Cd0.012, declared alpha[0,0.2]rad/Re[0,2e6]; rho1.225kg/m³, mu1.81e−5Pa·s, sound speed343m/s; root relative tolerance1e−10,80 iterations. The Re interval is an explicit teaching assumption enabling startup, not authenticated low-Re airfoil behavior.

At500rad/s:

| Radial cells | Thrust N | Torque N·m | Shaft W |
| ---: | ---: | ---: | ---: |
| 16 | 2.0285151091 | 0.02078119728 | 10.3905986401 |
| 32 | 2.0286955568 | 0.02078709695 | 10.3935484734 |
| 64 | 2.0287406597 | 0.02078857071 | 10.3942853529 |
| 128 | 2.0287519349 | 0.02078893907 | 10.3944695366 |

Successive thrust/torque differences decrease by approximately4, consistent with second-order midpoint radial quadrature on this smooth teaching geometry. At32 cells, Pi=7.241126212W, profile dissipation3.152422261W, ideal uniform active-disk bound7.086641496W; maximum root residual9.82e−11 and aggregate shaft identity defect zero at reported binary64 precision. This is equation/reference verification, not a manufacturer-data comparison, global whole-suite run, actual motor-loop verification or hardware correlation. Parent integration owns motor/controller time stepping and its separate energy checks.

Reviewed source SHA-256 before independent root review:

- `python/spike_core/propulsion_pod_propeller.py`: `6184c0e9199c6c257cec3c30a8537d36ea7beb1af1d78be7e2ca6c9850eb83c3`.
- `tests/python/test_propulsion_pod_propeller.py`: `810b84661f942beef546203d9f4c728e3b73b897983bb4626314431a6664148e`.

No registered production flow owner, app UI or capability flag is changed by these three owned files. Primary-source citations, passing analytical checks and a plotted airflow profile do not establish blade CFD, full propulsion-system physics or release readiness.
