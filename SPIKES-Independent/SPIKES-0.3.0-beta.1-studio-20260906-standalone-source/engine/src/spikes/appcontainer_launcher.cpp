#ifdef _WIN32

#define NOMINMAX
#include <windows.h>
#include <aclapi.h>
#include <userenv.h>

#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr wchar_t profile_name[] = L"SPIKESHostileModelSandboxV1";

std::wstring quote(std::wstring_view value) {
  if (value.find_first_of(L" \t\"") == std::wstring_view::npos) {
    return std::wstring(value);
  }
  std::wstring result = L"\"";
  std::size_t backslashes = 0;
  for (const wchar_t character : value) {
    if (character == L'\\') {
      ++backslashes;
    } else if (character == L'\"') {
      result.append(backslashes * 2 + 1, L'\\');
      result.push_back(L'\"');
      backslashes = 0;
    } else {
      result.append(backslashes, L'\\');
      backslashes = 0;
      result.push_back(character);
    }
  }
  result.append(backslashes * 2, L'\\');
  result.push_back(L'\"');
  return result;
}

void grant_path(const std::filesystem::path &path, PSID sid, DWORD access,
                DWORD inheritance) {
  PACL old_dacl = nullptr;
  PSECURITY_DESCRIPTOR descriptor = nullptr;
  const DWORD read_status = GetNamedSecurityInfoW(
      const_cast<wchar_t *>(path.c_str()), SE_FILE_OBJECT,
      DACL_SECURITY_INFORMATION, nullptr, nullptr, &old_dacl, nullptr,
      &descriptor);
  if (read_status != ERROR_SUCCESS) {
    throw std::runtime_error("cannot read staging ACL");
  }
  EXPLICIT_ACCESSW entry{};
  entry.grfAccessPermissions = access;
  entry.grfAccessMode = GRANT_ACCESS;
  entry.grfInheritance = inheritance;
  BuildTrusteeWithSidW(&entry.Trustee, sid);
  PACL updated = nullptr;
  const DWORD merge_status = SetEntriesInAclW(1, &entry, old_dacl, &updated);
  if (merge_status != ERROR_SUCCESS) {
    LocalFree(descriptor);
    throw std::runtime_error("cannot construct staging ACL");
  }
  const DWORD write_status = SetNamedSecurityInfoW(
      const_cast<wchar_t *>(path.c_str()), SE_FILE_OBJECT,
      DACL_SECURITY_INFORMATION, nullptr, nullptr, updated, nullptr);
  LocalFree(updated);
  LocalFree(descriptor);
  if (write_status != ERROR_SUCCESS) {
    throw std::runtime_error("cannot apply staging ACL");
  }
}

PSID sandbox_sid() {
  PSID sid = nullptr;
  const HRESULT created = CreateAppContainerProfile(
      profile_name, L"SPIKES hostile-model sandbox",
      L"Network-denied, staged-files-only model worker", nullptr, 0, &sid);
  if (SUCCEEDED(created)) {
    return sid;
  }
  const HRESULT derived =
      DeriveAppContainerSidFromAppContainerName(profile_name, &sid);
  if (FAILED(derived)) {
    throw std::runtime_error(
        "cannot create or derive AppContainer profile (HRESULT=" +
        std::to_string(static_cast<unsigned long>(created)) +
        ", derive=" + std::to_string(static_cast<unsigned long>(derived)) +
        ")");
  }
  return sid;
}

} // namespace

int wmain(int argc, wchar_t **argv) {
  if (argc < 2) {
    std::wcerr << L"usage: spikes_appcontainer_launcher CHILD [ARGS...]\n";
    return 64;
  }
  try {
    const auto child = std::filesystem::canonical(argv[1]);
    const auto working_directory = std::filesystem::current_path();
    if (child.parent_path() != working_directory) {
      throw std::invalid_argument(
          "AppContainer child must be staged directly in its working directory");
    }
    PSID sid = sandbox_sid();
    try {
      grant_path(working_directory, sid,
                 FILE_GENERIC_READ | FILE_GENERIC_WRITE | FILE_GENERIC_EXECUTE |
                     DELETE,
                 SUB_CONTAINERS_AND_OBJECTS_INHERIT);
      grant_path(child, sid, FILE_GENERIC_READ | FILE_GENERIC_EXECUTE,
                 NO_INHERITANCE);
      for (const auto &entry :
           std::filesystem::recursive_directory_iterator(working_directory)) {
        grant_path(entry.path(), sid,
                   entry.is_directory()
                       ? FILE_GENERIC_READ | FILE_GENERIC_WRITE |
                             FILE_GENERIC_EXECUTE | DELETE
                       : FILE_GENERIC_READ | FILE_GENERIC_EXECUTE,
                   entry.is_directory() ? SUB_CONTAINERS_AND_OBJECTS_INHERIT
                                        : NO_INHERITANCE);
      }

      SECURITY_CAPABILITIES security{};
      security.AppContainerSid = sid;
      SIZE_T attribute_size = 0;
      InitializeProcThreadAttributeList(nullptr, 1, 0, &attribute_size);
      std::vector<std::byte> attribute_storage(attribute_size);
      auto *attributes = reinterpret_cast<PPROC_THREAD_ATTRIBUTE_LIST>(
          attribute_storage.data());
      if (!InitializeProcThreadAttributeList(attributes, 1, 0,
                                             &attribute_size) ||
          !UpdateProcThreadAttribute(
              attributes, 0, PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
              &security, sizeof(security), nullptr, nullptr)) {
        throw std::runtime_error("cannot configure AppContainer attributes");
      }

      std::wstring command_line;
      for (int index = 1; index < argc; ++index) {
        if (!command_line.empty()) {
          command_line.push_back(L' ');
        }
        command_line += quote(argv[index]);
      }
      std::vector<wchar_t> mutable_command(command_line.begin(),
                                           command_line.end());
      mutable_command.push_back(L'\0');
      STARTUPINFOEXW startup{};
      startup.StartupInfo.cb = sizeof(startup);
      startup.lpAttributeList = attributes;
      PROCESS_INFORMATION process{};
      const DWORD creation_flags =
          EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED |
          CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW;
      if (!CreateProcessW(nullptr, mutable_command.data(), nullptr, nullptr,
                          FALSE, creation_flags, nullptr,
                          working_directory.c_str(), &startup.StartupInfo,
                          &process)) {
        const DWORD error = GetLastError();
        DeleteProcThreadAttributeList(attributes);
        throw std::runtime_error("cannot create AppContainer child (Win32=" +
                                 std::to_string(error) + ")");
      }
      DeleteProcThreadAttributeList(attributes);

      HANDLE job = CreateJobObjectW(nullptr, nullptr);
      if (job == nullptr) {
        TerminateProcess(process.hProcess, 70);
        throw std::runtime_error("cannot create sandbox job object");
      }
      JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
      limits.BasicLimitInformation.LimitFlags =
          JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_ACTIVE_PROCESS |
          JOB_OBJECT_LIMIT_PROCESS_MEMORY;
      limits.BasicLimitInformation.ActiveProcessLimit = 1;
      limits.ProcessMemoryLimit = 512ULL * 1024ULL * 1024ULL;
      if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                   &limits, sizeof(limits)) ||
          !AssignProcessToJobObject(job, process.hProcess)) {
        TerminateProcess(process.hProcess, 70);
        CloseHandle(job);
        throw std::runtime_error("cannot bind AppContainer child to job");
      }
      ResumeThread(process.hThread);
      WaitForSingleObject(process.hProcess, INFINITE);
      DWORD exit_code = 70;
      GetExitCodeProcess(process.hProcess, &exit_code);
      CloseHandle(process.hThread);
      CloseHandle(process.hProcess);
      CloseHandle(job);
      FreeSid(sid);
      return static_cast<int>(exit_code);
    } catch (...) {
      FreeSid(sid);
      throw;
    }
  } catch (const std::exception &error) {
    std::cerr << "SPIKES AppContainer launch failed: " << error.what() << '\n';
    return 70;
  }
}

#else
int main() { return 78; }
#endif
