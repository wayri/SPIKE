#pragma once

#include <nlohmann/json.hpp>

#include <string>

namespace spike::wxui {

struct AnalysisInputs {
    std::string mode{"dc"};
    std::string solver_id{"auto"};
    std::string formulation{"auto"};
    std::string net;
    std::string return_net;
    double source_voltage_v{3.3};
    double load_current_a{1.0};
    double source_x_mm{0.0};
    double source_y_mm{0.0};
    double load_x_mm{1.0};
    double load_y_mm{1.0};
    double mesh_target_mm{1.0};
    double zone_cell_mm{1.0};
    double max_drop_mv{50.0};
    double max_density_a_mm2{10.0};
    double frequency_start_hz{1.0e4};
    double frequency_stop_hz{1.0e7};
    int frequency_points{101};
    double transient_stop_s{1.0e-3};
    double transient_step_s{1.0e-6};
    int transient_decimation{10};
};

class RequestBuilder final {
public:
    static nlohmann::json BuildAnalysisRequest(
        const nlohmann::json& design,
        const AnalysisInputs& inputs,
        const std::string& analysis_id);
};

}  // namespace spike::wxui

