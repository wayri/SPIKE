#pragma once

#include <nlohmann/json.hpp>

#include <string>

namespace spike::wxui {

class DomainContracts final {
public:
    static nlohmann::json DesignMap(
        const nlohmann::json& assembly_designs,
        const nlohmann::json& active_design = nlohmann::json::object());
    static nlohmann::json SingleBoardAssembly(const nlohmann::json& design);
    static nlohmann::json SingleBoardDesigns(const nlohmann::json& design);
    static nlohmann::json MultiboardRequest(
        const nlohmann::json& assembly,
        const nlohmann::json& designs,
        const std::string& domain,
        const std::string& mode);
    static nlohmann::json ActiveBoardScope(
        const nlohmann::json& assembly,
        const std::string& active_design_id,
        const std::string& manifest_digest = {});
};

}  // namespace spike::wxui
