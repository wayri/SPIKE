# Synthetic interboard harness PI/SI result

The checked run completed for a 600 mm harness between the explicit synthetic
occurrences `harness-board-A` and `harness-board-B`. The retained connector is
`JH1` on each board, with reviewed pins `PWR`, `RET`, `AGG_P`, `AGG_N`, `VIC_P`
and `VIC_N`. The two differential pairs and power/return conductors share one
serialized route, while the SI electrical cross-section uses its own explicit
wire coordinates rather than display offsets.

The actual DC solve used a 12 V source, a 4 A board-B load, and two 0.0206897
ohm power conductors. Board-B voltage was 11.8344828 V and wire loss was
0.6620690 W. The KVL voltage error was 1.78e-15 V, the `I^2 R` loss error was
8.44e-15 W, and the native element power sum closed to 7.05e-15 W.

The public GUI-supported uniform differential SI path completed 33 points to
250 MHz. Its scalar modal reference impedance was 260.491 ohms; minimum through
magnitude was 0.979381 and maximum input reflection magnitude was 0.00380412.
This two-port result deliberately contains no victim coupling or common-mode
conversion.

The actual four-conductor MTL solve used 0.15 mm radius solid conductors at
`x = -7, -3, 3, 7 mm`, all 8 mm above an ideal infinite ground plane in an
assumed homogeneous `er = 2.4`, `tan(delta) = 0.008` dielectric. Peak
differential NEXT was 0.0172875 V/V (-35.2454 dB) at 117.1875 MHz; peak FEXT
was 0.0148354 V/V (-36.5740 dB) at 78.125 MHz. Maximum relative residual was
2.96e-16, sampled maximum singular value was 1.0, and reciprocity error was
1.20e-15. An actual control solve with all mutual RLGC entries removed produced
zero victim transfer.

The harness PI panel and uniform harness SI panel have public desktop flows.
The coupled MTL method is registered in the desktop worker bridge and preserves
all node, wire, port and board identities, but it has no dedicated report panel.
The assembly artifact supplies exact connector mappings, occurrence transforms,
route points and saved conductor identities to the existing 3D harness viewer.

These are original synthetic, experimental models. No real board pinout or
measured cable was supplied. The results do not include board copper, connector
launches or contacts, bends, shields, radiation, full-wave fields, BER,
protocol compliance, broadband causality qualification or measured correlation.
See [evidence/report.json](evidence/report.json) for the machine-readable scope
and [evidence/validation.json](evidence/validation.json) for the full sampled
frequency response and checks.
