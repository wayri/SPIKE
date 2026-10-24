# SPDX-License-Identifier: Apache-2.0
# SPIKE GUI Python workspace template; explicit reduced model, experimental.
# Source: Benjamin Vedder BLDC Driver rev 4.12, commit f1c65014d0caab5d99d888fc3025377861ac6ae2.
# Board source and derived evidence retain the source project's license; see parent pack.
import spike
import json
import math

SOURCE_NETLIST_SHA256 = '29430295c416ac7a69e0639ea5902b8b89d232b5bc3d2727f2b3dd58bf995f68'
EXPECTED = {'R23': {'value': '39k', 'pins': {'2': '/MCU/SENS1', '1': '/Mosfet driver/H3_VS'}}, 'R24': {'value': '2k2', 'pins': {'2': '/MCU/SENS1', '1': 'GND'}}, 'R26': {'value': '39k', 'pins': {'2': '/MCU/SENS2', '1': '/Mosfet driver/H2_VS'}}, 'R27': {'value': '2k2', 'pins': {'2': '/MCU/SENS2', '1': 'GND'}}, 'R32': {'value': '39k', 'pins': {'2': '/MCU/SENS3', '1': '/Mosfet driver/H1_VS'}}, 'R33': {'value': '2k2', 'pins': {'2': '/MCU/SENS3', '1': 'GND'}}}

def bind(expected):
    board = spike.boards.get()
    design = board["design"]
    assert design.get("name") == "BLDC_4", "Select the imported pinned BLDC_4 board first."
    inventory = {c["reference"]: c for c in spike.components.list(board_id=board["id"])}
    for ref, evidence in expected.items():
        c = inventory[ref]
        assert c["value"] == evidence["value"], (ref, "value differs from pinned netlist")
        assert set(c["nets"]) == set(evidence["pins"].values()), (ref, "connectivity differs")
    print("Bound selected board:", board["name"], board["design_id"])
    print("Source netlist SHA256:", SOURCE_NETLIST_SHA256)
    spike.publish_table("Actual source components", ["Reference", "Value", "Pin/net evidence"],
        [[ref, c["value"], json.dumps(c["pins"], sort_keys=True)] for ref,c in expected.items()],
        provenance="Pinned VESC4.12 netlist; selected board refs/values/net sets checked")
    return board

def solve(request):
    validation = spike.analysis.run("validate_native_mna", {"request": request})
    assert validation["valid"], validation
    result = spike.analysis.run("run_native_mna", {"request": request})
    assert result["status"] == "completed", result
    print("REQUEST_JSON=" + json.dumps(request, sort_keys=True))
    print("RESULT_JSON=" + json.dumps(result, sort_keys=True))
    return result

def request(elements, analysis, name):
    return {"contract": "spike/native-mna-request/v1", "request_id": name,
            "ground_node": "0", "elements": elements, "analysis": analysis}

def part(ref, kind, p, n, value):
    return {"id": ref, "type": kind, "positive_node": p, "negative_node": n,
            {"resistor":"resistance_ohm", "capacitor":"capacitance_f", "inductor":"inductance_h"}[kind]: value}

board = bind(EXPECTED)
# Three actual phase voltage dividers. Their ideal small-signal gain is flat.
# DC sweep is a hypothetical 0..50 V phase scenario, not a measured back-EMF waveform.
phase_volts=[0,5,10,15,20,25,30,35,40,45,50]
outputs={name:[] for name in ("SENS1","SENS2","SENS3")}
max_error=0.0
for voltage in phase_volts:
    elements=[]
    for index,(high,low) in enumerate((("R23","R24"),("R26","R27"),("R32","R33")),1):
        phase="phase"+str(index); sense="SENS"+str(index)
        elements += [{"id":"V_PHASE"+str(index),"type":"voltage_source","positive_node":phase,"negative_node":"0","dc_value":voltage},
                     part(high,"resistor",phase,sense,39000.0),part(low,"resistor",sense,"0",2200.0)]
    r=solve(request(elements,{"mode":"operating_point"},"vesc412-phase-dividers-"+str(voltage)))
    for name in outputs:
        value=r["data"]["node_voltage_v"][name];outputs[name].append(value)
        max_error=max(max_error,abs(value-voltage*2200/41200))
assert max_error<1e-11,max_error
spike.publish_plot("VESC4.12 phase-voltage sensing (back-EMF input path)",phase_volts,
    [{"name":name,"values":values} for name,values in outputs.items()],
    x_label="Supplied phase voltage",x_unit="V",y_label="Ideal sense voltage",y_unit="V",
    provenance="Actual 39k/2k2 divider topology; three curves coincide; hypothetical DC stimulus")
spike.publish_table("Phase sensing scope",["Metric","Value"],
    [["Divider gain V/V",2200/41200],["Max independent divider reference error V",max_error],
     ["Limitations","No motor back-EMF generation, commutation, ADC sampling/protection/loading or controller model"],
     ["Model status",r["model_status"]]],provenance="Six actual resistors checked against selected imported BLDC_4 design")
print("CHECK_MAX_DIVIDER_ERROR_V="+str(max_error))
