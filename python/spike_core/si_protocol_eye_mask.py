# SPDX-License-Identifier: Apache-2.0
"""Bind explicit eye masks to retained protocol-lane NRZ polyline evidence."""
from math import isfinite
from .si_eye_mask import validate_eye_mask, evaluate_eye_mask
from .si_eye_mask_profiles import standard_eye_mask


def validate_lane_mask(lane, suite):
    if "eye_mask" in lane and "eye_mask_id" in lane:
        raise ValueError("Choose eye_mask or eye_mask_id, not both.")
    if "eye_mask_id" in lane:
        mask = standard_eye_mask(lane["eye_mask_id"])
        req = lane["channel_request"]
        if suite["family"] != "USB" or req.get("signaling") != "differential" or req.get("bit_rate_hz") != 480e6:
            raise ValueError("USB HS masks require USB family, differential signaling and explicit 480 Mb/s.")
    elif "eye_mask" in lane:
        mask = validate_eye_mask(lane["eye_mask"])
        if mask["protocol"] != suite["family"]:
            raise ValueError("Mask protocol must match the suite family.")
    else:
        if "eye_voltage_mapping" in lane:
            raise ValueError("Voltage mapping requires an assigned eye mask.")
        return
    validate_eye_mask(mask)
    mapping = lane.get("eye_voltage_mapping")
    if mask["voltage_unit"] == "V":
        if not isinstance(mapping, dict) or set(mapping) != {"scale_v","offset_v","bit_rate_hz"}:
            raise ValueError("Voltage masks need explicit scale_v, offset_v and bit_rate_hz.")
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) for v in mapping.values()):
            raise ValueError("Voltage mapping values must be finite numbers.")
        if mapping["scale_v"] <= 0 or mapping["bit_rate_hz"] <= 0 or mapping["bit_rate_hz"] != lane["channel_request"].get("bit_rate_hz"):
            raise ValueError("Voltage scale must be positive and mapping bit rate must match the channel.")
    elif mapping is not None:
        raise ValueError("Normalized masks do not accept a voltage mapping.")


def run_lane_mask(lane, channel_result):
    if not ("eye_mask" in lane or "eye_mask_id" in lane):
        return None
    mask = standard_eye_mask(lane["eye_mask_id"]) if "eye_mask_id" in lane else validate_eye_mask(lane["eye_mask"])
    eye = channel_result.get("eye") or {}
    if eye.get("contract") != "spike/si-nrz-eye/v1" or not eye.get("traces"):
        return {"status":"blocked", "reason":"Mask testing requires retained NRZ eye traces with explicit phases; PAM4 phase statistics are not waveform evidence.", "mask":mask}
    mapping = lane.get("eye_voltage_mapping")
    traces=[]
    for trace in eye["traces"]:
        phases=trace.get("phase_ui")
        values=trace.get("values")
        if not isinstance(phases,list) or not isinstance(values,list) or len(phases) != len(values):
            return {"status":"blocked", "reason":"Saved eye record lacks exact phase coordinates; rerun the channel.","mask":mask}
        traces.append([{"time_ui":t,"value":v*mapping["scale_v"]+mapping["offset_v"] if mapping else v} for t,v in zip(phases,values)])
    result=evaluate_eye_mask(mask,traces,mask["voltage_unit"],evidence={
        "voltage_mapping":mapping, "bit_rate_hz":eye.get("bit_rate_hz"),
        "scope":"retained display traces only; all generated bits are not tested",
        "eye_normalization":eye.get("normalization"),
    })
    result["mask"]=mask
    if "eye_mask_id" in lane:
        result["limitations"].append("USB inner opening only: transition-dependent outer voltage limits, test mode, fixture calibration and measurement bandwidth are not assessed.")
    return result
