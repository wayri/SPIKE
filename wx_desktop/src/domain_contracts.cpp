#include "spike_wx/domain_contracts.hpp"

#include <stdexcept>

namespace spike::wxui {
namespace {

void RequireContract(const nlohmann::json& value, const char* contract, const char* label) {
    if (!value.is_object() || value.value("contract", "") != contract) {
        throw std::invalid_argument(std::string(label) + " must use " + contract);
    }
}

}  // namespace

nlohmann::json DomainContracts::DesignMap(
    const nlohmann::json& assembly_designs,
    const nlohmann::json& active_design) {
    nlohmann::json result = nlohmann::json::object();
    if (assembly_designs.is_object() && !assembly_designs.empty()) {
        RequireContract(assembly_designs, "spike/assembly-designs/v1", "Assembly design index");
        for (const auto& design : assembly_designs.value("designs", nlohmann::json::array())) {
            if (!design.is_object()) continue;
            const auto id = design.value("design_id", "");
            if (!id.empty()) result[id] = design;
        }
    }
    if (active_design.is_object() && active_design.value("contract", "") == "spike/design-ir/v2") {
        const auto id = active_design.value("design_id", "");
        if (!id.empty()) result[id] = active_design;
    }
    return result;
}

nlohmann::json DomainContracts::SingleBoardAssembly(const nlohmann::json& design) {
    RequireContract(design, "spike/design-ir/v2", "Active design");
    const auto design_id = design.value("design_id", "");
    if (design_id.empty()) throw std::invalid_argument("Active DesignIR has no design_id");
    return {
        {"contract", "spike/assembly-ir/v1"},
        {"assembly_id", "assembly-" + design_id},
        {"name", design.value("name", "Single-board assembly")},
        {"frame", {{"frame_id", "assembly"}}},
        {"boards", nlohmann::json::array({{
            {"id", "board-" + design_id}, {"name", design.value("name", "Board")}, {"design_id", design_id},
            {"frame", {{"frame_id", "frame-" + design_id}, {"parent_frame_id", "assembly"},
                {"transform", {1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0}}}}
        }})},
        {"harnesses", nlohmann::json::array()}, {"connector_mappings", nlohmann::json::array()},
        {"rigid_flex_links", nlohmann::json::array()}, {"parts", nlohmann::json::array()},
        {"materials", nlohmann::json::array()}, {"thermal_contacts", nlohmann::json::array()},
        {"electrical_bonds", nlohmann::json::array()}, {"extensions", nlohmann::json::object()},
        {"metadata", {{"created_by", "spike-wx"}, {"scope", "single_board"}}}
    };
}

nlohmann::json DomainContracts::SingleBoardDesigns(const nlohmann::json& design) {
    RequireContract(design, "spike/design-ir/v2", "Active design");
    const auto design_id = design.value("design_id", "");
    if (design_id.empty()) throw std::invalid_argument("Active DesignIR has no design_id");
    return {
        {"contract", "spike/assembly-designs/v1"},
        {"active_design_id", design_id},
        {"designs", nlohmann::json::array({design})}
    };
}

nlohmann::json DomainContracts::MultiboardRequest(
    const nlohmann::json& assembly,
    const nlohmann::json& designs,
    const std::string& domain,
    const std::string& mode) {
    RequireContract(assembly, "spike/assembly-ir/v1", "Assembly");
    if (!designs.is_object() || designs.empty()) throw std::invalid_argument("Retained assembly designs are required");
    if (domain != "pi" && domain != "si") throw std::invalid_argument("Multi-board domain must be pi or si");
    if (mode != "independent_board_batch" && mode != "coupled_harness_network") {
        throw std::invalid_argument("Multi-board mode is not supported");
    }
    return {
        {"contract", "spike/multiboard-analysis-request/v1"}, {"domain", domain}, {"mode", mode},
        {"assembly", assembly}, {"designs", designs}
    };
}

nlohmann::json DomainContracts::ActiveBoardScope(
    const nlohmann::json& assembly,
    const std::string& active_design_id,
    const std::string& manifest_digest) {
    RequireContract(assembly, "spike/assembly-ir/v1", "Assembly");
    if (active_design_id.empty()) throw std::invalid_argument("Active design identity is required");
    std::string board_id;
    std::size_t matches = 0;
    for (const auto& board : assembly.value("boards", nlohmann::json::array())) {
        if (board.value("design_id", "") == active_design_id) {
            board_id = board.value("id", "");
            ++matches;
        }
    }
    if (matches != 1 || board_id.empty()) {
        throw std::invalid_argument("Assembly-scoped analysis requires exactly one active board instance");
    }
    nlohmann::json result = {
        {"contract", "spike/assembly-analysis-scope/v1"}, {"mode", "active_board_only"},
        {"assembly", assembly}, {"active_board_id", board_id}, {"active_design_id", active_design_id}
    };
    if (!manifest_digest.empty()) result["project_manifest_digest"] = manifest_digest;
    return result;
}

}  // namespace spike::wxui
