# Native manufacturer-identity approximations

Status: engineering preview, unqualified, 20 October 2026.

## Claim and boundary

`manufacturer-executable-v1.json` adds five native-executable, exact-identity
approximations to the separate 208-row manufacturer discovery inventory:

| Discovery ID | Identity | Native reduction |
| --- | --- | --- |
| `ti-lm358` | Texas Instruments LM358 | Full eight-pin dual, two independent one-pole channels and approximate rail clamps |
| `adi-ad620` | Analog Devices AD620 | Full eight-pin instrumentation-amplifier DC gain relation, G=1 pole, approximate rail clamps |
| `onsemi-mmbt3904lt1g` | onsemi MMBT3904LT1G | Three-terminal Ebers-Moll NPN reduction |
| `onsemi-2n7002l` | onsemi 2N7002L | Source-tied-bulk Level-1 NMOS and static body diode |
| `nexperia-bas316` | Nexperia BAS316 | Static two-point Shockley curve |

Catalog presence means only that an independently authored SPIKE reduction can
be inserted into the owned native circuit backend. Every record says
`model_status=part_specific_approximation_unqualified`, `qualified=false`, and
`backend=native`. It is not a vendor model, manufacturer qualification, package
qualification, production validation, or promotion of the other 203 discovery
rows. No external model body, implementation, graph coordinates, test fixture,
or prose was copied or translated.

This stage does not add LM741 or a comparator because neither is an identity in
the 208-row discovery catalog. It does not silently create an alias. The
separate sourced-parts inventory includes those product families but retains its
own admission state.

## Primary references actually reviewed

The implementation used only these official data sheets. URLs identify the
reviewed publisher copies; later revisions require reassessment.

- Texas Instruments, *LM158, LM158A, LM258, LM258A, LM2904, LM2904V, LM358,
  LM358A Industry-Standard Dual Operational Amplifiers*, SLOS068AB, revised
  October 2024, pin functions and section 5.7. Reviewed fields: common eight-pin
  dual pinout, typical open-loop gain 100 V/mV, typical gain-bandwidth product
  0.7 MHz, typical open-loop output resistance 300 ohm, and output swing under
  the stated loads. <https://www.ti.com/lit/ds/symlink/lm358.pdf>
- Analog Devices, *AD620 Low Cost, Low Power Instrumentation Amplifier*, Rev. H,
  connection diagram, Table 2, and Gain Selection. Reviewed fields: eight-pin
  pinout, `G = 1 + 49.4 kohm/RG`, G=1 bandwidth 1 MHz, output swing with 10 kohm
  load, and operating supply range.
  <https://www.analog.com/media/en/technical-documentation/data-sheets/AD620.pdf>
- onsemi, *MMBT3904L, SMMBT3904L General Purpose Transistors NPN Silicon*,
  MMBT3904LT1/D, Electrical Characteristics and SOT-23 style 6. Reviewed fields:
  minimum hFE=100 at IC=10 mA and VCE=1 V, maximum VBE(sat)=0.85 V at
  IC=10 mA/IB=1 mA, minimum fT=300 MHz, maximum Cibo=8 pF, maximum Cobo=4 pF,
  and package pinout.
  <https://www.onsemi.com/download/data-sheet/pdf/mmbt3904lt1-d.pdf>
- onsemi, *2N7002L, 2V7002L MOSFET - N-Channel, Small Signal, SOT-23*,
  2N7002L/D Rev. 11, June 2024, Maximum Ratings, Electrical Characteristics,
  and SOT-23 style 21. Reviewed fields: 1.0 V to 2.5 V threshold range,
  minimum gFS=80 mS at ID=200 mA, Ciss/Coss/Crss maxima of 50/25/5 pF,
  body-diode forward-voltage maximum 1.5 V at 115 mA, and package pinout.
  <https://www.onsemi.com/download/data-sheet/pdf/2n7002l-d.pdf>
- Nexperia, *BAS316 High-speed switching diode*, Rev. 7, 1 July 2022,
  Pinning Information, Limiting Values, and Table 7. Reviewed fields: SOD323
  pinout; maximum VF=0.715 V at 1 mA and 0.855 V at 10 mA; maximum Cd=1.5 pF;
  maximum trr=4 ns; and voltage/current limits.
  <https://assets.nexperia.com/documents/data-sheet/BAS316.pdf>

These references provide device facts and bounded specifications. They do not
provide or license the SPIKE implementation, and a citation does not grant a
right to redistribute a manufacturer's simulation payload.

## Independent formulations

### LM358 dual one-pole reduction

For each channel, the open-loop state is

```text
v_e = A0 (v+ - v-)
tau_p d(v_p)/dt + v_p = v_e
v_raw = v_p
```

with `A0=100000`, `GBW=700000 Hz`, `Rdom=1000 ohm`, and

```text
fp = GBW/A0
Cdom = 1/(2*pi*fp*Rdom) = A0/(2*pi*GBW*Rdom)
     = 22.736420441699336 uF.
```

The output has 300 ohm series resistance. Static Shockley diodes referenced to
offset supply nodes qualitatively stop the output near 1.5 V below V+ and
0.02 V above V- at light load. A 0.7 V nominal diode-drop offset is an explicit
numerical construction, not a data-sheet parameter. Both channels and the shared
supply pins are present in one eight-pin subcircuit.

The ordinary unity-feedback transfer is approximately first order with closed-
loop time constant `1/(2*pi*GBW)` while it remains away from the clamps. The
model does not implement the published 0.3 V/us slew rate. Consequently a large
step can be much faster than the physical part even though its small-signal pole
is represented.

### AD620 gain-resistor reduction

A unity VCVS applies `vd = v(IN+) - v(IN-)` across RG1/RG2. With a finite
external positive `RG`, its source branch current is `iE=-vd/RG`. A CCVS then
adds `-49400*iE`, so the DC output before loading is

```text
vout - vref = vd - 49400*iE
            = (1 + 49400/RG) vd.
```

Distinct floating RG nets represent open RG (G=1); two 1e15-ohm references to
REF remove the otherwise floating common-mode degree of freedom. Shorting RG1
and RG2 to the same node is invalid. A 1 MHz RC pole records only the G=1
bandwidth. It intentionally does not claim the data-sheet bandwidths at G=10,
100, or 1000. The one-ohm output resistance is a numerical regularization, not
a sourced AD620 parameter. Static rail clamps approximate the 10-kohm-load
headrooms of 1.4 V below V+ and 1.2 V above V-.

### MMBT3904LT1G NPN reduction

The existing owned native NPN primitive uses its established Ebers-Moll form.
This catalog supplies `BF=100`, the data-sheet minimum at the selected 10 mA
condition, `CBE=8 pF`, and `CBC=4 pF`. It uses `N=1` and chooses

```text
IS = 10 mA / exp(0.85 V / VT) = 5.342746796539795e-17 A
VT = kT/q at 300.15 K.
```

This treats the maximum saturated VBE as a conservative forward-active proxy;
it is not a direct forward-active fit. `BR=1` is an explicit numerical
assumption. `TF=0.5 ns` is a rounded first-order estimate from the 300 MHz
minimum fT; it is not a switching-storage fit.

### 2N7002L NMOS reduction

The owned Level-1 saturation law is

```text
ID = KP/2 (VGS - VTO)^2, VDS >= VGS - VTO.
```

`VTO=1.75 V` is the stated midpoint assumption of the 1.0 V to 2.5 V limits.
Using `gm=KP*(VGS-VTO)` and the 80 mS minimum at 200 mA gives

```text
KP = gm^2/(2 ID) = 0.016 A/V^2.
```

The constant-capacitance reduction uses `CGD=Crss=5 pF`,
`CGS=Ciss-Crss=45 pF`, and `CDS=Coss-Crss=20 pF`. Combining maxima from one
bias point does not make a charge-conserving nonlinear capacitance model. The
source-tied body diode uses `N=2` and an IS chosen to reach 115 mA at the 1.5 V
maximum. Channel-length modulation is explicitly zero.

### BAS316 diode reduction

At `T=300.15 K`, solve the static Shockley expression through the two published
maximum-forward-voltage points:

```text
I = IS (exp(V/(N VT)) - 1)
N  = (0.855 - 0.715)/(VT ln(10)) = 2.3507211259269805
IS = 1 mA/exp(0.715/(N VT))      = 7.813707376518093 nA.
```

The native code retains `expm1`; omitting minus one in the displayed closed-form
derivation changes these forward points by less than the test tolerance. Because
the source points are maxima, this is an upper-limit curve through two bounds,
not a typical measured curve and not a guaranteed envelope between or away from
the two points. Cd and trr remain evidence only because the admitted netlist
diode card is static.

## Numerical behavior and failure policy

All recipes flatten to the existing owned native R/C, independent/dependent
source, static diode, Ebers-Moll NPN, or Level-1 NMOS primitives. No ngspice
fallback exists. Parser rejection, nonlinear nonconvergence, singular topology,
or unsupported integration is returned as a failure.

Large controlled-source gains, 1e15-ohm RG references, low external RG, ideal
sources, and exponential junctions can worsen MNA conditioning. The records are
small screening models, not unconditional convergence guarantees. The existing
native exponential limiting and nonlinear tolerances are unchanged. The op-amp
rail clamps make their macros nonlinear, so no small-signal AC claim is made.
Transient support is limited to the native backward-Euler and BDF2 paths; the
recipes add no adaptive-step or stability qualification.

No recipe enforces absolute maximum ratings. Ratings are applicability evidence,
not simulated protection. Inputs must be biased and returned by the surrounding
circuit. AD620 RG must be open on distinct nets or a finite positive resistance.
An altered or duplicated generated subcircuit fails installation; an exact
generated definition may be reused. Installation first reparses and flattens a
candidate document, then commits source, semantic parts, traceability metadata,
and undo state atomically.

## Executed verification

Run:

```powershell
$env:PYTHONPATH = "standalone/spikes_project/studio/python;."
$env:SPIKES_TEST_LIBRARY = "build-spikes-native-analysis-20261013/Release/spikes_c_api.dll"
python -m unittest standalone.spikes_project.tests.python.test_manufacturer_executable -v
```

On 20 October 2026, all seven focused tests passed against the local native DLL.
The checks bind all five records to the 208-row discovery catalog; prove the
other 203 rows remain unavailable; reject qualification, identity, and analysis
claim promotion; parse every generated recipe; exercise atomic install/undo;
and recompute the independent diode, MOSFET, and dominant-pole reductions.

Native operating-point results were:

| Fixture | Expected | Actual | Acceptance |
| --- | ---: | ---: | ---: |
| LM358 channel A follower, 0.5 V | 0.5 V | 0.4999948501 V | 20 uV absolute |
| LM358 channel B follower, 2 V | 2 V | 1.9999794002 V | 30 uV absolute |
| AD620, RG=5488.8889 ohm, vd=0.1 V | 1 V | 0.9999000099 V | 0.2 mV absolute |
| MMBT3904 at VBE=0.7 V | independent Ebers-Moll oracle | 29.99499877 uA | 2e-9 relative |
| 2N7002L, VGS=3 V saturation | 12.5 mA | 12.500000004 mA | 10 pA absolute |
| BAS316 at 0.715 V | 1 mA | 0.9999921863 mA | 10 nA absolute |

A native backward-Euler LM358 follower step also passed: at one nominal
`1/(2*pi*700 kHz)` time constant after the edge, its output was within 30 mV of
the independent first-order 63.2% oracle; by 2 us it was within 0.6 mV of the
1.5 V target. This verifies the implemented reduced pole, not LM358 large-signal
slew fidelity.

Tests that only parse or recompute parameter algebra are contract and code
verification. The operating-point/transient cases are synthetic reduced-model
verification. There is no measured-device correlation, lot/temperature spread,
vendor-model cross-check, or physical validation. Knowledgeable human numerical
and analog-model review remains required before release.

## User and developer workflow

The 208-row **Manufacturer products** catalog keeps identity discovery separate
from execution. Its executable-state filter exposes the five reviewed records;
the placement action stays disabled for the other 203. Selection details repeat
`qualified=false`, the source, valid-use statement, and limitations.

Placement presents every numbered package pin. The saved netlist retains the
full `XMAN` instance and mapping, then the schematic canvas displays the native
equivalent circuit after normal subcircuit flattening. This stage deliberately
does not invent a persistent compact package glyph or hide either LM358 channel.
The separate **Sourced electrical parts** panel and review-only vendor-model
intake keep their existing contracts.

The manufacturer browser can call:

- `availability(discovery_id)` for a fail-closed per-discovery state;
- `executable_record(discovery_id)` for the detached reviewed record;
- `source_pins(...)` for the complete required package-pin mapping;
- `native_recipe(...)` for inert generated source;
- `prepare_install(document, ..., mapping)` for a non-mutating candidate; and
- `install(document, ..., mapping)` for one atomic, undoable commit.

LM358 and AD620 require all eight pin mappings. The interface never silently
places a single amplifier while naming it as the full part. Saved components and
document metadata retain discovery ID, exact part number, source URL, compiled
source digest, model status, and `qualified=false`.

Future promotion requires an immutable source/revision review, independent DC,
AC and transient validation over the declared envelope, temperature/load/common-
mode tests, convergence and failure cases, physical measurements with uncertainty,
and knowledgeable human review. Vendor-model compatibility or a checksum alone
does not satisfy those gates.
