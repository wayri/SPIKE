# Main source snapshot

This private repository starts from the active SPIKE development source as of
2026-09-23. The working development tree was not modified by this import.
The snapshot includes the full React desktop application, Rust desktop host,
Python application services and numerical source, C++ kernels, tests, schemas,
examples, and maintained documentation.

Generated builds, downloaded toolchains, personal runtime settings, local logs,
and very large validation-result files were deliberately omitted from Git.
The omitted result files remain in the original development workspace; they
are data artifacts, not implementations. Do not treat this first commit as
recovered prior Git history or proof of ownership for third-party assets.
The source and solver capability limits remain those in docs/SOLVER_STATUS.md.

The staged public PI release is a separate downstream project. Changes here
should be reviewed and exported through explicit versioned interfaces so the
internal application and later public stages can evolve independently.
