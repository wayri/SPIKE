# Native sparseLizard Runtime

This directory builds the process-isolated sparseLizard runtime used by SPIKE.
The produced executable is a native Windows UCRT64 binary. It does not use WSL.

The adapter source in this directory is licensed under GPL-2.0-or-later because
it links to sparseLizard. It remains a separate process from the MIT-licensed
SPIKE desktop and exchanges only versioned files.

The current executable implements a deterministic DC conduction FEM self-test
on the unit-square mesh shipped with sparseLizard's RLC example. It verifies the
native compiler, sparseLizard, PETSc LU, SLEPc, Microsoft MPI, and OpenBLAS
runtime. The current MSYS2 PETSc package does not register MUMPS, so lumped
circuit coupling and production-scale factorization remain blocked until a
separately pinned PETSc/MUMPS build passes its own fixtures. This test does not
validate arbitrary PCB PI, SI, thermal, or EMI workflows.

## Windows Build

Run `scripts/install_sparselizard_native.ps1` from an elevated PowerShell. It
installs native Windows prerequisites, checks out the pinned upstream commit,
builds the runtime, packages non-system DLLs, executes the self-test, and writes
an integrity-bound manifest under
`runtime/external/sparselizard/native-windows`. Use `-BuildOnly` after the
prerequisites and source tree are already present.
