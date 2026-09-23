#include "spike_wx/worker_client.hpp"

#include <wx/stream.h>
#include <wx/utils.h>

#include <algorithm>
#include <chrono>
#include <random>
#include <stdexcept>
#include <utility>

namespace spike::wxui {

wxString QuoteCommandArgument(const wxString& value) {
    if (value.empty()) return "\"\"";
    if (value.find_first_of(" \t\"") == wxString::npos) return value;
    wxString result = "\"";
    unsigned backslashes = 0;
    for (const wxUniChar character : value) {
        if (character == '\\') {
            ++backslashes;
            continue;
        }
        if (character == '"') {
            for (unsigned index = 0; index < backslashes * 2 + 1; ++index) result += '\\';
            result += '"';
            backslashes = 0;
            continue;
        }
        for (unsigned index = 0; index < backslashes; ++index) result += '\\';
        backslashes = 0;
        result += character;
    }
    for (unsigned index = 0; index < backslashes * 2; ++index) result += '\\';
    result += '"';
    return result;
}

WorkerClient::WorkerClient(wxString command, LogCallback log_callback, wxString working_directory)
    : command_(std::move(command)),
      working_directory_(std::move(working_directory)),
      log_callback_(std::move(log_callback)) {}

WorkerClient::~WorkerClient() { Stop(); }

bool WorkerClient::Start() {
    if (IsRunning()) return true;
    process_ = std::make_unique<wxProcess>();
    process_->Redirect();
    wxExecuteEnv environment;
    environment.cwd = working_directory_;
    pid_ = wxExecute(command_, wxEXEC_ASYNC | wxEXEC_HIDE_CONSOLE, process_.get(), &environment);
    if (pid_ <= 0) {
        Log("Unable to launch SPIKE worker: " + command_);
        process_.reset();
        pid_ = 0;
        return false;
    }
    stdout_buffer_.clear();
    stderr_buffer_.clear();
    const auto location = working_directory_.empty() ? wxString() : wxString(" in ") + working_directory_;
    Log(wxString::Format("Worker started (PID %ld)", pid_) + location);
    return true;
}

void WorkerClient::Stop() {
    if (pid_ > 0) {
        wxKillError error = wxKILL_OK;
        wxKill(pid_, wxSIGKILL, &error, wxKILL_CHILDREN);
        if (error != wxKILL_OK && error != wxKILL_NO_PROCESS) {
            Log(wxString::Format("Worker termination returned code %d", static_cast<int>(error)));
        }
    }
    FailPending("Worker stopped", "WorkerStopped");
    process_.reset();
    pid_ = 0;
}

bool WorkerClient::Restart() {
    Stop();
    return Start();
}

std::string WorkerClient::NewRequestId() {
    static std::mt19937_64 generator(std::random_device{}());
    const auto now = std::chrono::steady_clock::now().time_since_epoch().count();
    return "wx-" + std::to_string(now) + "-" + std::to_string(generator());
}

std::string WorkerClient::Send(std::string method, nlohmann::json params, Callback callback) {
    if (!IsRunning() && !Start()) throw std::runtime_error("SPIKE worker is unavailable");
    if (IsBusy()) throw std::runtime_error("A worker request is already active");
    const auto id = NewRequestId();
    nlohmann::json request = {{"id", id}, {"method", std::move(method)}, {"params", std::move(params)}};
    auto line = request.dump();
    line.push_back('\n');
    auto* output = process_->GetOutputStream();
    if (output == nullptr || !output->IsOk()) throw std::runtime_error("Worker stdin is unavailable");
    callbacks_.emplace(id, std::move(callback));
    output->Write(line.data(), line.size());
    output->Sync();
    if (!output->IsOk()) {
        callbacks_.erase(id);
        throw std::runtime_error("Unable to write the worker request");
    }
    return id;
}

void WorkerClient::Poll() {
    if (!process_) return;
    Drain(process_->GetInputStream(), stdout_buffer_, true);
    Drain(process_->GetErrorStream(), stderr_buffer_, false);
    if (pid_ > 0 && !wxProcess::Exists(pid_)) {
        Log("Worker process exited");
        pid_ = 0;
        FailPending("The SPIKE worker exited before completing the request", "WorkerExited");
        process_.reset();
    }
}

void WorkerClient::CancelActive() {
    if (!IsBusy()) return;
    Log("Cancelling active operation by restarting its isolated worker process");
    Restart();
}

void WorkerClient::Drain(wxInputStream* stream, std::string& buffer, bool responses) {
    if (stream == nullptr) return;
    char chunk[4096];
    while (stream->CanRead()) {
        stream->Read(chunk, sizeof(chunk));
        const auto count = stream->LastRead();
        if (count == 0) break;
        buffer.append(chunk, count);
        if (buffer.size() > 16U * 1024U * 1024U) {
            Log("Worker output exceeded the 16 MiB protocol-line limit");
            buffer.clear();
            FailPending("Worker output exceeded the protocol limit", "WorkerProtocolError");
            return;
        }
    }
    std::size_t newline = 0;
    while ((newline = buffer.find('\n')) != std::string::npos) {
        auto line = buffer.substr(0, newline);
        buffer.erase(0, newline + 1);
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;
        if (responses) HandleResponseLine(line);
        else Log("worker: " + wxString::FromUTF8(line));
    }
}

void WorkerClient::FailPending(const std::string& message, const std::string& type) {
    auto pending = std::move(callbacks_);
    callbacks_.clear();
    for (auto& [id, callback] : pending) {
        if (callback) callback({{"id", id}, {"ok", false}, {"error", message}, {"type", type}});
    }
}

void WorkerClient::HandleResponseLine(const std::string& line) {
    try {
        const auto response = nlohmann::json::parse(line);
        const auto id = response.value("id", "");
        const auto found = callbacks_.find(id);
        if (found == callbacks_.end()) {
            Log("Worker returned an unknown request id");
            return;
        }
        auto callback = std::move(found->second);
        callbacks_.erase(found);
        if (callback) callback(response);
    } catch (const std::exception& error) {
        Log("Malformed worker response: " + wxString::FromUTF8(error.what()));
    }
}

void WorkerClient::Log(const wxString& line) const {
    if (log_callback_) log_callback_(line);
}

}  // namespace spike::wxui
