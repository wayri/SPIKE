#include "spike_wx/native_frame.hpp"
#include "spike_wx/worker_client.hpp"

#include <wx/app.h>
#include <wx/cmdline.h>
#include <wx/image.h>
#include <wx/msgdlg.h>
#include <wx/stdpaths.h>
#include <wx/utils.h>

#ifdef __WXMSW__
#include <wx/msw/darkmode.h>
#endif

#include <chrono>
#include <exception>
#include <filesystem>
#include <fstream>
#include <string>

namespace {

#ifdef __WXMSW__
class SpikeDarkModeSettings final : public wxDarkModeSettings {
public:
    wxColour GetColour(wxSystemColour index) override {
        switch (index) {
            case wxSYS_COLOUR_WINDOW: return wxColour(15, 25, 32);
            case wxSYS_COLOUR_WINDOWTEXT: return wxColour(217, 226, 234);
            case wxSYS_COLOUR_BTNFACE: return wxColour(27, 42, 52);
            case wxSYS_COLOUR_BTNTEXT: return wxColour(181, 197, 204);
            case wxSYS_COLOUR_HIGHLIGHT: return wxColour(38, 58, 69);
            case wxSYS_COLOUR_HIGHLIGHTTEXT: return wxColour(245, 195, 107);
            case wxSYS_COLOUR_MENU:
            case wxSYS_COLOUR_MENUBAR: return wxColour(20, 32, 41);
            case wxSYS_COLOUR_MENUTEXT: return wxColour(197, 212, 217);
            case wxSYS_COLOUR_GRAYTEXT: return wxColour(96, 119, 128);
            case wxSYS_COLOUR_3DSHADOW: return wxColour(43, 59, 70);
            case wxSYS_COLOUR_HOTLIGHT: return wxColour(240, 179, 75);
            case wxSYS_COLOUR_INFOBK: return wxColour(21, 37, 45);
            case wxSYS_COLOUR_INFOTEXT: return wxColour(197, 212, 217);
            case wxSYS_COLOUR_ACTIVECAPTION: return wxColour(28, 43, 53);
            case wxSYS_COLOUR_INACTIVECAPTION: return wxColour(20, 32, 41);
            case wxSYS_COLOUR_CAPTIONTEXT: return wxColour(217, 226, 234);
            default: return wxDarkModeSettings::GetColour(index);
        }
    }

    wxColour GetMenuColour(wxMenuColour which) override {
        switch (which) {
            case wxMenuColour::StandardFg: return wxColour(197, 212, 217);
            case wxMenuColour::StandardBg: return wxColour(20, 32, 41);
            case wxMenuColour::DisabledFg: return wxColour(96, 119, 128);
            case wxMenuColour::HotBg: return wxColour(38, 58, 69);
        }
        return wxColour(20, 32, 41);
    }

    wxPen GetBorderPen() override { return wxPen(wxColour(52, 74, 84)); }
};
#endif

bool IsRepositoryRoot(const std::filesystem::path& candidate) {
    return std::filesystem::is_regular_file(candidate / "python" / "spike_core" / "service.py") &&
           std::filesystem::is_regular_file(candidate / "app" / "src" / "App.tsx");
}

std::filesystem::path FindRepositoryRoot(const std::filesystem::path& executable) {
    for (auto candidate : {std::filesystem::current_path(), executable.parent_path()}) {
        for (int depth = 0; depth < 10 && !candidate.empty(); ++depth) {
            if (IsRepositoryRoot(candidate)) return std::filesystem::weakly_canonical(candidate);
            const auto parent = candidate.parent_path();
            if (parent == candidate) break;
            candidate = parent;
        }
    }
    return {};
}

std::filesystem::path FindPackagedWorker(
    const std::filesystem::path& executable,
    const std::filesystem::path& repository) {
    const std::filesystem::path candidates[] = {
        executable.parent_path() / "spike-worker.exe",
        executable.parent_path() / "worker" / "spike-worker.exe",
        repository / "app" / "src-tauri" / "target" / "release" / "bundled" / "spike-worker" / "spike-worker.exe",
        repository / "app" / "src-tauri" / "target" / "debug" / "bundled" / "spike-worker" / "spike-worker.exe"
    };
    for (const auto& candidate : candidates) {
        if (!candidate.empty() && std::filesystem::is_regular_file(candidate)) return candidate;
    }
    return {};
}

std::filesystem::path FindRepositoryPython(const std::filesystem::path& repository) {
    const auto candidate = repository / ".venv" / "Scripts" / "python.exe";
    return std::filesystem::is_regular_file(candidate) ? candidate : std::filesystem::path();
}

std::filesystem::path DiagnosticLogPath() {
    auto directory = std::filesystem::path(wxStandardPaths::Get().GetUserLocalDataDir().ToStdWstring()) / "logs";
    std::error_code error;
    std::filesystem::create_directories(directory, error);
    return directory / "spike-wx.log";
}

void AppendDiagnostic(const std::filesystem::path& path, const std::string& message) {
    if (path.empty()) return;
    std::ofstream stream(path, std::ios::app | std::ios::binary);
    if (!stream) return;
    const auto now = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
    std::tm local{};
    localtime_s(&local, &now);
    char stamp[32]{};
    std::strftime(stamp, sizeof(stamp), "%Y-%m-%d %H:%M:%S", &local);
    stream << '[' << stamp << "] " << message << '\n';
}

class SpikeWxApp final : public wxApp {
public:
    void OnInitCmdLine(wxCmdLineParser& parser) override {
        wxApp::OnInitCmdLine(parser);
        parser.AddOption({}, "worker", "path to a SPIKE worker executable", wxCMD_LINE_VAL_STRING);
        parser.AddOption({}, "open", "design or .spike project to open", wxCMD_LINE_VAL_STRING);
        parser.AddOption({}, "repository", "SPIKE repository root", wxCMD_LINE_VAL_STRING);
        parser.AddOption({}, "log", "runtime diagnostic log file", wxCMD_LINE_VAL_STRING);
        parser.AddParam("design-or-project", wxCMD_LINE_VAL_STRING, wxCMD_LINE_PARAM_OPTIONAL);
    }

    bool OnInit() override {
#ifdef __WXMSW__
        MSWEnableDarkMode(DarkMode_Always, new SpikeDarkModeSettings());
#else
        SetAppearance(Appearance::Dark);
#endif
        SetAppName("SPIKE Native");
        SetVendorName("SPIKE");
        log_path_ = DiagnosticLogPath();
        wxHandleFatalExceptions(true);
        wxInitAllImageHandlers();
        try {
            const auto executable = std::filesystem::path(wxStandardPaths::Get().GetExecutablePath().ToStdWstring());
            auto repository = FindRepositoryRoot(executable);
            wxString worker;
            wxString initial_path;
            wxString requested_log;
            for (int index = 1; index < argc; ++index) {
                if (argv[index] == "--worker" && index + 1 < argc) worker = argv[++index];
                else if (argv[index] == "--open" && index + 1 < argc) initial_path = argv[++index];
                else if (argv[index] == "--repository" && index + 1 < argc) repository = std::filesystem::path(argv[++index].ToStdWstring());
                else if (argv[index] == "--log" && index + 1 < argc) requested_log = argv[++index];
                else if (!argv[index].StartsWith("--") && initial_path.empty()) initial_path = argv[index];
            }
            if (!requested_log.empty()) log_path_ = std::filesystem::path(requested_log.ToStdWstring());
            const auto repository_python = worker.empty() ? FindRepositoryPython(repository) : std::filesystem::path();
            const auto packaged_worker = worker.empty() && repository_python.empty()
                ? FindPackagedWorker(executable, repository) : std::filesystem::path();
            const wxString command = !worker.empty()
                ? spike::wxui::QuoteCommandArgument(worker)
                : !repository_python.empty()
                    ? spike::wxui::QuoteCommandArgument(wxString(repository_python.wstring())) + " -m python.spike_core.service"
                : !packaged_worker.empty()
                    ? spike::wxui::QuoteCommandArgument(wxString(packaged_worker.wstring()))
                    : wxString("python -m python.spike_core.service");
            const wxString worker_directory = repository.empty() ? wxString() : wxString(repository.wstring());
            AppendDiagnostic(log_path_, "Starting SPIKE Native " SPIKE_WX_VERSION);
            AppendDiagnostic(log_path_, "Executable: " + executable.string());
            AppendDiagnostic(log_path_, "Repository: " + (repository.empty() ? std::string("not found") : repository.string()));
            AppendDiagnostic(log_path_, "Worker command: " + command.ToStdString());
            auto* frame = new spike::wxui::NativeFrame(command, worker_directory, repository, log_path_);
            frame->Show();
            SetTopWindow(frame);
            if (!initial_path.empty()) frame->CallAfter([frame, initial_path] { frame->OpenPath(initial_path); });
            return true;
        } catch (const std::exception& error) {
            AppendDiagnostic(log_path_, std::string("Startup exception: ") + error.what());
            wxMessageBox("SPIKE Native could not start.\n\n" + wxString::FromUTF8(error.what()) +
                "\n\nDiagnostic log:\n" + wxString(log_path_.wstring()), "SPIKE Native startup failure", wxOK | wxICON_ERROR);
            return false;
        }
    }

    bool OnExceptionInMainLoop() override {
        try {
            throw;
        } catch (const std::exception& error) {
            AppendDiagnostic(log_path_, std::string("UI exception: ") + error.what());
            wxMessageBox("SPIKE Native recovered from a UI error.\n\n" + wxString::FromUTF8(error.what()) +
                "\n\nDetails were written to:\n" + wxString(log_path_.wstring()), "SPIKE Native error", wxOK | wxICON_ERROR, GetTopWindow());
        } catch (...) {
            AppendDiagnostic(log_path_, "UI exception: unknown exception");
        }
        return true;
    }

    void OnUnhandledException() override { AppendDiagnostic(log_path_, "Unhandled C++ exception reached wxApp"); }
    void OnFatalException() override { AppendDiagnostic(log_path_, "Fatal native exception; inspect Windows Error Reporting for the faulting module"); }

private:
    std::filesystem::path log_path_;
};

}  // namespace

wxIMPLEMENT_APP(SpikeWxApp);
