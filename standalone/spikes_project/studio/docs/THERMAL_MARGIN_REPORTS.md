# Thermal margin reports

Analytics → Thermal margins generates an exportable JSON report for the captured run configuration. Existing Export report saves it. Warning/exceeded assessments also feed part alert markers.

Before running, add a `thermal_assessment` object to component Properties → Parameters → User metadata. These are explicitly supplied engineering inputs, not automatic datasheet extraction. Example shape (replace every value with reviewed part/system data):

```json
{"thermal_assessment":{"max_junction_c":150,"warning_margin_c":20,"supplied_temperature_c":135}}
```

Alternatively provide `ambient_c`, `steady_power_w`, `theta_ja_k_w` and `conditions_evidence` instead of `supplied_temperature_c`. This uses Tj = Ta + P × effective theta_JA, a steady-state approximation only. Evidence should identify the actual board, airflow, mounting and how power and resistance were established. It does not solve transient thermal impedance or infer heat from arbitrary electrical terminal power.

A result's `element_temperature_k` channel takes precedence when present. Current ordinary electrical runs do not generate that channel. Declared `temperature_k` metadata is deliberately not substituted for solved junction temperature. Reports disclose their input basis and captured run provenance. Re-run after changing assessment settings to capture the updated configuration.

Headroom is maximum rated junction temperature minus peak assessed junction temperature. Exceeded means zero/negative headroom; warning means headroom at or below the user-configurable warning margin. Other results say within declared margin, not universally safe. Unknown ratings/temperature, malformed inputs and nonfinite values are unavailable.

This is not service-life, failure-probability, thermal-cycling or performance-degradation prediction. Those require device-specific characterized relationships and operating history. Discarded rolling-capture history is not assessed.

Reference: [TI thermal system explanation](https://www.ti.com/document-viewer/lit/html/SSZTB80/GUID-D4E3F3F5-260D-45A1-862A-6E9A3052DC5A).

Manufacturer-model ingestion/qualification, redistribution review and physical LED/lamp/detector models remain separate outstanding work; this report does not establish those capabilities.
