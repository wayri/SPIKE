<!-- SPDX-License-Identifier: MIT -->

# Packaged circuit worker and IBIS-rejection examples

These examples exercise the actual packaged `spike-circuit-worker` and trusted
host supervisor strictly through their process boundary. They do not include
private SPIKES headers, link a private library, or expose C++ implementation
types.

Run from the public SPIKE repository root:

```powershell
python examples/circuit_worker/run_examples.py
```

The runner:

1. verifies every file in `spike-circuit-worker.manifest.json`;
2. admits exact worker and owned-DLL SHA-256 identities;
3. solves a structured voltage-source/resistor operating-point job under the
   Windows Job Object or POSIX process-group supervisor;
4. demonstrates rejection of a bad worker digest and a traversal control path;
5. demonstrates OS-enforced timeout termination;
6. verifies that this packaged worker does not advertise an IBIS process
   capability; and
7. demonstrates fail-closed rejection of an attempted raw IBIS payload.

The private runtime has a bounded, data-only IBIS table evaluator, but it is not
yet exposed through the packaged public process contract. Consequently there
is deliberately no successful public IBIS evaluation example here. Adding one
before a versioned process contract and capability advertisement would bypass
the intended public boundary. The rejection example prevents that absence from
being confused with arbitrary IBIS support.

Job controls are created in temporary directories and source files are never
modified. The example still does not claim arbitrary SPICE compatibility,
product qualification, or independent/measured correlation.
