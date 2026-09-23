# Manufacturer library qualification status

The project-local manufacturer shelf is an import/review workflow, not a
prequalified executable parts catalog. It retains user-supplied source,
provenance, pin declarations, dependency inventory and hashes. No vendor model
payload is bundled by this workflow. Review redistribution terms before sharing
a project that embeds manufacturer source.

The prior inspection of the [official TI LM358 model](https://www.ti.com/product/LM358)
recorded failure at a model declaration inside a subcircuit. Scoped static diode
models are now implemented and tested, so that historical error is not a current
blanket restriction. The complete LM358 archive has not been requalified: its
other model types and behavioral expressions require additional implementation.
It must remain not-qualified rather than be replaced with a renamed generic part.

See [model review checklist](manufacturer-model-qualification.md),
[open collection assessment](OPEN_MODEL_COLLECTIONS.md), and
[two-stage execution record](TWO_STAGE_SPICE_EXECUTION.md).
