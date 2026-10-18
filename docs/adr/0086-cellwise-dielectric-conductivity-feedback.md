# ADR 0086: Cellwise dielectric conductivity feedback

Status: Accepted for bounded experimental development; human review before release.

## Decision

Compose the existing one-way AC dielectric/thermal workflow in a steady
fixed-point loop with explicit supplied linear conductivity-temperature laws.
Evaluate conductivity at cell-mean nodal temperature, reject invalid trial
ranges and preserve original inputs. Generated per-cell material IDs appear
in both copied meshes with explicit original-material and source ownership.

Keep the existing one-way API unchanged. Require raw temperature and power
convergence, retain electrical evaluation and returned thermal states, and
reject iteration exhaustion. Relaxation controls the next iterate only.
No new solver dependency, numerical kernel or implementation language is added.

## Acceptance and limits

An independently assembled coupled discrete P1 system, zero-coefficient
compatibility and failure/resource/worker checks define PI02-S04 acceptance.
See [contract, derivation and scope](../PDN_DIELECTRIC_FEEDBACK.md).
This extends multiphysics foundations within PI/SI priority. It is not general
material-law, transient-stability, thermal-runaway or measured-hardware
qualification; all other constitutive properties remain fixed.
