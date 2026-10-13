# First manufacturer-model execution review

Assessed 2026-10-13.

## Outcome

The official TI LM358 and LM741 PSpice macro-model downloads both executed in the repository's bundled ngspice 46 runtime using original, bounded unity-follower test fixtures. The LM358 library is not accepted by plain ngspice: it requires ngspice's PSpice compatibility setting, `set ngbehavior=ps`. The LM741 library parsed and completed a transient analysis without that setting; the final measured run used the same PSpice-compatible harness for consistency.

This is executable compatibility evidence, not model validation. It does not establish datasheet fidelity, physical accuracy, stability over arbitrary loads, temperature behavior, package equivalence, hardware correlation, or redistribution rights.

## Provenance and identity

Both archives were downloaded from public, unauthenticated links on their official TI product pages. No access control, encryption, or download restriction was bypassed. The downloaded archives and extracted vendor files were left unmodified.

| MPN | Official listing | Direct archive | Archive identity | Extracted model identity |
| --- | --- | --- | --- | --- |
| LM358 | [TI LM358 product page](https://www.ti.com/product/LM358), “LMx58_LM2904 PSpice Model (Rev. C)” | [SNOM268](https://www.ti.com/lit/zip/SNOM268) | 23,655 bytes; SHA-256 `D3B7B2089C35518AB9F0F05290CF7856297E2680A40B0A731640923203A6DCC2` | `lmx58_lm2904.lib`, 12,026 bytes; SHA-256 `467A3E573420D1F5A21FAB57B76BE0E13073E854F609A73459A191958E314726` |
| LM741 | [TI LM741 product page](https://www.ti.com/product/LM741), “LM741 PSpice Model (Rev. B)” | [SNOM211B](https://www.ti.com/lit/zip/SNOM211B) | 23,013 bytes; SHA-256 `CDF5544CCF12A2957750A4C57C15B684528315E61488A85E99B96F1771F6D136` | `lm741.lib`, 2,596 bytes; SHA-256 `F58370983C8BD22BF6A59DDD05A1DD492F1A0EA60F673FFD460A356DA5E693DC` |

The LM358 listing/archive revision and the embedded macro-model revision are not the same label: TI lists archive Rev. C, while the extracted model header says `LMX58_LM2904 - Rev. B`. This record preserves both facts and does not infer equivalence. The LM741 file is a legacy National Semiconductor model delivered by TI; its `.SUBCKT LM741 1 2 99 50 28` pins are non-inverting input, inverting input, positive supply, negative supply, and output.

The archives contain PSpice project and symbol files in addition to the `.lib` files. No separate license file was present. The archived example projects refer to PSpice installation libraries such as `nom.lib`/`nom_pspti.lib`, but the two selected `.lib` macro-models have no external include dependency and were exercised independently with SPIKE-authored fixtures.

## Terms boundary

The product pages designate the downloads as evaluation items and point to TI terms. [TI's current Terms of Use](https://www.ti.com/legal/terms-conditions/terms-of-use.html), observed with an effective date of 2025-03-27, provide a narrow basis for unmodified non-commercial or personal downloads and separately state that downloadable software may be governed by an accompanying license. This review therefore proceeded only as a local evaluation with original notices preserved.

The LM741 source header contains a legacy permission to copy and distribute the model while prohibiting resale. The LM358 archive has no comparable package-level grant. Because both files now arrive through TI's current delivery path, and neither archive contained a separate license file, neither model is approved here for repository packaging or redistribution. Commercial use is also not approved by this review. A rights owner or qualified legal reviewer must resolve those uses before the vendor bytes are committed, published, or shipped.

This is a conservative engineering record, not legal advice.

## Dialect and dependency inspection

| Model | Subcircuit | External model dependencies | Observed dialect features | ngspice requirement |
| --- | --- | --- | --- | --- |
| LM358 | `LMX58_LM2904 IN+ IN- VCC VEE OUT` | None; helper subcircuits and models are in the same file | `VSWITCH`, `RES(T_ABS=-273.15)`, behavioral `VALUE` expressions, `IF`, `LIMIT`, `PWR`, `SGN`, `TABLE`, and boolean OR | `set ngbehavior=ps` |
| LM741 | `LM741 1 2 99 50 28` | None | Basic primitives, `POLY(1)` controlled sources, and embedded NPN/diode models | No compatibility mode needed for parsing/execution |

The compatibility setting is held in the separately authored fixture `.spiceinit`; neither vendor library was patched or translated.

## Reproduction fixture

Runtime: `runtime/external/Spice64/bin/ngspice_con.exe`, reporting ngspice 46 with KLU available, creation date 2026-03-29. The measured fixtures actually report **SPARSE 1.3** as their direct linear solver; they are not evidence of KLU performance. Executable size is 7,602,688 bytes and SHA-256 is `86C9EA5F645CA919E305639FA7BDB522355364C424D14E197F1ADE617FEB3453`.

The fixtures are intentionally small:

- LM358: single-supply 5 V follower, 0.5 V/3.0 V pulse, 10 kΩ and 100 pF load, 2 ms transient.
- LM741: ±15 V follower, −1 V/+1 V pulse, 10 kΩ and 100 pF load, 2 ms transient.
- Both use `.options reltol=1e-4 abstol=1e-12 vntol=1e-6` and measure settled points before and during the high pulse.

Fixture identities:

- `fixtures/lm358_unity_smoke.cir`: SHA-256 `D2A3D4F22F6C89A15ECE37CB29DC11BC2C44AA234E714094FC8797FC2F0985F9`
- `fixtures/lm741_unity_smoke.cir`: SHA-256 `04ADB8BF78013CDE662B1E4BE13CAF139591FA8C680CF3E98525B03FDF0152A4`
- `fixtures/.spiceinit`: SHA-256 `6F309FDDE9942930F4C2A68E25642AAFB4626AB4BF6788095E3704EA98A88DAA`

Run from `artifacts/manufacturer-review-20261013/fixtures` so the relative `.include` paths and local `.spiceinit` resolve. The measured runs used:

```powershell
& ../../../runtime/external/Spice64/bin/ngspice_con.exe -b lm358_unity_smoke.cir
& ../../../runtime/external/Spice64/bin/ngspice_con.exe -b lm741_unity_smoke.cir
```

## Execution evidence

| MPN | Mode | Exit | Rows | Low point | High point | Absolute errors |
| --- | --- | ---: | ---: | --- | --- | --- |
| LM358 | PSpice compatibility | 0 | 2,567 | 0.500000 V in; 0.501963 V out | 3.000000 V in; 3.001970 V out | 1.96287 mV low; 1.97367 mV high |
| LM741 | PSpice compatibility, common harness | 0 | 2,504 | −1.000000 V in; −0.999027 V out | 1.000000 V in; 1.001030 V out | 0.973473 mV low; 1.02655 mV high |

The first LM358 run intentionally retained plain-ngspice behavior. It exited 1 after `VSWITCH` model-type warnings and a fatal unsupported `if` function at vendor-library line 228. This is the direct evidence for the PSpice compatibility requirement. Log SHA-256: `3ABA7C4BAB3DFAEB795B7EC384932733682A8FC42501FEE1F7B4E35E0FEFD249`.

The first LM741 run exited 0 without compatibility mode and produced 2,504 transient rows. Because batch raw-output mode suppresses `.measure` reporting, that run establishes plain-parser/execution compatibility but not measured acceptance. The retained raw file SHA-256 is `281D9D4902687B513CBAFF451D6D0FD18DE5B93BAC01E7DF833EC55ED76BC2BD`.

Final measured log identities:

- LM358: SHA-256 `00FC4AAB08EE58CB6EE94FF04A55024D8287D25624CE98646EC3E944CFEEA510`
- LM741: SHA-256 `B434E0EDD423E9CD2DEA9E3C0BC7B67DB6381673D2D910E511495278832E3599`

ngspice emitted a warning in both compatible runs that subcircuit ground is not automatically mapped to node 0. The runs still converged and completed; the warning remains a qualification item rather than being hidden or rewritten.

## Admission decision

| MPN | Executable with bundled runtime | Minimum backend setting | Runnable-library admission | Redistribution/package admission |
| --- | --- | --- | --- | --- |
| LM358 | Yes, bounded smoke only | `ngbehavior=ps` | Eligible only as a user-supplied, hash-matched local model pending wider technical validation | Denied pending affirmative rights evidence |
| LM741 | Yes, bounded smoke only | None observed | Eligible only as a user-supplied, hash-matched local model pending wider technical validation | Denied pending affirmative rights evidence |

Do not use these smoke results to claim supported operating ranges or validated accuracy. Before any production-facing admission, add independent DC, AC, transient, slew, saturation/recovery, common-mode, load, and temperature comparisons against manufacturer limits, followed by knowledgeable human review.

## Local evidence layout

The ignored local directory `artifacts/manufacturer-review-20261013/` contains the original archives, extracted vendor files, authored fixtures, execution logs, raw output, and `review_manifest.json`. It is evidence for this local assessment, not a distributable payload. The manifest records all relevant hashes and the fail-closed rights decision.
