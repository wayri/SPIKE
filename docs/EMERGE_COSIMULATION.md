<!-- SPDX-License-Identifier: Apache-2.0 -->
# EMerge sampled AC and circuit-resistor thermal bridge

Experimental APIs integrated into the 0.4.0-alpha.1 source candidate on
23 October 2026: owned worker/CLI routes, desktop draft export and Python
Workspace templates. No public native ABI or physics-qualification promotion.
These compose existing services, not general EM/thermal or live SPICE execution.

## Primary foundation and independent derivation

K. Kurokawa, *Power Waves and the Scattering Matrix*, IEEE TMTT 13(2),
194–202 (1965), [DOI](https://doi.org/10.1109/TMTT.1965.1125964),
[reviewed paper](https://athena.ecs.csus.edu/~milica/EEE211/HL/kurokawapowerwaves.pdf).
Limited review on 23 October 2026: printed pages 194–196, equations (1),
(10)–(12). SPIKE's derivation, code, synthetic networks, fixtures and prose
are independently authored, without external implementation/example reuse.
Established mathematics, not publication novelty, determines this interface.

Use common positive real Z0 (ohms), RMS V/I phasors, port current into the
network and S[receive][excited]. Independently, define
`a=(V+Z0 I)/(2 sqrt(Z0))`, `b=(V-Z0 I)/(2 sqrt(Z0))`, with waves in sqrt(W).
Then `b=S a`, `V=sqrt(Z0)(a+b)`, `I=(a-b)/sqrt(Z0)` and each real port power
is `Re(V conj(I))=abs(a)^2-abs(b)^2`. RMS expressions have no factor one-half.
Complex reference impedances are unsupported.

A Thevenin boundary `V+Zs I=Vs` gives `a=Gamma b+u`, where
`Gamma=(Zs-Z0)/(Zs+Z0)` and `u=sqrt(Z0) Vs/(Zs+Z0)`. Directly solve
`(I-diag(Gamma) S) a=u`, avoiding singular S-to-Z/Y representations of ideal
throughs. Condition number must be finite and <=1e10; relative backward and
physical-boundary residuals must be <=1e-10, without regularization or clipping.
The boundary gate is checked per port as well as globally: a large excitation
cannot mask a weak-port cancellation failure. A natural-roundoff regression
uses diagonal S=(0,1-2^-53), sources 1e8 and 2 V, and series resistances 50
and 1e12 ohms. Direct wave subtraction loses weak-current accuracy; this
connection is explicitly rejected, not repaired by tolerance.
Sampled full-matrix SVD passivity requires `smax<=1+1e-10`; it does not prove
broadband causality or physical field accuracy.

Independent power checks at relative tolerance 1e-10 require
`sum Re(Vs conj(I))=sum Re(Zs) abs(I)^2+sum Re(V conj(I))`
and the wave/terminal power identity. Series resistance is nonnegative;
reactance is not heat. Net EM-port power can include radiation: it remains
unclassified, never automatically thermal heat.

## Internal interfaces

`extensions/emerge_suite/cosimulation.py:prepare_cosimulation_source` admits a
completed raw AnalysisResult with exact design binding, expected case/script
digests, and an explicit terminal pair/reference-plane label for every port.
It rejects error-severity source issues, preserves warning issues plus original
source status/provenance, and emits network_source compatible with owned
sampled-network/rational-fit source records. Reference planes are metadata,
not de-embedding. The explicit declaration
`rms_power_waves_common_positive_real_reference` is required but is not
independent EMerge field-amplitude calibration. Relative E/H and far-field
coefficients cannot be converted to watts by this API.

`python/spike_core/solvers/execution/coupling/em_network_ac.py:solve_em_network_ac` takes
`spike/em-network-ac-request/v1`: exact source, wave_convention, boundaries.
Source uses id, ordered port_names, reference_impedance_ohm, frequencies_hz,
and s_parameters with `{real,imag}` complex entries. Each source frequency has
one boundary dictionary covering every port, with voltage_v and impedance_ohm
`[real,imag]` pairs. No interpolation, extrapolation, normalization or port
dropping. Maximum 16 ports/512 samples, request/result limits 8/16 MiB,
cancellation between samples. This bounded reference/composition service does
not replace native production/HPC numerical owners.

`python/spike_core/solvers/execution/coupling/em_network_resistor_thermal.py:run_em_network_resistor_thermal`
takes `spike/em-network-resistor-thermal-request/v1`: ac_request,
thermal_request, sample_index, resistor_cell_weights. Every port's external
series resistor maps to explicit retained cell fractions summing to one within
1e-12, or null for outside the domain. No inferred geometry or renormalization.
Actual SI cell volumes convert watts to W/m3; the existing tetrahedral steady
thermal owner solves temperatures. Deposited plus outside heat and integrated
thermal source conserve resistor power within relative 1e-10. Pre-existing
thermal heat is rejected against double counting. One frequency case is
selected, never summed across unrelated sweeps. Thermal cancellation is checked
before/after that owner, not internally. Strict request schemas are registered
in schemas/manifest.json. Worker parameters must be exactly `{request: ...}`.
See [release integration evidence](validation/EMERGE_RELEASE_INTEGRATION_20261023.md).

## Desktop and CLI workflow

1. Open a completed EMerge result and select **Export co-simulation draft**.
   This downloads an editable worker-parameter JSON, not an admitted result.
   It preserves source diagnostics and provenance; standard JavaScript JSON
   serialization can canonicalize signed zero to zero, so retain the original
   artifact separately. Hashes taken from provenance are not independent proof
   of the currently loaded board: verify them against the intended case/script.
2. Fill every positive_node, negative_node and reference_plane; verify source
   hashes and explicitly declare `rms_power_waves_common_positive_real_reference`
   only when justified. The untouched draft is intentionally rejected. No
   default terminals, reference-plane shift or amplitude calibration is inferred.
3. In **Python Workspace > Template Library > Co-simulation and twins**, use
   **Prepare EMerge co-simulation source**. Set REQUEST_FILE to that reviewed
   worker-parameter file, and optional RESULT_FILE to a new JSON path to retain
   the complete packet. Templates do nothing with REQUEST_FILE unset, never
   publish a non-AnalysisResult, and refuse overwriting RESULT_FILE.
4. Use the prepared network_source in an AC request with explicit boundaries
   at every exact source frequency. Wrap it as `{request: <AC request>}` for
   the **Run sampled EM network AC** template. For resistor heat, supply the
   thermal mesh/materials/boundaries and cell fractions to **Run EM
   circuit-resistor thermal coupling**. The same-mesh dielectric/heat/elastic
   owner has a separate **Run dielectric AC / thermal / mechanical chain**
   template and worker method, not an EMerge material-loss model.

Worker methods: prepare_emerge_cosimulation_source, solve_em_network_ac,
run_em_network_resistor_thermal, run_pdn_dielectric_thermomechanical. The first
takes the six preparation fields inside request; others take their versioned
requests. No shell, arbitrary executable or netlist interpretation is added.

CLI files contain the inner request, without the worker wrapper:

```powershell
./spike.cmd --output prepared.json em-cosim prepare preparation-fields.json
./spike.cmd --output ac.json em-cosim ac network-ac-request.json
./spike.cmd --output thermal.json em-cosim resistor-thermal coupling-request.json
```

The preparation file has result, binding, expected_case_sha256,
expected_script_sha256, port_bindings and wave_convention. CLI execution limits
input to 8 MiB; template input is more conservatively limited to 4 MiB.

## Reproduce and executed evidence

```powershell
$env:OPENBLAS_NUM_THREADS='1'; $env:OMP_NUM_THREADS='1'; $env:MKL_NUM_THREADS='1'
./.venv/Scripts/python.exe -m unittest tests.python.test_em_network_cosimulation -v
./.venv/Scripts/python.exe examples/emerge/replay_cosimulation.py --output build/my-emerge-ac-replay
```

The example refuses an existing output directory and retains packet, request,
result and source/artifact SHA-256 manifest. It replays the retained
seven-frequency patch result, EMerge 3.0.0a19, unvalidated; not fresh FEM.
Binding hashes are self-pinned from retained provenance for offline replay,
not authenticated against a newly loaded board. New explicit circuit
assumptions are 2 V RMS and 50 ohm series/termination resistors. Source status
is not promoted. Executed `build/emerge-ac-replay-reviewed-20261023` passed seven
samples, maximum power discrepancy 7.8063e-18 W. This checks circuit consistency
on retained data, not measured or independent EM correlation.

Reviewed broader regression: 86 tests, zero skips, 6.864 s, spanning EMerge
adapter/multiport, sampled/rational networks, AC worker/schema, heat, feedback
and thermomechanical paths. Independent oracles include matched resistors,
reactive series components, ideal through, nonreciprocal three-port orientation
and permutation, exact frequency rows, failure/cancellation and conservative
resistor heat, warning retention and natural-roundoff weak-port refusal. An
independent numerical review identified the weak-port masking and lost-source-
diagnostic cases; both now have regression checks. This is not full-suite
release qualification. Human numerical review remains required.

The broader thermal-owner/backlog regression also passed 26 tests, zero skips,
in 90.512 s, including real owned-pad evidence regeneration in test setup.
Its first attempt failed because Windows sandbox temporary files could not be
written/removed. Re-execution used TEMP/TMP pointing to writable
`.local/test-temp/emerge-ac-qualification`; tests and gates were unchanged.

## Remaining general integration

Calibrated EM volumetric/surface dissipation, authenticated material/mesh
transfer, temperature re-solving with convergence/rollback, live SPICE devices,
causal transient models, an integrated graphical coupled-study editor and measured/independent EM
qualification remain open. Upstream [features](https://www.emerge-software.com/features)
and [thermal description](https://www.emerge-software.com/post/emere-2-6-heat-conduction)
are upstream descriptions, not SPIKE evidence. No external engine binaries
or datasets are redistributed here.
