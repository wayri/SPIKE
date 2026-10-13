<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native behavioral-expression acceleration

`src/spikes/behavioral_expression.hpp` remains the owned C++ bounded expression
DAG used by native behavioral devices. This change moves opcode decoding to
construction, replaces per-evaluation cache/ready allocations with bounded
thread-local scratch and generation tags, and replaces the type-erased recursive
function wrapper with a generic recursive lambda. Lazy conditional semantics
and all value/derivative formulas are retained; inactive invalid branches are
not evaluated. The signal vector and native solver interfaces are unchanged.

Each active evaluation thread retains approximately 136 KiB for at most 512
nodes. First-use zero-initialization still costs time; warm up the evaluator
before latency measurements. Shared programs remain immutable. The new native
test uses four real threads with independent signals and multiple programs;
it also checks exact old-evaluator parity across every opcode and branching
workload points, analytic/central-difference gradients, domain failures and lazy
IF handling. Allocation counting after warm-up changed from 200 to zero per
100 evaluator calls. This does not remove allocations elsewhere in MNA.

One Windows MSVC 19.51 Release study used a 217-node nonlinear/branching DAG,
five trials of 10,000 evaluations and alternating paired measurement order.
Across five executions, evaluator speedups ranged 1.356..1.533, mean 1.430 with
population standard deviation approximately .065. Host timing was noisy. The
pre-change executable agreed with the retained original evaluator near 1.007x,
so the comparison did not rely solely on a rewritten benchmark oracle.

Reproduce with `test_spikes_behavioral_speed`, built with strict FP rather than
fast-math. Timings are informational, never a fragile speed assertion. These
are expression-kernel measurements, not whole-circuit speed, multicore scaling,
hard-real-time guarantees or competitive simulator superiority. Native core,
transient/session, and model/circuit regressions must pass after integration.
