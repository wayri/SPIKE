#pragma once

#include "spike_wx/request_builder.hpp"
#include "spike_wx/worker_client.hpp"

#include <wx/aui/aui.h>
#include <wx/frame.h>
#include <wx/timer.h>

#include <nlohmann/json.hpp>

#include <filesystem>
#include <memory>
#include <string>

class wxChoice;
class wxListCtrl;
class wxNotebook;
class wxPanel;
class wxSearchCtrl;
class wxSpinCtrl;
class wxSpinCtrlDouble;
class wxStaticText;
class wxTextCtrl;
class wxTreeCtrl;
class wxWebView;

namespace spike::wxui {

class VtkViewport;

class NativeFrame final : public wxFrame {
public:
    explicit NativeFrame(
        wxString worker_command,
        wxString worker_working_directory = {},
        std::filesystem::path resource_root = {},
        std::filesystem::path diagnostic_log = {});
    ~NativeFrame() override;

    void OpenPath(const wxString& path);

private:
    enum : int {
        IdOpenDesign = wxID_HIGHEST + 100,
        IdNewProject,
        IdOpenProject,
        IdSaveProject,
        IdValidateDesign,
        IdPreflight,
        IdRun,
        IdCancel,
        IdFit,
        IdView2d,
        IdView3d,
        IdToggleNavigator,
        IdToggleSetup,
        IdToggleOutput,
        IdShowIssues,
        IdShowConsole,
        IdShowReport,
        IdWorkerHealth,
        IdCapabilities,
        IdDependencies,
        IdBenchmarks,
        IdPdnReview,
        IdSiWorkspace,
        IdSiExecute,
        IdEmiPreflight,
        IdEmiScreen,
        IdThermalWorkspace,
        IdThermalExecute,
        IdAssemblyWorkspace,
        IdAssemblyCreate,
        IdAssemblyAdmit,
        IdAssemblyPlan,
        IdAssemblyExecute,
        IdAdvancedWorkspace,
        IdAdvancedExecute,
        IdAbout,
        IdExportReport,
        IdPrintReport,
        IdWorkerTimer,
    };

    void BuildMenus();
    void BuildWorkspace();
    wxWindow* BuildTopBar();
    wxWindow* BuildRibbon();
    wxWindow* BuildViewportPane();
    wxWindow* BuildScenePane();
    wxWindow* BuildSetupPane();
    wxWindow* BuildBottomPane();
    wxWindow* BuildDcPage(wxWindow* parent);
    wxWindow* BuildAcPage(wxWindow* parent);
    wxWindow* BuildTransientPage(wxWindow* parent);
    wxWindow* BuildMeshPage(wxWindow* parent);
    wxWindow* BuildSiPage(wxWindow* parent);
    wxWindow* BuildEmiPage(wxWindow* parent);
    wxWindow* BuildThermalPage(wxWindow* parent);
    wxWindow* BuildAssemblyPage(wxWindow* parent);
    wxWindow* BuildAdvancedPage(wxWindow* parent);

    void OnNewProject(wxCommandEvent& event);
    void OnOpenDesign(wxCommandEvent& event);
    void OnOpenProject(wxCommandEvent& event);
    void OnSaveProject(wxCommandEvent& event);
    void OnValidateDesign(wxCommandEvent& event);
    void OnPreflight(wxCommandEvent& event);
    void OnRun(wxCommandEvent& event);
    void OnCancel(wxCommandEvent& event);
    void OnFit(wxCommandEvent& event);
    void OnExportReport(wxCommandEvent& event);
    void OnPrintReport(wxCommandEvent& event);
    void OnWorkspaceCommand(wxCommandEvent& event);
    void OnWorkerCommand(wxCommandEvent& event);
    void OnDomainCommand(wxCommandEvent& event);
    void OnAdvancedExecute(wxCommandEvent& event);
    void OnAbout(wxCommandEvent& event);
    void OnWorkerTimer(wxTimerEvent& event);
    void OnClose(wxCloseEvent& event);

    void LoadDesignPath(const wxString& path);
    void OpenPendingPath();
    void BeginWorkerHandshake();
    void InstallCapabilities(const nlohmann::json& capabilities);
    void InstallDesign(const nlohmann::json& design);
    void RefreshAssemblyWorkspace(bool show_in_viewport = false);
    void RestoreNativeState(const nlohmann::json& canonical);
    nlohmann::json ParseJsonEditor(wxTextCtrl* editor, const wxString& label) const;
    nlohmann::json AssemblyDesignMap() const;
    void PopulateNets();
    void PopulateSceneTree();
    AnalysisInputs ReadInputs() const;
    nlohmann::json SetupJson() const;
    void SendAnalysis(bool preflight_only);
    void InstallResult(const nlohmann::json& result);
    void RefreshReport();
    void ShowOutputPage(std::size_t index);
    void ShowJsonInOutput(const wxString& title, const nlohmann::json& value, std::size_t page = 0);
    void SendSimpleWorkerRequest(const std::string& method, nlohmann::json params, const wxString& label);
    void SendDomainWorkerRequest(
        const std::string& method, nlohmann::json params, const wxString& label, bool install_result = false);
    void AppendLog(const wxString& message);
    void SetBusy(bool busy, const wxString& status);
    void ApplyTheme(wxWindow* root);
    void UpdateProjectBadge();
    std::filesystem::path PlotlyPath() const;

    wxAuiManager aui_;
    wxTimer worker_timer_;
    std::unique_ptr<WorkerClient> worker_;
    VtkViewport* viewport_{nullptr};
    wxNotebook* ribbon_{nullptr};
    wxNotebook* setup_notebook_{nullptr};
    wxNotebook* bottom_notebook_{nullptr};
    wxSearchCtrl* scene_search_{nullptr};
    wxTreeCtrl* scene_tree_{nullptr};
    wxStaticText* worker_badge_{nullptr};
    wxStaticText* project_badge_{nullptr};
    wxChoice* mode_choice_{nullptr};
    wxChoice* net_choice_{nullptr};
    wxChoice* result_field_choice_{nullptr};
    wxTextCtrl* return_net_{nullptr};
    wxSpinCtrlDouble* source_voltage_{nullptr};
    wxSpinCtrlDouble* load_current_{nullptr};
    wxSpinCtrlDouble* source_x_{nullptr};
    wxSpinCtrlDouble* source_y_{nullptr};
    wxSpinCtrlDouble* load_x_{nullptr};
    wxSpinCtrlDouble* load_y_{nullptr};
    wxSpinCtrlDouble* frequency_start_{nullptr};
    wxSpinCtrlDouble* frequency_stop_{nullptr};
    wxSpinCtrl* frequency_points_{nullptr};
    wxSpinCtrlDouble* transient_stop_{nullptr};
    wxSpinCtrlDouble* transient_step_{nullptr};
    wxSpinCtrl* transient_decimation_{nullptr};
    wxSpinCtrlDouble* mesh_target_{nullptr};
    wxSpinCtrlDouble* zone_cell_{nullptr};
    wxSpinCtrlDouble* max_drop_{nullptr};
    wxSpinCtrlDouble* max_density_{nullptr};
    wxChoice* si_operation_{nullptr};
    wxTextCtrl* si_request_{nullptr};
    wxChoice* thermal_operation_{nullptr};
    wxTextCtrl* thermal_request_{nullptr};
    wxStaticText* assembly_summary_{nullptr};
    wxChoice* assembly_workload_{nullptr};
    wxChoice* assembly_domain_{nullptr};
    wxChoice* assembly_mode_{nullptr};
    wxSpinCtrlDouble* assembly_memory_{nullptr};
    wxChoice* assembly_operation_{nullptr};
    wxTextCtrl* assembly_request_{nullptr};
    wxChoice* advanced_method_{nullptr};
    wxTextCtrl* advanced_params_{nullptr};
    wxTextCtrl* log_{nullptr};
    wxTextCtrl* issues_{nullptr};
    wxListCtrl* probes_{nullptr};
    wxTextCtrl* power_tree_{nullptr};
    wxWebView* report_view_{nullptr};
    wxTextCtrl* report_fallback_{nullptr};
    wxString project_path_;
    wxString source_path_;
    wxString pending_open_path_;
    nlohmann::json design_v1_;
    nlohmann::json design_v2_;
    nlohmann::json capabilities_;
    nlohmann::json validation_;
    nlohmann::json last_request_;
    nlohmann::json last_result_;
    nlohmann::json assembly_ir_;
    nlohmann::json assembly_designs_;
    nlohmann::json domain_results_;
    std::string report_html_;
    std::filesystem::path resource_root_;
    std::filesystem::path diagnostic_log_;
    bool busy_{false};
    bool closing_{false};
};

}  // namespace spike::wxui
