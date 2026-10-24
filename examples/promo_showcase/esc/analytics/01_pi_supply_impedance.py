# SPDX-License-Identifier: Apache-2.0
# SPIKE GUI Python workspace template; explicit reduced model, experimental.
# Source: Benjamin Vedder BLDC Driver rev 4.12, commit f1c65014d0caab5d99d888fc3025377861ac6ae2.
# Board source and derived evidence retain the source project's license; see parent pack.
import spike
import json
import math

SOURCE_NETLIST_SHA256 = '29430295c416ac7a69e0639ea5902b8b89d232b5bc3d2727f2b3dd58bf995f68'
EXPECTED = {'C39': {'value': '10u,50V', 'pins': {'1': 'GND', '2': 'V_SUPPLY'}}, 'C43': {'value': '10u,50V', 'pins': {'2': 'GND', '1': 'V_SUPPLY'}}, 'C44': {'value': '10u,50V', 'pins': {'2': 'GND', '1': 'V_SUPPLY'}}, 'C49': {'value': '10u,50V', 'pins': {'2': 'GND', '1': 'V_SUPPLY'}}, 'C51': {'value': '15u, 100v', 'pins': {'1': 'GND', '2': 'V_SUPPLY'}}, 'C1': {'value': '10u,50V', 'pins': {'1': 'GND', '2': 'V_SUPPLY'}}, 'C37': {'value': '15u,100V', 'pins': {'1': 'GND', '2': 'V_SUPPLY'}}, 'C40': {'value': '10u,50V', 'pins': {'1': 'GND', '2': 'V_SUPPLY'}}, 'C9': {'value': '10u,50V', 'pins': {'1': 'GND', '2': 'V_SUPPLY'}}, 'C8': {'value': '10u,50V', 'pins': {'1': 'GND', '2': 'V_SUPPLY'}}}

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
# Actual parallel capacitor values from V_SUPPLY to GND. Ideal capacitors only.
# Supplied 20 mOhm + 100 nH source-return loop is an illustrative scenario,
# not extracted trace/package/cable values. AC current source = 1 A.
values = {ref: float(c["value"].split(",")[0].replace("u", ""))*1e-6 for ref,c in EXPECTED.items()}
elements = [part("ASSUMED_SOURCE_R", "resistor", "bus", "source_loop", .020),
            part("ASSUMED_SOURCE_L", "inductor", "source_loop", "0", 100e-9),
            {"id":"I_TEST", "type":"current_source", "positive_node":"0", "negative_node":"bus", "ac_magnitude":1.0}]
elements += [part(ref,"capacitor","bus","0",value) for ref,value in values.items()]
r = solve(request(elements, {"mode":"ac","start_hz":100,"stop_hz":1e6,"points":121,"scale":"log"}, "vesc412-supplied-pi"))
f = r["data"]["frequency_hz"]
z = r["data"]["node_voltage_v"]["bus"]["magnitude"]
assert all(math.isfinite(v) and v > 0 for v in z)
z_complex = r["data"]["node_voltage_v"]["bus"]
actual = [complex(a,b) for a,b in zip(z_complex["real"],z_complex["imaginary"])]
reference = [1/(1/(.020+1j*2*math.pi*v*100e-9)+1j*2*math.pi*v*sum(values.values())) for v in f]
max_pi_error = max(abs(a-b) for a,b in zip(actual,reference))
assert max_pi_error < 1e-10, max_pi_error
print("CHECK_MAX_PI_COMPLEX_ERROR_OHM="+str(max_pi_error))
spike.publish_plot("VESC4.12 PI: supplied reduced supply network", [math.log10(v) for v in f],
    [{"name":"Input impedance |Z|", "values":z}], x_label="log10 frequency", x_unit="log10(Hz)",
    y_label="Driving-point impedance", y_unit="ohm",
    provenance="Actual V_SUPPLY capacitors; assumed 20mOhm/100nH source; ideal C, no PCB extraction")
spike.publish_table("PI scenario scope", ["Item","Value"],
    [["Actual nominal parallel capacitance", str(sum(values.values())*1e6)+" uF"],
     ["Supplied source loop", "20 mOhm + 100 nH"],
     ["Limitations", "No ESR/ESL, DC bias derating, nonlinear inverter, geometry extraction or qualification"],
     ["Model status", r["model_status"]]], provenance="Explicit experimental linear MNA scenario")
print("Experimental reduced PI scenario; no whole-board PI or ESC control validation.")
