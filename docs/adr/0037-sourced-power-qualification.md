<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 SigHarmonic -->
# Sourced power qualification boundaries

Status: experimental development, October 6, 2026.

Add a local developer API for hash-admitted decks, explicit observable gates,
native step refinement and immutable numerical evidence artifacts. No vendor
model copying into source control, model substitution or hardware qualification.
Use immutable include snapshots and pass actual saved-step limits to the native
ABI. Existing parser/runner behavior remains the default for other consumers.

Add a separate strict thermal-transient/quasi-static resistor-feedback contract
reusing existing electrical and thermal kernels. Require explicit full loss
mapping, thermal capacities/links and unrelaxed conservation/convergence checks.
It does not replace the semiconductor or electrical-transient solver and adds
no inferred cooling. A synthetic shared sink cannot model bare-PCB fan cooling.

No GUI or production worker exposure is added by this decision. Trusted process
isolation, model licensing/applicability review, current source/CAD equivalence,
human numerical review and independent/measured qualification remain required.
