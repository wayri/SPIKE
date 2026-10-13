// SPDX-License-Identifier: Apache-2.0

//! Development startup only. Packaged desktops use embedded assets.
use std::io::{Read, Write};
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr, TcpStream};
use std::time::{Duration, Instant};

const PROBE_BUDGET: Duration = Duration::from_secs(2);

fn endpoints(url: &tauri::Url) -> Result<Vec<SocketAddr>, String> {
    if url.scheme() != "http" || !url.username().is_empty() || url.password().is_some() {
        return Err(
            "Development readiness checks require an HTTP loopback URL without credentials".into(),
        );
    }
    let port = url
        .port_or_known_default()
        .ok_or("Development URL has no port")?;
    let hosts = match url.host_str() {
        Some("localhost") => vec![
            IpAddr::V6(Ipv6Addr::LOCALHOST),
            IpAddr::V4(Ipv4Addr::LOCALHOST),
        ],
        Some(host) => {
            let address: IpAddr = host
                .trim_matches(['[', ']'])
                .parse()
                .map_err(|_| "Development URL must use localhost or a loopback IP address")?;
            if !address.is_loopback() {
                return Err("Development URL must use a loopback address".into());
            }
            vec![address]
        }
        None => return Err("Development URL has no host".into()),
    };
    Ok(hosts
        .into_iter()
        .map(|ip| SocketAddr::new(ip, port))
        .collect())
}

fn read_status(reader: &mut impl Read) -> Result<(), String> {
    let mut line = Vec::new();
    // Bound both response storage and protocol parsing; a live TCP listener is
    // insufficient evidence that the frontend can serve a page.
    for _ in 0..256 {
        let mut byte = [0];
        if reader
            .read(&mut byte)
            .map_err(|e| format!("HTTP response failed: {e}"))?
            == 0
        {
            return Err("Development server closed before returning HTTP status".into());
        }
        line.push(byte[0]);
        if byte[0] == b'\n' {
            let text = String::from_utf8_lossy(&line);
            let mut parts = text.split_whitespace();
            return match (parts.next(), parts.next()) {
                (Some("HTTP/1.1" | "HTTP/1.0"), Some("200")) => Ok(()),
                _ => Err(format!("Development server returned {}", text.trim())),
            };
        }
    }
    Err("Development server HTTP status exceeded 256 bytes".into())
}

struct DeadlineReader {
    stream: TcpStream,
    deadline: Instant,
}

impl Read for DeadlineReader {
    fn read(&mut self, bytes: &mut [u8]) -> std::io::Result<usize> {
        let remaining = self
            .deadline
            .checked_duration_since(Instant::now())
            .filter(|duration| !duration.is_zero())
            .ok_or_else(|| {
                std::io::Error::new(std::io::ErrorKind::TimedOut, "development server deadline")
            })?;
        self.stream.set_read_timeout(Some(remaining))?;
        self.stream.read(bytes)
    }
}

fn probe(url: &tauri::Url) -> Result<(), String> {
    let mut errors = Vec::new();
    for endpoint in endpoints(url)? {
        match probe_endpoint(url, endpoint, PROBE_BUDGET) {
            Ok(()) => return Ok(()),
            Err(error) => errors.push(format!("{endpoint}: {error}")),
        }
    }
    Err(errors.join("\n"))
}

fn probe_endpoint(url: &tauri::Url, endpoint: SocketAddr, budget: Duration) -> Result<(), String> {
    let deadline = Instant::now() + budget;
    let mut stream = TcpStream::connect_timeout(&endpoint, budget)
        .map_err(|e| format!("connect failed: {e}"))?;
    let remaining = deadline
        .checked_duration_since(Instant::now())
        .filter(|duration| !duration.is_zero())
        .ok_or("Development connection deadline exceeded")?;
    stream
        .set_write_timeout(Some(remaining))
        .map_err(|e| e.to_string())?;
    let path = match url.query() {
        Some(query) => format!("{}?{query}", url.path()),
        None => url.path().to_string(),
    };
    let request = format!(
        "GET {path} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\n\r\n",
        url.authority()
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|e| format!("HTTP request failed: {e}"))?;
    read_status(&mut DeadlineReader { stream, deadline })
}

fn check_with_retry(
    mut check: impl FnMut() -> Result<(), String>,
    mut retry: impl FnMut(&str) -> bool,
) -> Result<(), String> {
    match check() {
        Ok(()) => Ok(()),
        Err(error) if retry(&error) => check(),
        Err(error) => Err(error),
    }
}

pub fn ensure_ready(url: Option<&tauri::Url>) -> bool {
    let Some(url) = url else {
        return true;
    };
    let mut retried = false;
    let result = check_with_retry(
        || probe(url),
        |error| {
            eprintln!("SPIKE development frontend unavailable at {url}: {error}");
            let response = rfd::MessageDialog::new()
            .set_title("SPIKE development frontend unavailable")
            .set_level(rfd::MessageLevel::Error)
            .set_description(format!("The development frontend at {url} did not respond.\n\nStart `npm run dev` from the app directory, then retry once. For normal development, use `npm run tauri dev` to start both processes. Packaged SPIKE uses embedded assets.\n\n{error}"))
            .set_buttons(rfd::MessageButtons::OkCancelCustom("Retry".into(), "Exit".into()))
            .show();
            retried = response == rfd::MessageDialogResult::Custom("Retry".into());
            retried
        },
    );
    if let Err(error) = result {
        eprintln!("SPIKE development startup stopped: {error}");
        if retried {
            rfd::MessageDialog::new()
                .set_title("SPIKE development startup stopped")
                .set_level(rfd::MessageLevel::Error)
                .set_description(format!("The frontend at {url} is still unavailable after retry. Start the local frontend server and launch SPIKE again.\n\n{error}"))
                .set_buttons(rfd::MessageButtons::Ok)
                .show();
        }
        return false;
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_loopback_http_is_probed() {
        for url in [
            "https://localhost:1420",
            "http://example.com:1420",
            "http://192.168.1.2:1420",
            "http://user:pass@localhost:1420",
        ] {
            assert!(
                endpoints(&tauri::Url::parse(url).unwrap()).is_err(),
                "{url}"
            );
        }
        for url in [
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "http://[::1]:1420",
        ] {
            assert!(endpoints(&tauri::Url::parse(url).unwrap())
                .unwrap()
                .iter()
                .all(|address| address.ip().is_loopback()));
        }
    }

    #[test]
    fn http_errors_empty_and_oversized_responses_fail() {
        assert!(read_status(&mut &b"HTTP/1.1 200 OK\r\n"[..]).is_ok());
        for bytes in [
            &b"HTTP/1.1 503 Unavailable\r\n"[..],
            &b""[..],
            &b"garbage\n"[..],
            &[b'a'; 257][..],
        ] {
            assert!(read_status(&mut &*bytes).is_err());
        }
    }

    #[test]
    fn timeout_is_reported_and_retry_can_recover() {
        struct Timeout;
        impl Read for Timeout {
            fn read(&mut self, _: &mut [u8]) -> std::io::Result<usize> {
                Err(std::io::Error::new(
                    std::io::ErrorKind::TimedOut,
                    "fixture timeout",
                ))
            }
        }
        assert!(read_status(&mut Timeout)
            .unwrap_err()
            .contains("fixture timeout"));
        let mut calls = 0;
        assert!(check_with_retry(
            || {
                calls += 1;
                if calls == 1 {
                    Err("offline".into())
                } else {
                    Ok(())
                }
            },
            |_| true
        )
        .is_ok());
        assert_eq!(calls, 2);
        calls = 0;
        assert!(check_with_retry(
            || {
                calls += 1;
                Err("offline".into())
            },
            |_| true
        )
        .is_err());
        assert_eq!(calls, 2);
        calls = 0;
        assert!(check_with_retry(
            || {
                calls += 1;
                Err("offline".into())
            },
            |_| false
        )
        .is_err());
        assert_eq!(calls, 1);
    }

    #[test]
    fn live_loopback_http_and_stalled_server_have_bounded_results() {
        use std::net::TcpListener;
        for respond in [true, false] {
            let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
            let endpoint = listener.local_addr().unwrap();
            let server = std::thread::spawn(move || {
                let (mut stream, _) = listener.accept().unwrap();
                stream
                    .set_read_timeout(Some(Duration::from_secs(1)))
                    .unwrap();
                let mut request = [0; 512];
                assert!(stream.read(&mut request).unwrap() > 0);
                if respond {
                    stream
                        .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
                        .unwrap();
                } else {
                    std::thread::sleep(Duration::from_millis(250));
                }
            });
            let url = tauri::Url::parse(&format!("http://{endpoint}/")).unwrap();
            let started = Instant::now();
            let result = probe_endpoint(&url, endpoint, Duration::from_millis(100));
            assert_eq!(result.is_ok(), respond, "{result:?}");
            assert!(started.elapsed() < Duration::from_secs(2));
            server.join().unwrap();
        }
    }
}
