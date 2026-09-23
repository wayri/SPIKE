#ifdef _WIN32
#define NOMINMAX
#include <winsock2.h>
#include <windows.h>
#include <ws2tcpip.h>

#include <filesystem>
#include <fstream>
#include <string>

int wmain(int argc, wchar_t **argv) {
  if (argc != 3) {
    return 64;
  }
  HANDLE forbidden = CreateFileW(argv[1], GENERIC_READ, FILE_SHARE_READ, nullptr,
                                 OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
  const DWORD file_error =
      forbidden == INVALID_HANDLE_VALUE ? GetLastError() : ERROR_SUCCESS;
  if (forbidden != INVALID_HANDLE_VALUE) {
    CloseHandle(forbidden);
  }
  const bool filesystem_denied =
      file_error == ERROR_ACCESS_DENIED || file_error == ERROR_FILE_NOT_FOUND ||
      file_error == ERROR_PATH_NOT_FOUND;

  WSADATA data{};
  bool network_denied = false;
  int network_error = 0;
  if (WSAStartup(MAKEWORD(2, 2), &data) == 0) {
    SOCKET socket_handle = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (socket_handle != INVALID_SOCKET) {
      sockaddr_in endpoint{};
      endpoint.sin_family = AF_INET;
      endpoint.sin_port = htons(9);
      InetPtonW(AF_INET, L"1.1.1.1", &endpoint.sin_addr);
      const int connected = connect(
          socket_handle, reinterpret_cast<const sockaddr *>(&endpoint),
          sizeof(endpoint));
      network_error = connected == SOCKET_ERROR ? WSAGetLastError() : 0;
      network_denied = connected == SOCKET_ERROR && network_error == WSAEACCES;
      closesocket(socket_handle);
    }
    WSACleanup();
  }
  std::ofstream output(std::filesystem::path(argv[2]),
                       std::ios::binary | std::ios::trunc);
  output << "{\"filesystem_denied\":"
         << (filesystem_denied ? "true" : "false")
         << ",\"filesystem_error\":" << file_error
         << ",\"network_denied\":" << (network_denied ? "true" : "false")
         << ",\"network_error\":" << network_error << "}";
  return filesystem_denied && network_denied && output ? 0 : 1;
}
#else
int main() { return 78; }
#endif
