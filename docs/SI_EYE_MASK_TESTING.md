# Eye-mask testing in protocol suites

Open a protocol suite, choose its eye analysis, and assign a mask under
Eye mask. Masks start unassigned. USB suites offer two built-in USB 2.0
high-speed inner-opening profiles. Other protocols accept a user-owned
polygon-mask JSON with its protocol, revision, source locator and clause.

## Standard profiles and conditions

USB 2.0 HS Template 1 inner opening applies to the hub at TP2 and to a device
without a captive cable at TP3. Template 2 applies to a device with a captive
cable at TP2. These numerical coordinates were independently encoded from
section 7.1.2.2, Figures 7-13/7-14 of the USB 2.0 base specification. The
source locator is retained in every mask result. Original specification text,
artwork and files are not redistributed.

Selecting either profile requires differential NRZ at 480 Mbit/s. Enter the
explicit voltage scale and offset for the retained eye normalization:
V = normalized value times scale_v plus offset_v. These are evidence inputs,
not fitting knobs: use the stimulus amplitude, bias and reference plane from
your model. No source amplitude or fixture attenuation is inferred.

Only the inner-opening polygons are tested. The 475/525 mV transition-dependent
outer voltage limits, rise/fall and monotonicity requirements, test modes,
fixture calibration and bandwidth are not tested by these profiles. The result
is an inner-opening screen, not a complete USB template or certification test.
Standard-specific masks for Ethernet, PCIe, DDR and other revisions/test points
are not fabricated. Import the applicable mask and preserve its provenance.

## Verdict and display

The UI overlays forbidden polygons on the eye in UI and either volts or
normalized units. PASS means none of the retained points or connecting linear
segments touched a polygon. FAIL includes the number of violating point/segment
primitives; this is not the number of erroneous bits or BER. Contact with a
boundary fails. Separate eye traces are not joined.

Exact binary64 phase coordinates are retained by new NRZ runs. Older records
without them must be rerun for mask testing; a drawn legacy plot is insufficient
phase evidence. PAM4 phase statistics currently have no retained waveform
traces and are blocked for polygon testing. Invalid mappings, incompatible
units, self-intersecting masks and excessive work are rejected.

The current NRZ generator retains at most 256 display traces. Mask evaluation
covers those retained polylines, not all generated bits, unsampled excursions,
noise distributions or extrapolated rare-event behavior. Voltage mapping and
scope accompany the verdict. Overall compliance remains not_evaluated.

## Worker and result contract

The run_si_protocol_test_suite worker method accepts per-lane eye_mask or eye_mask_id
(mutually exclusive). Built-in IDs are usb2.hs.template1.inner and
usb2.hs.template2.inner. Voltage masks also require eye_voltage_mapping with
scale_v, offset_v and bit_rate_hz matching the channel request.

Custom masks use schema spike/si-eye-mask/v1, id, name, protocol matching the
suite family, revision, source containing locator/clause, voltage_unit V or
normalized, and polygons of [time_ui, voltage] vertices with implicit closure.
No repeated closing vertex is needed. Coordinates are not translated or fitted.

Results retain lanes[].eye_mask_result, its mask/source, mapping, verdict,
hit counts, limits and samples tested. Eye test records also retain mask_test;
summary has mask_pass_count and mask_fail_count. The overall
protocol_pass_claimed flag stays false. Export the suite result JSON to retain
the mask verdict and provenance; channel-only reports do not include it.

## Verification

Independent polygon tests cover boundaries, tangent/collinear contact,
concavity, segment crossings with outside endpoints, units and malformed data.
Protocol integration checks a real computed channel against passing and failing
fixture masks, authoritative numerical USB coordinates, rate/family binding,
voltage mapping and missing phase evidence. These validate the evaluator and
integration; they do not qualify protocol models or hardware.
