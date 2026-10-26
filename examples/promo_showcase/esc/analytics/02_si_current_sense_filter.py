# SPDX-License-Identifier: Apache-2.0
# SPIKE GUI Python workspace template; explicit reduced model, experimental.
# Source: Benjamin Vedder BLDC Driver rev 4.12, commit f1c65014d0caab5d99d888fc3025377861ac6ae2.
# Board source and derived evidence retain the source project's license; see parent pack.
import spike
import json
import math

SOURCE_NETLIST_SHA256 = '29430295c416ac7a69e0639ea5902b8b89d232b5bc3d2727f2b3dd58bf995f68'
EXPECTED = {'R50': {'value': '100R', 'pins': {'1': '/Mosfet driver/SH2_A', '2': 'Net-(C36-Pad1)'}}, 'R51': {'value': '100R', 'pins': {'1': '/Mosfet driver/SH2_B', '2': 'Net-(C36-Pad2)'}}, 'C36': {'value': '2.2n', 'pins': {'2': 'Net-(C36-Pad2)', '1': 'Net-(C36-Pad1)'}}}

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
# Actual SH2 differential RC input filter to DRV8302. Amplifier is ideal open input.
# Opposing ideal sources supply a 1 V differential small-signal stimulus.
elements = [
    {"id":"V_POS", "type":"voltage_source", "positive_node":"sh2a", "negative_node":"0", "ac_magnitude":.5},
    {"id":"V_NEG", "type":"voltage_source", "positive_node":"0", "negative_node":"sh2b", "ac_magnitude":.5},
    part("R50","resistor","sh2a","amp_pos",100.0),
    part("R51","resistor","sh2b","amp_neg",100.0),
    part("C36","capacitor","amp_pos","amp_neg",2.2e-9)]
r = solve(request(elements,{"mode":"ac","start_hz":100,"stop_hz":1e7,"points":141,"scale":"log"},"vesc412-sh2-filter"))
f=r["data"]["frequency_hz"]; v=r["data"]["node_voltage_v"]
diff=[complex(a,b)-complex(c,d) for a,b,c,d in zip(v["amp_pos"]["real"],v["amp_pos"]["imaginary"],v["amp_neg"]["real"],v["amp_neg"]["imaginary"])]
# Independent analytical RC reference checks the actual executed linear circuit.
corner=1/(2*math.pi*(100+100)*2.2e-9)
errors=[abs(value-1/(1+1j*2*math.pi*freq*200*2.2e-9)) for freq,value in zip(f,diff)]
assert max(errors)<1e-10, max(errors)
spike.publish_plot("VESC4.12 SI: SH2 analog differential sense filter",[math.log10(v) for v in f],
    [{"name":"Differential gain", "values":[20*math.log10(abs(v)) for v in diff]}],
    x_label="log10 frequency",x_unit="log10(Hz)",y_label="Voltage transfer",y_unit="dB",
    provenance="Actual R50=100R, R51=100R, C36=2.2n; ideal stimulus and unloaded amplifier input")
spike.publish_plot("SH2 differential sense phase",[math.log10(v) for v in f],
    [{"name":"Differential phase", "values":[math.degrees(math.atan2(v.imag,v.real)) for v in diff]}],
    x_label="log10 frequency",x_unit="log10(Hz)",y_label="Phase",y_unit="deg",
    provenance="Executed native MNA; reduced analog RC network, not digital SI")
spike.publish_table("Current sensing evidence",["Metric","Value"],
    [["Analytical corner Hz",corner],["Max analytical complex error",max(errors)],
     ["Model scope","Analog input RC only; no shunt value, DRV8302 amplifier/ADC dynamics or EMI extraction"],
     ["Model status",r["model_status"]]],provenance="Existing linear MNA compared with independent first-order RC reference")
print("CHECK_MAX_COMPLEX_ERROR="+str(max(errors)))
