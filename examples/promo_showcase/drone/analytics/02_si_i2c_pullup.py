# SPDX-License-Identifier: GPL-3.0-only
# IRIS board-derived reduced analysis, Eugene109/IRIS commit999dd2eb725d550889c1ffe2c09f8de0390d081b.
# Adaptation: selected source components/topology + explicitly supplied scenario parameters.
# https://github.com/Eugene109/IRIS ; retain upstream LICENSE and attribution.
import spike
import json
import math
import os
from pathlib import Path

SOURCE_SHA256 = {'ProPrj_IRIS.kicad_pcb': '0f512d8f9de9cc2f328a7323641e3e8188c000d35441cd24bae700187e290ee8', 'BOM.md': '8a6d2d3a9d0b75920f4a4221b2dc23f44d1b5e3676fbf73774a36c61d84630b9'}
EXPECTED = {'R11': {'value': '', 'pins': {'1': '3V3', '2': 'I2C1_SDA'}, 'nominal_value': '2.2kΩ', 'mpn': 'FRC0402J222 TS'}, 'R12': {'value': '', 'pins': {'1': '3V3', '2': 'I2C1_SCLK'}, 'nominal_value': '2.2kΩ', 'mpn': 'FRC0402J222 TS'}}

def bind(expected):
    board = spike.boards.get()
    design = board["design"]
    assert design.get("name") == "ProPrj_IRIS", "Select the imported pinned IRIS board first."
    inventory = {c["reference"]: c for c in spike.components.list(board_id=board["id"])}
    for ref, evidence in expected.items():
        c = inventory[ref]
        assert c["value"] == evidence["value"], (ref, "value differs from pinned netlist")
        assert set(c["nets"]) == set(evidence["pins"].values()), (ref, "connectivity differs")
    print("Bound selected board:", board["name"], board["design_id"])
    print("Source PCB and BOM SHA256:", SOURCE_SHA256)
    spike.publish_table("Actual source components", ["Reference", "Value", "Pin/net evidence"],
        [[ref, c["nominal_value"], json.dumps(c["pins"], sort_keys=True)] for ref,c in expected.items()],
        provenance="Pinned IRIS PCB connectivity + BOM nominal values; imported blank Value fields retained")
    return board

def solve(request):
    validation = spike.analysis.run("validate_native_mna", {"request": request})
    assert validation["valid"], validation
    result = spike.analysis.run("run_native_mna", {"request": request})
    assert result["status"] == "completed", result
    print("REQUEST_JSON=" + json.dumps(request, sort_keys=True))
    evidence_dir = os.environ.get("SPIKE_ANALYTICS_EVIDENCE_DIR")
    if evidence_dir:
        path = Path(evidence_dir) / (request["request_id"] + ".actual-result.json")
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("RESULT_FILE=" + str(path))
    print("RESULT_SUMMARY=" + json.dumps({"status":result["status"], "diagnostics":result["diagnostics"], "model_status":result["model_status"]}))
    return result

def request(elements, analysis, name):
    return {"contract": "spike/native-mna-request/v1", "request_id": name,
            "ground_node": "0", "elements": elements, "analysis": analysis}

def part(ref, kind, p, n, value):
    return {"id": ref, "type": kind, "positive_node": p, "negative_node": n,
            {"resistor":"resistance_ohm", "capacitor":"capacitance_f", "inductor":"inductance_h"}[kind]: value}

board = bind(EXPECTED)
# Actual I2C1 pullups R11 SDA / R12 SCLK, 2.2kOhm per source BOM.
# Supplied bus capacitance sensitivity (50/100/200pF), ideal input/no active driver.
# Ideal rail step is the release-equivalent first-order charging scenario only.
rows=[];series=[];max_error=0.0
for pf in [50,100,200]:
    c=pf*1e-12
    e=[{"id":"V_PULLUP","type":"voltage_source","positive_node":"rail","negative_node":"0",
        "waveform":{"type":"step","initial":0.0,"final":3.3,"delay_s":1e-6}},
       part("R11","resistor","rail","I2C1_SDA",2200.0),
       part("R12","resistor","rail","I2C1_SCLK",2200.0),
       part("ASSUMED_C_SDA","capacitor","I2C1_SDA","0",c),
       part("ASSUMED_C_SCLK","capacitor","I2C1_SCLK","0",c)]
    r=solve(request(e,{"mode":"transient","time_step_s":1e-9,"stop_time_s":4e-6},"iris-i2c-pullup-"+str(pf)+"pf"))
    t=r["data"]["time_s"];volts=r["data"]["node_voltage_v"]["I2C1_SDA"]
    ref=[3.3*(1-math.exp(-max(0,x-1e-6)/(2200*c))) for x in t]
    error=max(abs(a-b) for a,b in zip(volts,ref));assert error<.035,error
    max_error=max(error,max_error)
    assert max(abs(a-b) for a,b in zip(volts,r["data"]["node_voltage_v"]["I2C1_SCLK"]))<1e-11
    series.append({"name":str(pf)+" pF supplied bus C","values":volts})
    rows.append([pf,2200*c*1e9,math.log(.7/.3)*2200*c*1e9,error])
spike.publish_plot("IRIS actual I2C1 pullups: supplied bus-C charging sensitivity",[x*1e6 for x in t],series,
    x_label="Time",x_unit="us",y_label="Ideal SDA charging voltage",y_unit="V",
    provenance="Actual R11/R12=2.2k from BOM; actual I2C1 nets from PCB; supplied C and ideal step/no driver")
spike.publish_table("I2C1 analytical checks",["Supplied bus C","RC time constant","30-70% RC rise time","Max transient error"],rows,
    units=["pF","ns","ns","V"],provenance="First-order RC reference; no I2C compliance claim; fixed-step backward Euler")
spike.publish_table("IRIS sensing SI limits",["Scope","Detail"],
    [["Included","Actual R11/R12 and imported net identities; ideal linear RC charging"],
     ["Not modeled","MCU/sensor IO, bus contention, clock stretching, thresholds, firmware, crosstalk or geometry-based SI"],
     ["Model status",r["model_status"]]],provenance="Explicit experimental reduced scenario; source conversion warnings remain")
print("CHECK_MAX_RC_ERROR_V="+str(max_error))
