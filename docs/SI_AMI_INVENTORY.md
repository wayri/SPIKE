<!-- SPDX-License-Identifier: Apache-2.0 -->
# AMI parameter and package inventory

Status: **inventory only; execution unsupported**. This is an independent
non-executing Python adapter, not an AMI simulator, complete IBIS validator,
device model qualification or protocol compliance result. Existing IBIS
DC-slope reduction and SI channel kernels are unchanged.

## API and use

`python.spike_core.solvers.signal_integrity.receivers.si_ami_inventory.parse_ami_parameters(text, name="model.ami")`
returns `spike/si-ami-parameter-inventory/v1`. It retains the exact ASCII source
SHA-256, source byte count, root, parameter paths, typed descriptor values,
descriptions, groups and explicitly unvalidated reserved-parameter paths.
Malformed or unsupported input raises `SiAmiInventoryError`; no partial success
is returned. Keep the original source independently; the inventory is not a
lossless source replacement. The public function is directly callable from
Python. Worker methods `inspect_si_ami_parameters` (exact `text` plus optional
`name`) and `inspect_si_ami_package` (exact `{request: ...}`) now expose the
non-executing inventory. No CLI model-execution or GUI DLL-loading control is
enabled. `service_si_models.py` owns this process boundary.

The authored scalar subset supports nested groups, comments, multiline quoted
strings, Usage, Type, Description, Value, Range, List, Corner, Default and
List_Tip, including the optional Format prefix. Types are Float, Integer,
Boolean, String, Tap and UI. UI values remain symbolic unit intervals; the
adapter does not convert them to seconds or apply them to an equalizer.

`inspect_ami_package(request)` accepts exactly:

- `contract`: `spike/si-ami-package-request/v1`;
- `direction`: caller-declared `tx` or `rx`;
- `platform`: caller-declared OS/compiler/32-or-64-bit tag;
- `parameter_file`: exactly `path`, ASCII `text`, and lowercase `sha256`;
- `executable_file`: exactly `path`, canonical `base64`, and lowercase `sha256`.

The result is `spike/si-ami-package-inventory/v1`, containing the parameter
inventory, declared platform/direction and byte-verified member identities.
The structural request schema is
[`si-ami-package-request-v1.schema.json`](../schemas/si-ami-package-request-v1.schema.json),
with ID `spike/si-ami-package-request/v1`. Schema acceptance does not replace
decoder checks for path safety, matching hashes, canonical base64, decoded
byte limits or AMI semantics. Finite JSON and process transport budgets remain
separate admission requirements.
It omits the executable bytes. These are two supplied virtual members, **not**
a complete dependency package. Paths are inert relative names, never opened
or extracted. Absolute, traversal, ambiguous and reserved Windows names fail.
Hash identity establishes neither executable trust nor redistribution rights.

## Bounds and admission

Both APIs always return `execution_admitted: false` and `abi_verified: false`.
They do not accept fields that could override either result. No library loader,
process runner, filesystem read, archive extraction or native entry point is
used. Tests supply invented non-library bytes to establish that inventory
acceptance cannot be mistaken for executable compatibility.

Resource limits: 1 MiB ASCII parameter text, 65,536 lexical tokens, 4,096
characters per token, 256 per branch name, 32 nesting levels, 8,192 nodes,
2,048 parameters, 4 MiB decoded executable bytes and 4 MiB compact-JSON result.
Repeated deep paths count toward that response bound. Limits are adapter policy,
not claims about specification maxima. Parsing and list-tip checking are
bounded linear passes; no user-specified range is expanded. Integer inventory
is signed 32-bit; numeric overflow/underflow outside binary64 fails closed.

This subset requires an explicit supported AMI version from 5.1 through 8.0,
with the required startup declarations checked. It inventories other reserved
parameters only as explicitly unvalidated. Usage Dep anywhere in the tree
requires version 6.1 or later and an explicit, checked Resolve_Exists True
declaration (IBIS 8.0 section 10.4, page 253); no resolver is executed.
Descriptor fragments are rejected as incomplete parameters rather than accepted
as empty groups. Reserved_Parameters and Model_Specific remain containers,
while Description-only annotations on nested groups remain supported.
Table, Increment, Steps, statistical
distribution formats, ignore blocks, implicit-version 5.0 input and complete
reserved-parameter semantic validation are unsupported. Recovery is to retain
the original source and use an appropriately qualified implementation, not to
delete unsupported declarations to make a model executable.

## ABI boundary and source review

The primary reference reviewed on 23 October 2026 is the official
[IBIS 8.0 specification](https://ibis.org/ver8.0/ver8_0.pdf), ratified
5 December 2025: sections 10.1 (model-file association), 10.2.1 (function
inventory), 10.2.3 (function signatures), 10.3.2-10.3.5 and 10.3.7 (parameter
structure/types/formats), and 10.4 (general reserved declarations).

The specification distinguishes parameter metadata from executable functions.
AMI_Init and AMI_Close are required; AMI_GetWave and the paired resolve
functions depend on the model. The C-facing interface involves pointers,
buffer ownership and platform-sensitive types. Declared platform tags cannot
establish a compatible ABI. These observations do not implement any calls.

A future execution feature requires a separately reviewed isolated process
host, actual binary/platform/export/dependency checks, explicit trust and
license admission, bounded IPC, cancellation and crash containment, correct
memory ownership, and independent behavioral evidence. It must not route a
model library into the main process or repurpose this inventory admission.

Implementation, data structures, prose and fixtures were independently authored.
No external implementation, code example, model binary or dataset was copied.
No governing physical model or numerical kernel is changed here.

## Verification

Run `.venv/Scripts/python.exe -m unittest tests.python.test_si_ami_inventory -v`.
The synthetic tests cover recursive typed inventory, exact source identity,
comments/strings, case sensitivity, malformed/duplicate declarations, scalar
type/range/default checks, reserved declarations, explicit unsupported states,
all parser resource guards, package digests, canonical encoding, path rejection,
and non-execution despite supplied native-library-looking member names.
No vendor-model or external checker comparison has been executed; this is
not full-format qualification. Broader channel behavior remains separately
qualified by its existing tests.
