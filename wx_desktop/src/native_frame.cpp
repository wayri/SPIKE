#include "spike_wx/native_frame.hpp"

#include "spike_wx/domain_contracts.hpp"
#include "spike_wx/report_writer.hpp"
#include "spike_wx/vtk_viewport.hpp"

#include <wx/artprov.h>
#include <wx/button.h>
#include <wx/choice.h>
#include <wx/control.h>
#include <wx/datetime.h>
#include <wx/dirdlg.h>
#include <wx/filedlg.h>
#include <wx/filename.h>
#include <wx/listctrl.h>
#include <wx/listbox.h>
#include <wx/msgdlg.h>
#include <wx/notebook.h>
#include <wx/panel.h>
#include <wx/scrolwin.h>
#include <wx/srchctrl.h>
#include <wx/sizer.h>
#include <wx/spinctrl.h>
#include <wx/statbox.h>
#include <wx/stattext.h>
#include <wx/stdpaths.h>
#include <wx/textctrl.h>
#include <wx/toolbar.h>
#include <wx/treectrl.h>
#include <wx/version.h>
#include <wx/webview.h>

#include <algorithm>
#include <cctype>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <initializer_list>
#include <stdexcept>
#include <utility>
#include <vector>

namespace spike::wxui {
namespace {

const wxColour ShellBackground(16, 24, 32);
const wxColour HeaderBackground(23, 35, 44);
const wxColour PanelBackground(20, 32, 41);
const wxColour ToolBackground(27, 42, 52);
const wxColour InputBackground(15, 25, 32);
const wxColour BorderColour(43, 59, 70);
const wxColour PrimaryText(217, 226, 234);
const wxColour SecondaryText(157, 176, 183);
const wxColour MutedText(119, 145, 157);
const wxColour Accent(240, 179, 75);

wxSpinCtrlDouble* Number(wxWindow* parent, double value, double minimum, double maximum, double increment, int digits = 4) {
    auto* control = new wxSpinCtrlDouble(parent, wxID_ANY);
    control->SetRange(minimum, maximum);
    control->SetIncrement(increment);
    control->SetDigits(digits);
    control->SetValue(value);
    return control;
}

void AddField(wxFlexGridSizer* grid, wxWindow* parent, const wxString& label, wxWindow* control) {
    grid->Add(new wxStaticText(parent, wxID_ANY, label), 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, 7);
    grid->Add(control, 1, wxEXPAND);
}

std::string AnalysisId(const std::string& mode) {
    const auto now = std::chrono::system_clock::now().time_since_epoch();
    return "wx-" + mode + "-" + std::to_string(std::chrono::duration_cast<std::chrono::milliseconds>(now).count());
}

bool Good(const nlohmann::json& response) {
    return response.is_object() && response.value("ok", false) && response.contains("result");
}

wxString ErrorMessage(const nlohmann::json& response, const wxString& fallback) {
    wxString message = wxString::FromUTF8(response.value("error", fallback.ToStdString()));
    const auto detail = response.value("error_detail", nlohmann::json::object());
    if (detail.is_object()) {
        const auto code = detail.value("code", response.value("error_code", ""));
        const auto diagnostic = detail.value("message", "");
        if (!diagnostic.empty()) message = wxString::FromUTF8(diagnostic);
        if (!code.empty()) message = wxString::FromUTF8(code) + ": " + message;
    }
    return message;
}

struct RibbonAction {
    int id;
    const char* label;
    const char* help;
};

struct RibbonGroup {
    const char* label;
    std::initializer_list<RibbonAction> actions;
};

wxPanel* MakeRibbonPage(wxNotebook* notebook, std::initializer_list<RibbonGroup> groups) {
    auto* page = new wxPanel(notebook);
    page->SetName("spike-ribbon-page");
    auto* row = new wxBoxSizer(wxHORIZONTAL);
    for (const auto& group : groups) {
        auto* box = new wxStaticBoxSizer(wxVERTICAL, page, group.label);
        auto* buttons = new wxBoxSizer(wxHORIZONTAL);
        for (const auto& action : group.actions) {
            auto* button = new wxButton(box->GetStaticBox(), action.id, action.label, wxDefaultPosition, wxDefaultSize, wxBU_EXACTFIT);
            button->SetToolTip(action.help);
            button->SetMinSize(wxSize(70, 34));
            buttons->Add(button, 0, wxALL, 3);
        }
        box->Add(buttons, 0, wxALL, 2);
        row->Add(box, 0, wxEXPAND | wxALL, 4);
    }
    row->AddStretchSpacer();
    page->SetSizer(row);
    return page;
}

nlohmann::json DefaultThermalScenario() {
    return {
        {"contract", "spike/thermal/v1"}, {"scenario_id", "wx-native-default"},
        {"name", "Native compact board estimate"}, {"mode", "steady_state"},
        {"application_environment", "domestic"}, {"medium", "air"}, {"enclosure", "open"},
        {"convection", "natural"},
        {"bounding_volume_mm", {{"x", 220.0}, {"y", 140.0}, {"z", 40.0}}},
        {"ambient_temperature_c", 25.0}, {"gravity", "-Z"},
        {"heat_sources", nlohmann::json::array({{
            {"id", "board-load"}, {"power_w", 3.3}, {"position", {110.0, 70.0, 1.0}},
            {"theta_ja_c_per_w", 12.5}
        }})},
        {"mesh", {{"cell_size_mm", 2.0}, {"max_cells", 1000000}}},
        {"run", {{"end_time_s", 60.0}, {"write_interval_s", 1.0}, {"max_iterations", 2000}, {"residual_target", 1e-6}}},
        {"options", {{"radiation", false}, {"turbulence", "auto"}}}
    };
}

}  // namespace

NativeFrame::NativeFrame(
    wxString worker_command,
    wxString worker_working_directory,
    std::filesystem::path resource_root,
    std::filesystem::path diagnostic_log)
    : wxFrame(nullptr, wxID_ANY, "SPIKE - Electronic Systems Integrity Workbench [Native]", wxDefaultPosition, wxSize(1580, 960)),
      aui_(this), worker_timer_(this, IdWorkerTimer), resource_root_(std::move(resource_root)),
      diagnostic_log_(std::move(diagnostic_log)) {
    SetMinSize(wxSize(1100, 700));
    SetBackgroundColour(ShellBackground);
    SetForegroundColour(PrimaryText);
    BuildMenus();
    CreateStatusBar(3);
    const int status_widths[] = {-2, 180, 190};
    GetStatusBar()->SetStatusWidths(3, status_widths);
    BuildWorkspace();
    ApplyTheme(this);
    UpdateProjectBadge();
    viewport_->SetLogCallback([this](const wxString& message) { AppendLog("VTK: " + message); });
    for (const int id : {IdOpenDesign, IdOpenProject, IdSaveProject}) {
        if (id == IdOpenDesign) Bind(wxEVT_BUTTON, &NativeFrame::OnOpenDesign, this, id);
        else if (id == IdOpenProject) Bind(wxEVT_BUTTON, &NativeFrame::OnOpenProject, this, id);
        else Bind(wxEVT_BUTTON, &NativeFrame::OnSaveProject, this, id);
    }
    Bind(wxEVT_BUTTON, &NativeFrame::OnValidateDesign, this, IdValidateDesign);
    Bind(wxEVT_BUTTON, &NativeFrame::OnPreflight, this, IdPreflight);
    Bind(wxEVT_BUTTON, &NativeFrame::OnRun, this, IdRun);
    Bind(wxEVT_BUTTON, &NativeFrame::OnCancel, this, IdCancel);
    Bind(wxEVT_BUTTON, &NativeFrame::OnFit, this, IdFit);
    Bind(wxEVT_BUTTON, &NativeFrame::OnExportReport, this, IdExportReport);
    Bind(wxEVT_BUTTON, &NativeFrame::OnPrintReport, this, IdPrintReport);
    Bind(wxEVT_BUTTON, &NativeFrame::OnAbout, this, IdAbout);
    for (const int id : {IdView2d, IdView3d, IdToggleNavigator, IdToggleSetup, IdToggleOutput, IdShowIssues, IdShowConsole, IdShowReport, IdAdvancedWorkspace}) {
        Bind(wxEVT_BUTTON, &NativeFrame::OnWorkspaceCommand, this, id);
    }
    for (const int id : {IdWorkerHealth, IdCapabilities, IdDependencies, IdBenchmarks}) {
        Bind(wxEVT_BUTTON, &NativeFrame::OnWorkerCommand, this, id);
    }
    for (const int id : {IdPdnReview, IdSiWorkspace, IdSiExecute, IdEmiPreflight, IdEmiScreen,
             IdThermalWorkspace, IdThermalExecute, IdAssemblyWorkspace, IdAssemblyCreate,
             IdAssemblyAdmit, IdAssemblyPlan, IdAssemblyExecute}) {
        Bind(wxEVT_BUTTON, &NativeFrame::OnDomainCommand, this, id);
    }
    Bind(wxEVT_BUTTON, &NativeFrame::OnAdvancedExecute, this, IdAdvancedExecute);
    Bind(wxEVT_TIMER, &NativeFrame::OnWorkerTimer, this, IdWorkerTimer);
    Bind(wxEVT_CLOSE_WINDOW, &NativeFrame::OnClose, this);
    worker_ = std::make_unique<WorkerClient>(
        std::move(worker_command),
        [this](const wxString& line) { AppendLog(line); },
        std::move(worker_working_directory));
    if (!worker_->Start()) {
        SetStatusText("Worker unavailable — open Console for diagnostics", 0);
        if (worker_badge_) worker_badge_->SetLabel("Worker unavailable");
    }
    worker_timer_.Start(25);
    CallAfter([this] { BeginWorkerHandshake(); });
    Centre();
}

NativeFrame::~NativeFrame() {
    worker_timer_.Stop();
    worker_.reset();
    aui_.UnInit();
}

void NativeFrame::BuildMenus() {
    auto* file = new wxMenu();
    file->Append(IdNewProject, "New project\tCtrl+N");
    file->Append(IdOpenDesign, "Open design...\tCtrl+O");
    file->Append(IdOpenProject, "Open SPIKE project...");
    file->Append(IdSaveProject, "Save project as...\tCtrl+Shift+S");
    file->AppendSeparator();
    file->Append(IdExportReport, "Export self-contained HTML report...");
    file->Append(IdPrintReport, "Print / Save PDF...");
    file->AppendSeparator();
    file->Append(wxID_EXIT, "Exit");
    auto* edit = new wxMenu();
    edit->Append(wxID_UNDO, "Undo\tCtrl+Z");
    edit->Append(wxID_REDO, "Redo\tCtrl+Y");
    edit->Enable(wxID_UNDO, false);
    edit->Enable(wxID_REDO, false);
    auto* view = new wxMenu();
    view->Append(IdView3d, "3D board view");
    view->Append(IdView2d, "2D layout view");
    view->Append(IdFit, "Fit board to viewport\tF");
    view->AppendSeparator();
    view->AppendCheckItem(IdToggleNavigator, "Scene navigator")->Check(true);
    view->AppendCheckItem(IdToggleSetup, "Analysis setup")->Check(true);
    view->AppendCheckItem(IdToggleOutput, "Results and console")->Check(true);
    auto* analysis = new wxMenu();
    analysis->Append(IdValidateDesign, "Validate design");
    analysis->Append(IdPreflight, "Preflight and mesh preview\tF6");
    analysis->Append(IdRun, "Run analysis\tF5");
    analysis->Append(IdCancel, "Cancel active operation\tShift+F5");
    analysis->AppendSeparator();
    analysis->Append(IdPdnReview, "PDN target review");
    analysis->Append(IdSiWorkspace, "HF / SI workspace");
    analysis->Append(IdEmiPreflight, "EMI preflight");
    analysis->Append(IdThermalWorkspace, "Thermal workspace");
    analysis->AppendSeparator();
    analysis->Append(IdAssemblyWorkspace, "Single / multi-board workspace");
    auto* reports = new wxMenu();
    reports->Append(IdShowReport, "Engineering report preview");
    reports->Append(IdPrintReport, "Print or save PDF...");
    reports->Append(IdExportReport, "Export offline HTML...");
    auto* project = new wxMenu();
    project->Append(IdValidateDesign, "Validate design");
    project->Append(IdShowIssues, "Issues");
    project->Append(IdShowConsole, "Console");
    auto* tools = new wxMenu();
    tools->Append(IdWorkerHealth, "Worker health");
    tools->Append(IdCapabilities, "Capability matrix");
    tools->Append(IdDependencies, "Dependency status");
    tools->Append(IdBenchmarks, "Solver verification");
    tools->AppendSeparator();
    tools->Append(IdAdvancedWorkspace, "Advanced native workbench");
    auto* help = new wxMenu();
    help->Append(IdAbout, "About SPIKE Native");
    auto* bar = new wxMenuBar();
    bar->Append(file, "File");
    bar->Append(edit, "Edit");
    bar->Append(view, "View");
    bar->Append(analysis, "Analysis");
    bar->Append(reports, "Reports");
    bar->Append(project, "Project");
    bar->Append(tools, "Tools");
    bar->Append(help, "Help");
    SetMenuBar(bar);

    Bind(wxEVT_MENU, &NativeFrame::OnNewProject, this, IdNewProject);
    Bind(wxEVT_MENU, &NativeFrame::OnOpenDesign, this, IdOpenDesign);
    Bind(wxEVT_MENU, &NativeFrame::OnOpenProject, this, IdOpenProject);
    Bind(wxEVT_MENU, &NativeFrame::OnSaveProject, this, IdSaveProject);
    Bind(wxEVT_MENU, &NativeFrame::OnValidateDesign, this, IdValidateDesign);
    Bind(wxEVT_MENU, &NativeFrame::OnPreflight, this, IdPreflight);
    Bind(wxEVT_MENU, &NativeFrame::OnRun, this, IdRun);
    Bind(wxEVT_MENU, &NativeFrame::OnCancel, this, IdCancel);
    Bind(wxEVT_MENU, &NativeFrame::OnFit, this, IdFit);
    Bind(wxEVT_MENU, &NativeFrame::OnExportReport, this, IdExportReport);
    Bind(wxEVT_MENU, &NativeFrame::OnPrintReport, this, IdPrintReport);
    for (const int id : {IdView2d, IdView3d, IdToggleNavigator, IdToggleSetup, IdToggleOutput, IdShowIssues, IdShowConsole, IdShowReport, IdAdvancedWorkspace}) {
        Bind(wxEVT_MENU, &NativeFrame::OnWorkspaceCommand, this, id);
    }
    for (const int id : {IdWorkerHealth, IdCapabilities, IdDependencies, IdBenchmarks}) {
        Bind(wxEVT_MENU, &NativeFrame::OnWorkerCommand, this, id);
    }
    for (const int id : {IdPdnReview, IdSiWorkspace, IdSiExecute, IdEmiPreflight, IdEmiScreen,
             IdThermalWorkspace, IdThermalExecute, IdAssemblyWorkspace, IdAssemblyCreate,
             IdAssemblyAdmit, IdAssemblyPlan, IdAssemblyExecute}) {
        Bind(wxEVT_MENU, &NativeFrame::OnDomainCommand, this, id);
    }
    Bind(wxEVT_MENU, &NativeFrame::OnAbout, this, IdAbout);
    Bind(wxEVT_MENU, [this](wxCommandEvent&) { Close(); }, wxID_EXIT);
}

void NativeFrame::BuildWorkspace() {
    auto* art = aui_.GetArtProvider();
    art->SetColour(wxAUI_DOCKART_BACKGROUND_COLOUR, ShellBackground);
    art->SetColour(wxAUI_DOCKART_SASH_COLOUR, BorderColour);
    art->SetColour(wxAUI_DOCKART_ACTIVE_CAPTION_COLOUR, HeaderBackground);
    art->SetColour(wxAUI_DOCKART_ACTIVE_CAPTION_GRADIENT_COLOUR, HeaderBackground);
    art->SetColour(wxAUI_DOCKART_INACTIVE_CAPTION_COLOUR, PanelBackground);
    art->SetColour(wxAUI_DOCKART_INACTIVE_CAPTION_GRADIENT_COLOUR, PanelBackground);
    art->SetColour(wxAUI_DOCKART_ACTIVE_CAPTION_TEXT_COLOUR, Accent);
    art->SetColour(wxAUI_DOCKART_INACTIVE_CAPTION_TEXT_COLOUR, SecondaryText);
    art->SetColour(wxAUI_DOCKART_BORDER_COLOUR, BorderColour);
    art->SetMetric(wxAUI_DOCKART_CAPTION_SIZE, 28);
    art->SetMetric(wxAUI_DOCKART_SASH_SIZE, 4);

    aui_.AddPane(BuildTopBar(), wxAuiPaneInfo().Name("topbar").Top().Row(0).CaptionVisible(false).PaneBorder(false)
        .Gripper(false).Resizable(false).CloseButton(false).MinSize(-1, 50).BestSize(-1, 50));
    aui_.AddPane(BuildRibbon(), wxAuiPaneInfo().Name("ribbon").Top().Row(1).CaptionVisible(false).PaneBorder(false)
        .Gripper(false).Resizable(false).CloseButton(false).MinSize(-1, 116).BestSize(-1, 122));
    aui_.AddPane(BuildViewportPane(), wxAuiPaneInfo().Name("viewport").CenterPane().CaptionVisible(false).CloseButton(false));
    aui_.AddPane(BuildScenePane(), wxAuiPaneInfo().Name("project").Left().Caption("Scene Navigator").BestSize(285, -1).MinSize(230, 250));
    aui_.AddPane(BuildSetupPane(), wxAuiPaneInfo().Name("setup").Right().Caption("ANALYSIS SETUP").BestSize(420, -1).MinSize(340, 350));
    aui_.AddPane(BuildBottomPane(), wxAuiPaneInfo().Name("output").Bottom().Caption("RESULTS AND CONSOLE").BestSize(-1, 235).MinSize(400, 170));
    aui_.Update();
}

wxWindow* NativeFrame::BuildTopBar() {
    auto* panel = new wxPanel(this);
    panel->SetName("spike-topbar");
    auto* row = new wxBoxSizer(wxHORIZONTAL);
    auto* brand = new wxStaticText(panel, wxID_ANY, "SPIKE");
    brand->SetFont(wxFontInfo(15).Bold().FaceName("Segoe UI").Underlined(false));
    brand->SetForegroundColour(PrimaryText);
    row->Add(brand, 0, wxALIGN_CENTER_VERTICAL | wxLEFT, 18);
    auto* subtitle = new wxStaticText(panel, wxID_ANY, "ELECTRONIC SYSTEMS INTEGRITY WORKBENCH");
    subtitle->SetFont(wxFontInfo(8).FaceName("Segoe UI"));
    subtitle->SetForegroundColour(MutedText);
    row->Add(subtitle, 0, wxALIGN_CENTER_VERTICAL | wxLEFT, 10);
    auto* divider = new wxStaticText(panel, wxID_ANY, "|");
    divider->SetForegroundColour(BorderColour);
    row->Add(divider, 0, wxALIGN_CENTER_VERTICAL | wxLEFT | wxRIGHT, 20);
    auto* project_label = new wxStaticText(panel, wxID_ANY, "PROJECT");
    project_label->SetForegroundColour(MutedText);
    project_label->SetFont(wxFontInfo(8).Bold());
    row->Add(project_label, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, 8);
    project_badge_ = new wxStaticText(panel, wxID_ANY, "Untitled project");
    project_badge_->SetForegroundColour(PrimaryText);
    row->Add(project_badge_, 0, wxALIGN_CENTER_VERTICAL);
    row->AddStretchSpacer();
    auto* search = new wxSearchCtrl(panel, wxID_ANY, {}, wxDefaultPosition, wxSize(190, 30));
    search->SetName("spike-search");
    search->SetDescriptiveText("Search workspace   Ctrl K");
    search->Bind(wxEVT_TEXT, [this, search](wxCommandEvent&) {
        if (!scene_search_) return;
        scene_search_->SetValue(search->GetValue());
        PopulateSceneTree();
        auto& pane = aui_.GetPane("project");
        if (!pane.IsShown()) { pane.Show(true); aui_.Update(); }
    });
    row->Add(search, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, 10);
    auto* help = new wxButton(panel, IdAbout, "Help", wxDefaultPosition, wxSize(58, 30), wxBU_EXACTFIT);
    help->SetToolTip("About SPIKE Native and capability status");
    row->Add(help, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, 8);
    auto* avatar = new wxStaticText(panel, wxID_ANY, "YW", wxDefaultPosition, wxSize(30, 30), wxALIGN_CENTER_HORIZONTAL);
    avatar->SetBackgroundColour(Accent);
    avatar->SetForegroundColour(wxColour(19, 32, 40));
    avatar->SetFont(wxFontInfo(9).Bold());
    row->Add(avatar, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, 18);
    panel->SetSizer(row);
    return panel;
}

wxWindow* NativeFrame::BuildViewportPane() {
    auto* panel = new wxPanel(this);
    panel->SetName("spike-viewport-host");
    auto* layout = new wxBoxSizer(wxVERTICAL);
    auto* toolbar = new wxPanel(panel);
    toolbar->SetName("spike-viewport-toolbar");
    auto* row = new wxBoxSizer(wxHORIZONTAL);
    const auto add = [&](int id, const wxString& label, const wxString& tip) {
        auto* button = new wxButton(toolbar, id, label, wxDefaultPosition, wxDefaultSize, wxBU_EXACTFIT);
        button->SetMinSize(wxSize(54, 28));
        button->SetToolTip(tip);
        row->Add(button, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, 4);
    };
    add(IdView2d, "2D", "Top orthographic source-layout view");
    add(IdView3d, "3D", "Isometric VTK scene view");
    auto* separator = new wxStaticText(toolbar, wxID_ANY, "  |  ");
    separator->SetForegroundColour(BorderColour);
    row->Add(separator, 0, wxALIGN_CENTER_VERTICAL);
    add(IdToggleNavigator, "Navigator", "Show or hide the design hierarchy");
    add(IdToggleSetup, "Analysis", "Show or hide analysis setup");
    add(IdFit, "Fit", "Fit the complete active design");
    add(IdShowIssues, "Issues", "Open validation and capability diagnostics");
    add(IdShowReport, "Results", "Open engineering result and report views");
    auto* field_label = new wxStaticText(toolbar, wxID_ANY, "FIELD");
    field_label->SetForegroundColour(MutedText);
    field_label->SetFont(wxFontInfo(8).Bold());
    row->Add(field_label, 0, wxALIGN_CENTER_VERTICAL | wxLEFT | wxRIGHT, 8);
    result_field_choice_ = new wxChoice(toolbar, wxID_ANY, wxDefaultPosition, wxSize(145, 28));
    result_field_choice_->Append("Geometry");
    result_field_choice_->SetSelection(0);
    result_field_choice_->SetToolTip("Select a spatial scalar field from the active analysis result");
    result_field_choice_->Bind(wxEVT_CHOICE, [this](wxCommandEvent&) {
        if (!result_field_choice_ || result_field_choice_->GetSelection() <= 0 || last_result_.empty()) {
            viewport_->ClearResult();
            SetStatusText("Native design geometry displayed", 0);
            return;
        }
        const auto metric = result_field_choice_->GetStringSelection().ToStdString();
        viewport_->LoadResult(last_result_, metric);
        SetStatusText("Result field: " + wxString::FromUTF8(metric), 0);
    });
    row->Add(result_field_choice_, 0, wxALIGN_CENTER_VERTICAL);
    row->AddStretchSpacer();
    auto* context = new wxStaticText(toolbar, wxID_ANY, "BOARD VIEWPORT   |   SOURCE LAYOUT");
    context->SetForegroundColour(MutedText);
    context->SetFont(wxFontInfo(8).Bold());
    row->Add(context, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, 12);
    toolbar->SetSizer(row);
    layout->Add(toolbar, 0, wxEXPAND | wxLEFT | wxRIGHT, 8);
    viewport_ = new VtkViewport(panel);
    layout->Add(viewport_, 1, wxEXPAND);
    panel->SetSizer(layout);
    return panel;
}

wxWindow* NativeFrame::BuildRibbon() {
    ribbon_ = new wxNotebook(this, wxID_ANY, wxDefaultPosition, wxDefaultSize, wxNB_TOP | wxNB_NOPAGETHEME);
    ribbon_->AddPage(MakeRibbonPage(ribbon_, {
        {"PROJECT", {{IdOpenDesign, "Import", "Import KiCad or IPC-2581 through the canonical worker"}, {IdOpenProject, "Open", "Open a verified .spike v3 project"}, {IdSaveProject, "Save As", "Save a portable .spike v3 project"}}},
        {"DESIGN READINESS", {{IdValidateDesign, "Validate", "Validate the active DesignIR"}, {IdShowIssues, "Issues", "Open design and workflow diagnostics"}}},
        {"WORKSPACE", {{IdToggleNavigator, "Navigator", "Toggle the scene navigator"}, {IdToggleSetup, "Setup", "Toggle analysis setup"}, {IdFit, "Fit", "Fit the active board"}}}
    }), "Home");
    ribbon_->AddPage(MakeRibbonPage(ribbon_, {
        {"POWER ANALYSES", {{IdPreflight, "DC preflight", "Preflight DC with the current setup"}, {IdRun, "Run PI", "Run DC, AC, or transient PI"}, {IdCancel, "Stop", "Cancel by restarting the isolated worker"}}},
        {"REVIEW", {{IdPdnReview, "PDN target", "Review the latest AC result against a target"}, {IdShowReport, "PI report", "Generate the offline engineering report"}}}
    }), "PI");
    ribbon_->AddPage(MakeRibbonPage(ribbon_, {
        {"PROTOCOL WORKSPACES", {{IdSiWorkspace, "SI setup", "Open exact SI protocol and channel request workbench"}, {IdSiExecute, "Run request", "Execute the selected SI worker contract"}}},
        {"INTERCHANGE", {{IdCapabilities, "Solver matrix", "Inspect worker capabilities and solver state"}, {IdShowReport, "SI report", "Open the engineering report workspace"}}}
    }), "HF / SI");
    ribbon_->AddPage(MakeRibbonPage(ribbon_, {
        {"SCREENING", {{IdEmiPreflight, "Preflight", "Validate the current EMI domain"}, {IdEmiScreen, "Risk screen", "Run screening-only EMI ranking"}}},
        {"FULL-WAVE", {{IdCapabilities, "Engine gates", "Inspect full-wave solver availability"}}}
    }), "EMI");
    ribbon_->AddPage(MakeRibbonPage(ribbon_, {
        {"THERMAL", {{IdThermalWorkspace, "Setup", "Open compact and field thermal request workbench"}, {IdThermalExecute, "Run request", "Validate, estimate, plan, prepare, or run thermal work"}, {IdCapabilities, "OpenFOAM gate", "Inspect thermal solver availability"}}},
        {"OUTPUT", {{IdShowReport, "Report", "Open the report workspace"}}}
    }), "Thermal");
    ribbon_->AddPage(MakeRibbonPage(ribbon_, {
        {"ASSEMBLY", {{IdAssemblyWorkspace, "Workspace", "View retained board instances and harnesses"}, {IdAssemblyAdmit, "Resources", "Estimate assembly resource admission"}, {IdAssemblyPlan, "Plan PI / SI", "Plan independent or coupled-request multi-board work"}}},
        {"EXECUTION", {{IdAssemblyExecute, "Advanced", "Run independent SI batches or explicit harness-network preparation"}, {IdCapabilities, "Limits", "Inspect authoritative capability gates"}}}
    }), "Systems");
    ribbon_->AddPage(MakeRibbonPage(ribbon_, {
        {"MEASUREMENTS", {{IdShowIssues, "Issues", "Open diagnostics"}, {IdShowConsole, "Probe log", "Open console and protocol data"}}}
    }), "Probes");
    ribbon_->AddPage(MakeRibbonPage(ribbon_, {
        {"RESULT VIEWS", {{IdView3d, "3D fields", "Show the VTK result viewport"}, {IdView2d, "2D layout", "Use the top orthographic board view"}, {IdFit, "Fit", "Fit result geometry"}}},
        {"REVISION REVIEW", {{IdShowIssues, "Limits", "Open result and validation issues"}, {IdShowReport, "Report", "Open the engineering report"}}}
    }), "Results");
    ribbon_->AddPage(MakeRibbonPage(ribbon_, {
        {"REPORT", {{IdShowReport, "Preview", "Preview the offline engineering report"}, {IdPrintReport, "Print / PDF", "Print or save the report as PDF"}, {IdExportReport, "Export HTML", "Export a self-contained report"}}}
    }), "Reports");
    ribbon_->AddPage(MakeRibbonPage(ribbon_, {
        {"APPLICATION", {{IdWorkerHealth, "Worker", "Check worker health"}, {IdDependencies, "Dependencies", "Inspect runtime dependencies"}, {IdBenchmarks, "Verification", "Run bounded solver verification"}, {IdCapabilities, "Capabilities", "Inspect model status and validity"}}},
        {"EXPERT TOOLS", {{IdAdvancedWorkspace, "Workbench", "Open SPICE, solver, extension, topology, field, and layout worker contracts"}}}
    }), "Settings");
    return ribbon_;
}

wxWindow* NativeFrame::BuildScenePane() {
    auto* panel = new wxPanel(this);
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    scene_search_ = new wxSearchCtrl(panel, wxID_ANY);
    scene_search_->SetDescriptiveText("Search nets, layers, components...");
    sizer->Add(scene_search_, 0, wxEXPAND | wxALL, 8);
    scene_tree_ = new wxTreeCtrl(panel, wxID_ANY, wxDefaultPosition, wxDefaultSize,
        wxTR_HAS_BUTTONS | wxTR_LINES_AT_ROOT | wxTR_SINGLE | wxTR_HIDE_ROOT);
    sizer->Add(scene_tree_, 1, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 8);
    sizer->Add(new wxStaticText(panel, wxID_ANY, "Analysis mode"), 0, wxLEFT | wxRIGHT | wxTOP, 8);
    mode_choice_ = new wxChoice(panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, {"DC IR drop", "AC impedance", "Transient PI"});
    mode_choice_->SetSelection(0);
    sizer->Add(mode_choice_, 0, wxEXPAND | wxALL, 8);
    sizer->Add(new wxStaticText(panel, wxID_ANY, "Power net"), 0, wxLEFT | wxRIGHT, 8);
    net_choice_ = new wxChoice(panel, wxID_ANY);
    sizer->Add(net_choice_, 0, wxEXPAND | wxALL, 8);
    sizer->Add(new wxStaticText(panel, wxID_ANY, "Explicit return net (optional)"), 0, wxLEFT | wxRIGHT, 8);
    return_net_ = new wxTextCtrl(panel, wxID_ANY);
    sizer->Add(return_net_, 0, wxEXPAND | wxALL, 8);
    auto* hint = new wxStaticText(panel, wxID_ANY,
        "Open a KiCad or IPC-2581 design. The authoritative importer and solver run in the isolated SPIKE worker.");
    hint->Wrap(220);
    sizer->Add(hint, 0, wxEXPAND | wxALL, 8);
    worker_badge_ = new wxStaticText(panel, wxID_ANY, "Checking worker...");
    worker_badge_->SetFont(worker_badge_->GetFont().Bold());
    sizer->Add(worker_badge_, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 8);
    scene_search_->Bind(wxEVT_TEXT, [this](wxCommandEvent&) { PopulateSceneTree(); });
    scene_tree_->Bind(wxEVT_TREE_SEL_CHANGED, [this](wxTreeEvent& event) {
        const auto label = scene_tree_->GetItemText(event.GetItem());
        for (unsigned index = 0; index < net_choice_->GetCount(); ++index) {
            if (net_choice_->GetString(index) == label) {
                net_choice_->SetSelection(index);
                SetStatusText("Selected analysis net: " + label, 0);
                break;
            }
        }
    });
    panel->SetSizer(sizer);
    return panel;
}

wxWindow* NativeFrame::BuildSetupPane() {
    setup_notebook_ = new wxNotebook(this, wxID_ANY);
    setup_notebook_->AddPage(BuildDcPage(setup_notebook_), "Terminals / DC");
    setup_notebook_->AddPage(BuildAcPage(setup_notebook_), "AC");
    setup_notebook_->AddPage(BuildTransientPage(setup_notebook_), "Transient");
    setup_notebook_->AddPage(BuildMeshPage(setup_notebook_), "Mesh / limits");
    setup_notebook_->AddPage(BuildSiPage(setup_notebook_), "HF / SI");
    setup_notebook_->AddPage(BuildEmiPage(setup_notebook_), "EMI");
    setup_notebook_->AddPage(BuildThermalPage(setup_notebook_), "Thermal");
    setup_notebook_->AddPage(BuildAssemblyPage(setup_notebook_), "Assembly");
    setup_notebook_->AddPage(BuildAdvancedPage(setup_notebook_), "Advanced");
    return setup_notebook_;
}

wxWindow* NativeFrame::BuildDcPage(wxWindow* parent) {
    auto* panel = new wxPanel(parent);
    auto* grid = new wxFlexGridSizer(2, 8, 8);
    grid->AddGrowableCol(1);
    source_voltage_ = Number(panel, 3.3, 0.001, 100000.0, 0.1, 4);
    load_current_ = Number(panel, 1.0, 0.001, 100000.0, 0.1, 4);
    source_x_ = Number(panel, 0.0, -1e6, 1e6, 0.1, 4);
    source_y_ = Number(panel, 0.0, -1e6, 1e6, 0.1, 4);
    load_x_ = Number(panel, 1.0, -1e6, 1e6, 0.1, 4);
    load_y_ = Number(panel, 1.0, -1e6, 1e6, 0.1, 4);
    AddField(grid, panel, "Source voltage (V)", source_voltage_);
    AddField(grid, panel, "Load current (A)", load_current_);
    AddField(grid, panel, "Source X (mm)", source_x_);
    AddField(grid, panel, "Source Y (mm)", source_y_);
    AddField(grid, panel, "Load X (mm)", load_x_);
    AddField(grid, panel, "Load Y (mm)", load_y_);
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    sizer->Add(grid, 0, wxEXPAND | wxALL, 10);
    sizer->Add(new wxStaticText(panel, wxID_ANY,
        "Coordinates map onto the connected conductor. Pad picking and multi-terminal tables are the next vertical-slice increment."),
        0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    panel->SetSizer(sizer);
    return panel;
}

wxWindow* NativeFrame::BuildAcPage(wxWindow* parent) {
    auto* panel = new wxPanel(parent);
    auto* grid = new wxFlexGridSizer(2, 8, 8);
    grid->AddGrowableCol(1);
    frequency_start_ = Number(panel, 1.0e4, 1.0, 1.0e15, 1000.0, 2);
    frequency_stop_ = Number(panel, 1.0e7, 2.0, 1.0e15, 1000.0, 2);
    frequency_points_ = new wxSpinCtrl(panel, wxID_ANY);
    frequency_points_->SetRange(2, 100000);
    frequency_points_->SetValue(101);
    AddField(grid, panel, "Start frequency (Hz)", frequency_start_);
    AddField(grid, panel, "Stop frequency (Hz)", frequency_stop_);
    AddField(grid, panel, "Points", frequency_points_);
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    sizer->Add(grid, 0, wxEXPAND | wxALL, 10);
    panel->SetSizer(sizer);
    return panel;
}

wxWindow* NativeFrame::BuildTransientPage(wxWindow* parent) {
    auto* panel = new wxPanel(parent);
    auto* grid = new wxFlexGridSizer(2, 8, 8);
    grid->AddGrowableCol(1);
    transient_stop_ = Number(panel, 1.0e-3, 1.0e-12, 1.0e6, 1.0e-4, 9);
    transient_step_ = Number(panel, 1.0e-6, 1.0e-12, 1.0e6, 1.0e-7, 12);
    transient_decimation_ = new wxSpinCtrl(panel, wxID_ANY);
    transient_decimation_->SetRange(1, 50000);
    transient_decimation_->SetValue(10);
    AddField(grid, panel, "Stop time (s)", transient_stop_);
    AddField(grid, panel, "Integration step (s)", transient_step_);
    AddField(grid, panel, "Output decimation", transient_decimation_);
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    sizer->Add(grid, 0, wxEXPAND | wxALL, 10);
    panel->SetSizer(sizer);
    return panel;
}

wxWindow* NativeFrame::BuildMeshPage(wxWindow* parent) {
    auto* panel = new wxPanel(parent);
    auto* grid = new wxFlexGridSizer(2, 8, 8);
    grid->AddGrowableCol(1);
    mesh_target_ = Number(panel, 1.0, 0.0001, 10000.0, 0.1, 4);
    zone_cell_ = Number(panel, 1.0, 0.0001, 10000.0, 0.1, 4);
    max_drop_ = Number(panel, 50.0, 0.0, 1.0e9, 1.0, 3);
    max_density_ = Number(panel, 10.0, 0.0, 1.0e9, 0.5, 3);
    AddField(grid, panel, "Mesh target (mm)", mesh_target_);
    AddField(grid, panel, "Zone cell (mm)", zone_cell_);
    AddField(grid, panel, "Max drop (mV)", max_drop_);
    AddField(grid, panel, "Max density (A/mm2)", max_density_);
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    sizer->Add(grid, 0, wxEXPAND | wxALL, 10);
    panel->SetSizer(sizer);
    return panel;
}

wxWindow* NativeFrame::BuildSiPage(wxWindow* parent) {
    auto* panel = new wxPanel(parent);
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    auto* title = new wxStaticText(panel, wxID_ANY, "HF / Signal Integrity");
    title->SetFont(title->GetFont().Bold());
    sizer->Add(title, 0, wxALL, 10);
    auto* detail = new wxStaticText(panel, wxID_ANY,
        "SPIKE 0.2.5 exposes bounded geometry-derived uniform-channel analysis, imported Touchstone networks, NEXT/FEXT, TDR/TDT, and normalized NRZ eyes. Every result retains its model-status and validity gates.");
    detail->Wrap(310);
    sizer->Add(detail, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    si_operation_ = new wxChoice(panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, {
        "Validate protocol suite", "Plan protocol analysis", "Run uniform channel", "Run protocol test suite"
    });
    si_operation_->SetSelection(0);
    sizer->Add(si_operation_, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    sizer->Add(new wxStaticText(panel, wxID_ANY,
        "Exact request JSON (suite object for validation; params or request object for other operations)"),
        0, wxEXPAND | wxLEFT | wxRIGHT, 10);
    si_request_ = new wxTextCtrl(panel, wxID_ANY,
        "{\n  \"contract\": \"spike/si-protocol-suite/v1\"\n}", wxDefaultPosition, wxSize(-1, 210),
        wxTE_MULTILINE | wxTE_RICH2);
    si_request_->SetFont(wxFontInfo(8).Family(wxFONTFAMILY_TELETYPE));
    sizer->Add(si_request_, 1, wxEXPAND | wxALL, 10);
    auto* row = new wxBoxSizer(wxHORIZONTAL);
    row->Add(new wxButton(panel, IdSiWorkspace, "Capabilities"), 1, wxRIGHT, 5);
    row->Add(new wxButton(panel, IdSiExecute, "Execute selected"), 1, wxLEFT, 5);
    sizer->Add(row, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    panel->SetSizer(sizer);
    return panel;
}

wxWindow* NativeFrame::BuildEmiPage(wxWindow* parent) {
    auto* panel = new wxPanel(parent);
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    auto* title = new wxStaticText(panel, wxID_ANY, "EMI screening workflow");
    title->SetFont(title->GetFont().Bold());
    sizer->Add(title, 0, wxALL, 10);
    auto* detail = new wxStaticText(panel, wxID_ANY,
        "The selected analysis net becomes the candidate domain and the explicit return net becomes the return domain. Screening uses declared dV/dt, dI/dt, current, loop-area, and return-discontinuity metrics; it is not a compliance result.");
    detail->Wrap(310);
    sizer->Add(detail, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    sizer->Add(new wxButton(panel, IdEmiPreflight, "Validate EMI setup"), 0, wxEXPAND | wxLEFT | wxRIGHT | wxTOP, 10);
    sizer->Add(new wxButton(panel, IdEmiScreen, "Run screening-only ranking"), 0, wxEXPAND | wxALL, 10);
    panel->SetSizer(sizer);
    return panel;
}

wxWindow* NativeFrame::BuildThermalPage(wxWindow* parent) {
    auto* panel = new wxPanel(parent);
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    auto* title = new wxStaticText(panel, wxID_ANY, "Thermal and airflow");
    title->SetFont(title->GetFont().Bold());
    sizer->Add(title, 0, wxALL, 10);
    auto* detail = new wxStaticText(panel, wxID_ANY,
        "Validate a bounded natural-convection board enclosure before preparing OpenFOAM. CFD results remain solver- and mesh-dependent.");
    detail->Wrap(310);
    sizer->Add(detail, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    thermal_operation_ = new wxChoice(panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, {
        "Validate scenario", "Compact estimate", "Plan field job", "Prepare OpenFOAM case", "Run prepared case", "Capabilities"
    });
    thermal_operation_->SetSelection(0);
    sizer->Add(thermal_operation_, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    sizer->Add(new wxStaticText(panel, wxID_ANY,
        "Thermal scenario JSON; field planning and case execution also accept the exact worker params object."),
        0, wxEXPAND | wxLEFT | wxRIGHT, 10);
    thermal_request_ = new wxTextCtrl(panel, wxID_ANY, wxString::FromUTF8(DefaultThermalScenario().dump(2)),
        wxDefaultPosition, wxSize(-1, 230), wxTE_MULTILINE | wxTE_RICH2);
    thermal_request_->SetFont(wxFontInfo(8).Family(wxFONTFAMILY_TELETYPE));
    sizer->Add(thermal_request_, 1, wxEXPAND | wxALL, 10);
    auto* row = new wxBoxSizer(wxHORIZONTAL);
    row->Add(new wxButton(panel, IdThermalWorkspace, "Open setup"), 1, wxRIGHT, 5);
    row->Add(new wxButton(panel, IdThermalExecute, "Execute selected"), 1, wxLEFT, 5);
    sizer->Add(row, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    panel->SetSizer(sizer);
    return panel;
}

wxWindow* NativeFrame::BuildAssemblyPage(wxWindow* parent) {
    auto* panel = new wxPanel(parent);
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    auto* title = new wxStaticText(panel, wxID_ANY, "Single-board / multi-board system");
    title->SetFont(title->GetFont().Bold());
    sizer->Add(title, 0, wxALL, 10);
    assembly_summary_ = new wxStaticText(panel, wxID_ANY,
        "No AssemblyIR is loaded. Create a single-board assembly after importing a board, or open a .spike v3 assembly.");
    assembly_summary_->Wrap(310);
    sizer->Add(assembly_summary_, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    auto* grid = new wxFlexGridSizer(2, 7, 7);
    grid->AddGrowableCol(1);
    assembly_workload_ = new wxChoice(panel, wxID_ANY, wxDefaultPosition, wxDefaultSize,
        {"visualization", "pi_dc", "pi_ac", "thermal", "full_wave"});
    assembly_workload_->SetSelection(0);
    assembly_domain_ = new wxChoice(panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, {"pi", "si"});
    assembly_domain_->SetSelection(0);
    assembly_mode_ = new wxChoice(panel, wxID_ANY, wxDefaultPosition, wxDefaultSize,
        {"independent_board_batch", "coupled_harness_network"});
    assembly_mode_->SetSelection(0);
    assembly_memory_ = Number(panel, 8.0, 0.25, 4096.0, 0.25, 2);
    AddField(grid, panel, "Admission workload", assembly_workload_);
    AddField(grid, panel, "Plan domain", assembly_domain_);
    AddField(grid, panel, "Plan mode", assembly_mode_);
    AddField(grid, panel, "Memory limit (GiB)", assembly_memory_);
    sizer->Add(grid, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    auto* actions = new wxBoxSizer(wxHORIZONTAL);
    actions->Add(new wxButton(panel, IdAssemblyCreate, "Create / View"), 1, wxRIGHT, 3);
    actions->Add(new wxButton(panel, IdAssemblyAdmit, "Resources"), 1, wxLEFT | wxRIGHT, 3);
    actions->Add(new wxButton(panel, IdAssemblyPlan, "Plan"), 1, wxLEFT, 3);
    sizer->Add(actions, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    assembly_operation_ = new wxChoice(panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, {
        "Run independent SI batch", "Compile harness electrical network", "Bind coupled reduced network",
        "Validate active-board scope"
    });
    assembly_operation_->SetSelection(0);
    sizer->Add(assembly_operation_, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    assembly_request_ = new wxTextCtrl(panel, wxID_ANY,
        "{\n  \"contract\": \"spike/multiboard-si-independent-batch-request/v1\",\n  \"multiboard_request\": {},\n  \"jobs\": []\n}",
        wxDefaultPosition, wxSize(-1, 185), wxTE_MULTILINE | wxTE_RICH2);
    assembly_request_->SetFont(wxFontInfo(8).Family(wxFONTFAMILY_TELETYPE));
    sizer->Add(assembly_request_, 1, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    sizer->Add(new wxButton(panel, IdAssemblyExecute, "Execute exact advanced request"), 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    auto* gate = new wxStaticText(panel, wxID_ANY,
        "Independent board planning is supported. SI batches execute sequentially. Harness compilation and reduced-network binding are inspectable preparation only; coupled PI/SI solver execution remains blocked in 0.2.5.");
    gate->Wrap(310);
    sizer->Add(gate, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    panel->SetSizer(sizer);
    return panel;
}

wxWindow* NativeFrame::BuildAdvancedPage(wxWindow* parent) {
    auto* panel = new wxPanel(parent);
    auto* sizer = new wxBoxSizer(wxVERTICAL);
    auto* title = new wxStaticText(panel, wxID_ANY, "Advanced native workbench");
    title->SetFont(title->GetFont().Bold());
    title->SetForegroundColour(Accent);
    sizer->Add(title, 0, wxALL, 10);
    auto* detail = new wxStaticText(panel, wxID_ANY,
        "Direct access to the same versioned worker operations used by the Tauri workbenches. "
        "Design-aware operations automatically receive the active DesignIR unless an explicit design is supplied.");
    detail->Wrap(350);
    sizer->Add(detail, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    advanced_method_ = new wxChoice(panel, wxID_ANY, wxDefaultPosition, wxDefaultSize, {
        "list_solvers", "list_external_engines", "list_accelerators", "list_extensions", "list_importers",
        "capability_ledger", "solver_manager", "sparselizard_runtime_status", "thermal_capabilities",
        "converter_capabilities", "validate_spice_workspace", "compose_spice_workspace",
        "validate_native_mna", "run_native_mna", "compile_spice_workspace_native_mna",
        "run_spice_workspace_native_mna", "validate_field_circuit_cosimulation",
        "validate_topology_circuit", "bridge_topology_to_analysis_spec", "validate_pi_path",
        "extract_net_geometry", "extract_power_path", "pdn_optimize", "model_library",
        "prepare_sparselizard_case", "prepare_openems_case", "validate_layout_evaluation"
    });
    advanced_method_->SetSelection(0);
    sizer->Add(new wxStaticText(panel, wxID_ANY, "WORKER OPERATION"), 0, wxLEFT | wxRIGHT, 10);
    sizer->Add(advanced_method_, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    sizer->Add(new wxStaticText(panel, wxID_ANY, "PARAMETERS (JSON)"), 0, wxLEFT | wxRIGHT, 10);
    advanced_params_ = new wxTextCtrl(panel, wxID_ANY, "{}", wxDefaultPosition, wxSize(-1, 250),
        wxTE_MULTILINE | wxTE_RICH2);
    advanced_params_->SetFont(wxFontInfo(9).Family(wxFONTFAMILY_TELETYPE));
    sizer->Add(advanced_params_, 1, wxEXPAND | wxALL, 10);
    auto* execute = new wxButton(panel, IdAdvancedExecute, "Execute versioned worker operation");
    execute->SetMinSize(wxSize(-1, 36));
    sizer->Add(execute, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    auto* gate = new wxStaticText(panel, wxID_ANY,
        "Capability and model-status gates remain authoritative. This workspace exposes released contracts; it does not relabel experimental, preparation-only, or unavailable solvers as production-ready.");
    gate->Wrap(350);
    gate->SetForegroundColour(MutedText);
    sizer->Add(gate, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);
    advanced_method_->Bind(wxEVT_CHOICE, [this](wxCommandEvent&) {
        const auto method = advanced_method_->GetStringSelection();
        if (method == "validate_spice_workspace" || method == "compose_spice_workspace" ||
            method == "compile_spice_workspace_native_mna" || method == "run_spice_workspace_native_mna") {
            advanced_params_->SetValue("{\n  \"workspace\": {}\n}");
        } else if (method == "extract_net_geometry") {
            advanced_params_->SetValue("{\n  \"net_name\": \"\"\n}");
        } else if (method == "model_library") {
            advanced_params_->SetValue("{\n  \"query\": \"\",\n  \"limit\": 150\n}");
        } else if (method == "solver_manager") {
            advanced_params_->SetValue("{\n  \"refresh\": true\n}");
        } else {
            advanced_params_->SetValue("{}");
        }
    });
    panel->SetSizer(sizer);
    return panel;
}

wxWindow* NativeFrame::BuildBottomPane() {
    bottom_notebook_ = new wxNotebook(this, wxID_ANY);
    issues_ = new wxTextCtrl(bottom_notebook_, wxID_ANY,
        "No validation has been run.", wxDefaultPosition, wxDefaultSize,
        wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2);
    probes_ = new wxListCtrl(bottom_notebook_, wxID_ANY, wxDefaultPosition, wxDefaultSize, wxLC_REPORT | wxLC_SINGLE_SEL);
    probes_->InsertColumn(0, "Probe");
    probes_->InsertColumn(1, "Net");
    probes_->InsertColumn(2, "Measurement");
    probes_->InsertColumn(3, "Value");
    power_tree_ = new wxTextCtrl(bottom_notebook_, wxID_ANY,
        "Power-tree and topology data will appear when retained in the active project.", wxDefaultPosition, wxDefaultSize,
        wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2);
    log_ = new wxTextCtrl(bottom_notebook_, wxID_ANY, {}, wxDefaultPosition, wxDefaultSize,
        wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2);
    log_->SetFont(wxFontInfo(9).Family(wxFONTFAMILY_TELETYPE));
    wxWindow* report_page = nullptr;
    if (wxWebView::IsBackendAvailable(wxWebViewBackendEdge)) {
        report_view_ = wxWebView::New(bottom_notebook_, wxID_ANY, wxWebViewDefaultURLStr, wxDefaultPosition, wxDefaultSize, wxWebViewBackendEdge);
    }
    if (report_view_) {
        report_view_->SetPage("<html><body style='font:14px Segoe UI;padding:30px'><h2>Engineering report</h2><p>Open a design and run an analysis.</p></body></html>", "");
        report_page = report_view_;
    } else {
        report_fallback_ = new wxTextCtrl(bottom_notebook_, wxID_ANY,
            "The Microsoft Edge WebView2 runtime is unavailable. SPIKE Native will continue without an embedded preview; exported self-contained HTML reports remain available.",
            wxDefaultPosition, wxDefaultSize, wxTE_MULTILINE | wxTE_READONLY | wxTE_RICH2);
        report_page = report_fallback_;
    }
    bottom_notebook_->AddPage(issues_, "Issues");
    bottom_notebook_->AddPage(probes_, "Probe table");
    bottom_notebook_->AddPage(power_tree_, "Power tree");
    bottom_notebook_->AddPage(log_, "Console");
    bottom_notebook_->AddPage(report_page, "Report");
    return bottom_notebook_;
}

void NativeFrame::OpenPath(const wxString& path) {
    if (path.empty()) return;
    if (worker_ && worker_->IsBusy()) {
        pending_open_path_ = path;
        SetStatusText("Waiting for the SPIKE worker before opening " + wxFileName(path).GetFullName(), 0);
        return;
    }
    if (wxFileName(path).GetExt().CmpNoCase("spike") == 0) {
        if (busy_) return;
        SetBusy(true, "Verifying project package...");
        try {
            worker_->Send("read_project_package", {{"path", path.ToStdString()}}, [this, path](const nlohmann::json& response) {
                if (!Good(response)) { SetBusy(false, ErrorMessage(response, "Project open failed")); return; }
                const auto& opened = response["result"];
                const auto signature = opened.value("manifest_signature", nlohmann::json::object());
                if (signature.value("present", false) && !signature.value("verified", false)) {
                    SetBusy(false, "Signed project requires a configured native trust key");
                    ShowJsonInOutput("Unverified package signature", signature);
                    return;
                }
                project_path_ = path;
                const auto canonical = opened.value("canonical", nlohmann::json::object());
                design_v2_ = canonical.value("design_ir", nlohmann::json::object());
                assembly_ir_ = canonical.value("assembly_ir", nlohmann::json::object());
                assembly_designs_ = canonical.value("assembly_designs", nlohmann::json::object());
                RestoreNativeState(canonical);
                const auto projected = opened.value("project", nlohmann::json::object());
                InstallDesign(projected.value("design", nlohmann::json::object()));
                RefreshAssemblyWorkspace(!assembly_ir_.empty());
                const auto results = canonical.value("results", nlohmann::json::object());
                last_result_ = results.value("latest", nlohmann::json::object());
                if (last_result_.empty() && results.contains("runs") && results["runs"].is_array() && !results["runs"].empty()) {
                    const auto& latest = results["runs"].back();
                    last_result_ = latest.contains("result") && latest["result"].is_object() ? latest["result"] : latest;
                }
                if (!last_result_.empty()) InstallResult(last_result_);
                SetBusy(false, signature.value("present", false) ? "Verified signed project opened" : "Unsigned project opened");
            });
        } catch (const std::exception& error) {
            SetBusy(false, wxString::FromUTF8(error.what()));
        }
        return;
    }
    LoadDesignPath(path);
}

void NativeFrame::OpenPendingPath() {
    if (closing_ || pending_open_path_.empty() || (worker_ && worker_->IsBusy())) return;
    const auto path = pending_open_path_;
    pending_open_path_.clear();
    CallAfter([this, path] { OpenPath(path); });
}

void NativeFrame::OnNewProject(wxCommandEvent&) {
    if (busy_) return;
    project_path_.clear();
    source_path_.clear();
    design_v1_ = nlohmann::json::object();
    design_v2_ = nlohmann::json::object();
    assembly_ir_ = nlohmann::json::object();
    assembly_designs_ = nlohmann::json::object();
    domain_results_ = nlohmann::json::object();
    last_request_ = nlohmann::json::object();
    last_result_ = nlohmann::json::object();
    validation_ = nlohmann::json::object();
    report_html_.clear();
    net_choice_->Clear();
    scene_tree_->DeleteAllItems();
    issues_->SetValue("No validation has been run.");
    power_tree_->SetValue("Power-tree and topology data will appear when retained in the active project.");
    viewport_->LoadDesign({{"tracks", nlohmann::json::array()}, {"vias", nlohmann::json::array()}});
    RefreshAssemblyWorkspace();
    UpdateProjectBadge();
    SetStatusText("New SPIKE native project created", 0);
    SetStatusText("No design", 1);
}

void NativeFrame::BeginWorkerHandshake() {
    if (closing_ || !worker_ || !worker_->IsRunning() || worker_->IsBusy()) return;
    try {
        worker_->Send("health", nlohmann::json::object(), [this](const nlohmann::json& response) {
            if (closing_) return;
            if (!Good(response) || response["result"].value("status", "") != "ready") {
                const auto message = ErrorMessage(response, "Worker health check failed");
                SetStatusText(message, 0);
                if (worker_badge_) worker_badge_->SetLabel("Worker degraded");
                return;
            }
            const auto& health = response["result"];
            const auto version = health.value("worker_version", "unknown");
            SetStatusText("SPIKE worker " + wxString::FromUTF8(version) + " ready", 0);
            if (worker_badge_) worker_badge_->SetLabel("Worker " + wxString::FromUTF8(version) + " ready");
            AppendLog("Health: " + wxString::FromUTF8(health.dump()));
            try {
                worker_->Send("capabilities", nlohmann::json::object(), [this](const nlohmann::json& capability_response) {
                    if (closing_) return;
                    if (!Good(capability_response)) {
                        AppendLog(ErrorMessage(capability_response, "Capability discovery failed"));
                        OpenPendingPath();
                        return;
                    }
                    InstallCapabilities(capability_response["result"]);
                });
            } catch (const std::exception& error) {
                AppendLog("Capability discovery failed: " + wxString::FromUTF8(error.what()));
                OpenPendingPath();
            }
        });
    } catch (const std::exception& error) {
        AppendLog("Worker handshake failed: " + wxString::FromUTF8(error.what()));
    }
}

void NativeFrame::InstallCapabilities(const nlohmann::json& capabilities) {
    capabilities_ = capabilities;
    const auto analyses = capabilities_.value("analyses", nlohmann::json::object());
    const auto state = [&analyses](const char* key) {
        return analyses.value(key, nlohmann::json::object()).value("state", "unknown");
    };
    AppendLog(
        "Capabilities: DC=" + wxString::FromUTF8(state("dc"))
        + ", AC=" + wxString::FromUTF8(state("ac"))
        + ", transient=" + wxString::FromUTF8(state("transient"))
        + ", SI=" + wxString::FromUTF8(state("geometry_uniform_channel"))
        + ", EMI=" + wxString::FromUTF8(state("emi_emc"))
        + ", thermal=" + wxString::FromUTF8(state("thermal")));
    OpenPendingPath();
}

void NativeFrame::OnOpenDesign(wxCommandEvent&) {
    wxFileDialog dialog(this, "Open design", {}, {},
        "Supported designs (*.kicad_pcb;*.ipc2581)|*.kicad_pcb;*.ipc2581|KiCad PCB (*.kicad_pcb)|*.kicad_pcb|IPC-2581 (*.ipc2581)|*.ipc2581",
        wxFD_OPEN | wxFD_FILE_MUST_EXIST);
    if (dialog.ShowModal() == wxID_OK) OpenPath(dialog.GetPath());
}

void NativeFrame::LoadDesignPath(const wxString& path) {
    if (busy_) return;
    SetBusy(true, "Importing canonical design...");
    source_path_ = path;
    try {
        worker_->Send("import_design_v2", {{"path", path.ToStdString()}}, [this, path](const nlohmann::json& response) {
            if (!Good(response)) { SetBusy(false, ErrorMessage(response, "Design import failed")); return; }
            design_v2_ = response["result"].value("design", nlohmann::json::object());
            assembly_ir_ = nlohmann::json::object();
            assembly_designs_ = nlohmann::json::object();
            const auto report = response["result"].value("report", nlohmann::json::object());
            AppendLog(
                "Import completed: " + wxString::FromUTF8(report.value("status", "unknown"))
                + wxString::Format(", %zu warnings, %zu unsupported records",
                    report.value("warnings", nlohmann::json::array()).size(),
                    report.value("unsupported", nlohmann::json::array()).size()));
            try {
                worker_->Send("load_design", {{"path", path.ToStdString()}}, [this](const nlohmann::json& loaded) {
                    if (!Good(loaded)) { SetBusy(false, ErrorMessage(loaded, "Design projection failed")); return; }
                    try {
                        InstallDesign(loaded["result"]);
                        RefreshAssemblyWorkspace();
                        SetBusy(false, "Design imported");
                    } catch (const std::exception& error) {
                        SetBusy(false, "Design import could not be applied: " + wxString::FromUTF8(error.what()));
                        ShowOutputPage(3);
                    }
                });
            } catch (const std::exception& error) {
                SetBusy(false, wxString::FromUTF8(error.what()));
            }
        });
    } catch (const std::exception& error) {
        SetBusy(false, wxString::FromUTF8(error.what()));
    }
}

void NativeFrame::OnOpenProject(wxCommandEvent&) {
    if (busy_) return;
    wxFileDialog dialog(this, "Open SPIKE project", {}, {}, "SPIKE projects (*.spike)|*.spike", wxFD_OPEN | wxFD_FILE_MUST_EXIST);
    if (dialog.ShowModal() != wxID_OK) return;
    OpenPath(dialog.GetPath());
}

void NativeFrame::OnSaveProject(wxCommandEvent&) {
    if (busy_ || design_v2_.empty()) return;
    wxFileDialog dialog(this, "Save SPIKE project", {}, "native-port.spike", "SPIKE projects (*.spike)|*.spike",
        wxFD_SAVE | wxFD_OVERWRITE_PROMPT);
    if (dialog.ShowModal() != wxID_OK) return;
    const auto analysis_id = last_request_.value("spec", nlohmann::json::object()).value("analysis_id", "");
    const auto design_id = design_v2_.value("design_id", "");
    nlohmann::json analysis_runs = nlohmann::json::array();
    if (!last_request_.empty()) {
        analysis_runs.push_back({{"id", analysis_id}, {"design_id", design_id}, {"spec", last_request_.value("spec", nlohmann::json::object())}});
    }
    nlohmann::json result_runs = nlohmann::json::array();
    if (!last_result_.empty()) {
        result_runs.push_back({{"id", analysis_id.empty() ? last_result_.value("analysis_id", "wx-result") : analysis_id},
            {"design_id", design_id}, {"result", last_result_}});
    }
    nlohmann::json wx_state = {
        {"contract", "spike/wx-desktop-state/v3"}, {"setup", SetupJson()},
        {"worker_capabilities", capabilities_},
        {"domain_drafts", {
            {"si", si_request_ ? si_request_->GetValue().ToStdString() : "{}"},
            {"thermal", thermal_request_ ? thermal_request_->GetValue().ToStdString() : "{}"},
            {"assembly", assembly_request_ ? assembly_request_->GetValue().ToStdString() : "{}"}
        }},
        {"domain_selections", {
            {"si_operation", si_operation_ ? si_operation_->GetSelection() : 0},
            {"thermal_operation", thermal_operation_ ? thermal_operation_->GetSelection() : 0},
            {"assembly_workload", assembly_workload_ ? assembly_workload_->GetSelection() : 0},
            {"assembly_domain", assembly_domain_ ? assembly_domain_->GetSelection() : 0},
            {"assembly_mode", assembly_mode_ ? assembly_mode_->GetSelection() : 0},
            {"assembly_operation", assembly_operation_ ? assembly_operation_->GetSelection() : 0},
            {"assembly_memory_gb", assembly_memory_ ? assembly_memory_->GetValue() : 8.0}
        }},
        {"domain_results", domain_results_}
    };
    nlohmann::json snapshot = {
        {"project", {{"name", wxFileName(dialog.GetPath()).GetFullName().ToStdString()}}},
        {"design_ir", design_v2_},
        {"workspace", {
            {"contract", "spike/workspace-state/v1"}, {"viewMode", "3D"},
            {"docks", {{"leftOpen", aui_.GetPane("project").IsShown()}, {"rightOpen", aui_.GetPane("setup").IsShown()},
                {"bottomOpen", aui_.GetPane("output").IsShown()}, {"sidePanelsPinned", true}, {"bottomPinned", true},
                {"leftWidthPx", aui_.GetPane("project").rect.width}, {"rightWidthPx", aui_.GetPane("setup").rect.width},
                {"bottomHeightPx", aui_.GetPane("output").rect.height}, {"activeBottomDock", "Console"}}},
            {"viewports", {{"threeD", nullptr}, {"twoD", nullptr}}}
        }},
        {"analyses", {{"contract", "spike/analysis-index/v1"}, {"runs", analysis_runs}}},
        {"results", {{"contract", "spike/result-index/v1"}, {"runs", result_runs}}},
        {"reports", {{"contract", "spike/report-index/v1"}, {"reports", nlohmann::json::array()}}},
        {"audit", nlohmann::json::array({{{"event", "project_saved"}, {"source", "wx_desktop"}}})},
        {"extensions", {{"spike.wx_desktop", wx_state}}}
    };
    if (!assembly_ir_.empty()) snapshot["assembly_ir"] = assembly_ir_;
    if (!assembly_designs_.empty()) snapshot["assembly_designs"] = assembly_designs_;
    SetBusy(true, "Saving project package...");
    try {
        worker_->Send("write_project_package", {
            {"path", dialog.GetPath().ToStdString()}, {"snapshot", snapshot}, {"profile", "portable_project"},
            {"base_package_path", project_path_.ToStdString()}
        }, [this, path = dialog.GetPath()](const nlohmann::json& response) {
            if (!Good(response)) { SetBusy(false, ErrorMessage(response, "Project save failed")); return; }
            project_path_ = path;
            UpdateProjectBadge();
            SetBusy(false, "Project saved");
        });
    } catch (const std::exception& error) { SetBusy(false, wxString::FromUTF8(error.what())); }
}

void NativeFrame::OnValidateDesign(wxCommandEvent&) {
    if (busy_ || design_v1_.empty()) {
        SetStatusText("Import or open a design before validation", 0);
        return;
    }
    SetBusy(true, "Validating canonical design...");
    try {
        worker_->Send("validate_design", {{"design", design_v1_}}, [this](const nlohmann::json& response) {
            if (!Good(response)) { SetBusy(false, ErrorMessage(response, "Design validation failed")); return; }
            validation_ = response["result"];
            ShowJsonInOutput("Design validation", validation_, 0);
            const auto counts = validation_.value("counts", nlohmann::json::object());
            SetBusy(false, wxString::Format("Validation: %d errors, %d warnings",
                counts.value("errors", 0), counts.value("warnings", 0)));
        });
    } catch (const std::exception& error) {
        SetBusy(false, wxString::FromUTF8(error.what()));
    }
}

void NativeFrame::OnWorkspaceCommand(wxCommandEvent& event) {
    switch (event.GetId()) {
        case IdView2d:
            viewport_->SetTopView();
            SetStatusText("2D orthographic board view selected", 0);
            break;
        case IdView3d:
            viewport_->SetPerspectiveView();
            SetStatusText("3D board view selected", 0);
            break;
        case IdToggleNavigator: aui_.GetPane("project").Show(!aui_.GetPane("project").IsShown()); aui_.Update(); break;
        case IdToggleSetup: aui_.GetPane("setup").Show(!aui_.GetPane("setup").IsShown()); aui_.Update(); break;
        case IdToggleOutput: aui_.GetPane("output").Show(!aui_.GetPane("output").IsShown()); aui_.Update(); break;
        case IdShowIssues: ShowOutputPage(0); break;
        case IdShowConsole: ShowOutputPage(3); break;
        case IdShowReport: RefreshReport(); ShowOutputPage(4); break;
        case IdAdvancedWorkspace:
            aui_.GetPane("setup").Show(true);
            aui_.Update();
            if (setup_notebook_) setup_notebook_->SetSelection(8);
            SetStatusText("Advanced native worker workbench ready", 0);
            break;
        default: break;
    }
}

void NativeFrame::OnWorkerCommand(wxCommandEvent& event) {
    switch (event.GetId()) {
        case IdWorkerHealth: SendSimpleWorkerRequest("health", nlohmann::json::object(), "Worker health"); break;
        case IdCapabilities:
            if (!capabilities_.empty()) ShowJsonInOutput("SPIKE capability matrix", capabilities_);
            else SendSimpleWorkerRequest("capabilities", nlohmann::json::object(), "Capability matrix");
            break;
        case IdDependencies: SendSimpleWorkerRequest("dependencies", nlohmann::json::object(), "Dependency status"); break;
        case IdBenchmarks: SendSimpleWorkerRequest("benchmarks", nlohmann::json::object(), "Solver verification"); break;
        default: break;
    }
}

void NativeFrame::OnDomainCommand(wxCommandEvent& event) {
    if (event.GetId() == IdAssemblyWorkspace) {
        if (setup_notebook_) setup_notebook_->SetSelection(7);
        RefreshAssemblyWorkspace(true);
        return;
    }
    if (event.GetId() == IdAssemblyCreate) {
        try {
            if (assembly_ir_.empty()) {
                assembly_ir_ = DomainContracts::SingleBoardAssembly(design_v2_);
                assembly_designs_ = DomainContracts::SingleBoardDesigns(design_v2_);
            }
            RefreshAssemblyWorkspace(true);
            SetStatusText("Assembly workspace ready", 0);
        } catch (const std::exception& error) {
            SetStatusText("Assembly creation failed: " + wxString::FromUTF8(error.what()), 0);
        }
        return;
    }
    if (event.GetId() == IdAssemblyAdmit || event.GetId() == IdAssemblyPlan) {
        try {
            if (assembly_ir_.empty()) throw std::invalid_argument("Open an assembly or create a single-board assembly first");
            const auto designs = AssemblyDesignMap();
            if (event.GetId() == IdAssemblyAdmit) {
                SendDomainWorkerRequest("estimate_assembly_resources", {
                    {"assembly", assembly_ir_}, {"designs", designs},
                    {"workload", assembly_workload_->GetStringSelection().ToStdString()},
                    {"memory_limit_gb", assembly_memory_->GetValue()}
                }, "Assembly resource admission");
            } else {
                const auto request = DomainContracts::MultiboardRequest(
                    assembly_ir_, designs, assembly_domain_->GetStringSelection().ToStdString(),
                    assembly_mode_->GetStringSelection().ToStdString());
                SendDomainWorkerRequest("plan_multiboard_analysis", {{"request", request}}, "Multi-board PI / SI plan");
            }
        } catch (const std::exception& error) {
            SetStatusText("Assembly request rejected: " + wxString::FromUTF8(error.what()), 0);
        }
        return;
    }
    if (event.GetId() == IdAssemblyExecute) {
        try {
            if (assembly_operation_->GetSelection() == 3) {
                const auto active = assembly_designs_.value("active_design_id", design_v2_.value("design_id", ""));
                const auto scope = DomainContracts::ActiveBoardScope(assembly_ir_, active);
                SendDomainWorkerRequest("validate_assembly_analysis_scope",
                    {{"assembly_scope", scope}, {"design", design_v2_}}, "Active-board analysis scope");
                return;
            }
            const auto request = ParseJsonEditor(assembly_request_, "Assembly advanced request");
            const std::string methods[] = {
                "run_multiboard_si_independent_batch", "compile_multiboard_harness_network",
                "bind_multiboard_coupled_reduced_network"
            };
            const wxString labels[] = {
                "Independent multi-board SI batch", "Harness electrical-network compilation",
                "Coupled reduced-network binding"
            };
            const auto index = std::clamp(assembly_operation_->GetSelection(), 0, 2);
            SendDomainWorkerRequest(methods[index], {{"request", request}}, labels[index], index == 0);
        } catch (const std::exception& error) {
            SetStatusText("Advanced assembly request rejected: " + wxString::FromUTF8(error.what()), 0);
        }
        return;
    }
    if (event.GetId() == IdSiWorkspace) {
        const auto analyses = capabilities_.value("analyses", nlohmann::json::object());
        nlohmann::json si = {
            {"uniform_channel", analyses.value("geometry_uniform_channel", nlohmann::json::object())},
            {"next_fext", analyses.value("next_fext", nlohmann::json::object())},
            {"sparameter_network", analyses.value("sparameter_network", nlohmann::json::object())},
            {"eye_diagram", analyses.value("eye_diagram", nlohmann::json::object())},
            {"protocol_presets", analyses.value("protocol_presets", nlohmann::json::object())}
        };
        ShowJsonInOutput("HF / SI capabilities and validity", si);
        if (setup_notebook_) setup_notebook_->SetSelection(4);
        return;
    }
    if (event.GetId() == IdSiExecute) {
        try {
            auto value = ParseJsonEditor(si_request_, "SI request");
            const auto selection = si_operation_->GetSelection();
            if (selection == 0) {
                auto params = value.contains("suite") ? value : nlohmann::json{{"suite", value}};
                SendDomainWorkerRequest("validate_si_protocol_suite", std::move(params), "SI protocol-suite validation");
            } else if (selection == 1) {
                auto params = value.contains("suite") ? value : nlohmann::json{{"suite", value}, {"available_capabilities", nlohmann::json::array()}};
                SendDomainWorkerRequest("plan_si_protocol_analysis", std::move(params), "SI protocol analysis plan");
            } else {
                nlohmann::json params = value.contains("request") ? value : nlohmann::json{{"request", value}};
                if (!params.contains("design")) params["design"] = design_v2_;
                SendDomainWorkerRequest(selection == 2 ? "run_si_uniform_channel" : "run_si_protocol_test_suite",
                    std::move(params), selection == 2 ? "Uniform SI channel" : "SI protocol test suite", true);
            }
        } catch (const std::exception& error) {
            SetStatusText("SI request rejected: " + wxString::FromUTF8(error.what()), 0);
        }
        return;
    }
    if (event.GetId() == IdThermalWorkspace) {
        if (setup_notebook_) setup_notebook_->SetSelection(6);
        return;
    }
    if (event.GetId() == IdThermalExecute) {
        try {
            auto value = ParseJsonEditor(thermal_request_, "Thermal request");
            const auto selection = thermal_operation_->GetSelection();
            if (selection == 5) {
                SendDomainWorkerRequest("thermal_capabilities", nlohmann::json::object(), "Thermal capabilities");
            } else if (selection == 0 || selection == 1) {
                auto params = value.contains("scenario") ? value : nlohmann::json{{"scenario", value}};
                SendDomainWorkerRequest(selection == 0 ? "validate_thermal" : "estimate_thermal",
                    std::move(params), selection == 0 ? "Thermal validation" : "Compact thermal estimate", selection == 1);
            } else if (selection == 2) {
                auto params = value.contains("request") ? value : nlohmann::json{{"request", value}};
                SendDomainWorkerRequest("plan_thermal_field_job", std::move(params), "Thermal field-job plan");
            } else if (selection == 3) {
                auto params = value.contains("scenario") ? value : nlohmann::json{{"scenario", value}};
                wxDirDialog dialog(this, "Select OpenFOAM case output directory", {}, wxDD_DEFAULT_STYLE | wxDD_DIR_MUST_EXIST);
                if (dialog.ShowModal() != wxID_OK) return;
                params["output_dir"] = dialog.GetPath().ToStdString();
                if (!assembly_ir_.empty()) {
                    const auto active = assembly_designs_.value("active_design_id", design_v2_.value("design_id", ""));
                    params["assembly_scope"] = DomainContracts::ActiveBoardScope(assembly_ir_, active);
                }
                SendDomainWorkerRequest("prepare_thermal_case", std::move(params), "OpenFOAM case preparation");
            } else {
                if (!value.contains("case_dir")) throw std::invalid_argument("Run prepared case requires a params object containing case_dir");
                if (!assembly_ir_.empty() && !value.contains("assembly_scope")) {
                    const auto active = assembly_designs_.value("active_design_id", design_v2_.value("design_id", ""));
                    value["assembly_scope"] = DomainContracts::ActiveBoardScope(assembly_ir_, active);
                }
                SendDomainWorkerRequest("run_thermal_case", std::move(value), "OpenFOAM thermal run", true);
            }
        } catch (const std::exception& error) {
            SetStatusText("Thermal request rejected: " + wxString::FromUTF8(error.what()), 0);
        }
        return;
    }
    if (event.GetId() == IdPdnReview) {
        if (last_result_.empty()) { SetStatusText("Run an AC impedance analysis before PDN review", 0); return; }
        SendSimpleWorkerRequest("pdn_review", {
            {"result", last_result_}, {"target_ohm", 0.05}, {"net", net_choice_->GetStringSelection().ToStdString()},
            {"candidates", nlohmann::json::array()}
        }, "PDN target review");
        return;
    }
    if (design_v1_.empty() || net_choice_->GetStringSelection().empty()) {
        SetStatusText("Import a design and select an analysis net first", 0);
        return;
    }
    const auto candidate = net_choice_->GetStringSelection().ToStdString();
    std::string return_net = return_net_->GetValue().ToStdString();
    if (return_net.empty() && design_v1_.contains("nets")) {
        for (const auto& net : design_v1_["nets"]) {
            auto name = net.value("name", "");
            auto upper = name;
            std::transform(upper.begin(), upper.end(), upper.begin(), [](unsigned char character) { return static_cast<char>(std::toupper(character)); });
            if (upper.find("GND") != std::string::npos && name != candidate) { return_net = name; break; }
        }
    }
    const auto step = std::max(transient_step_->GetValue(), 1e-12);
    nlohmann::json setup = {
        {"contract", "spike/emi-setup/v1"}, {"selected_nets", {candidate}},
        {"return_nets", return_net.empty() ? nlohmann::json::array() : nlohmann::json::array({return_net})},
        {"requested_analyses", {"conducted_screening", "near_field", "far_field"}},
        {"frequency", {{"start_hz", frequency_start_->GetValue()}, {"stop_hz", frequency_stop_->GetValue()}, {"points", frequency_points_->GetValue()}}},
        {"environment", {{"kind", "free_space"}}},
        {"mesh", {{"resolution_mm", std::max(mesh_target_->GetValue(), 0.0001)}, {"padding_cells", 8}}},
        {"max_solver_time_s", 3600}, {"excitation", {{"mode", "prepass_results"}, {"ports", nlohmann::json::array()}}},
        {"net_metrics", nlohmann::json::array({{
            {"net", candidate}, {"source", "wx_setup_estimate"},
            {"dv_dt_v_per_s", source_voltage_->GetValue() / step}, {"di_dt_a_per_s", load_current_->GetValue() / step},
            {"peak_current_a", load_current_->GetValue()}, {"loop_area_mm2", 0.0}, {"return_discontinuities", return_net.empty() ? 1 : 0}
        }})}
    };
    if (setup_notebook_) setup_notebook_->SetSelection(5);
    SendSimpleWorkerRequest(event.GetId() == IdEmiScreen ? "emi_screen" : "emi_preflight",
        {{"design", design_v1_}, {"setup", setup}}, event.GetId() == IdEmiScreen ? "EMI risk screen" : "EMI preflight");
}

void NativeFrame::OnAdvancedExecute(wxCommandEvent&) {
    if (!advanced_method_ || !advanced_params_) return;
    try {
        const auto method = advanced_method_->GetStringSelection().ToStdString();
        if (method.empty()) throw std::invalid_argument("Select a worker operation first");
        auto params = ParseJsonEditor(advanced_params_, "Advanced worker parameters");
        const std::initializer_list<const char*> design_methods = {
            "validate_spice_workspace", "compose_spice_workspace", "compile_spice_workspace_native_mna",
            "run_spice_workspace_native_mna", "validate_topology_circuit", "bridge_topology_to_analysis_spec",
            "validate_pi_path", "extract_net_geometry", "extract_power_path", "prepare_sparselizard_case",
            "prepare_openems_case"
        };
        const bool needs_design = std::any_of(design_methods.begin(), design_methods.end(),
            [&method](const char* candidate) { return method == candidate; });
        if (needs_design && !params.contains("design")) {
            if (design_v1_.empty()) throw std::invalid_argument("This operation requires an imported design");
            params["design"] = design_v1_;
        }
        SendDomainWorkerRequest(method, std::move(params),
            "Advanced workbench: " + wxString::FromUTF8(method));
    } catch (const std::exception& error) {
        SetStatusText("Advanced operation rejected: " + wxString::FromUTF8(error.what()), 0);
    }
}

void NativeFrame::OnAbout(wxCommandEvent&) {
    wxMessageBox(
        "SPIKE Native 0.2.5 parity workbench\n\nC++20 / wxWidgets " wxVERSION_STRING
        "\nVTK native rendering\nCurrent SPIKE JSON-line worker and .spike v3 contracts",
        "About SPIKE Native", wxOK | wxICON_INFORMATION, this);
}

void NativeFrame::InstallDesign(const nlohmann::json& design) {
    if (!design.is_object() || design.value("contract", "") != "spike/v1") {
        throw std::runtime_error("Worker returned an invalid spike/v1 design");
    }
    design_v1_ = design;
    last_result_ = nlohmann::json::object();
    AppendLog("Installing design: nets");
    PopulateNets();
    AppendLog("Installing design: scene tree");
    PopulateSceneTree();
    AppendLog("Installing design: VTK viewport");
    viewport_->LoadDesign(design_v1_);
    AppendLog("Installing design: viewport ready");
    SetTitle("SPIKE - " + wxString::FromUTF8(design_v1_.value("name", "Design")) + " [Native]");
    UpdateProjectBadge();
    issues_->SetValue("Design loaded. Choose Project > Validate design to refresh canonical diagnostics.");
    const auto topology = design_v1_.value("metadata", nlohmann::json::object()).value("topologies", nlohmann::json::object());
    power_tree_->SetValue(topology.empty()
        ? wxString("No retained PI/SI topology is present in this design projection.")
        : wxString::FromUTF8(topology.dump(2)));
    SetStatusText(wxString::Format("%zu tracks | %zu vias", design.value("tracks", nlohmann::json::array()).size(), design.value("vias", nlohmann::json::array()).size()), 1);
}

nlohmann::json NativeFrame::ParseJsonEditor(wxTextCtrl* editor, const wxString& label) const {
    if (!editor) throw std::invalid_argument(label.ToStdString() + " editor is unavailable");
    try {
        auto value = nlohmann::json::parse(editor->GetValue().ToStdString());
        if (!value.is_object()) throw std::invalid_argument("top-level JSON value must be an object");
        return value;
    } catch (const nlohmann::json::exception& error) {
        throw std::invalid_argument(label.ToStdString() + " contains invalid JSON: " + error.what());
    }
}

nlohmann::json NativeFrame::AssemblyDesignMap() const {
    return DomainContracts::DesignMap(assembly_designs_, design_v2_);
}

void NativeFrame::RefreshAssemblyWorkspace(bool show_in_viewport) {
    if (!assembly_summary_) return;
    if (assembly_ir_.empty()) {
        assembly_summary_->SetLabel(
            "No AssemblyIR is loaded. Create a single-board assembly after importing a board, or open a .spike v3 assembly.");
        assembly_summary_->Wrap(310);
        PopulateSceneTree();
        return;
    }
    const auto boards = assembly_ir_.value("boards", nlohmann::json::array());
    const auto harnesses = assembly_ir_.value("harnesses", nlohmann::json::array());
    const auto designs = AssemblyDesignMap();
    assembly_summary_->SetLabel(wxString::Format(
        "%zu board instance%s · %zu retained design%s · %zu harness%s",
        boards.size(), boards.size() == 1 ? "" : "s", designs.size(), designs.size() == 1 ? "" : "s",
        harnesses.size(), harnesses.size() == 1 ? "" : "es"));
    assembly_summary_->Wrap(310);
    PopulateSceneTree();
    if (show_in_viewport) viewport_->LoadAssembly(assembly_ir_, designs);
}

void NativeFrame::RestoreNativeState(const nlohmann::json& canonical) {
    const auto extensions = canonical.value("extensions", nlohmann::json::object());
    const auto state = extensions.value("spike.wx_desktop", nlohmann::json::object());
    if (!state.is_object()) return;
    const auto drafts = state.value("domain_drafts", nlohmann::json::object());
    if (si_request_ && drafts.contains("si") && drafts["si"].is_string()) si_request_->SetValue(wxString::FromUTF8(drafts["si"].get<std::string>()));
    if (thermal_request_ && drafts.contains("thermal") && drafts["thermal"].is_string()) thermal_request_->SetValue(wxString::FromUTF8(drafts["thermal"].get<std::string>()));
    if (assembly_request_ && drafts.contains("assembly") && drafts["assembly"].is_string()) assembly_request_->SetValue(wxString::FromUTF8(drafts["assembly"].get<std::string>()));
    const auto selections = state.value("domain_selections", nlohmann::json::object());
    const auto restore_choice = [&selections](wxChoice* choice, const char* key) {
        if (!choice) return;
        const auto value = selections.value(key, 0);
        if (value >= 0 && value < static_cast<int>(choice->GetCount())) choice->SetSelection(value);
    };
    restore_choice(si_operation_, "si_operation");
    restore_choice(thermal_operation_, "thermal_operation");
    restore_choice(assembly_workload_, "assembly_workload");
    restore_choice(assembly_domain_, "assembly_domain");
    restore_choice(assembly_mode_, "assembly_mode");
    restore_choice(assembly_operation_, "assembly_operation");
    if (assembly_memory_) assembly_memory_->SetValue(selections.value("assembly_memory_gb", 8.0));
    domain_results_ = state.value("domain_results", nlohmann::json::object());
}

void NativeFrame::PopulateNets() {
    net_choice_->Clear();
    if (design_v1_.contains("nets") && design_v1_["nets"].is_array()) {
        for (const auto& net : design_v1_["nets"]) {
            const auto name = net.value("name", "");
            if (!name.empty()) net_choice_->Append(wxString::FromUTF8(name));
        }
    }
    if (net_choice_->GetCount()) net_choice_->SetSelection(0);
}

void NativeFrame::PopulateSceneTree() {
    if (!scene_tree_) return;
    const auto query = scene_search_ ? scene_search_->GetValue().Lower() : wxString();
    const auto matches = [&query](const wxString& value) { return query.empty() || value.Lower().Contains(query); };
    scene_tree_->Freeze();
    scene_tree_->DeleteAllItems();
    const auto root = scene_tree_->AddRoot("SPIKE");
    if (!assembly_ir_.empty()) {
        const auto assembly = scene_tree_->AppendItem(root,
            "Assembly: " + wxString::FromUTF8(assembly_ir_.value("name", assembly_ir_.value("assembly_id", "System"))));
        const auto boards = scene_tree_->AppendItem(assembly, "Board instances");
        for (const auto& instance : assembly_ir_.value("boards", nlohmann::json::array())) {
            const auto label = wxString::FromUTF8(instance.value("name", instance.value("id", "Board")));
            if (matches(label)) scene_tree_->AppendItem(boards, label);
        }
        const auto harnesses = scene_tree_->AppendItem(assembly, "Harnesses");
        for (const auto& harness : assembly_ir_.value("harnesses", nlohmann::json::array())) {
            const auto label = wxString::FromUTF8(harness.value("name", harness.value("id", "Harness")));
            if (matches(label)) scene_tree_->AppendItem(harnesses, label);
        }
        scene_tree_->Expand(assembly);
        scene_tree_->Expand(boards);
    }
    const auto board = scene_tree_->AppendItem(
        root,
        design_v1_.empty() ? wxString("No design") : wxString::FromUTF8(design_v1_.value("name", "Board")));
    const auto append_values = [&](const wxTreeItemId& parent, const nlohmann::json& values, const char* field, std::size_t limit = 2000) {
        std::size_t count = 0;
        if (!values.is_array()) return;
        for (const auto& value : values) {
            if (count++ >= limit) break;
            std::string raw;
            if (value.is_object()) {
                raw = value.value(field, "");
            } else if (value.is_string()) {
                raw = value.get<std::string>();
            }
            const auto text = wxString::FromUTF8(raw);
            if (!text.empty() && matches(text)) scene_tree_->AppendItem(parent, text);
        }
    };
    const auto layers = scene_tree_->AppendItem(board, "Layers");
    append_values(layers, design_v1_.value("layers", nlohmann::json::array()), "name");
    const auto nets = scene_tree_->AppendItem(board, "Nets");
    append_values(nets, design_v1_.value("nets", nlohmann::json::array()), "name");
    const auto components = scene_tree_->AppendItem(board, "Components");
    append_values(components, design_v1_.value("components", nlohmann::json::array()), "reference");
    const auto vias = scene_tree_->AppendItem(board, "Vias");
    const auto via_count = design_v1_.value("vias", nlohmann::json::array()).size();
    scene_tree_->AppendItem(vias, wxString::Format("%zu plated via records", via_count));
    const auto probes = scene_tree_->AppendItem(board, "Probes");
    scene_tree_->AppendItem(probes, "No persistent probes");
    scene_tree_->Expand(board);
    scene_tree_->Expand(nets);
    scene_tree_->Thaw();
}

AnalysisInputs NativeFrame::ReadInputs() const {
    AnalysisInputs inputs;
    inputs.mode = mode_choice_->GetSelection() == 1 ? "ac" : mode_choice_->GetSelection() == 2 ? "transient" : "dc";
    inputs.net = net_choice_->GetStringSelection().ToStdString();
    inputs.return_net = return_net_->GetValue().ToStdString();
    inputs.source_voltage_v = source_voltage_->GetValue();
    inputs.load_current_a = load_current_->GetValue();
    inputs.source_x_mm = source_x_->GetValue(); inputs.source_y_mm = source_y_->GetValue();
    inputs.load_x_mm = load_x_->GetValue(); inputs.load_y_mm = load_y_->GetValue();
    inputs.frequency_start_hz = frequency_start_->GetValue();
    inputs.frequency_stop_hz = frequency_stop_->GetValue();
    inputs.frequency_points = frequency_points_->GetValue();
    inputs.transient_stop_s = transient_stop_->GetValue();
    inputs.transient_step_s = transient_step_->GetValue();
    inputs.transient_decimation = transient_decimation_->GetValue();
    inputs.mesh_target_mm = mesh_target_->GetValue();
    inputs.zone_cell_mm = zone_cell_->GetValue();
    inputs.max_drop_mv = max_drop_->GetValue();
    inputs.max_density_a_mm2 = max_density_->GetValue();
    return inputs;
}

nlohmann::json NativeFrame::SetupJson() const {
    const auto inputs = ReadInputs();
    nlohmann::json setup = {
        {"contract", "spike/wx-analysis-setup/v1"}, {"mode", inputs.mode}, {"net", inputs.net},
        {"return_net", inputs.return_net}, {"source_voltage_v", inputs.source_voltage_v},
        {"load_current_a", inputs.load_current_a},
        {"source_position_mm", {inputs.source_x_mm, inputs.source_y_mm}},
        {"load_position_mm", {inputs.load_x_mm, inputs.load_y_mm}},
        {"frequency", {{"start_hz", inputs.frequency_start_hz}, {"stop_hz", inputs.frequency_stop_hz}, {"points", inputs.frequency_points}}},
        {"transient", {{"stop_s", inputs.transient_stop_s}, {"step_s", inputs.transient_step_s}, {"decimation", inputs.transient_decimation}}},
        {"mesh", {{"target_mm", inputs.mesh_target_mm}, {"zone_cell_mm", inputs.zone_cell_mm}}},
        {"limits", {{"max_drop_mv", inputs.max_drop_mv}, {"max_density_a_mm2", inputs.max_density_a_mm2}}}
    };
    setup["workspaces"] = {
        {"si_operation", si_operation_ ? si_operation_->GetStringSelection().ToStdString() : ""},
        {"thermal_operation", thermal_operation_ ? thermal_operation_->GetStringSelection().ToStdString() : ""},
        {"assembly", {
            {"present", !assembly_ir_.empty()},
            {"boards", assembly_ir_.value("boards", nlohmann::json::array()).size()},
            {"harnesses", assembly_ir_.value("harnesses", nlohmann::json::array()).size()},
            {"plan_domain", assembly_domain_ ? assembly_domain_->GetStringSelection().ToStdString() : ""},
            {"plan_mode", assembly_mode_ ? assembly_mode_->GetStringSelection().ToStdString() : ""}
        }},
        {"domain_results", domain_results_}
    };
    return setup;
}

void NativeFrame::OnPreflight(wxCommandEvent&) { SendAnalysis(true); }
void NativeFrame::OnRun(wxCommandEvent&) { SendAnalysis(false); }

void NativeFrame::SendAnalysis(bool preflight_only) {
    if (busy_ || design_v1_.empty()) return;
    try {
        const auto inputs = ReadInputs();
        last_request_ = RequestBuilder::BuildAnalysisRequest(design_v1_, inputs, AnalysisId(inputs.mode));
        SetBusy(true, preflight_only ? "Running preflight..." : "Preflighting analysis...");
        worker_->Send("preflight_analysis", last_request_, [this, preflight_only](const nlohmann::json& validation) {
            if (!Good(validation)) { SetBusy(false, ErrorMessage(validation, "Preflight failed")); return; }
            const auto& result = validation["result"];
            AppendLog("Preflight: " + wxString::FromUTF8(result.dump(2)));
            if (result.contains("mesh") && result["mesh"].is_object()) {
                nlohmann::json preview = {
                    {"fields", {{"visualization", {{"mesh", result["mesh"].value("cells", nlohmann::json::array())}}}}}
                };
                viewport_->LoadResult(preview);
            }
            if (preflight_only || !result.value("can_solve", false)) {
                SetBusy(false, result.value("can_solve", false) ? "Preflight passed" : "Preflight blocked; inspect issues");
                return;
            }
            SetStatusText("Running isolated solver...", 0);
            try {
                worker_->Send("run_analysis", last_request_, [this](const nlohmann::json& response) {
                    if (!Good(response)) { SetBusy(false, ErrorMessage(response, "Analysis failed")); return; }
                    InstallResult(response["result"]);
                    SetBusy(false, "Analysis " + wxString::FromUTF8(response["result"].value("status", "finished")));
                });
            } catch (const std::exception& error) { SetBusy(false, wxString::FromUTF8(error.what())); }
        });
    } catch (const std::exception& error) {
        SetBusy(false, wxString::FromUTF8(error.what()));
        wxMessageBox(wxString::FromUTF8(error.what()), "Invalid analysis setup", wxOK | wxICON_WARNING, this);
    }
}

void NativeFrame::InstallResult(const nlohmann::json& result) {
    last_result_ = result;
    if (result_field_choice_) {
        result_field_choice_->Clear();
        result_field_choice_->Append("Geometry");
        const nlohmann::json* scalar_fields = nullptr;
        const auto fields = last_result_.value("fields", nlohmann::json::object());
        const auto visualization = fields.value("visualization", nlohmann::json::object());
        if (visualization.contains("scalar_fields") && visualization["scalar_fields"].is_object()) {
            scalar_fields = &visualization["scalar_fields"];
        } else if (fields.contains("scalar_fields") && fields["scalar_fields"].is_object()) {
            scalar_fields = &fields["scalar_fields"];
        }
        if (scalar_fields) {
            for (const auto& [name, samples] : scalar_fields->items()) {
                if (samples.is_array() && !samples.empty()) result_field_choice_->Append(wxString::FromUTF8(name));
            }
        }
        if (result_field_choice_->GetCount() > 1) {
            result_field_choice_->SetSelection(1);
            viewport_->LoadResult(last_result_, result_field_choice_->GetString(1).ToStdString());
        } else {
            result_field_choice_->SetSelection(0);
            viewport_->ClearResult();
        }
    } else {
        viewport_->LoadResult(last_result_);
    }
    AppendLog("Analysis result: " + wxString::FromUTF8(last_result_.dump(2)));
    RefreshReport();
}

void NativeFrame::RefreshReport() {
    if (last_result_.empty()) {
        SetStatusText("Run an analysis before generating a report", 0);
        return;
    }
    try {
        const auto runtime = ReportWriter::LoadPlotlyRuntime(PlotlyPath());
        const auto project_name = project_path_.empty() ? source_path_.ToStdString() : project_path_.ToStdString();
        report_html_ = ReportWriter::BuildHtml(project_name, design_v1_, SetupJson(), last_result_, runtime);
        if (report_view_) report_view_->SetPage(wxString::FromUTF8(report_html_), "");
        else if (report_fallback_) report_fallback_->SetValue(
            "Report generated successfully. WebView2 is unavailable, so use Reports > Export offline HTML to view it in a browser.");
    } catch (const std::exception& error) {
        AppendLog("Report preview unavailable: " + wxString::FromUTF8(error.what()));
    }
}

std::filesystem::path NativeFrame::PlotlyPath() const {
    const std::filesystem::path repository = resource_root_.empty() ? std::filesystem::current_path() : resource_root_;
    const auto source_asset = repository / "app" / "node_modules" / "plotly.js-dist-min" / "plotly.min.js";
    if (std::filesystem::is_regular_file(source_asset)) return source_asset;
    const auto packaged = std::filesystem::path(wxStandardPaths::Get().GetExecutablePath().ToStdWstring()).parent_path() / "assets" / "plotly.min.js";
    return packaged;
}

void NativeFrame::OnExportReport(wxCommandEvent&) {
    if (last_result_.empty()) return;
    if (report_html_.empty()) RefreshReport();
    if (report_html_.empty()) return;
    wxFileDialog dialog(this, "Export engineering report", {}, "spike-report.html", "HTML reports (*.html)|*.html",
        wxFD_SAVE | wxFD_OVERWRITE_PROMPT);
    if (dialog.ShowModal() != wxID_OK) return;
    try {
        ReportWriter::WriteFile(std::filesystem::path(dialog.GetPath().ToStdWstring()), report_html_);
        SetStatusText("Self-contained offline report exported", 0);
    } catch (const std::exception& error) {
        wxMessageBox(wxString::FromUTF8(error.what()), "Report export failed", wxOK | wxICON_ERROR, this);
    }
}

void NativeFrame::OnPrintReport(wxCommandEvent&) {
    if (report_html_.empty()) RefreshReport();
    if (report_html_.empty()) return;
    if (report_view_) report_view_->Print();
    else wxMessageBox("WebView2 is unavailable. Export the self-contained HTML report and print it from a browser.",
        "Report preview unavailable", wxOK | wxICON_INFORMATION, this);
}

void NativeFrame::OnCancel(wxCommandEvent&) {
    if (!busy_) return;
    worker_->CancelActive();
    SetBusy(false, "Operation cancelled; worker restarted");
}

void NativeFrame::OnFit(wxCommandEvent&) { viewport_->Fit(); }
void NativeFrame::OnWorkerTimer(wxTimerEvent&) { if (worker_) worker_->Poll(); }

void NativeFrame::ShowOutputPage(std::size_t index) {
    if (!bottom_notebook_) return;
    auto& pane = aui_.GetPane("output");
    pane.Show(true);
    aui_.Update();
    if (index < bottom_notebook_->GetPageCount()) bottom_notebook_->SetSelection(index);
}

void NativeFrame::ShowJsonInOutput(const wxString& title, const nlohmann::json& value, std::size_t page) {
    const auto output = title + "\n\n" + wxString::FromUTF8(value.dump(2));
    if (page == 0 && issues_) issues_->SetValue(output);
    else AppendLog(output);
    ShowOutputPage(page);
}

void NativeFrame::SendSimpleWorkerRequest(const std::string& method, nlohmann::json params, const wxString& label) {
    if (busy_ || closing_) return;
    SetBusy(true, label + "...");
    try {
        worker_->Send(method, std::move(params), [this, label](const nlohmann::json& response) {
            if (closing_) return;
            if (!Good(response)) {
                const auto message = ErrorMessage(response, label + " failed");
                ShowJsonInOutput(label + " failed", response, 0);
                SetBusy(false, message);
                return;
            }
            if (label.Contains("Capabilit")) InstallCapabilities(response["result"]);
            ShowJsonInOutput(label, response["result"], 0);
            SetBusy(false, label + " completed");
        });
    } catch (const std::exception& error) {
        SetBusy(false, label + " failed: " + wxString::FromUTF8(error.what()));
    }
}

void NativeFrame::SendDomainWorkerRequest(
    const std::string& method,
    nlohmann::json params,
    const wxString& label,
    bool install_result) {
    if (busy_ || closing_) return;
    SetBusy(true, label + "...");
    try {
        worker_->Send(method, std::move(params), [this, method, label, install_result](const nlohmann::json& response) {
            if (closing_) return;
            if (!Good(response)) {
                const auto message = ErrorMessage(response, label + " failed");
                ShowJsonInOutput(label + " failed", response, 0);
                SetBusy(false, message);
                return;
            }
            domain_results_[method] = response["result"];
            ShowJsonInOutput(label, response["result"], 0);
            if (install_result) InstallResult(response["result"]);
            SetBusy(false, label + " completed");
        });
    } catch (const std::exception& error) {
        SetBusy(false, label + " failed: " + wxString::FromUTF8(error.what()));
    }
}

void NativeFrame::ApplyTheme(wxWindow* root) {
    if (!root || dynamic_cast<VtkViewport*>(root)) return;
    wxColour background = root->GetParent() ? root->GetParent()->GetBackgroundColour() : ShellBackground;
    const auto name = root->GetName();
    if (name == "spike-topbar") background = HeaderBackground;
    else if (name == "spike-ribbon-page") background = ToolBackground;
    else if (name == "spike-viewport-toolbar") background = wxColour(16, 29, 36);
    else if (name == "spike-viewport-host") background = ShellBackground;
    else if (dynamic_cast<wxNotebook*>(root)) background = HeaderBackground;
    else if (dynamic_cast<wxTextCtrl*>(root) || dynamic_cast<wxTreeCtrl*>(root) ||
             dynamic_cast<wxListCtrl*>(root) || dynamic_cast<wxChoice*>(root) ||
             dynamic_cast<wxSpinCtrl*>(root) || dynamic_cast<wxSpinCtrlDouble*>(root) ||
             name == "spike-search") background = InputBackground;
    else if (dynamic_cast<wxButton*>(root)) background = ToolBackground;
    else if (dynamic_cast<wxPanel*>(root)) background = PanelBackground;

    root->SetBackgroundColour(background);
    root->SetForegroundColour(PrimaryText);
    if (auto* button = dynamic_cast<wxButton*>(root)) {
        button->SetForegroundColour(SecondaryText);
        button->SetBackgroundColour(ToolBackground);
    } else if (dynamic_cast<wxStaticText*>(root)) {
        root->SetBackgroundColour(root->GetParent() ? root->GetParent()->GetBackgroundColour() : background);
    } else if (dynamic_cast<wxTextCtrl*>(root) || dynamic_cast<wxTreeCtrl*>(root) || dynamic_cast<wxListCtrl*>(root)) {
        root->SetForegroundColour(PrimaryText);
    }
    for (auto* child : root->GetChildren()) ApplyTheme(child);
    root->Refresh(false);
}

void NativeFrame::UpdateProjectBadge() {
    if (!project_badge_) return;
    wxString label = "Untitled project";
    if (!project_path_.empty()) label = wxFileName(project_path_).GetFullName();
    else if (!source_path_.empty()) label = wxFileName(source_path_).GetFullName();
    else if (!design_v1_.empty()) label = wxString::FromUTF8(design_v1_.value("name", "Design"));
    project_badge_->SetLabel(label);
    project_badge_->GetParent()->Layout();
}

void NativeFrame::AppendLog(const wxString& message) {
    const auto line = "[" + wxDateTime::Now().FormatISOTime() + "] " + message;
    if (!diagnostic_log_.empty()) {
        std::ofstream stream(diagnostic_log_, std::ios::app | std::ios::binary);
        if (stream) stream << line.ToStdString() << '\n';
    }
    if (log_) log_->AppendText(line + "\n");
}

void NativeFrame::SetBusy(bool busy, const wxString& status) {
    if (closing_) return;
    busy_ = busy;
    SetStatusText(status, 0);
    SetStatusText(busy ? "Worker busy" : "Worker ready", 2);
    if (GetToolBar()) {
        GetToolBar()->EnableTool(IdRun, !busy);
        GetToolBar()->EnableTool(IdPreflight, !busy);
        GetToolBar()->EnableTool(IdCancel, busy);
    }
}

void NativeFrame::OnClose(wxCloseEvent& event) {
    closing_ = true;
    worker_timer_.Stop();
    if (worker_) worker_->Stop();
    event.Skip();
}

}  // namespace spike::wxui
