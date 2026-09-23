# SPIKE Runtime Resources

Release builds place signed, platform-specific runtime bundles here during
packaging. Development builds use the repository worker and host Python.

Expected release layout:

```text
runtime/
  bin/python(.exe)
  worker/spike_worker(.exe)
  solvers/ngspice/<platform>/...
  solvers/peec-2.5d/<platform>/...
  solvers/mom/<platform>/...
  solvers/fullwave-3d/<platform>/...
  solvers/openfoam/<platform>/...
  converters/freecad/<platform>/...
  converters/blender/<platform>/...
```

The desktop application must verify the lock manifest before launching a
bundled worker. Optional solvers and converters may be absent, but their
capabilities must be shown as unavailable rather than downloaded implicitly.
Each solver directory must contain a signed bundle inventory and a
`spike/solver-plugin/v1` manifest. Solver executables run from private job
directories and are never launched through a shell.
