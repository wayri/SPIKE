#pragma once

#include <nlohmann/json.hpp>

#include <filesystem>
#include <string>

namespace spike::wxui {

class ReportWriter final {
public:
    static std::string LoadPlotlyRuntime(const std::filesystem::path& path);
    static std::string BuildHtml(
        std::string project_name,
        const nlohmann::json& design,
        const nlohmann::json& setup,
        const nlohmann::json& result,
        const std::string& plotly_runtime);
    static void WriteFile(const std::filesystem::path& path, const std::string& html);
};

}  // namespace spike::wxui

