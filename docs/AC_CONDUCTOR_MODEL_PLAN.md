# AC Conductor Model Plan

## Status

The native PEEC adapter executes experimental AC RLCG requests. It is not yet a
validated sign-off solver. The routed-copper DC solver must not consume an AC
request.

## Required Physics

The native AC engine solves frequency-dependent resistance and partial
inductance from the conductor geometry. Skin loss uses the closed-form
one-dimensional slab internal impedance through the conductor's thin
dimension. Proximity effect remains capability-gated because it requires
coupled current redistribution, not a scalar multiplier.

Dielectric loss, dispersion, copper thickness, plating, temperature, and return
geometry must be included in the solver handoff and provenance.

## Roughness Models

SPIKE exposes model-specific parameters:

- `none`: smooth conductor reference.
- `hammerstad`: implemented empirical correction using RMS roughness and skin depth. This
  is a compatibility/engineering estimate, not a universal roughness model.
- `huray`: snowball model using nodule radius and surface-area ratio. RMS
  roughness alone is not a valid Huray parameter set.
- `gradient`: conductivity-gradient/surface-impedance model using measured
  surface-profile standard deviation. This is intended for the higher-accuracy
  implementation and requires validation against measured fixtures.

Primary references:

- Huray et al., "Fundamentals of a 3-D 'snowball' model for surface roughness
  power losses," IEEE SPI 2007, DOI
  [10.1109/SPI.2007.4512227](https://doi.org/10.1109/SPI.2007.4512227).
- Helmreich et al., "A Physical Surface Roughness Model and Its Applications,"
  IEEE Transactions on Microwave Theory and Techniques 65(10), DOI
  [10.1109/TMTT.2017.2695192](https://doi.org/10.1109/TMTT.2017.2695192).

## Accuracy Gates

Before the AC solver can be promoted from experimental to validated:

1. Compare smooth-conductor results against analytical slab-impedance and
   resistance references.
2. Validate proximity-effect current redistribution on coupled-strip and
   plane-return fixtures.
3. Validate every roughness model independently using its required measured
   inputs.
4. Compare insertion loss, phase delay, and impedance against measured coupons
   over the declared frequency range.
5. Publish mesh convergence, conditioning, applicable geometry limits, and
   expected error bands in every result.
6. Reject or downgrade requests whose material or roughness inputs are
   insufficient for the selected model.

## Request Contract

AC requests carry:

- frequency start, stop, and point count;
- explicit source and sink arrays, including stored profiles;
- selected power net and probes;
- skin-effect and proximity-effect requirements;
- roughness model and model-specific parameters;
- stackup, dielectric, copper, via, pad, zone, and routed geometry;
- limits and solver/formulation selection.

The plugin registry must select only a solver declaring all requested
capabilities. Unsupported requests remain exportable for inspection but cannot
produce a result labelled approximate or validated.
