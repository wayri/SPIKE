# SPDX-License-Identifier: Apache-2.0
"""Admit native CHT fields, independently check face balances, scale to SI."""
import math

from .native_cht import RESULT, kernel_arguments


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def _close(a, b, tolerance=1e-10):
    return abs(a-b) <= tolerance * max(1., abs(a), abs(b))


def _thermal_residual(theta, u, v, n, ratio, peclet, hot):
    """Independently sum outward Fourier and upwind enthalpy face fluxes."""
    rows, solid, largest = 3*n//2, n//4, 0.
    conductivity = lambda j: 1. if solid <= j < solid+n else ratio
    for j in range(rows):
        for i in range(n):
            p, terms, diagonal = j*n+i, [], 0.
            for ni, nj in ((i-1, j), (i+1, j), (i, j-1), (i, j+1)):
                if ni < 0 or ni >= n:
                    continue
                if nj < 0 or nj >= rows:
                    g = 2*ratio
                    terms.append(g*(theta[p]-(hot if nj < 0 else 0.)))
                    diagonal += g
                    continue
                a, b = conductivity(j), conductivity(nj)
                g = 2/(1/a+1/b)
                terms.append(g*(theta[p]-theta[nj*n+ni]))
                diagonal += g
                if solid <= j < solid+n and solid <= nj < solid+n:
                    jf = j-solid
                    normal_velocity = (u[jf*(n+1)+i+1] if ni > i else
                        -u[jf*(n+1)+i] if ni < i else
                        v[(jf+1)*n+i] if nj > j else -v[jf*n+i])
                    enthalpy_capacity = peclet*normal_velocity/n
                    upstream = theta[p] if enthalpy_capacity >= 0 else theta[nj*n+ni]
                    terms.append(enthalpy_capacity*upstream)
                    diagonal += max(enthalpy_capacity, 0.)
            largest = max(largest, abs(math.fsum(terms))/max(1., diagonal))
    return largest


def admit_native_cht_result(raw, s, scales):
    _require(isinstance(raw, dict), "Expected native object")
    echoed = ("n", "reynolds", "lid", "peclet", "solid_k_ratio", "hot_k", "cold_k",
              "max_flow_steps", "steady_tolerance", "thermal_tolerance", "max_thermal_iterations")
    arrays = ("theta", "u", "v", "pressure", "face_u", "face_v", "interface_bottom_theta",
              "interface_top_theta", "interface_bottom_flux", "interface_top_flux")
    scalars = ("flow_time", "flow_dt", "divergence_linf", "steady_rate_linf", "poisson_residual_linf",
               "thermal_residual_linf", "hot_flux", "cold_flux", "balance_raw", "balance_relative",
               "theta_min", "theta_max")
    _require(set(raw) == {"schema", "status", "rows", "flow_steps", "thermal_iterations",
                           *echoed, *arrays, *scalars}, "Unexpected native output fields")
    _require(raw["schema"] == "spike-native-cht-v1", "Wrong native schema")
    for key, expected in zip(echoed, kernel_arguments(s, scales)):
        _require(_number(raw[key]) and raw[key] == expected, f"Stale native {key}")
    n, rows = s["n"], 3*s["n"]//2
    _require(type(raw["n"]) is int and type(raw["rows"]) is int and raw["rows"] == rows,
             "Wrong grid identity")
    for key, maximum in (("flow_steps", s["max_flow_steps"]),
                          ("thermal_iterations", s["max_thermal_iterations"])):
        _require(type(raw[key]) is int and 0 <= raw[key] <= maximum, "Invalid iteration count")
    _require(raw["status"] in ("converged", "failed_to_converge"), "Unknown status")
    _require(all(_number(raw[k]) for k in scalars), "Nonfinite native diagnostics")
    for key in ("flow_time", "flow_dt", "divergence_linf", "steady_rate_linf", "poisson_residual_linf",
                "thermal_residual_linf", "balance_relative"):
        _require(raw[key] >= 0, "Negative native diagnostic")
    accepted = raw["status"] == "converged"
    lengths = (n*rows, n*n, n*n, n*n, n*(n+1), n*(n+1), n, n, n, n)
    for key, length in zip(arrays, lengths):
        values = raw[key]
        _require(isinstance(values, list) and len(values) == (length if accepted else 0)
                 and all(_number(v) for v in values), f"Invalid native {key}")
    result = {"contract": RESULT, "status": raw["status"], "model_status": "experimental",
        "production_qualified": False, "settings": s, "scales": scales,
        "diagnostics": {key: raw[key] for key in (*scalars, "flow_steps", "thermal_iterations")},
        "fields": None, "interfaces": None,
        "limitations": ["2D square cavity and two fixed solid slabs; no imported CAD",
            "Steady constant-property incompressible Newtonian laminar fluid, passive energy",
            "No buoyancy, viscous heat, turbulence, compressibility, phase change or radiation",
            "No transient thermal storage, deforming mesh, rotor, aeroelasticity or FSI",
            "Convergence of a discrete system is not continuum or measured validation",
            "Knowledgeable human numerical review required before release"]}
    if not accepted:
        return result
    _require(raw["flow_steps"] > 0 and raw["flow_dt"] > 0
             and raw["flow_time"] >= raw["flow_dt"], "Invalid accepted flow time")
    _require(raw["steady_rate_linf"] < s["steady_tolerance"]
             and raw["poisson_residual_linf"] <= 4e-9, "Unconverged flow")
    theta, u, v = raw["theta"], raw["face_u"], raw["face_v"]
    _require(min(theta) >= -1e-7 and max(theta) <= 1+1e-7, "Passive temperature bound failed")
    _require(_close(min(theta), raw["theta_min"]) and _close(max(theta), raw["theta_max"]),
             "Temperature extrema disagree")
    _require(all(u[j*(n+1)] == 0 and u[j*(n+1)+n] == 0 for j in range(n))
             and all(v[i] == 0 and v[n*n+i] == 0 for i in range(n)), "Closed wall flux violated")
    divergence = max(abs(u[j*(n+1)+i+1]-u[j*(n+1)+i]
                         +v[(j+1)*n+i]-v[j*n+i])*n for j in range(n) for i in range(n))
    _require(divergence <= 1e-7 and _close(divergence, raw["divergence_linf"]),
             "Returned MAC mass balance failed")
    for j in range(n):
        for i in range(n):
            _require(_close(raw["u"][j*n+i], (u[j*(n+1)+i]+u[j*(n+1)+i+1])/2)
                     and _close(raw["v"][j*n+i], (v[j*n+i]+v[(j+1)*n+i])/2),
                     "Cell velocity is not the returned MAC average")
    k = scales["solid_k_ratio"]
    delta = s["hot_temperature_k"]-s["cold_temperature_k"]
    # The equal-temperature branch has zero normalized temperature and flux.
    hot = math.fsum(2*k*((1 if delta else 0)-theta[i]) for i in range(n))
    cold = math.fsum(2*k*theta[(rows-1)*n+i] for i in range(n))
    _require(_close(hot, raw["hot_flux"], 1e-8) and _close(cold, raw["cold_flux"], 1e-8),
             "Boundary heat flux does not match the thermal field")
    raw_balance = hot-cold
    relative = abs(raw_balance)/max(abs(hot), abs(cold), 1e-30)
    _require(_close(raw_balance, raw["balance_raw"], 1e-8)
             and _close(relative, raw["balance_relative"], 1e-8), "Forged global heat balance")
    _require(relative <= s["thermal_tolerance"]*1.01
             and raw["thermal_residual_linf"] <= s["thermal_tolerance"], "Unconverged thermal balance")
    independent_residual = _thermal_residual(theta, u, v, n, k, scales["peclet"], 1. if delta else 0.)
    _require(independent_residual <= s["thermal_tolerance"]*1.01
             and _close(independent_residual, raw["thermal_residual_linf"]),
             "Returned thermal field fails independent local energy balance")
    result["diagnostics"]["independent_thermal_residual_linf"] = independent_residual
    for prefix, lower in (("bottom", n//4-1), ("top", n//4+n-1)):
        for i in range(n):
            a, b = theta[lower*n+i], theta[(lower+1)*n+i]
            expected_flux = 2*k/(k+1)*(a-b)
            expected_t = (k*a+b)/(k+1) if prefix == "bottom" else (a+k*b)/(k+1)
            _require(_close(expected_flux, raw[f"interface_{prefix}_flux"][i])
                     and _close(expected_t, raw[f"interface_{prefix}_theta"][i]),
                     "Interface flux or temperature does not match both materials")
    length, span, velocity, rho, kf = (s["length_m"], s["span_m"], scales["velocity_scale_m_s"],
                                      s["density_kg_m3"], s["fluid_conductivity_w_mk"])
    temperatures = [s["cold_temperature_k"]+delta*t for t in theta]
    result["fields"] = {"thermal": {"n": n, "rows": rows,
        "x_m": [(i+.5)*length/n for j in range(rows) for i in range(n)],
        "y_m": [(-.25+(j+.5)/n)*length for j in range(rows) for i in range(n)],
        "region": ["hot_solid" if j < n//4 else "fluid" if j < n//4+n else "cold_solid"
                   for j in range(rows) for i in range(n)], "temperature_k": temperatures},
        "fluid": {"u_m_s": [a*velocity for a in raw["u"]],
            "v_m_s": [a*velocity for a in raw["v"]],
            "gauge_pressure_pa": [a*rho*velocity**2 for a in raw["pressure"]]}}
    result["interfaces"] = {prefix: {"x_m": [(i+.5)*length/n for i in range(n)],
        "y_m": 0. if prefix == "bottom" else length, "face_area_m2": length*span/n,
        "temperature_k": [s["cold_temperature_k"]+delta*t for t in raw[f"interface_{prefix}_theta"]],
        "heat_flux_positive_y_w_m2": [q*kf*delta*n/length for q in raw[f"interface_{prefix}_flux"]]}
        for prefix in ("bottom", "top")}
    result["diagnostics"].update({"hot_input_w": hot*kf*delta*span,
        "cold_output_w": cold*kf*delta*span, "raw_energy_balance_w": raw_balance*kf*delta*span,
        "maximum_temperature_k": max(temperatures), "minimum_temperature_k": min(temperatures),
        "interface_heat_flow_w": {prefix: math.fsum(result["interfaces"][prefix][
            "heat_flux_positive_y_w_m2"])*length*span/n for prefix in ("bottom", "top")}})
    for field in (result["fields"]["fluid"], result["interfaces"]["bottom"], result["interfaces"]["top"]):
        for value in field.values():
            if isinstance(value, list):
                _require(all(_number(v) for v in value), "SI field overflow")
    _require(all(_number(v) for v in temperatures), "SI temperature overflow")
    return result
