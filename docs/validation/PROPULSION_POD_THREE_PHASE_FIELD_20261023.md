# Three-phase planar PM field ports — 23 October 2026

## Scope and source revision

`python/spike_core/propulsion_pod_three_phase_field.py`, contract `spike/propulsion-pod-three-phase-field-state/v1`, is an original Apache-2.0 synthetic one-pole-pair planar PM benchmark. It is a separate six-region geometry and five-solve field basis, not a relabeling of the two-phase ports. It reuses the unchanged `magnetic_fem.py` P1 kernel (SHA-256 ae92fe4e55ea0e5a1fa37369daa219c6e110589bae93ea5e20faa1b85f2c18ff). No external implementation is copied. This authoring derivation requires separate independent review and knowledgeable human numerical review before release.

Three positive winding regions are centered at 0, 120, 240 degrees, each with its negative return at +180 degrees. Each region occupies a 30-degree annular sector; six regions do not overlap. Angular mesh counts are multiples of 48, preserving the 120-degree phase symmetry and sector boundaries. Circular material interfaces are inscribed polygons. Each signed current basis chi integrates to +N/-N turns; its net integral is zero. Turns are dimensionless, chi has units m^-2, current density Jz=sum(chi_k i_k) has A/m^2, Az has Wb/m, and extrusion depth d is meters.

The actual PM rotor is a fixed circular isotropic linear recoil region, with Br(theta)=Br*(cos theta,sin theta). Rotating remanence in this geometry is an exact constitutive parameterization of this benchmark. It does not model slots, an actual outrunner, saturation, eddy/hysteresis loss, end turns, or a vendor motor. There is no claimed VESC motor calibration, thermal model, propeller, or controller in this module.

## Field and terminal derivation

Let K be the boundary-reduced positive P1 reluctivity matrix. Assemble winding load C using the same element area/3 quadrature used to extract linkage. Let F contain x/y PM source loads. Solve K A=[C,F] with outer Az=0; three unit-current solves and two PM solves are actual calls to the established kernel. With r=(cos theta,sin theta), a=A*[i;r]. Then

- L=d*C^T*K^-1*C, M=d*C^T*K^-1*F, S=d*F^T*K^-1*F.
- lambda=L*i+M*r in Wb-turn; L is symmetric positive semidefinite (this fixture has positive full rank).
- c=d*integral_PM Br^2/(2mu) dArea is constant for rigid isotropic recoil material.
- Wprime=.5*i^T*L*i+i^T*M*r+.5*r^T*S*r-c.
- U=i^T*lambda-Wprime=.5*i^T*L*i-.5*r^T*S*r+c.
- torque=dWprime/dtheta=i^T*M*rprime+rprime^T*S*r in N m.

Thus d(lambda)/dtheta=M*rprime=d(torque)/di. The PM source potential Cpm=.5*r^T*S*r is retained; using bare .5*a^T*K*a as the port energy would omit PM source work. Gauge invariance follows separately for every phase from integral chi_k=0. These are physical phase winding linkages, with no Clarke transform or zero-sequence projection applied to the field matrices.

## Floating-star connection and coupling contract

`ThreePhaseFieldMotor(spec)` exposes `inductance_h` (3x3), `pm_flux_basis_wb_turn` (3x2), `pm_self_matrix_j` (2x2), and `coupling_terms(theta)` containing psi, its angle derivative, Cpm and Cpm prime. `evaluate(currents3,theta,include_field=False)` returns linkage, torque, U/Wprime, derivatives, and optionally reconstructed actual P1 fields. Specification validation is pure and bounded; mesh admission is at most 12000 nodes.

Only floating-star currents are admitted: |sum(i)| <= 1e-10*max(1,max|i|). Invalid currents are rejected, never silently projected. Current solver must impose sum(i)=0 and solve the neutral voltage: v_phase-v_neutral=R*i+d(lambda)/dt. Consequently i^T*v_line=i^T*(v_line-v_neutral*1), so neutral potential contributes no power. Two independent coordinates q with i=Tq, T=[[1,0],[0,1],[-1,-1]], give terminal lambda_q=T^T*lambda and L_q=T^T*L*T; root may use this constraint but must not reinterpret coordinates as different physical windings.

Exact harmonic secants remain delta(psi)/delta(theta)=psi_prime(mid)*sinc(delta(theta)/2), delta(Cpm)/delta(theta)=Cpm_prime(mid)*sinc(delta(theta)). With midpoint current ibar, torque_DG=ibar^T*delta(psi)/delta(theta)+delta(Cpm)/delta(theta) satisfies ibar^T*delta(lambda)=delta(U)+torque_DG*delta(theta), including simultaneous balanced-current changes. Caller owns time integration, inversion constraints, dissipation and shaft/load closure.

## Executed evidence

`.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_three_phase_field tests.python.test_propulsion_pod_field tests.python.test_magnetic_fem -q`

Tests cover an independent full PDE solve, area-quadrature linkage, full-PDE virtual-work torque, six disjoint signed regions, gauge shift, neutral rejection/common-voltage power invariance, cyclic phase permutation with 120-degree rotor rotation, symmetric positive L, constrained torque/current reciprocity, continuous shaft energy, exact finite-step DG energy, zero PM and periodicity, input bounds. Default mesh has 1057 nodes/2016 triangles. Five actual basis residuals are at most 5.54e-11 A. L diagonal is 20.7715188 microhenry, mutual terms -3.82217154 microhenry. At currents (5,-2,-3) A and theta .4 rad torque is -0.0110369588397 N m. These characterize this numerical model, not hardware constants. No general error bound, external FEM correlation, measured validation, or production qualification is claimed.

## Primary references and real-motor evidence gap

[Haus and Melcher, Electromagnetic Fields and Energy, section 11.7](https://web.mit.edu/6.013_book/www/chapter11/11.7.html) establishes multi-terminal magnetic coenergy, force and reciprocity. [Meeker, Magnetic Circuit Derivation of Energy Stored in a Permanent Magnet, April 5 2007](https://www.femm.info/doku/doku.php?id=pmenergy) treats linear recoil PM stored energy. Independently authored finite-dimensional reduction above specifies the exact implemented functional; references alone do not validate this implementation.

A real-motor adapter requires legally reusable cross-sectional geometry and slot/pole topology, stack length, air gap, winding connection/turns/phase orientation and current distribution, PM remanence/recoil data and temperature, material B-H data, mechanical/electrical angle and polarity definition, winding resistance/end-turn treatment, and measured or independently established linkage/back-EMF/torque references. An off-the-shelf motor name, an unlicensed CAD model, or a demonstration of rotation does not provide those data. This module accepts none of those missing facts by inference.
