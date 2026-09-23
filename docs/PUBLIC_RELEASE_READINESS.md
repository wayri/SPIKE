<!-- SPDX-License-Identifier: MIT -->

# Public release readiness

SPIKES `0.3.0-beta.1` is a technically verified public-release candidate for
the bounded circuit-engine and SDK surface. It is not currently authorized for
public distribution. The SPIKE desktop remains independently versioned at
`0.2.5`, and the native multiphysics adapter remains `integration_pending`.

Build into a fresh directory, then verify the exact report and archive:

```powershell
python scripts/build_spikes_engine_release.py --library C:\absolute\path\spikes_c_api.dll --output-root C:\fresh\release-directory
python scripts/verify_spikes_engine_release.py C:\fresh\release-directory\SPIKES-0.3.0-beta.1-release.json --output C:\fresh\release-directory\SPIKES-0.3.0-beta.1-verification.json
python scripts/run_public_release_gate.py --engine-report C:\fresh\release-directory\SPIKES-0.3.0-beta.1-release.json --output C:\fresh\release-directory\SPIKES-0.3.0-beta.1-public-release-gate.json
```

The verifier rejects traversal, duplicate paths, symbolic links, undeclared or
missing files, digest drift, manifest drift, version drift, and widened claims.
It extracts the archive to a temporary side-by-side location, launches the
packaged CLI without depending on the source checkout, and removes the staged
installation. This is a portable-engine smoke, not an MSI/NSIS upgrade test.

The public gate has three outcomes:

- `PASS`: technical checks and all external release authorizations are present.
- `BLOCKED_EXTERNAL`: the technical candidate passes, but owner/counsel,
  dependency, signature, clean-machine, or auditable-CI evidence is missing.
- `FAIL`: a technical invariant failed. The artifact must not be distributed.

The current expected outcome is `BLOCKED_EXTERNAL`. Do not rename that result
to `PASS`, remove blockers from the report, or advertise production readiness.
Complete ownership/provenance review, the version-specific SBOM and third-party
notice review, archive signing, clean-machine qualification, and auditable CI
for the exact immutable digest first.

Public claims remain deliberately narrow. The package does not claim complete
SPICE3 or arbitrary IBIS compatibility, arbitrary PCB field physics,
competitive superiority, hard real-time behavior, or production signing.
