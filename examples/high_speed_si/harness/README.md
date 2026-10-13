# Interboard harness PI and coupled SI reference

This original synthetic example joins two explicit board occurrences,
`harness-board-A` and `harness-board-B`, with a 600 mm six-conductor harness.
It provides a power/return loop plus differential aggressor and victim pairs.
No board pinout, cable construction or measured data is inferred.

Run from the repository root with a fresh destination:

```powershell
python examples/high_speed_si/harness/run_interboard_harness.py `
  --output-dir build/interboard-harness-reference
```

The run executes the actual `run_harness_pi`, `extract_parallel_round_rlgc`,
public GUI-supported `run_harness_si`, and coupled `run_harness_mtl` paths. It
checks DC KVL, `I^2 R`, native power closure, the bounded uniform differential
two-port, sampled MTL residual/passivity/reciprocity, differential NEXT/FEXT,
and a second actual solve with mutual RLGC removed. The coupled MTL method is
registered in the desktop worker bridge but does not yet have a dedicated MTL
report panel; `integration.json` records that exact UI boundary.

`assembly-view.json` and `harness-document.json` retain board occurrence,
connector, pin, wire, pair, route and cross-section identities for the existing
harness editor and interactive 3D conductor viewer. `integration.json` records
the applicable schemas and current source anchors. Full requests, results,
validation values, runtime versions and hashes are saved separately.

The model is experimental and not production qualified. The SI result is a
straight thin-wire quasi-TEM approximation above an ideal infinite ground
plane. It does not solve connector launches, board copper, bends, shields,
radiation, BER or protocol compliance, and it has no measured correlation.
