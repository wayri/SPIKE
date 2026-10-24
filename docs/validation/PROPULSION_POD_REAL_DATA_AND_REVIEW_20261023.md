# Propulsion pod: independent real-data admission and method review

Review date: 23 October 2026. This record separates real hardware evidence from mathematical verification. No reviewed candidate presently supplies a complete licensed, characterized small motor suitable for claiming a real VESC-motor-blade-thermal simulation. No third-party motor CAD or implementation code is redistributed by this review. A synthetic model must retain its synthetic identity even when attached to a real controller-board drawing or an attractive CAD envelope.

## 1. Primary-data inventory and decision

The machine-readable inventory is `examples/promo_showcase/propulsion_pod/real_hardware/source_inventory.json`. Revisions were obtained from GitHub branch metadata; pinned README and root-directory metadata were reviewed. Missing license means reuse rights remain unestablished, not a declaration that the owner cannot later grant permission. The inventory stores source links and original review facts rather than copying third-party documents.

| Candidate and pinned revision | Data relevance | Admission decision |
| --- | --- | --- |
| [VivekAruja prototype README](https://github.com/VivekAruja/bldc-motor-design-project/blob/7ee5523739e17f6ae4af36183785efe70ba079f1/README.md), `7ee5523739e17f6ae4af36183785efe70ba079f1` | Physical six-slot/eight-pole plastic outrunner; actual winding differs from the design calculation. The author reports observational testing and no sustained rotation. | API license is null; no license file appears in the pinned root listing. Do not redistribute CAD. Does not provide the required measured R/L, magnet recoil, inertia, thermal or performance chain. Numerical target specifications are not measured ratings. |
| [brenocq integration README](https://github.com/brenocq/bldc-motor/blob/b74fb1d7a4637e437ef5a33e78a36db7c28fac7e/README.md), `b74fb1d7a4637e437ef5a33e78a36db7c28fac7e` | Project integrates a commercial EM3215 using its original windings; mechanical work concerns integration. | [MIT license](https://github.com/brenocq/bldc-motor/blob/b74fb1d7a4637e437ef5a33e78a36db7c28fac7e/LICENSE), copyright 2023 Breno Cunha Queiroz, applies to associated project material. It does not establish vendor internal motor CAD or a measured material/parameter dataset. No such CAD admitted by this review. |
| [rajivtctech design README](https://github.com/rajivtctech/Pancake-Motor-Design/blob/973633af59ba9c3f66ad5fdb01bf08710e0214e1/README.md), `973633af59ba9c3f66ad5fdb01bf08710e0214e1` | Describes a PCB axial machine with three-phase star winding and dual rotors. | API license is null and no pinned root license exists. The README alone establishes neither manufacturing/test results nor thermal characterization. Do not execute/copy its generators or redistribute CAD under unestablished terms. |

A separate reference candidate is [Eomys/Pyleecan Toyota Prius data](https://github.com/Eomys/pyleecan/blob/8654bd49fc005fdb19a38b1e39cd5d06198cdac1/pyleecan/Data/Machine/Toyota_Prius.json), pinned `8654bd49fc005fdb19a38b1e39cd5d06198cdac1`. The file identifies Pyleecan 1.3.8, saved 13 April 2022, and supplies machine geometry/winding/material parameters. Pyleecan's repository declares Apache-2.0; exact data/notice lineage must accompany any later redistribution. Its steel thermal `Cp=1` and conductivity components `=1` demonstrate that this example is not a qualified thermal dataset. Magnetic parameters in a model file are not proof of original manufacturer measurements. The IPM traction-machine topology/scale is also distinct from the requested small propulsion motor; no parameter transfer or rescaling is admitted here.

Primary physical-characterization lineage for a separate Prius benchmark is [ORNL/TM-2004/137, Hsu, 28 July 2004, DOI10.2172/885676](https://digital.library.unt.edu/ark:/67531/metadc892414/) and [ORNL/TM-2006/423, Evaluation of 2004 Toyota Prius Hybrid Electric Drive System](https://info.ornl.gov/sites/publications/files/Pub1870.pdf). The latter describes bench, back-EMF, locked-rotor, thermal and performance studies of a 50 kW traction machine. This establishes a potential independent benchmark lineage, not a VESC small-motor validation claim. No numerical transcriptions from these reports are used in the new model by this review.

## 2. Evidence required to admit a real motor

An exact hardware revision needs rights-cleared internal geometry, signed winding/phase connection and conductor/end-turn geometry; magnet source, recoil/temperature curves and steel B-H/loss provenance; phase resistance at a stated temperature and inductance conventions at stated current/angle/frequency; rotor mass distribution/inertia; and thermal masses, interfaces, contact resistances and measured cooling boundaries. Measured speed, back-EMF, torque, current and temperature responses must then discriminate the model from plausible wrong parameterizations.

Line-to-line star resistance is twice equal phase resistance; delta/star identification cannot be guessed. Phase inductance requires mutual and neutral conventions, and the end-turn contribution must not be counted twice. A grade label such as N52 does not identify vendor recoil permeability, remanence temperature curve, irreversible demagnetization knee or installed magnetization. External CAD volume does not identify rotor inertia without material/part density and rotating-part membership. A generic material database is a declared assumption, not a measurement on the selected motor.

## 3. Independently reviewed three-phase field method

Reviewed `python/spike_core/propulsion_pod_three_phase_field.py`, SHA-256 `8071df345e58a7a848f7a4870110f6152815d9d9cfa147aa83755e4c61750a05`; tests SHA-256 `77a9fac46ba4502910ee41bb172875caa97bf07654895bbcc083866c8a61cca3`. The reference remains a fixed circular, linear isotropic recoil-PM, synthetic one-pole-pair machine. It has six disjoint signed winding regions: positive a/b/c at 0/120/240 degrees and opposite negative returns. Normalized winding loading and linkage use the same quadrature. Five actual existing P1-kernel basis solves give three winding columns and two angular PM columns. This is an exact linear finite-element reduction on that fixed mesh, not an empirical motor lookup table.

Let `Ka=C i+F r(theta)`, `r=(cos(theta),sin(theta))`, and depth `d`. Then

```
L=d C^T K^-1 C, M=d C^T K^-1 F, S=d F^T K^-1 F,
lambda=L i+M r,
Wco=.5 i^T L i+i^T M r+.5 r^T S r-c,
U=.5 i^T L i-.5 r^T S r+c,
tau=i^T M r'+r'^T S r,
c=d integral_PM |Br|^2/(2 mu) dA.
```

All three physical phase currents are retained and must sum to zero for floating star. A common neutral voltage therefore contributes zero power. For reduced coordinates `i=E q`, `E=[[1,0],[0,1],[-1,-1]]`, use `E^T L E`, `E^T lambda` and `E^T v`; using the leading 2x2 block of L would drop the return phase and be incorrect. Torque reciprocity is tested along zero-sum current directions. Mechanical angle equals electrical angle only for the single admitted pole pair; do not transplant this field into an eight-pole product without changing geometry/source harmonics and derivatives.

The derivation follows [Haus and Melcher, Electromagnetic Fields and Energy (1989), section11.7](https://web.mit.edu/6.013_book/www/chapter11/11.7.html), including the zero-current PM-energy term, and the independently derived discrete-work identity in `PROPULSION_POD_COUPLING_DERIVATION_20261023.md`. Fixed permeability and fixed PM-source amplitude are necessary for the current five-column superposition. Saturation, rotating segmented iron/magnets, eddy/hysteresis loss and measured machine identity are absent. No consequential equation defect was found in the reviewed snapshot.

Independent execution:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_three_phase_field -v
```

Seven tests passed (zero skips). They cover direct full-kernel re-solve/linkage/virtual work, six signed regions and gauge invariance, neutral/admission checks, 120-degree cyclic symmetry and positive reciprocal inductance, constrained power reciprocity, exact harmonic discrete work, and zero-PM/periodicity. This verifies the implemented mathematical reference, not a real motor. Owner-reported larger test counts are not borrowed as independent execution here.

## 4. Thermal feedback derivation and admission criteria

For constant positive node capacity `C_j=m_j cp_j` in J/K and symmetric passive conductances `G_jk>=0` in W/K, integrate

```
C_j (T_j1-T_j0)/h = P_j_mid + sum_k G_jk (T_k_mid-T_j_mid)
                         - G_jambient (T_j_mid-Tambient).
```

Pairwise internal conductive exchange cancels exactly when summed. Ambient outflow is signed: a warmer ambient may heat a colder node. Constant-capacity thermal storage is `sum C_j(T_j-Treference)`. This control-volume energy accounting is consistent with [Schrage, TFAWS2024, ONYX thermal formulation, capacitance and conductance sections](https://tfaws.nasa.gov/wp-content/uploads/TFAWS2024-ID-14-Paper.pdf); this reference does not validate supplied motor thermal parameters.

Use positive `R_phase(T)=R_ref[1+alpha(T-T_ref)]` only inside an admitted temperature range. Evaluate the same midpoint resistance in the circuit equation and thermal copper source `sum R_phase(T_mid) i_phase_mid^2`. Joule heat is then an internal transfer from electrical storage/work to thermal storage. The combined electrical-mechanical-thermal ledger includes ambient heat and external shaft work, and must not subtract Joule heat again after adding it to the thermal node. A no-loss adiabatic exchange and a constant-power RC analytic reference discriminate that double count.

If the PM source changes with temperature, the current magnetic energy is also temperature dependent. Simply multiplying linkage by Br(T), while retaining the fixed-source ledger, omits conjugate thermomagnetic work/entropy. Variable L(T), thermal expansion and demagnetization likewise require a derived energy/constitutive treatment. The initial bounded feedback should therefore use R(T) only, constant field properties and positive specified thermal capacities/conductances, while declaring those supplied thermal parameters unvalidated. A temperature color over a motor CAD envelope does not prove spatial thermal resolution or conjugate motor/air heat transfer.

## 5. Independently reviewed thermal and constrained-star step

Thermal helper reviewed at SHA-256 `974562117f11e5699a69e10814bbf627729b4a116466f066cc47ec2d2058e07e`; tests `1b1c60c4161bf3b8eff7bc9d843ca886d5139bb289088582b9c1e641d1e6091c`. Its eleven nodes are three phase windings, six phase-major high/low MOSFETs, motor case and board case. With affine loss `p(T)=p0+diag(beta)T` and passive network matrix G, it solves exactly for the midpoint:

```
[diag(2C/h)+G-diag(beta)] Tmid = diag(2C/h) T0+p0+gambient Tamb,
T1=2Tmid-T0.
```

It rejects nonpositive/ill-conditioned systems, nonpositive resistance and temperatures outside the declared range. An independent review exposed that SPD alone permits midpoint RC overshoot below ambient at large steps. The owner added a conservative nonnegative old-state matrix gate `2C/h-diag(G)+beta>=0` and an explicit large-step rejection test. Combined with the SPD M-matrix structure and nonnegative affine feedback about ambient, this avoids the identified oscillatory passive RC step; it is not a general nonlinear thermal-accuracy proof. Default capacities, contact/ambient conductances and MOS temperature slope remain supplied illustrative quantities.

For each phase, ideal synchronous averaged conduction uses `Rleg=D Rhi+(1-D)Rlo`, with heating `D i^2Rhi` and `(1-D)i^2Rlo`. This derives by integrating a constant phase current through complementary high/low conduction intervals; it excludes PWM ripple, deadtime/body-diode conduction, switching/gate losses and measured MOS temperature characterization. [TI SLVAF76, equations1-2](https://www.ti.com/lit/an/slvaf76/slvaf76.pdf) gives the corresponding averaged high/low conduction estimates. [NBS Handbook100, issued21 February1966, section1.1(b), tables2-3](https://nvlpubs.nist.gov/nistpubs/Legacy/hb/nbshandbook100.pdf) gives the standard copper coefficient .00393/K at20 degC. Moving the reference to25 degC requires `alpha25=alpha20/(1+5 alpha20)` for the same linear law. The helper explicitly declares its .00393/K at298.15K illustrative, so it is not presented as that exact standard law or measured winding fit.

The constrained step `python/spike_core/propulsion_pod_three_phase.py` was independently executed at SHA-256 `15ff45d49ea4ada0084fa82cd1de7a100f5c5ca02bb5d7417c6f314912e2936b`. It applies the E projection from section3, retains all three resistance/end-turn terms, solves the neutral as a constraint reaction, and checks all phase KVL equations, KCL and shaft residual separately. A nested temperature fixed point recomputes the electrical/shaft state for a guessed midpoint resistance, then exactly updates thermal temperature from the same midpoint currents and bearing power. The final accepted KVL recomputes resistance from the returned thermal midpoint, rather than reporting residuals against the previous guess. An initially missing thermal-capacity attribute was corrected to use the helper's returned storage; both findings were fixed before the independent successful run.

If `epsilonT=max|T1new-T1guess|`, the guessed and accepted thermal midpoints differ by at most `epsilonT/2`. Each phase's combined winding/leg resistance discrepancy is bounded by

```
|delta Rphase| <= epsilonT/2 [Rw_ref alphaCu
                    +D Rhi_ref alphaMOS+(1-D)Rlo_ref alphaMOS].
```

Its raw circuit voltage discrepancy is at most `|ibar_phase| |delta Rphase|`. Since projection onto zero-mean phase residuals can enlarge an infinity norm by at most two, the reported neutral-eliminated residual is bounded by twice that plus the linear-solve residual. For default values, current envelope200A and epsilonT=1e-8K, this gives at most about6.45e-10V after neutral projection, below the1e-8V phase gate. Larger admitted parameters or a looser iteration tolerance may fail that gate; temperature-change tolerance alone never overrides it. The heat-exchange mismatch is bounded by `h sum ibar_phase^2 |delta Rphase|`; the complete energy gate separately tests it. Temperature/R feedback does not alter Br or L, preserving the fixed-field constitutive identity.

The combined ledger is `source work - fluid shaft work - magnetic/kinetic storage change - thermal storage change - ambient heat`. Joule and bearing heat enter the thermal nodes and are not subtracted twice. This is a partitioned fixed point that converges to a common implicit step, not a one-step-lag thermal source. Temperature iteration failure, shaft bracketing failure and residual/energy failures reject the step without modifying passed arrays. No public service admission or resumable controller rollback is established solely by this internal helper review.

Independent execution:

```powershell
.venv/Scripts/python.exe -m unittest tests.python.test_propulsion_pod_thermal tests.python.test_propulsion_pod_three_phase_field -q
```

All15 tests passed: eight thermal and seven field tests. Additionally, an independently constructed200-step smoke run used the actual three-phase field, thermal network and existing hover-BEM provider with h=1e-4s, bus12V, end-turnL=.0002H/phase, J=5e-6kgm^2, b=1e-6Nms, and duties `.5+.08*dpsi/max(abs(dpsi))` recomputed from the current angle. This is a mathematical feedback fixture, not VESC firmware or blade CFD. It reached90.5408635365rad/s, max temperature298.167986550K, at most two thermal iterations. Maximum phase KVL1.51e-14V, KCL8.88e-16A, shaft residual1.12e-13Nm, step energy defect1.58e-11J and summed defect6.24e-11J. The tiny thermal temperature increment entails cancellation in C deltaT; energy accuracy must be judged on physical exchange/storage scales, not a large ambient-temperature baseline.

## 6. Blade CFD implementation review status

The preliminary symmetric-stress Taylor-Hood source was inspected. Final test execution/source hash and any remaining findings will be appended once the owner completes its bounded cases. This section does not certify full-RPM blade CFD, thermal code integration into a GUI or a complete real-hardware loop. Actuator/body-force flow and BEM retain those identities. Required knowledgeable human numerical review remains open before release.

## 7. Selected openly documented composed pair

The source search progressed beyond the initial candidates: OpenMotor CIAG_2_28 125_25, pinned`1e1e56d7cf64ea393793ca5c06189251f87b6e98`, is selected with ENOLA Casalino300mm+5degree geometry/experiments, DOI10.5281/zenodo.20111572v1. Exact source files, hashes, native geometry inspection, primary licenses, data-quality findings and join instructions are retained in`examples/promo_showcase/propulsion_pod/real_hardware/README.md` and`source_inventory.json`. This updates the initial search decision without filling remaining physical-property gaps by assumption.

OpenMotor's CERN-OHL-W-2.0 source includes real internal616-solid STEP assembly and a17-row motor/30inchprop test; ENOLA's CC-BY-SA4.0 selected+5degree STL is closed by edge incidence and has a matching experimental CSV. The latter is30cm, not30inch. These two sources are a composed research reference pair, not a matched test. The original motor measurements use~80Vbus and cannot qualify the selected60V MOSFET board. Any proposed<=48V operating point is a different preliminary assumption. Source data remain unmodified; no full motor/CFD/thermal field is claimed executed from this source selection.

Primary API rights inspection also established that CREATOR PMSM dataset DOI10.3217/sns1d-77m43 is CC-BY-NC4.0; the arXiv article's CC-BY-NC-ND terms are distinct. CREATOR is a strong separate research benchmark, but not the chosen commercially reusable open-hardware source. Its primary paper distinguishes directly measured resistance from FEA-derived d/q inductances; do not label all published parameters measurements.
