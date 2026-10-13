# High-frequency conductor loss

The bounded geometry SI channel now uses frequency-dependent isolated slab
internal impedance by default, including both resistance and reactance. This
replaces its previous DC-only trace resistance. Single-ended and coupled
four-port paths use the same kernel. Existing saved extraction records without
conductor-loss metadata retain their original DC behavior; rerun extraction
to obtain the new model. This is experimental, not high-frequency qualification.

## Selecting loss models

The SI request accepts an optional loss_model object:

~~~json
"loss_model": {
  "conductor": "slab_skin",
  "roughness_model": "hammerstad",
  "rms_roughness_um": 2.0
}
~~~

Choose conductor dc for the previous reference model. Roughness requires
slab_skin and an explicit hammerstad selection; invalid or unsupported fields
are rejected. Conductivity, thickness and width come from the retained design.
Dielectric conductance remains omega C tan(delta), using the declared material
loss tangent. Unknown loss tangent remains explicitly marked unknown.
These request controls are available through the existing SI worker and CLI;
there is no new desktop roughness editor in this change.

For explicit AC PI requests, conductor.roughness_rms_um enables the same RMS
loss correction. conductor.include_internal_reactance defaults to false,
preserving explicit line L. If enabled, L_h_per_m MUST contain external
inductance only and field_bias_ratio must be zero. Nonzero imposed-field bias
still supports Joule loss, but its reactive energy is not admitted into that
scalar line model. Results record internal_reactance_ohm_per_m separately.

## Equations and numerical evidence

With exp(+j omega t), uniform isotropic conductivity sigma, permeability mu,
width w and thickness t, diffusion gives k squared = j omega mu sigma.
Symmetric broad-face excitation gives Zint per metre = k coth(kt/2)/(2 sigma w).
At DC this tends to R = 1/(sigma w t) and Lint = mu t/(12w).
In deep skin it tends to (1+j)/(2 sigma w delta), where
 delta = sqrt(1/(pi f mu sigma)). SI's electrostatic-derived inductance is
external, so adding internal reactance does not count the same energy twice.
Small-argument series and a bounded large-argument asymptote avoid overflow.
The equations, implementation and fixtures are independently authored.

Roughness multiplies real resistance by
1 + (2/pi) atan(1.4 (RMS/delta) squared), bounded between one and two.
It leaves smooth-conductor reactance unchanged. This empirical magnitude
correction is NOT a causal broadband phase model. TDR and eye results using it
remain exploratory, including finite-band transform artifacts.

Tests check independent real-form diffusion, DC and high-frequency limits,
branch continuity, passive sweeps, RMS bounds, SI reciprocity and S-matrix
singular values, changed insertion loss, unchanged DC, schema admission and
PI internal-energy selection. They establish these equations and integration,
not measured channel correlation or arbitrary-geometry accuracy.

## Limits and solver choice

200 MHz is not a universal model boundary. Skin depth relative to conductor
thickness, cross-section geometry, wavelength, return paths and material data
control suitability. The symmetric infinite-width slab omits side edges,
one-sided return-driven current crowding, return-plane conductor loss and
geometry-derived proximity redistribution. No new dielectric dispersion,
Huray roughness, magnetic dispersion, radiation or connector model is claimed.
Coupled SI includes mutual electrostatic and inductive coupling, but its
conductor diffusion remains isolated per trace.

Native PEEC retains its existing isolated skin-resistance and RMS roughness
models. The EMerge board/Gerber full-wave generator remains zero-thickness
perfect electric conductor geometry: requested finite-conductor, surface
impedance or roughness losses must be refused. Dielectric loss is supported
separately. A perfect-conductor full-wave solve cannot validate copper loss.
Independent finite-conductivity field correlation, return-current extraction,
material dispersion and knowledgeable numerical review remain release gates.
