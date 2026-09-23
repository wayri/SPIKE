# Rigid-flex design support

SPIKE's normalized `DesignIR` identifies board construction independently of
the EDA source:

- `technology`: `rigid`, `flex`, or `rigid-flex`;
- `regions`: closed rigid, flex, transition, and stiffener outlines;
- `bends`: bend polylines with optional radius and angle metadata.

## KiCad authoring convention

Until KiCad exposes a single native rigid-flex exchange object, SPIKE imports
closed graphics from named user layers. A layer name or user-visible layer name
must contain `Flex`, `Rigid`, `Transition`, or `Stiffener`. A bend layer must
contain `Bend`; `R1.5`/`Radius 1.5` and `A90`/`Angle 90` annotations are parsed
as millimetres and degrees. The source drawing and layer names remain in the IR
for audit and round-trip purposes.

## Solver policy

DC and transient conductor analyses currently use the flat fabrication
reference. Their reports must state that bend strain and
deformation-dependent resistance are excluded. Frequency-domain rigid-flex
analysis requires regional stackups (or an explicit uniform-stackup policy)
and a solver plugin declaring `regional_stackup`. Deformed geometry is rejected
unless the selected plugin declares `deformed_rigid_flex`.

The viewport may display region and bend metadata, but visualization never
upgrades an unsupported solver mode. Solver plugins receive the same region and
bend records in `spike/solver-geometry/v1` and each
`spike/net-geometry/v1` bundle.
