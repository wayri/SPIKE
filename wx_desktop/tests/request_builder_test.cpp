#include "spike_wx/request_builder.hpp"

#include <cassert>
#include <iostream>
#include <stdexcept>

int main() {
    using spike::wxui::AnalysisInputs;
    using spike::wxui::RequestBuilder;
    const nlohmann::json design = {{"contract", "spike/v1"}, {"name", "fixture"}};

    AnalysisInputs dc;
    dc.net = "VDD";
    const auto dc_request = RequestBuilder::BuildAnalysisRequest(design, dc, "dc-test");
    assert(dc_request.at("spec").at("mode") == "dc");
    assert(dc_request.at("spec").at("sources").at(0).at("voltage_v") == 3.3);

    AnalysisInputs ac = dc;
    ac.mode = "ac";
    const auto ac_request = RequestBuilder::BuildAnalysisRequest(design, ac, "ac-test");
    assert(ac_request.at("spec").at("frequency_points") == 101);

    AnalysisInputs transient = dc;
    transient.mode = "transient";
    const auto transient_request = RequestBuilder::BuildAnalysisRequest(design, transient, "tran-test");
    assert(transient_request.at("spec").at("transient").at("max_internal_steps") == 50000);

    bool rejected = false;
    try {
        ac.frequency_stop_hz = ac.frequency_start_hz;
        (void)RequestBuilder::BuildAnalysisRequest(design, ac, "bad-ac");
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    assert(rejected);
    std::cout << "SPIKE wx request-builder tests passed\n";
    return 0;
}
