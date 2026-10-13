# SPDX-License-Identifier: Apache-2.0
"""Small exact-MPN passive seed transcribed from official manufacturer sources."""
from __future__ import annotations

from copy import deepcopy


_DATE = "2026-10-12"
_IDEAL_LIMIT = (
    "Ideal nominal two-terminal model only; tolerance, temperature coefficient, "
    "frequency dependence, voltage coefficient, parasitics, aging, and derating are metadata, not simulated."
)
_SHUNT_LIMIT = (
    "Discovery metadata only. Four-terminal force/sense behavior and thermal/electrical limits require "
    "a reviewed vendor model and explicit terminal mapping before simulation."
)


def _passive(*, ident, manufacturer, mpn, category, value, unit, label, tolerance,
             package, ratings, url, document, fields, description):
    kind = {
        "resistor": "ideal_nominal_resistor",
        "capacitor": "ideal_nominal_capacitor",
        "inductor": "ideal_nominal_inductor",
    }[category]
    return {
        "id": ident, "manufacturer": manufacturer, "mpn": mpn, "category": category,
        "description": description, "nominal": {"value": value, "unit": unit, "label": label},
        "tolerance": {"kind": "symmetric", "value": tolerance, "unit": "percent", "display": f"+/-{tolerance}%"},
        "ratings": ratings, "package": package,
        "pins": [{"number": "1", "name": "1", "role": "terminal"},
                 {"number": "2", "name": "2", "role": "terminal"}],
        "model": {"kind": kind, "readiness": "placeable_ideal_nominal", "limitations": _IDEAL_LIMIT},
        "source": {"url": url, "accessed_on": _DATE, "document": document, "fields": fields},
    }


def _res(**kw):
    return _passive(category="resistor", unit="ohm", **kw)


def _cap(**kw):
    return _passive(category="capacitor", unit="F", **kw)


def _ind(**kw):
    return _passive(category="inductor", unit="H", **kw)


def _shunt(*, ident, mpn, value, tolerance, power, url, document):
    row = _res(
        ident=ident, manufacturer="Isabellenhuette", mpn=mpn, value=value,
        label=f"{value * 1000:g} mOhm", tolerance=tolerance,
        package="BVN 1216 four-terminal welded shunt",
        ratings=[{"name": "rated_power_at_70_c", "value": power, "unit": "W", "condition": "terminal temperature 70 degree C"}],
        url=url, document=document,
        fields=["exact ordering code", "resistance", "tolerance", "power rating", "four-terminal configuration"],
        description="Four-terminal precision current-sense shunt",
    )
    row["pins"] = [
        {"number": "1", "name": "FORCE+", "role": "force_positive"},
        {"number": "2", "name": "SENSE+", "role": "sense_positive"},
        {"number": "3", "name": "SENSE-", "role": "sense_negative"},
        {"number": "4", "name": "FORCE-", "role": "force_negative"},
    ]
    row["model"] = {"kind": "none", "readiness": "vendor_model_required", "limitations": _SHUNT_LIMIT}
    return row


def records():
    """Return fresh exact-MPN records; no manufacturer model data is bundled."""
    panasonic = "https://industrial.panasonic.com/ww/products/pt/high-precision-chip-resistors/models/"
    kyocera = "https://search.kyocera-avx.com/product/"
    samsung = "https://product.samsungsem.com/mlcc/CL10B104KB8NNN.do"
    vishay = "https://www.vishay.com/doc/?63395="
    rows = [
        _res(ident="panasonic.era3veb1002v", manufacturer="Panasonic", mpn="ERA3VEB1002V", value=10000, label="10 kohm", tolerance=0.1, package="0603 (1.6 x 0.8 mm)", ratings=[{"name":"rated_power","value":0.125,"unit":"W"}], url=panasonic+"ERA3VEB1002V", document="Panasonic ERA3VEB1002V model page", fields=["exact MPN","resistance","tolerance","power","case size"], description="High-stability thin-film chip resistor"),
        _res(ident="panasonic.era3aeb1020v", manufacturer="Panasonic", mpn="ERA3AEB1020V", value=102, label="102 ohm", tolerance=0.1, package="0603 (1.6 x 0.8 mm)", ratings=[{"name":"rated_power","value":0.1,"unit":"W"}], url=panasonic+"ERA3AEB1020V", document="Panasonic ERA3AEB1020V model page", fields=["exact MPN","resistance","tolerance","power","case size"], description="High-reliability thin-film chip resistor"),
        _res(ident="panasonic.era3aeb203v", manufacturer="Panasonic", mpn="ERA3AEB203V", value=20000, label="20 kohm", tolerance=0.1, package="0603 (1.6 x 0.8 mm)", ratings=[{"name":"rated_power","value":0.1,"unit":"W"}], url=panasonic+"ERA3AEB203V", document="Panasonic ERA3AEB203V model page", fields=["exact MPN","resistance","tolerance","power","case size"], description="High-reliability thin-film chip resistor"),
        _res(ident="panasonic.era2aeb103x", manufacturer="Panasonic", mpn="ERA2AEB103X", value=10000, label="10 kohm", tolerance=0.1, package="0402 (1.0 x 0.5 mm)", ratings=[{"name":"rated_power","value":0.063,"unit":"W"}], url="https://na.industrial.panasonic.com/products/resistors/smd-chip-resistors/series/36034/model/44240", document="Panasonic ERA2AEB103X model page", fields=["exact MPN","resistance","tolerance","power","case size"], description="High-reliability thin-film chip resistor"),
        _cap(ident="kyocera.04025c104kat2a", manufacturer="KYOCERA AVX", mpn="04025C104KAT2A", value=1e-7, label="100 nF", tolerance=10, package="0402", ratings=[{"name":"rated_voltage","value":50,"unit":"VDC"}], url=kyocera+"04025C104KAT2A", document="KYOCERA AVX product search record", fields=["exact MPN","capacitance","tolerance","rated voltage","dielectric","case size"], description="X7R multilayer ceramic capacitor"),
        _cap(ident="kyocera.06033c104kat2a", manufacturer="KYOCERA AVX", mpn="06033C104KAT2A", value=1e-7, label="100 nF", tolerance=10, package="0603", ratings=[{"name":"rated_voltage","value":25,"unit":"VDC"}], url=kyocera+"06033C104KAT2A", document="KYOCERA AVX product search record", fields=["exact MPN","capacitance","tolerance","rated voltage","dielectric","case size"], description="X7R multilayer ceramic capacitor"),
        _cap(ident="samsung.cl10b104kb8nnnc", manufacturer="Samsung Electro-Mechanics", mpn="CL10B104KB8NNNC", value=1e-7, label="100 nF", tolerance=10, package="0603 (1608 metric)", ratings=[{"name":"rated_voltage","value":50,"unit":"VDC"}], url=samsung, document="Samsung Electro-Mechanics CL10B104KB8NNN# product page", fields=["exact packaged MPN","capacitance","tolerance","rated voltage","X7R","case size"], description="X7R multilayer ceramic capacitor"),
        _cap(ident="murata.gcm188r71c334ka37d", manufacturer="Murata", mpn="GCM188R71C334KA37D", value=3.3e-7, label="0.33 uF", tolerance=10, package="0603 (1608 metric), paper tape", ratings=[{"name":"rated_voltage","value":16,"unit":"VDC"}], url="https://search.murata.co.jp/Ceramy/image/img/A01X/G101/ENG/GCM188R71C334KA37-01A.pdf", document="Murata GCM188R71C334KA37 reference sheet", fields=["exact packaged MPN","capacitance","tolerance","rated voltage","X7R","dimensions"], description="AEC-Q200 X7R multilayer ceramic capacitor"),
        _res(ident="panasonic.era2aeb102x", manufacturer="Panasonic", mpn="ERA2AEB102X", value=1000, label="1 kohm", tolerance=0.1, package="0402 (1.0 x 0.5 mm)", ratings=[{"name":"rated_power","value":0.063,"unit":"W"}], url="https://na.industrial.panasonic.com/products/resistors/smd-chip-resistors/series/36034/model/44239", document="Panasonic ERA2AEB102X model page", fields=["exact MPN","resistance","tolerance","power","case size"], description="High-reliability thin-film chip resistor"),
        _res(ident="panasonic.era3aeb2372v", manufacturer="Panasonic", mpn="ERA3AEB2372V", value=23700, label="23.7 kohm", tolerance=0.1, package="0603 (1.6 x 0.8 mm)", ratings=[{"name":"rated_power","value":0.1,"unit":"W"}], url=panasonic+"ERA3AEB2372V", document="Panasonic ERA3AEB2372V model page", fields=["exact MPN","resistance","tolerance","power","case size"], description="High-reliability thin-film chip resistor"),
        _res(ident="vishay.crcw060310k0fkea", manufacturer="Vishay Dale", mpn="CRCW060310K0FKEA", value=10000, label="10 kohm", tolerance=1, package="0603", ratings=[{"name":"rated_voltage","value":50,"unit":"V"}], url=vishay, document="Vishay SiP12107 reference design BOM", fields=["exact MPN","resistance","tolerance","rated voltage","PCB footprint"], description="Thick-film chip resistor"),
        _res(ident="vishay.crcw0603100kfkea", manufacturer="Vishay Dale", mpn="CRCW0603100KFKEA", value=100000, label="100 kohm", tolerance=1, package="0603", ratings=[{"name":"rated_voltage","value":50,"unit":"V"}], url=vishay, document="Vishay SiP12107 reference design BOM", fields=["exact MPN","resistance","tolerance","rated voltage","PCB footprint"], description="Thick-film chip resistor"),
        _ind(ident="coilcraft.lps4018-103mrc", manufacturer="Coilcraft", mpn="LPS4018-103MRC", value=10e-6, label="10 uH", tolerance=20, package="LPS4018 shielded low-profile SMD", ratings=[{"name":"dcr_max","value":0.2,"unit":"ohm","condition":"25 degree C"},{"name":"irms_20_c_rise","value":0.9,"unit":"A","condition":"20 degree C temperature rise from 25 degree C ambient"}], url="https://www.coilcraft.com/en-us/products/power/shielded-inductors/ferrite-drum/lps/lps4018/", document="Coilcraft LPS4018 official product table", fields=["exact MPN","inductance","tolerance","DCR maximum","conditioned Irms","package family"], description="Shielded low-profile ferrite power inductor"),
        _ind(ident="coilcraft.lps4018-223mrc", manufacturer="Coilcraft", mpn="LPS4018-223MRC", value=22e-6, label="22 uH", tolerance=20, package="LPS4018 shielded low-profile SMD", ratings=[{"name":"dcr_max","value":0.36,"unit":"ohm","condition":"25 degree C"},{"name":"irms_20_c_rise","value":0.65,"unit":"A","condition":"20 degree C temperature rise from 25 degree C ambient"}], url="https://www.coilcraft.com/en-us/products/power/shielded-inductors/ferrite-drum/lps/lps4018/", document="Coilcraft LPS4018 official product table", fields=["exact MPN","inductance","tolerance","DCR maximum","conditioned Irms","package family"], description="Shielded low-profile ferrite power inductor"),
        _ind(ident="pulse.pa4340.103anlt", manufacturer="Pulse Electronics", mpn="PA4340.103ANLT", value=10e-6, label="10 uH", tolerance=20, package="Molded shielded SMD, 6.0 x 5.4 x 3.0 mm maximum", ratings=[{"name":"rated_current","value":3.8,"unit":"A","condition":"manufacturer rated-current method at 25 degree C"},{"name":"dcr_max","value":0.103,"unit":"ohm","condition":"25 degree C"}], url="https://productfinder.pulseelectronics.com/api/open/part-attachments/datasheet/PA4340.153ANLT", document="Pulse PA4340.XXXANLT datasheet P819.G", fields=["exact MPN","inductance","tolerance","rated current","DCR maximum","maximum dimensions"], description="High-current molded power inductor"),
        _ind(ident="pulse.pa4340.223anlt", manufacturer="Pulse Electronics", mpn="PA4340.223ANLT", value=22e-6, label="22 uH", tolerance=20, package="Molded shielded SMD, 6.0 x 5.4 x 3.0 mm maximum", ratings=[{"name":"rated_current","value":2.4,"unit":"A","condition":"manufacturer rated-current method at 25 degree C"},{"name":"dcr_max","value":0.228,"unit":"ohm","condition":"25 degree C"}], url="https://productfinder.pulseelectronics.com/api/open/part-attachments/datasheet/PA4340.153ANLT", document="Pulse PA4340.XXXANLT datasheet P819.G", fields=["exact MPN","inductance","tolerance","rated current","DCR maximum","maximum dimensions"], description="High-current molded power inductor"),
        _shunt(ident="isabellenhuette.bvn-z-r0005-1.0", mpn="BVN-Z-R0005-1.0", value=0.0005, tolerance=1, power=10, url="https://www.isabellenhuette.de/fileadmin/Daten/Praezisionswiderstaende/Datenblaetter/BVN.pdf", document="Isabellenhuette BVN datasheet, issue 15-February-2024"),
        _shunt(ident="isabellenhuette.bvn-z-r001-1.0", mpn="BVN-Z-R001-1.0", value=0.001, tolerance=1, power=10, url="https://www.isabellenhuette.de/fileadmin/Daten/Praezisionswiderstaende/Datenblaetter/BVN.pdf", document="Isabellenhuette BVN datasheet, issue 15-February-2024"),
    ]
    return deepcopy(rows)
