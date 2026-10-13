# SPDX-License-Identifier: Apache-2.0
"""Fail-closed manufacturer-model acquisition catalog.

Catalog records are evidence leads, not bundled models and not runnable library
entries.  No function in this module downloads, parses, imports, or executes a
manufacturer model.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlparse


CATALOG_SCHEMA = "spikes.manufacturer-model-catalog.v1"
ADMISSION_SCHEMA = "spikes.user-model-admission-evidence.v1"
ASSESSED_ON = "2026-10-13"
TARGET_PER_CATEGORY = 100
MAX_EVIDENCE_FILE_BYTES = 64 * 1024 * 1024

CANONICAL_CATEGORIES = (
    "opamp",
    "bjt",
    "npn",
    "pnp",
    "mosfet",
    "nmos",
    "pmos",
    "ganfet",
    "sicfet",
    "mesfet",
    "pin_diode",
    "diode",
    "schottky",
    "controller",
    "pwm",
)

_CATEGORY_ALIASES = {
    "op_amp": "opamp",
    "operational_amplifier": "opamp",
    "bipolar": "bjt",
    "bipolar_transistor": "bjt",
    "n_channel": "nmos",
    "n_channel_mosfet": "nmos",
    "p_channel": "pmos",
    "p_channel_mosfet": "pmos",
    "gan": "ganfet",
    "gan_fet": "ganfet",
    "sic": "sicfet",
    "sic_mosfet": "sicfet",
    "pin": "pin_diode",
    "pin-diode": "pin_diode",
    "schottky_diode": "schottky",
    "pwm_controller": "pwm",
}

_MODEL_READY_STATES = {
    "catalog_only",
    "manufacturer_model_page_unreviewed",
    "manufacturer_download_unreviewed",
    "manufacturer_clickthrough_unreviewed",
}

_PRIMARY_HOSTS = {
    "Texas Instruments": ("ti.com",),
    "Analog Devices": ("analog.com",),
    "Infineon Technologies": ("infineon.com",),
    "Nexperia": ("nexperia.com",),
    "STMicroelectronics": ("st.com",),
    "Wolfspeed": ("wolfspeed.com",),
    "ROHM Semiconductor": ("rohm.com",),
    "Vishay": ("vishay.com",),
    "Qorvo": ("qorvo.com",),
    "MACOM": ("macom.com",),
}

_PLACEHOLDER_MPN = re.compile(
    r"(?:^|[-_.])(?:generic|placeholder|example|sample|dummy|test|todo|tbd|mpn\d*)(?:$|[-_.])",
    re.IGNORECASE,
)
_MPN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9,+./()_-]{1,79}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class ManufacturerCatalogError(ValueError):
    """Raised when catalog or evidence-admission input is invalid."""


def _category(value: str) -> str:
    normalized = str(value).strip().lower().replace(" ", "_")
    normalized = _CATEGORY_ALIASES.get(normalized, normalized)
    if normalized not in CANONICAL_CATEGORIES:
        raise ManufacturerCatalogError(f"Unknown manufacturer-model category: {value!r}.")
    return normalized


def _source(url: str, document: str, fields: Sequence[str]) -> dict[str, object]:
    return {
        "url": url,
        "accessed_on": ASSESSED_ON,
        "document": document,
        "fields": list(fields),
    }


def _row(
    *,
    ident: str,
    manufacturer: str,
    mpn: str,
    categories: Sequence[str],
    url: str,
    document: str,
    fields: Sequence[str] = ("exact manufacturer MPN", "device classification"),
    model_readiness: str = "catalog_only",
    model_download_url: str | None = None,
    required_backend: str = "not_selected",
    license_state: str = "model_terms_not_assessed",
    evidence_categories: Sequence[str] = ("identity", "classification"),
    limitations: str = "Catalog evidence only; no model payload has been acquired or qualified.",
) -> dict[str, object]:
    return {
        "schema": CATALOG_SCHEMA,
        "id": ident,
        "manufacturer": manufacturer,
        "mpn": mpn,
        "categories": list(categories),
        "source": _source(url, document, fields),
        "model_readiness": model_readiness,
        "model_download_url": model_download_url,
        "required_backend": required_backend,
        "license_state": license_state,
        "redistribution_approved": False,
        "runnable": False,
        "evidence_categories": list(evidence_categories),
        "limitations": limitations,
    }


def _simple_rows(
    *,
    manufacturer: str,
    prefix: str,
    categories: Sequence[str],
    parts: Sequence[tuple[str, str]],
    document: str,
    required_backend: str = "not_selected",
) -> list[dict[str, object]]:
    return [
        _row(
            ident=f"{prefix}.{re.sub(r'[^a-z0-9]+', '-', mpn.lower()).strip('-')}",
            manufacturer=manufacturer,
            mpn=mpn,
            categories=categories,
            url=url,
            document=document,
            required_backend=required_backend,
        )
        for mpn, url in parts
    ]


def _build_catalog() -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []

    # TI pages explicitly list these downloads and evaluation-item terms.
    ti_models = (
        ("LM358", "SNOM268", "LMx58_LM2904 PSpice Model Rev. C"),
        ("LM741", "SNOM211B", "LM741 PSpice Model Rev. B"),
        ("TL072", "SLOJ067", "TL072/TL072A/TL072B PSpice Model"),
        ("NE5532", None, "NE5532 product and design resources"),
        ("OPA197", "SBOMA34D", "OPAx197 PSpice Model Rev. D"),
        ("OPA2197", "SBOMA34D", "OPAx197 PSpice Model Rev. D"),
    )
    for mpn, model_id, document in ti_models:
        rows.append(_row(
            ident=f"ti.{mpn.lower()}", manufacturer="Texas Instruments", mpn=mpn,
            categories=("opamp",), url=f"https://www.ti.com/product/{mpn}",
            document=document,
            fields=("exact manufacturer MPN", "device classification", "manufacturer model listing"),
            model_readiness="manufacturer_download_unreviewed" if model_id else "manufacturer_model_page_unreviewed",
            model_download_url=f"https://www.ti.com/lit/zip/{model_id}" if model_id else None,
            required_backend="external_pspice_or_compatible_adapter.review_required",
            license_state="ti_evaluation_item_terms_review_required",
            evidence_categories=("identity", "classification", "model_listing", "terms_pointer"),
        ))

    adi_parts = (
        ("AD811", "https://www.analog.com/en/products/ad811.html"),
        ("ADA4522-1", "https://www.analog.com/en/products/ada4522-1.html"),
        ("ADA4522-2", "https://www.analog.com/en/products/ada4522-2.html"),
        ("ADA4522-4", "https://www.analog.com/en/products/ada4522-4.html"),
        ("OP07", "https://www.analog.com/en/products/op07.html"),
        ("OP27", "https://www.analog.com/en/products/op27.html"),
        ("AD8628", "https://www.analog.com/en/products/ad8628.html"),
        ("LT1012", "https://www.analog.com/en/products/lt1012.html"),
    )
    for mpn, url in adi_parts:
        direct = "https://www.analog.com/media/en/simulation-models/spice-models/ad811.cir" if mpn == "AD811" else None
        rows.append(_row(
            ident=f"adi.{mpn.lower()}", manufacturer="Analog Devices", mpn=mpn,
            categories=("opamp",), url=url,
            document=f"Analog Devices {mpn} product page and Tools & Simulations listing",
            fields=("exact manufacturer MPN", "device classification", "manufacturer model listing"),
            model_readiness="manufacturer_clickthrough_unreviewed" if direct else "manufacturer_model_page_unreviewed",
            model_download_url=direct,
            required_backend="external_ltspice_or_spice_adapter.review_required",
            license_state="adi_clickthrough_and_model_origin_review_required",
            evidence_categories=("identity", "classification", "model_listing", "license_terms" if direct else "terms_pointer"),
        ))

    rows.extend(_simple_rows(
        manufacturer="Nexperia", prefix="nexperia", categories=("bjt", "npn"),
        document="Nexperia product page and BJT portfolio documentation",
        required_backend="external_spice_adapter.review_required",
        parts=(
            ("BC847B,215", "https://www.nexperia.com/product/BC847B"),
            ("BC846B,215", "https://www.nexperia.com/product/BC846B"),
            ("BC817-40,215", "https://www.nexperia.com/product/BC817-40"),
            ("PMBT2222A,215", "https://www.nexperia.com/product/PMBT2222A"),
            ("MMBT3904,215", "https://www.nexperia.com/product/MMBT3904"),
        ),
    ))
    rows.extend(_simple_rows(
        manufacturer="STMicroelectronics", prefix="st", categories=("bjt", "npn"),
        document="STMicroelectronics transistor product page",
        required_backend="external_spice_adapter.review_required",
        parts=(
            ("2N2222A", "https://www.st.com/en/transistors/2n2222a.html"),
            ("BC547B", "https://www.st.com/en/transistors/bc547b.html"),
            ("BC337-40", "https://www.st.com/en/transistors/bc337-40.html"),
            ("MMBT2222A", "https://www.st.com/en/transistors/mmbt2222a.html"),
            ("TIP41C", "https://www.st.com/en/power-bipolar-transistors/tip41c.html"),
        ),
    ))
    rows.extend(_simple_rows(
        manufacturer="Nexperia", prefix="nexperia", categories=("bjt", "pnp"),
        document="Nexperia product page and BJT portfolio documentation",
        required_backend="external_spice_adapter.review_required",
        parts=(
            ("BC857B,215", "https://www.nexperia.com/product/BC857B"),
            ("BC856B,215", "https://www.nexperia.com/product/BC856B"),
            ("BC807-40,215", "https://www.nexperia.com/product/BC807-40"),
            ("PMBT2907A,215", "https://www.nexperia.com/product/PMBT2907A"),
            ("MMBT3906,215", "https://www.nexperia.com/product/MMBT3906"),
        ),
    ))
    rows.extend(_simple_rows(
        manufacturer="STMicroelectronics", prefix="st", categories=("bjt", "pnp"),
        document="STMicroelectronics transistor product page",
        required_backend="external_spice_adapter.review_required",
        parts=(
            ("2N2907A", "https://www.st.com/en/transistors/2n2907a.html"),
            ("BC557B", "https://www.st.com/en/transistors/bc557b.html"),
            ("BC327-40", "https://www.st.com/en/transistors/bc327-40.html"),
            ("MMBT2907A", "https://www.st.com/en/transistors/mmbt2907a.html"),
            ("TIP42C", "https://www.st.com/en/power-bipolar-transistors/tip42c.html"),
        ),
    ))

    rows.extend(_simple_rows(
        manufacturer="Nexperia", prefix="nexperia", categories=("mosfet", "nmos"),
        document="Nexperia MOSFET product page",
        required_backend="external_spice_adapter.review_required",
        parts=(
            ("2N7002,215", "https://www.nexperia.com/product/2N7002"),
            ("BSS138P,215", "https://www.nexperia.com/product/BSS138P"),
            ("PMV20XNE,215", "https://www.nexperia.com/product/PMV20XNE"),
            ("PSMN1R0-40YLD", "https://www.nexperia.com/product/PSMN1R0-40YLD"),
            ("BUK9Y12-40E", "https://www.nexperia.com/product/BUK9Y12-40E"),
        ),
    ))
    rows.extend(_simple_rows(
        manufacturer="Infineon Technologies", prefix="infineon", categories=("mosfet", "nmos"),
        document="Infineon MOSFET product page; model compatibility remains unreviewed",
        required_backend="external_simetrix_pspice_adapter.review_required",
        parts=(
            ("IRF540NPBF", "https://www.infineon.com/part/IRF540N"),
            ("IRLZ44NPBF", "https://www.infineon.com/part/IRLZ44N"),
            ("IPB017N10N5ATMA1", "https://www.infineon.com/part/IPB017N10N5"),
            ("BSC010N04LS6ATMA1", "https://www.infineon.com/part/BSC010N04LS6"),
            ("BSZ0902NSIATMA1", "https://www.infineon.com/part/BSZ0902NSI"),
        ),
    ))
    rows.extend(_simple_rows(
        manufacturer="STMicroelectronics", prefix="st", categories=("mosfet", "nmos"),
        document="STMicroelectronics power MOSFET product page",
        required_backend="external_pspice_adapter.review_required",
        parts=(
            ("STL110N10F7", "https://www.st.com/en/power-transistors/stl110n10f7.html"),
            ("STP55NF06", "https://www.st.com/en/power-transistors/stp55nf06.html"),
        ),
    ))
    rows.extend(_simple_rows(
        manufacturer="Nexperia", prefix="nexperia", categories=("mosfet", "pmos"),
        document="Nexperia P-channel MOSFET product page",
        required_backend="external_spice_adapter.review_required",
        parts=(
            ("BSS84P,215", "https://www.nexperia.com/product/BSS84P"),
            ("PMV65XP,215", "https://www.nexperia.com/product/PMV65XP"),
            ("PMV48XP,215", "https://www.nexperia.com/product/PMV48XP"),
            ("PMV30XP,215", "https://www.nexperia.com/product/PMV30XP"),
        ),
    ))
    rows.extend(_simple_rows(
        manufacturer="Infineon Technologies", prefix="infineon", categories=("mosfet", "pmos"),
        document="Infineon P-channel MOSFET product page",
        required_backend="external_simetrix_pspice_adapter.review_required",
        parts=(
            ("IRF9540NPBF", "https://www.infineon.com/part/IRF9540N"),
            ("IPD90P04P4L-04", "https://www.infineon.com/part/IPD90P04P4L-04"),
            ("BSP316PH6327XTSA1", "https://www.infineon.com/part/BSP316P"),
            ("BSP322PH6327XTSA1", "https://www.infineon.com/part/BSP322P"),
        ),
    ))

    nexperia_gan = (
        "GANB1R2-040QBA", "GANB4R8-040CBA", "GANB8R0-040CBA", "GANB012-040CBA",
        "GAN039-650NBB", "GAN039-650NTB", "GAN041-650WSB", "GAN063-650WSA",
        "GAN080-650EBE", "GAN111-650WSB", "GAN140-650EBE", "GAN140-650FBE",
        "GAN190-650EBE", "GAN190-650FBE",
    )
    for mpn in nexperia_gan:
        rows.append(_row(
            ident=f"nexperia.{mpn.lower()}", manufacturer="Nexperia", mpn=mpn,
            categories=("ganfet",),
            url="https://www.nexperia.com/products/gan-fets/high-voltage-gan-650-v",
            document="Nexperia 2025 Power GaN FET selection guide and product portfolio",
            fields=("exact manufacturer MPN", "GaN FET classification", "package and voltage family"),
            required_backend="external_spice_or_sparameter_backend.review_required",
        ))
    for mpn in ("IGLD65R055D2", "IGLT65R110D2"):
        rows.append(_row(
            ident=f"infineon.{mpn.lower()}", manufacturer="Infineon Technologies", mpn=mpn,
            categories=("ganfet",), url=f"https://www.infineon.com/part/{mpn}",
            document=f"Infineon {mpn} CoolGaN product page",
            fields=("exact manufacturer MPN", "GaN transistor classification", "manufacturer model access pointer"),
            model_readiness="manufacturer_model_page_unreviewed",
            required_backend="external_simetrix_spice_adapter.review_required",
            license_state="infineon_model_terms_review_required",
            evidence_categories=("identity", "classification", "model_listing", "terms_pointer"),
        ))
    for mpn in ("GNP1070TC-Z", "GNP1150TCA-Z"):
        rows.append(_row(
            ident=f"rohm.{mpn.lower()}", manufacturer="ROHM Semiconductor", mpn=mpn,
            categories=("ganfet",),
            url="https://www.rohm.com/news-detail?defaultGroupId=false&news-title=2023-05-08_news_gan",
            document="ROHM 650 V GaN HEMT mass-production announcement",
            fields=("exact manufacturer MPN", "GaN HEMT classification"),
            required_backend="external_spice_adapter.review_required",
        ))

    wolfspeed_sic = (
        "C3M0015065D", "C3M0015065K", "C3M0025065D", "C3M0025065J1",
        "C3M0025065K", "C3M0025065L", "C3M0045065D", "C3M0045065J1",
        "C3M0045065K", "C3M0045065L", "C3M0060065D", "C3M0060065K",
    )
    for mpn in wolfspeed_sic:
        rows.append(_row(
            ident=f"wolfspeed.{mpn.lower()}", manufacturer="Wolfspeed", mpn=mpn,
            categories=("sicfet",),
            url="https://assets.wolfspeed.com/uploads/2022/04/wolfspeed_power_line_card.pdf",
            document="Wolfspeed SiC Power Products Catalog",
            fields=("exact manufacturer MPN", "SiC MOSFET classification", "voltage/package family"),
            required_backend="external_spice_adapter.review_required",
        ))
    for mpn in ("SCT4018KR", "SCT4026DE", "SCT4045DE", "SCT4036KR"):
        rows.append(_row(
            ident=f"rohm.{mpn.lower()}", manufacturer="ROHM Semiconductor", mpn=mpn,
            categories=("sicfet",),
            url="https://www.rohm.com/products/sic-power-devices/sic-mosfet/information",
            document="ROHM SiC MOSFET product and simulation-model information",
            fields=("exact manufacturer MPN", "SiC MOSFET classification", "manufacturer model family"),
            model_readiness="manufacturer_model_page_unreviewed",
            required_backend="external_spice_psim_or_plecs_adapter.review_required",
            license_state="rohm_model_terms_review_required",
            evidence_categories=("identity", "classification", "model_listing", "terms_pointer"),
        ))

    rows.extend(_simple_rows(
        manufacturer="Qorvo", prefix="qorvo", categories=("mesfet",),
        document="Qorvo product page identifying GaAs MESFET technology",
        required_backend="rf_spice_or_sparameter_backend.review_required",
        parts=(
            ("FH101-G", "https://store.qorvo.com/products/detail/fh101g-qorvo/395632/"),
            ("NBB-400", "https://store.qorvo.com/datasheets/qorvo/NBB-400.pdf"),
        ),
    ))
    rows.extend(_simple_rows(
        manufacturer="MACOM", prefix="macom", categories=("mesfet",),
        document="MACOM product page identifying 0.5-micron GaAs MESFET process",
        required_backend="rf_spice_or_sparameter_backend.review_required",
        parts=(
            ("MAAM02350-A2", "https://www.macom.com/products/product-detail/MAAM02350-A2"),
            ("MAAM37000-A1", "https://www.macom.com/products/product-detail/MAAM37000-A1"),
        ),
    ))

    for mpn in ("BAR64-02V", "BAR64-03W", "BAR64-04W", "BAR64-05W", "BAR64-06W"):
        rows.append(_row(
            ident=f"infineon.{mpn.lower()}", manufacturer="Infineon Technologies", mpn=mpn,
            categories=("diode", "pin_diode"), url=f"https://www.infineon.com/part/{mpn}",
            document="Infineon RF PIN diode product page",
            fields=("exact manufacturer MPN", "PIN-diode classification", "manufacturer model pointer"),
            model_readiness="manufacturer_model_page_unreviewed",
            required_backend="external_spice_or_rf_backend.review_required",
            license_state="infineon_model_terms_review_required",
            evidence_categories=("identity", "classification", "model_listing", "terms_pointer"),
        ))
    rows.extend(_simple_rows(
        manufacturer="MACOM", prefix="macom", categories=("diode", "pin_diode"),
        document="MACOM PIN diode product page and simulation-model listing",
        required_backend="external_spice_or_rf_backend.review_required",
        parts=(
            ("MADP-000907-14020P", "https://www.macom.com/products/product-detail/MADP-000907-14020P"),
            ("MADP-009989-14320T", "https://www.macom.com/products/product-detail/MADP-009989"),
            ("MA4P7493-134", "https://www.macom.com/products/product-detail/MA4P7493-134"),
            ("MADP-007448-12790T", "https://www.macom.com/products/product-detail/MADP-007448-12790T"),
        ),
    ))

    rows.extend(_simple_rows(
        manufacturer="STMicroelectronics", prefix="st", categories=("diode",),
        document="STMicroelectronics diode product page",
        required_backend="external_pspice_adapter.review_required",
        parts=(
            ("1N4148", "https://www.st.com/en/diodes-and-rectifiers/1n4148.html"),
            ("1N4007", "https://www.st.com/en/diodes-and-rectifiers/1n4007.html"),
            ("1N5408", "https://www.st.com/en/diodes-and-rectifiers/1n5408.html"),
            ("UF4007", "https://www.st.com/en/diodes-and-rectifiers/uf4007.html"),
            ("STTH102", "https://www.st.com/en/diodes-and-rectifiers/stth102.html"),
            ("1N6640U", "https://www.st.com/en/space-products/1n6640u.html"),
        ),
    ))
    rows.extend(_simple_rows(
        manufacturer="Vishay", prefix="vishay", categories=("diode",),
        document="Vishay diode product documentation",
        required_backend="external_spice_adapter.review_required",
        parts=(
            ("1N4148-E3/54", "https://www.vishay.com/en/product/81857/"),
            ("1N4007-E3/54", "https://www.vishay.com/en/product/88503/"),
            ("UF4007-E3/54", "https://www.vishay.com/en/product/88755/"),
            ("ES1J-E3/61T", "https://www.vishay.com/en/product/88729/"),
        ),
    ))

    rows.extend(_simple_rows(
        manufacturer="STMicroelectronics", prefix="st", categories=("diode", "schottky"),
        document="STMicroelectronics Schottky diode product page and PSpice-family listing",
        required_backend="external_pspice_adapter.review_required",
        parts=(
            ("STPS0560Z", "https://www.st.com/en/diodes-and-rectifiers/stps0560z.html"),
            ("STPS2L60", "https://www.st.com/en/diodes-and-rectifiers/stps2l60.html"),
            ("STPS5L60", "https://www.st.com/en/diodes-and-rectifiers/stps5l60.html"),
            ("STPS10L60", "https://www.st.com/en/diodes-and-rectifiers/stps10l60.html"),
            ("BAT54", "https://www.st.com/en/diodes-and-rectifiers/bat54.html"),
        ),
    ))
    rows.extend(_simple_rows(
        manufacturer="Nexperia", prefix="nexperia", categories=("diode", "schottky"),
        document="Nexperia Schottky diode product page",
        required_backend="external_spice_adapter.review_required",
        parts=(
            ("BAT54,215", "https://www.nexperia.com/product/BAT54"),
            ("PMEG2010AEB,115", "https://www.nexperia.com/product/PMEG2010AEB"),
            ("PMEG4010CEJ,115", "https://www.nexperia.com/product/PMEG4010CEJ"),
            ("PMEG6010CEJ,115", "https://www.nexperia.com/product/PMEG6010CEJ"),
            ("PMEG120G20ELRX", "https://www.nexperia.com/product/PMEG120G20ELR"),
        ),
    ))

    for mpn in (
        "UC3842", "UC3843", "UC3844", "UC3845", "UC3842A", "UCC28C42",
        "UCC2800", "TL494", "SG3525A", "LM5030", "UCC28950", "UCC28740",
    ):
        rows.append(_row(
            ident=f"ti.{mpn.lower()}", manufacturer="Texas Instruments", mpn=mpn,
            categories=("controller", "pwm"), url=f"https://www.ti.com/product/{mpn}",
            document=f"TI {mpn} PWM controller product page",
            fields=("exact manufacturer MPN", "PWM-controller classification", "product status/features"),
            required_backend="external_pspice_or_behavioral_adapter.review_required",
            license_state="model_terms_not_assessed",
        ))

    return tuple(rows)


_CATALOG = _build_catalog()


def catalog() -> list[dict[str, object]]:
    """Return isolated catalog records; every row remains non-runnable."""
    return deepcopy(list(_CATALOG))


def search_catalog(
    query: str = "",
    *,
    manufacturer: str | None = None,
    category: str | None = None,
    model_readiness: str | None = None,
) -> list[dict[str, object]]:
    """Search catalog facts without changing eligibility or readiness."""
    terms = tuple(term.casefold() for term in str(query).split() if term)
    wanted_category = _category(category) if category is not None else None
    wanted_manufacturer = str(manufacturer).strip().casefold() if manufacturer else None
    if model_readiness is not None and model_readiness not in _MODEL_READY_STATES:
        raise ManufacturerCatalogError(f"Unknown model readiness: {model_readiness!r}.")
    matches = []
    for row in _CATALOG:
        if wanted_manufacturer and str(row["manufacturer"]).casefold() != wanted_manufacturer:
            continue
        if wanted_category and wanted_category not in row["categories"]:
            continue
        if model_readiness and row["model_readiness"] != model_readiness:
            continue
        haystack = " ".join((str(row["id"]), str(row["manufacturer"]), str(row["mpn"]), *row["categories"])).casefold()
        if all(term in haystack for term in terms):
            matches.append(deepcopy(row))
    return matches


def coverage_summary() -> dict[str, object]:
    """Return exact overlapping category counts and 100-record acquisition gaps."""
    counts = {
        category: sum(category in row["categories"] for row in _CATALOG)
        for category in CANONICAL_CATEGORIES
    }
    return {
        "schema": CATALOG_SCHEMA,
        "assessed_on": ASSESSED_ON,
        "unique_records": len(_CATALOG),
        "runnable_records": 0,
        "target_per_category": TARGET_PER_CATEGORY,
        "counts": counts,
        "shortfalls": {category: max(0, TARGET_PER_CATEGORY - count) for category, count in counts.items()},
        "targets_met": {category: count >= TARGET_PER_CATEGORY for category, count in counts.items()},
        "counting_note": (
            "Counts overlap by design: npn and pnp records are members of bjt; nmos and pmos "
            "are members of mosfet; pin_diode and schottky are members of diode."
        ),
    }


def validate_catalog(rows: Iterable[Mapping[str, object]] | None = None) -> dict[str, object]:
    """Validate provenance and fail-closed model-readiness invariants."""
    inspected = list(_CATALOG if rows is None else rows)
    issues: list[str] = []
    seen_ids: set[str] = set()
    seen_parts: set[tuple[str, str]] = set()
    for index, row in enumerate(inspected):
        label = f"row[{index}]"
        ident = str(row.get("id", ""))
        manufacturer = str(row.get("manufacturer", ""))
        mpn = str(row.get("mpn", ""))
        if not ident or ident in seen_ids:
            issues.append(f"{label}: missing or duplicate id {ident!r}")
        seen_ids.add(ident)
        part_key = (manufacturer.casefold(), mpn.casefold())
        if not mpn or _MPN_RE.fullmatch(mpn) is None or _PLACEHOLDER_MPN.search(mpn):
            issues.append(f"{label}: invalid or placeholder MPN {mpn!r}")
        if part_key in seen_parts:
            issues.append(f"{label}: duplicate manufacturer/MPN {manufacturer!r}/{mpn!r}")
        seen_parts.add(part_key)
        categories = row.get("categories")
        if not isinstance(categories, list) or not categories:
            issues.append(f"{label}: categories must be a non-empty list")
        else:
            for value in categories:
                if value not in CANONICAL_CATEGORIES:
                    issues.append(f"{label}: unknown category {value!r}")
        source = row.get("source")
        if not isinstance(source, Mapping):
            issues.append(f"{label}: source mapping is required")
        else:
            source_url = str(source.get("url", ""))
            parsed = urlparse(source_url)
            expected_hosts = _PRIMARY_HOSTS.get(manufacturer, ())
            if parsed.scheme != "https" or not parsed.hostname:
                issues.append(f"{label}: source URL must be HTTPS")
            elif expected_hosts and not any(parsed.hostname == host or parsed.hostname.endswith(f".{host}") for host in expected_hosts):
                issues.append(f"{label}: source host is not a primary {manufacturer} host")
            if source.get("accessed_on") != ASSESSED_ON:
                issues.append(f"{label}: source assessment date is missing or stale")
        if row.get("model_readiness") not in _MODEL_READY_STATES:
            issues.append(f"{label}: unknown model_readiness")
        if row.get("runnable") is not False:
            issues.append(f"{label}: catalog record must not be runnable")
        if row.get("redistribution_approved") is not False:
            issues.append(f"{label}: redistribution must remain unapproved")
        model_url = row.get("model_download_url")
        if model_url is not None:
            parsed_model = urlparse(str(model_url))
            if parsed_model.scheme != "https" or not parsed_model.hostname:
                issues.append(f"{label}: model download URL must be HTTPS")
            if row.get("model_readiness") not in {
                "manufacturer_download_unreviewed", "manufacturer_clickthrough_unreviewed"
            }:
                issues.append(f"{label}: download URL requires an unreviewed download readiness state")
    return {
        "valid": not issues,
        "record_count": len(inspected),
        "issues": issues,
        "schema": CATALOG_SCHEMA,
    }


def propose_user_model_admission(
    original_file: str | Path,
    *,
    manufacturer: str,
    mpn: str,
    categories: Sequence[str],
    license_evidence: Sequence[str],
) -> dict[str, object]:
    """Hash an original user file and create *unapproved* review evidence.

    The file is read only for hashing.  It is not copied, parsed, imported,
    loaded as a library, or executed.
    """
    if _MPN_RE.fullmatch(str(mpn)) is None or _PLACEHOLDER_MPN.search(str(mpn)):
        raise ManufacturerCatalogError("An exact, non-placeholder manufacturer MPN is required.")
    normalized_categories = tuple(dict.fromkeys(_category(item) for item in categories))
    if not normalized_categories:
        raise ManufacturerCatalogError("At least one canonical category is required.")
    evidence = tuple(str(item).strip() for item in license_evidence if str(item).strip())
    if not evidence:
        raise ManufacturerCatalogError("At least one license-evidence reference is required.")
    path = Path(original_file)
    if path.is_symlink():
        raise ManufacturerCatalogError("Symlink model evidence is not accepted.")
    if not path.is_file():
        raise ManufacturerCatalogError("Model evidence must name an existing regular file.")
    size = path.stat().st_size
    if size > MAX_EVIDENCE_FILE_BYTES:
        raise ManufacturerCatalogError(
            f"Model evidence exceeds the {MAX_EVIDENCE_FILE_BYTES}-byte hashing limit."
        )
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    result = {
        "schema": ADMISSION_SCHEMA,
        "state": "unapproved",
        "manufacturer": str(manufacturer).strip(),
        "mpn": str(mpn),
        "categories": list(normalized_categories),
        "original_path": str(path.resolve()),
        "original_size_bytes": size,
        "original_sha256": digest.hexdigest(),
        "license_evidence": list(evidence),
        "copied": False,
        "parsed": False,
        "imported": False,
        "executed": False,
        "runnable": False,
        "redistribution_approved": False,
        "required_reviews": [
            "manufacturer identity and exact MPN mapping",
            "license and redistribution rights",
            "model origin and content integrity",
            "pin mapping, dialect, backend compatibility, and behavior",
            "numerical and physical qualification for the intended envelope",
        ],
    }
    if _SHA256_RE.fullmatch(str(result["original_sha256"])) is None:
        raise AssertionError("Internal SHA-256 formatting failure.")
    return result


__all__ = [
    "ADMISSION_SCHEMA",
    "ASSESSED_ON",
    "CANONICAL_CATEGORIES",
    "CATALOG_SCHEMA",
    "ManufacturerCatalogError",
    "TARGET_PER_CATEGORY",
    "catalog",
    "coverage_summary",
    "propose_user_model_admission",
    "search_catalog",
    "validate_catalog",
]
