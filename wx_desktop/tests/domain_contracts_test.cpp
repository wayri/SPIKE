#include "spike_wx/domain_contracts.hpp"

#include <cassert>
#include <iostream>
#include <stdexcept>

int main() {
    using spike::wxui::DomainContracts;
    const nlohmann::json design = {
        {"contract", "spike/design-ir/v2"}, {"design_id", "main"}, {"name", "Main"},
        {"layers", nlohmann::json::array()}, {"tracks", nlohmann::json::array()}
    };
    const auto assembly = DomainContracts::SingleBoardAssembly(design);
    const auto index = DomainContracts::SingleBoardDesigns(design);
    const auto designs = DomainContracts::DesignMap(index, design);
    assert(assembly.at("boards").size() == 1);
    assert(designs.at("main").at("contract") == "spike/design-ir/v2");
    const auto plan = DomainContracts::MultiboardRequest(assembly, designs, "pi", "independent_board_batch");
    assert(plan.at("contract") == "spike/multiboard-analysis-request/v1");
    const auto scope = DomainContracts::ActiveBoardScope(assembly, "main", "digest");
    assert(scope.at("active_board_id") == "board-main");
    bool rejected = false;
    try {
        (void)DomainContracts::MultiboardRequest(assembly, designs, "thermal", "independent_board_batch");
    } catch (const std::invalid_argument&) { rejected = true; }
    assert(rejected);
    std::cout << "SPIKE wx domain-contract tests passed\n";
    return 0;
}
