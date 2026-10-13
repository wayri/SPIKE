# Palace native workflow

SPIKE's original Apache-2.0 adapter connects to a separately installed Palace
runtime. No upstream source, examples, meshes or binaries are included.

## Workflow and API

Use the SDK applications palace-discover, palace-validate, palace-prepare,
palace-run and palace-import. Supply parameters.config as strict JSON with the
five native sections Problem, Model, Domains, Boundaries and Solver. Author
materials, domain/boundary attribute assignments, ports and solver settings in
these sections using the official reference. SPIKE does not translate PCB
geometry or invent domain labels, boundary conditions or excitation settings.
Explicit Model.L0 records meters per mesh coordinate unit. Comments and integer
range extensions must be expanded into strict JSON before submission.

Select an absolute mesh_path and optionally runtime_path. Validate returns the
mesh digest; review it and supply expected_mesh_sha256 before Run. Source bytes,
configuration and host design binding are retained in a private UUID job under
SPIKE_STATE_HOME/palace-jobs. Prepare changes only Model.Mesh and Problem.Output
to the staged mesh and private output directory. Import uses job_id and requires
matching design/input bindings and recorded successful runtime exit.

All documented problem types are admitted: Eigenmode, Driven, Transient,
Electrostatic, Magnetostatic and BoundaryMode. Adapter admission checks are not
Palace schema validation. When installed, Validate additionally runs contained
Palace --dry-run (at most 120 seconds) and records its exit and resolved-config
diagnostics. When unavailable, validation_scope explicitly states admission
only. The selected runtime owns detailed native schema,
mesh compatibility and physical-model checks. Unknown types and external
partitioning/file assets return unsupported. Mesh formats are passed to Palace;
SPIKE neither repairs nor claims to validate mesh attributes or topology.

Limits: configuration 2 MiB, mesh 256 MiB, timeout_s 1..3300 (default 180),
memory_limit_mb 256..32768 (default 2048), 2 MiB per output stream, 256 MiB
retained output admission, 4096 artifact entries. CSV tables up to 2 MiB each,
10000 rows, 256 columns and a total 6 MiB exchange are returned without sampling.
Oversized tables remain artifact references. threads=1 is the only admitted
allocation; this means one MPI rank. Solver-internal thread defaults are not
controlled by this adapter. Caller commands, shells and argument lists are not
accepted. Installed POSIX Palace launcher uses one MPI rank; native binaries
receive the staged configuration path directly. Native Windows runtime support
requires an executable installed by the user; WSL/container launches are absent.

A fixed guardian supervises the native process, with common OS memory/time,
process tree and stream containment. Cancellation propagates when the SDK
wrapper dies. Failed exits, missing output and malformed tables cannot be
reported as solved. Retained jobs are user-owned recovery artifacts; remove
obsolete palace-jobs directories through ordinary local file management.

## Results and limits

CSV headers and values are preserved as strings, including native units and
NaN entries for undefined quantities. UI numeric plots may use finite samples
only. No S matrix completion, dB/phase conversion or inferred result values are
performed. Native ParaView/GLVis outputs are returned as file references with
byte counts and SHA256 digests. Palace writes raw-appended binary VTK;
an optional VTK reader provides a contained exact native-point preview for up
to four VTU artifacts of at most 64 MiB each. It returns up to 2000 native
points and 16 arrays (up to 9 components) without interpolation. The UI exposes
those points and returned finite field values; complete connectivity, cell
arrays and time-series field animation remain unsupported. Missing VTK is
explicitly reported with install guidance. ParaView remains available for full
native field inspection. Preview coordinates retain mesh units with explicit
Model.L0, and known E/B arrays retain SI units. Unknown array units remain null.
Completion is experimental and does not prove accuracy, convergence or hardware
qualification. No real Palace runtime qualification was performed here.

## Provenance and verification

Authoritative interface references consulted 2026-10-10:
- https://awslabs.github.io/palace/stable/config/config/
- https://awslabs.github.io/palace/stable/config/reference/
- https://awslabs.github.io/palace/stable/guide/problem/
- https://awslabs.github.io/palace/stable/run/
- https://awslabs.github.io/palace/stable/guide/postprocessing/

Only published interface behavior informed this clean-room adapter. Tests use
original inert mesh/artifact bytes and process fixtures, not upstream examples
or physical accuracy oracles. Run `python -m unittest discover -s tests/python -p test_palace_extension.py -v` for admission, source binding, unsupported
assets, output integrity, malformed tables and cancellation plumbing checks.
