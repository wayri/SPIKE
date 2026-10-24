<!-- SPDX-License-Identifier: Apache-2.0 -->
# ADR0130: Isolated trusted-development AMI execution

Experimental development boundary, 23 October 2026. Not production or vendor
qualification; required knowledgeable numerical/security review remains open.

The owner prioritizes executable AMI ahead of further solver expansion.
Parameter inventory remains non-executing. A separate C++20 executable owns
the AMI native ABI and library lifetime; Python admits inputs, stages exact
model bytes and supervises the child. C++ is justified by the native ABI and
fault-isolation boundary, not a claim of a faster Python implementation.
The loader is never linked into the desktop, Python extension or main worker.

The first admitted platform is MSVC Windows x64 with static runtime. Strict
dependency admission and system-directory loading precede model execution.
Existing suspended-process Windows Job Object supervision limits memory,
child-process creation, wall time and cancellation. This is **not a security
sandbox**: trusted native code retains current-user filesystem and network
access. Explicit trust/license/dependency review cannot be supplied by an
imported design or inferred from a matching digest. The generic worker does
not expose a native-library execution method in this revision.

The explicit Python development API requires the separately admitted host
identity. The optional `SPIKE_BUILD_AMI_HOST` CMake target is off by default;
normal installers do not silently gain an arbitrary-library loader. Generic
PAM3 simulation has a separate strict JSON worker route and cannot request
native execution. POSIX hosting, arbitrary dependency packages, vendor
interoperability, full IBIS association and generation-specific protocol
qualification remain separately admitted work.

See [execution interface and limits](../SI_AMI_EXECUTION.md) and
[PAM3 method and evidence](../SI_PAM3.md). Synthetic fixture results establish
only the exact executed ABI subset, not model accuracy or standards compliance.
