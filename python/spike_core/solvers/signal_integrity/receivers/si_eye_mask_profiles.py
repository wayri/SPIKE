# SPDX-License-Identifier: Apache-2.0
"""Independently encoded numerical inner-opening criteria, not copied artwork."""

SOURCE = "https://www.usb.org/document-library/usb-20-specification"


def standard_eye_mask(profile_id: str) -> dict:
    rows = {
        "usb2.hs.template1.inner": ("USB 2.0 HS Template 1 inner opening", .075, .375, .625, .925, .300, "7.1.2.2, Figure 7-13"),
        "usb2.hs.template2.inner": ("USB 2.0 HS Template 2 inner opening", .125, .350, .650, .875, .175, "7.1.2.2, Figure 7-14"),
    }
    if not isinstance(profile_id,str) or profile_id not in rows:
        raise ValueError("Unknown standard eye-mask profile.")
    name, left, top_left, top_right, right, height, clause = rows[profile_id]
    polygon = [[left,0],[top_left,height],[top_right,height],[right,0],[top_right,-height],[top_left,-height]]
    return {"schema":"spike/si-eye-mask/v1", "id":profile_id, "name":name,
            "protocol":"USB", "revision":"USB 2.0 base specification (2000)",
            "source":{"locator":SOURCE,"clause":clause}, "voltage_unit":"V",
            "polygons":[polygon,[[x+1,y] for x,y in polygon]]}
