<!-- SPDX-License-Identifier: Apache-2.0 -->

# Layout-scoring process examples

Run from the SPIKE repository root:

```powershell
python examples/layout_scoring/run_examples.py
```

The runner exercises capability discovery, prepare and score operations for
autorouter, autoplacer, and joint consumers. It also proves that a tampered
DesignIR digest and a path-traversal control are rejected.

The score example uses a correlated verification-only native result with a
4 W loss, a 5 W normalization, and weight 2, producing the expected
dimensionless lower-is-better score of 1.6.

These examples demonstrate orchestration and scoring. They do not claim that
this process routes, places, generates a 3-D mesh, or solves physics.
