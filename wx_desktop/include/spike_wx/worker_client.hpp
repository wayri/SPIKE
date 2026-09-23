#pragma once

#include <wx/process.h>
#include <wx/string.h>

#include <nlohmann/json.hpp>

#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <unordered_map>

namespace spike::wxui {

class WorkerClient final {
public:
    using Callback = std::function<void(const nlohmann::json&)>;
    using LogCallback = std::function<void(const wxString&)>;

    explicit WorkerClient(
        wxString command,
        LogCallback log_callback = {},
        wxString working_directory = {});
    ~WorkerClient();

    WorkerClient(const WorkerClient&) = delete;
    WorkerClient& operator=(const WorkerClient&) = delete;

    bool Start();
    void Stop();
    bool Restart();
    [[nodiscard]] bool IsRunning() const noexcept { return pid_ > 0; }
    [[nodiscard]] bool IsBusy() const noexcept { return !callbacks_.empty(); }

    std::string Send(std::string method, nlohmann::json params, Callback callback);
    void Poll();
    void CancelActive();

private:
    static std::string NewRequestId();
    void Drain(wxInputStream* stream, std::string& buffer, bool responses);
    void HandleResponseLine(const std::string& line);
    void FailPending(const std::string& message, const std::string& type);
    void Log(const wxString& line) const;

    wxString command_;
    wxString working_directory_;
    LogCallback log_callback_;
    std::unique_ptr<wxProcess> process_;
    long pid_{0};
    std::uint64_t sequence_{0};
    std::string stdout_buffer_;
    std::string stderr_buffer_;
    std::unordered_map<std::string, Callback> callbacks_;
};

wxString QuoteCommandArgument(const wxString& value);

}  // namespace spike::wxui
