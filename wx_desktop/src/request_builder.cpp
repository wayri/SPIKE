#include "spike_wx/request_builder.hpp"

#include <cmath>
#include <stdexcept>
#include <unordered_set>

namespace spike::wxui {
namespace {

void RequireFinitePositive(double value, const char* name) {
    if (!std::isfinite(value) || value <= 0.0) {
        throw std::invalid_argument(std::string(name) + " must be positive and finite");
    }
}

}  // namespace

nlohmann::json RequestBuilder::BuildAnalysisRequest(
    const nlohmann::json& design,
    const AnalysisInputs& inputs,
    const std::string& analysis_id) {
    if (!design.is_object() || design.value("contract", "") != "spike/v1") {
        throw std::invalid_argument("A spike/v1 design is required");
    }
    if (inputs.net.empty()) {
        throw std::invalid_argument("Select a power net before analysis");
    }
    if (inputs.mode != "dc" && inputs.mode != "ac" && inputs.mode != "transient") {
        throw std::invalid_argument("Analysis mode must be dc, ac, or transient");
    }
    RequireFinitePositive(inputs.source_voltage_v, "Source voltage");
    RequireFinitePositive(inputs.load_current_a, "Load current");
    RequireFinitePositive(inputs.mesh_target_mm, "Mesh target");
    RequireFinitePositive(inputs.zone_cell_mm, "Zone cell size");

    if (inputs.mode == "ac") {
        RequireFinitePositive(inputs.frequency_start_hz, "AC start frequency");
        if (!std::isfinite(inputs.frequency_stop_hz) ||
            inputs.frequency_stop_hz <= inputs.frequency_start_hz ||
            inputs.frequency_points < 2) {
            throw std::invalid_argument("AC stop frequency must exceed start frequency and use at least two points");
        }
    }
    if (inputs.mode == "transient") {
        RequireFinitePositive(inputs.transient_stop_s, "Transient stop time");
        RequireFinitePositive(inputs.transient_step_s, "Transient step");
        if (inputs.transient_step_s > inputs.transient_stop_s || inputs.transient_decimation < 1) {
            throw std::invalid_argument("Transient step/decimation is invalid");
        }
        if (std::ceil(inputs.transient_stop_s / inputs.transient_step_s) > 50000.0) {
            throw std::invalid_argument("Transient setup exceeds 50,000 internal steps");
        }
    }

    nlohmann::json required = nlohmann::json::array();
    if (inputs.mode == "dc") {
        required = {"dc_resistance", "tracks", "through_vias", "pads", "copper_zones"};
    } else if (inputs.mode == "ac") {
        required = {"frequency_dependent_impedance", "partial_inductance", "skin_effect"};
    } else {
        required = {"transient_waveforms", "geometry_transient", "voltage_drop", "current_density"};
    }

    nlohmann::json net_names = nlohmann::json::array({inputs.net});
    const bool explicit_return = !inputs.return_net.empty() && inputs.mode != "ac";
    if (explicit_return && inputs.return_net != inputs.net) {
        net_names.push_back(inputs.return_net);
        required.push_back("explicit_return_path");
    }

    nlohmann::json spec = {
        {"contract", "spike/v1"},
        {"analysis_id", analysis_id},
        {"mode", inputs.mode},
        {"solver_id", inputs.solver_id},
        {"formulation", inputs.formulation},
        {"required_capabilities", required},
        {"net_names", net_names},
        {"sources", nlohmann::json::array({{
            {"id", "wx-source-1"}, {"name", "Source 1"}, {"net", inputs.net},
            {"position_mm", {inputs.source_x_mm, inputs.source_y_mm}},
            {"layer_scope", "connected_conductor"}, {"voltage_v", inputs.source_voltage_v},
            {"terminal_role", "source_positive"}, {"domain_id", "main"}
        }})},
        {"loads", nlohmann::json::array({{
            {"id", "wx-load-1"}, {"name", "Load 1"}, {"net", inputs.net},
            {"position_mm", {inputs.load_x_mm, inputs.load_y_mm}},
            {"layer_scope", "connected_conductor"}, {"current_a", inputs.load_current_a},
            {"terminal_role", "load_positive"}, {"pair_id", "load-pair-1"}, {"domain_id", "main"}
        }})},
        {"return_path", {
            {"mode", explicit_return ? "explicit" : "implicit"},
            {"net", explicit_return ? inputs.return_net : ""},
            {"domain_id", "main"}, {"galvanically_isolated", false}
        }},
        {"probes", nlohmann::json::array()},
        {"frequency_start_hz", inputs.frequency_start_hz},
        {"frequency_stop_hz", inputs.frequency_stop_hz},
        {"frequency_points", inputs.frequency_points},
        {"transient", {
            {"stop_time_s", inputs.transient_stop_s}, {"time_step_s", inputs.transient_step_s},
            {"time_step_mode", "manual"}, {"output_decimation", inputs.transient_decimation},
            {"output_decimation_mode", "manual"}, {"playback_fps", 20},
            {"initial_condition", "operating_point"}, {"integration", "backward_euler"},
            {"max_internal_steps", 50000}, {"max_output_frames", 1000},
            {"max_solver_time_s", 120.0}, {"memory_budget_mb", 2048},
            {"capacitance_model", "auto"}, {"visual_sample_limit", 12000}
        }},
        {"mesh", {
            {"dimension", "surface_2_5d"}, {"target_size_mm", inputs.mesh_target_mm},
            {"zone_cell_mm", inputs.zone_cell_mm}, {"max_preview_cells", 25000},
            {"via_model", "extracted"}, {"via_plating_thickness_mm", 0.025}
        }},
        {"limits", {
            {"max_voltage_drop_mv", inputs.max_drop_mv},
            {"max_current_density_a_mm2", inputs.max_density_a_mm2}
        }},
        {"options", {{"client", "spike-wx"}}}
    };

    return {
        {"contract", "spike/analysis-request/v1"},
        {"design", design},
        {"spec", spec}
    };
}

}  // namespace spike::wxui

