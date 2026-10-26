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
EXPECTED = {'C118': {'value': '', 'pins': {'1': '7.4V_BATTERY', '2': 'GND'}, 'nominal_value': '330uF', 'mpn': 'RVT16V330M6X8'}, 'C96': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '10uF', 'mpn': 'CL21B106KOQNNNE'}, 'C57': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '22uF', 'mpn': 'CL21A226MAYNNNE'}, 'C38': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '22uF', 'mpn': 'CL21A226MAYNNNE'}, 'C68': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '22uF', 'mpn': 'CL21A226MAYNNNE'}, 'C5': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '22uF', 'mpn': 'CL21A226MAYNNNE'}, 'C58': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '22uF', 'mpn': 'CL21A226MAYNNNE'}, 'C37': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '22uF', 'mpn': 'CL21A226MAYNNNE'}, 'C117': {'value': '', 'pins': {'1': '7.4V_BATTERY', '2': 'GND'}, 'nominal_value': '330uF', 'mpn': 'RVT16V330M6X8'}, 'C59': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '22uF', 'mpn': 'CL21A226MAYNNNE'}, 'C6': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '22uF', 'mpn': 'CL21A226MAYNNNE'}, 'C55': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '22uF', 'mpn': 'CL21A226MAYNNNE'}, 'C120': {'value': '', 'pins': {'1': '7.4V_BATTERY', '2': 'GND'}, 'nominal_value': '330uF', 'mpn': 'RVT16V330M6X8'}, 'C119': {'value': '', 'pins': {'1': '7.4V_BATTERY', '2': 'GND'}, 'nominal_value': '330uF', 'mpn': 'RVT16V330M6X8'}, 'C70': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '22uF', 'mpn': 'CL21A226MAYNNNE'}, 'C4': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '22uF', 'mpn': 'CL21A226MAYNNNE'}, 'C36': {'value': '', 'pins': {'1': 'GND', '2': '7.4V_BATTERY'}, 'nominal_value': '22uF', 'mpn': 'CL21A226MAYNNNE'}}

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
# Actual PCB battery-bus capacitor membership, nominal capacitance joined from BOM.md.
# Scenario source-loop R=30mOhm L=150nH; explicitly supplied, not geometry extracted.
values={ref:float(c["nominal_value"].replace("uF",""))*1e-6 for ref,c in EXPECTED.items()}
e=[part("ASSUMED_SOURCE_R","resistor","battery_bus","loop",.030),
   part("ASSUMED_SOURCE_L","inductor","loop","0",150e-9),
   {"id":"I_TEST","type":"current_source","positive_node":"0","negative_node":"battery_bus","ac_magnitude":1.0}]
e += [part(ref,"capacitor","battery_bus","0",value) for ref,value in values.items()]
r=solve(request(e,{"mode":"ac","start_hz":10,"stop_hz":1e6,"points":151,"scale":"log"},"iris-battery-bus-reduced-pi"))
f=r["data"]["frequency_hz"];v=r["data"]["node_voltage_v"]["battery_bus"]
actual=[complex(a,b) for a,b in zip(v["real"],v["imaginary"])]
reference=[1/(1/(.030+1j*2*math.pi*x*150e-9)+1j*2*math.pi*x*sum(values.values())) for x in f]
error=max(abs(a-b) for a,b in zip(actual,reference));assert error<1e-10,error
spike.publish_plot("IRIS battery bus: actual capacitors / supplied source loop",[math.log10(x) for x in f],
    [{"name":"Input impedance |Z|","values":v["magnitude"]}],x_label="log10 frequency",x_unit="log10(Hz)",y_label="Driving-point impedance",y_unit="ohm",
    provenance="Actual PCB net membership + BOM nominal C; assumed30mOhm/150nH; ideal capacitors")
spike.publish_table("IRIS reduced PI scope",["Metric","Value"],
    [["Nominal parallel capacitance uF",sum(values.values())*1e6],["Actual capacitor count",len(values)],
     ["Complex analytical error ohm",error],["Limitations","No ESR/ESL, bias derating, battery electrochemistry, ESC switching or field extraction"],
     ["Model status",r["model_status"]]],provenance="Imported EasyEDA-converted board has blank Value fields; BOM supplies actual nominal values")
print("CHECK_MAX_PI_ERROR_OHM="+str(error))
