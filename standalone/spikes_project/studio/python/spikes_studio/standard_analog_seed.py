# SPDX-License-Identifier: Apache-2.0
"""Sourced standard-analog catalog candidates for discovery and review only.

The records contain independently transcribed catalog facts, not manufacturer
models.  They are deliberately non-executable until an applicable vendor model,
its terms, pin mapping, and behavior have been reviewed and qualified.
"""

from __future__ import annotations


_DATE = "2026-10-12"
_MODEL = {
    "kind": "none",
    "readiness": "vendor_model_required",
    "limitations": (
        "Discovery/review metadata only; no executable model is supplied. "
        "Acquire and review an applicable vendor model, its license, version, "
        "package pin mapping, operating envelope, and solver behavior before use."
    ),
}


def _record(*, ident, manufacturer, mpn, category, description, nominal, package,
            pins, rating, url, document, fields):
    return {
        "id": ident,
        "manufacturer": manufacturer,
        "mpn": mpn,
        "category": category,
        "description": description,
        "nominal": nominal,
        "tolerance": {
            "kind": "not_applicable",
            "display": "No single component tolerance; review conditioned datasheet limits",
        },
        "ratings": [rating],
        "package": package,
        "pins": [
            {"number": number, "name": name, "role": role}
            for number, name, role in pins
        ],
        "model": dict(_MODEL),
        "source": {
            "url": url,
            "accessed_on": _DATE,
            "document": document,
            "fields": fields,
        },
    }


def records():
    """Return exact-orderable-package records, isolated from caller mutation."""
    dual_opamp_pins = (
        ("1", "1OUT", "output"), ("2", "1IN-", "input_inverting"),
        ("3", "1IN+", "input_noninverting"), ("4", "VCC-", "negative_supply"),
        ("5", "2IN+", "input_noninverting"), ("6", "2IN-", "input_inverting"),
        ("7", "2OUT", "output"), ("8", "VCC+", "positive_supply"),
    )
    inamp_pins = (
        ("1", "RG", "gain_resistor"), ("2", "IN-", "input_inverting"),
        ("3", "IN+", "input_noninverting"), ("4", "V-", "negative_supply"),
        ("5", "REF", "reference"), ("6", "OUT", "output"),
        ("7", "V+", "positive_supply"), ("8", "RG", "gain_resistor"),
    )
    rows = [
        _record(
            ident="ti.tl072cp", manufacturer="Texas Instruments", mpn="TL072CP",
            category="operational_amplifier",
            description="Dual low-noise FET-input operational amplifier",
            nominal={"value": 2, "unit": "count", "label": "2 amplifier channels"},
            package="PDIP-8 (P)", pins=dual_opamp_pins,
            rating={"name": "typical_gain_bandwidth", "value": 3000000, "unit": "Hz", "qualifier": "typical"},
            url="https://www.ti.com/product/TL072/part-details/TL072CP",
            document="TI TL072CP orderable-part page and TL07xx datasheet Rev. W",
            fields=["exact orderable MPN", "channel count", "gain bandwidth", "package", "pinout"],
        ),
        _record(
            ident="ti.ne5532p", manufacturer="Texas Instruments", mpn="NE5532P",
            category="operational_amplifier",
            description="Dual low-noise operational amplifier for audio applications",
            nominal={"value": 2, "unit": "count", "label": "2 amplifier channels"},
            package="PDIP-8 (P)", pins=dual_opamp_pins,
            rating={"name": "typical_unity_gain_bandwidth", "value": 12000000, "unit": "Hz", "qualifier": "typical"},
            url="https://www.ti.com/product/NE5532/part-details/NE5532P",
            document="TI NE5532P orderable-part page and NE5532x datasheet Rev. K",
            fields=["exact orderable MPN", "channel count", "unity-gain bandwidth", "package", "pinout"],
        ),
        _record(
            ident="ti.opa197idr", manufacturer="Texas Instruments", mpn="OPA197IDR",
            category="operational_amplifier",
            description="Single 36 V precision rail-to-rail input/output operational amplifier",
            nominal={"value": 1, "unit": "count", "label": "1 amplifier channel"},
            package="SOIC-8 (D)",
            pins=(("1", "NC", "no_connect"), ("2", "IN-", "input_inverting"),
                  ("3", "IN+", "input_noninverting"), ("4", "V-", "negative_supply"),
                  ("5", "NC", "no_connect"), ("6", "OUT", "output"),
                  ("7", "V+", "positive_supply"), ("8", "NC", "no_connect")),
            rating={"name": "total_supply_voltage", "value": [4.5, 36], "unit": "V"},
            url="https://www.ti.com/product/OPA197/part-details/OPA197IDR",
            document="TI OPA197IDR orderable-part page and OPAx197 datasheet Rev. C",
            fields=["exact orderable MPN", "channel count", "supply range", "package", "pinout"],
        ),
        _record(
            ident="ti.ina128p", manufacturer="Texas Instruments", mpn="INA128P",
            category="instrumentation_amplifier",
            description="Precision low-power instrumentation amplifier",
            nominal={"value": 1, "unit": "count", "label": "1 instrumentation amplifier"},
            package="PDIP-8 (P)", pins=inamp_pins,
            rating={"name": "total_supply_voltage", "value": [4.5, 36], "unit": "V"},
            url="https://www.ti.com/product/INA128/part-details/INA128P",
            document="TI INA128P orderable-part page and INA12x datasheet Rev. G",
            fields=["exact orderable MPN", "supply range", "package", "pinout"],
        ),
        _record(
            ident="adi.ad620anz", manufacturer="Analog Devices", mpn="AD620ANZ",
            category="instrumentation_amplifier",
            description="Low-drift low-power instrumentation amplifier",
            nominal={"value": 1, "unit": "count", "label": "1 instrumentation amplifier"},
            package="8-lead PDIP (N)", pins=inamp_pins,
            rating={"name": "dual_supply_voltage", "value": [2.3, 18], "unit": "V", "condition": "magnitude of each split supply rail"},
            url="https://www.analog.com/en/products/ad620.html",
            document="Analog Devices AD620 product page and datasheet Rev. H",
            fields=["exact part model", "supply range", "package", "pinout"],
        ),
        _record(
            ident="adi.ad623anz", manufacturer="Analog Devices", mpn="AD623ANZ",
            category="instrumentation_amplifier",
            description="Single- and dual-supply rail-to-rail instrumentation amplifier",
            nominal={"value": 1, "unit": "count", "label": "1 instrumentation amplifier"},
            package="8-lead PDIP (N)", pins=inamp_pins,
            rating={"name": "single_supply_voltage", "value": [2.7, 12], "unit": "V"},
            url="https://www.analog.com/en/products/ad623.html",
            document="Analog Devices AD623 product page and datasheet Rev. G",
            fields=["exact part model", "supply range", "package", "pinout"],
        ),
        _record(
            ident="onsemi.2n3904bu", manufacturer="onsemi", mpn="2N3904BU",
            category="bipolar_transistor", description="NPN general-purpose transistor",
            nominal={"value": 40, "unit": "V", "label": "40 V minimum collector-emitter breakdown"},
            package="TO-92-3 LF (case 135AN)",
            pins=(("1", "E", "emitter"), ("2", "B", "base"), ("3", "C", "collector")),
            rating={"name": "collector_emitter_breakdown_min", "value": 40, "unit": "V", "condition": "IC = 1 mA, IB = 0"},
            url="https://www.onsemi.com/download/data-sheet/pdf/2n3904-d.pdf",
            document="onsemi 2N3904 datasheet",
            fields=["ordering suffix", "V(BR)CEO", "package style", "pinout"],
        ),
        _record(
            ident="onsemi.2n3906bu", manufacturer="onsemi", mpn="2N3906BU",
            category="bipolar_transistor", description="PNP general-purpose transistor",
            nominal={"value": 40, "unit": "V", "label": "40 V minimum collector-emitter breakdown magnitude"},
            package="TO-92 (TO-226), case 29, style 1",
            pins=(("1", "E", "emitter"), ("2", "B", "base"), ("3", "C", "collector")),
            rating={"name": "collector_emitter_breakdown_magnitude_min", "value": 40, "unit": "V", "condition": "IC = 1 mA, IB = 0"},
            url="https://www.onsemi.com/download/data-sheet/pdf/2n3906-d.pdf",
            document="onsemi 2N3906 datasheet",
            fields=["ordering suffix", "V(BR)CEO", "package style", "pinout"],
        ),
        _record(
            ident="onsemi.mmbt2222alt1g", manufacturer="onsemi", mpn="MMBT2222ALT1G",
            category="bipolar_transistor", description="NPN general-purpose amplifier transistor",
            nominal={"value": 40, "unit": "V", "label": "40 V collector-emitter voltage maximum"},
            package="SOT-23, case 318, style 6",
            pins=(("1", "B", "base"), ("2", "E", "emitter"), ("3", "C", "collector")),
            rating={"name": "collector_emitter_voltage_max", "value": 40, "unit": "V"},
            url="https://www.onsemi.com/pdf/datasheet/mmbt2222lt1-d.pdf",
            document="onsemi MMBT2222L/MMBT2222AL datasheet",
            fields=["exact orderable MPN", "collector-emitter voltage", "package", "pinout"],
        ),
        _record(
            ident="onsemi.fqp30n06l", manufacturer="onsemi", mpn="FQP30N06L",
            category="mosfet", description="60 V logic-level N-channel power MOSFET",
            nominal={"value": 60, "unit": "V", "label": "60 V drain-source breakdown minimum"},
            package="TO-220",
            pins=(("1", "G", "gate"), ("2", "D", "drain"), ("3", "S", "source"), ("TAB", "D", "drain_tab")),
            rating={"name": "drain_source_breakdown_min", "value": 60, "unit": "V", "condition": "VGS = 0 V, ID = 250 uA"},
            url="https://www.onsemi.com/download/data-sheet/pdf/fqp30n06l-d.pdf",
            document="onsemi FQP30N06L datasheet Rev. C1",
            fields=["exact MPN", "BVDSS", "package", "pinout"],
        ),
        _record(
            ident="nexperia.bc847b-215", manufacturer="Nexperia", mpn="BC847B,215",
            category="bipolar_transistor", description="45 V, 100 mA NPN general-purpose transistor",
            nominal={"value": 45, "unit": "V", "label": "45 V collector-emitter voltage maximum"},
            package="SOT23 (TO-236AB)",
            pins=(("1", "B", "base"), ("2", "E", "emitter"), ("3", "C", "collector")),
            rating={"name": "collector_emitter_voltage_max", "value": 45, "unit": "V"},
            url="https://www.nexperia.com/product/BC847",
            document="Nexperia BC847 product page and BC847 series datasheet",
            fields=["exact orderable MPN", "VCEO", "collector current", "package", "pinout"],
        ),
        _record(
            ident="nexperia.bc857b-215", manufacturer="Nexperia", mpn="BC857B,215",
            category="bipolar_transistor", description="45 V, 100 mA PNP general-purpose transistor",
            nominal={"value": 45, "unit": "V", "label": "45 V collector-emitter voltage magnitude maximum"},
            package="SOT23 (TO-236AB)",
            pins=(("1", "B", "base"), ("2", "E", "emitter"), ("3", "C", "collector")),
            rating={"name": "collector_emitter_voltage_magnitude_max", "value": 45, "unit": "V"},
            url="https://www.nexperia.com/products/bipolar-transistors/general-purpose-and-low-vcesat-bipolar-transistors/single-bipolar-transistors/single-bipolar-transistors-100-v/serie/bc856-bc857-bc858",
            document="Nexperia BC856/BC857/BC858 product page and datasheet",
            fields=["exact orderable MPN", "VCEO", "collector current", "package", "pinout"],
        ),
        _record(
            ident="nexperia.2n7002-215", manufacturer="Nexperia", mpn="2N7002,215",
            category="mosfet", description="60 V, 300 mA N-channel small-signal MOSFET",
            nominal={"value": 60, "unit": "V", "label": "60 V drain-source voltage maximum"},
            package="SOT23 (TO-236AB)",
            pins=(("1", "G", "gate"), ("2", "S", "source"), ("3", "D", "drain")),
            rating={"name": "drain_source_voltage_max", "value": 60, "unit": "V"},
            url="https://www.nexperia.com/product/2N7002",
            document="Nexperia 2N7002 product page and datasheet",
            fields=["exact orderable MPN", "VDS", "drain current", "package", "pinout"],
        ),
    ]
    return rows
