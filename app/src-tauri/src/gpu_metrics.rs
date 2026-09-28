//! OS counters only. GPU busy time is the busiest physical engine, never a sum
//! of unrelated engines or an estimate based on rendering frame rate.
use serde::Serialize;
use std::collections::{HashMap, HashSet};

#[derive(Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GpuSnapshot {
    pub source: &'static str,
    pub status: &'static str,
    pub system_percent: Option<f64>,
    pub process_percent: Option<f64>,
    pub dedicated_memory_bytes: Option<u64>,
    pub shared_memory_bytes: Option<u64>,
}

fn engine_usage(values: &[(String, f64)], pids: Option<&HashSet<u32>>) -> Option<f64> {
    let mut engines = HashMap::<&str, f64>::new();
    for (name, value) in values {
        if !value.is_finite() || *value < 0.0 {
            continue;
        }
        let Some(rest) = name.strip_prefix("pid_") else {
            continue;
        };
        let Some((pid, engine)) = rest.split_once('_') else {
            continue;
        };
        let Ok(pid) = pid.parse::<u32>() else {
            continue;
        };
        if pids.is_some_and(|set| !set.contains(&pid)) {
            continue;
        }
        *engines.entry(engine).or_default() += value;
    }
    // Empty process matches mean idle, provided the OS query itself succeeded.
    Some(
        engines
            .values()
            .copied()
            .fold(0.0, f64::max)
            .clamp(0.0, 100.0),
    )
}

fn process_memory(values: &[(String, f64)], pids: &HashSet<u32>) -> u64 {
    values
        .iter()
        .filter(|(name, value)| {
            value.is_finite()
                && *value >= 0.0
                && name
                    .strip_prefix("pid_")
                    .and_then(|rest| rest.split('_').next())
                    .and_then(|pid| pid.parse::<u32>().ok())
                    .is_some_and(|pid| pids.contains(&pid))
        })
        .fold(0_u64, |sum, (_, value)| sum.saturating_add(*value as u64))
}

#[cfg(target_os = "windows")]
mod platform {
    use super::*;
    use std::{mem::size_of, ptr};
    #[repr(C)]
    struct Value {
        status: u32,
        value: f64,
    }
    #[repr(C)]
    struct Item {
        name: *const u16,
        value: Value,
    }
    #[link(name = "pdh")]
    extern "system" {
        fn PdhOpenQueryW(source: *const u16, data: usize, query: *mut isize) -> u32;
        fn PdhAddEnglishCounterW(
            query: isize,
            path: *const u16,
            data: usize,
            counter: *mut isize,
        ) -> u32;
        fn PdhCollectQueryData(query: isize) -> u32;
        fn PdhGetFormattedCounterArrayW(
            counter: isize,
            format: u32,
            bytes: *mut u32,
            count: *mut u32,
            buffer: *mut Item,
        ) -> u32;
        fn PdhCloseQuery(query: isize) -> u32;
    }
    pub struct Sampler {
        query: isize,
        counters: [isize; 5],
        warmed: bool,
    }
    impl Default for Sampler {
        fn default() -> Self {
            let mut result = Self {
                query: 0,
                counters: [0; 5],
                warmed: false,
            };
            unsafe {
                if PdhOpenQueryW(ptr::null(), 0, &mut result.query) != 0 {
                    return result;
                }
                for (index, path) in [
                    r"\GPU Engine(*)\Utilization Percentage",
                    r"\GPU Process Memory(*)\Dedicated Usage",
                    r"\GPU Process Memory(*)\Shared Usage",
                    r"\Process(*)\ID Process",
                    r"\Process(*)\Working Set - Private",
                ]
                .iter()
                .enumerate()
                {
                    let wide: Vec<u16> = path.encode_utf16().chain(Some(0)).collect();
                    if PdhAddEnglishCounterW(
                        result.query,
                        wide.as_ptr(),
                        0,
                        &mut result.counters[index],
                    ) != 0
                    {
                        result.counters[index] = 0;
                    }
                }
            }
            result
        }
    }
    impl Drop for Sampler {
        fn drop(&mut self) {
            if self.query != 0 {
                unsafe {
                    PdhCloseQuery(self.query);
                }
            }
        }
    }
    fn read(counter: isize) -> Option<Vec<(String, f64)>> {
        if counter == 0 {
            return None;
        }
        // Process lists can change between sizing and reading. Retry with a
        // fresh sizing call and enforce a bounded, correctly aligned buffer.
        for _ in 0..3 {
            let mut bytes = 0_u32;
            let mut count = 0_u32;
            unsafe {
                let status = PdhGetFormattedCounterArrayW(
                    counter,
                    0x200,
                    &mut bytes,
                    &mut count,
                    ptr::null_mut(),
                );
                if status == 0 && bytes == 0 {
                    return Some(Vec::new());
                }
                if status != 0x800007d2 || bytes == 0 || bytes > 32 * 1024 * 1024 {
                    return None;
                }
                let mut buffer = vec![0_u64; (bytes as usize + 7) / 8];
                let status = PdhGetFormattedCounterArrayW(
                    counter,
                    0x200,
                    &mut bytes,
                    &mut count,
                    buffer.as_mut_ptr().cast(),
                );
                if status == 0x800007d2 {
                    continue;
                }
                if status != 0 || count as usize * size_of::<Item>() > bytes as usize {
                    return None;
                }
                let begin = buffer.as_ptr() as usize;
                let end = begin + bytes as usize;
                let mut result = Vec::new();
                for item in
                    std::slice::from_raw_parts(buffer.as_ptr().cast::<Item>(), count as usize)
                {
                    if item.value.status > 1 || !item.value.value.is_finite() {
                        continue;
                    }
                    let address = item.name as usize;
                    if address < begin || address >= end || address % 2 != 0 {
                        continue;
                    }
                    let text =
                        std::slice::from_raw_parts(item.name, ((end - address) / 2).min(4096));
                    let Some(length) = text.iter().position(|value| *value == 0) else {
                        continue;
                    };
                    result.push((String::from_utf16_lossy(&text[..length]), item.value.value));
                }
                if count > 0 && result.is_empty() {
                    return None;
                }
                return Some(result);
            }
        }
        None
    }
    impl Sampler {
        pub fn sample(&mut self, pids: &HashSet<u32>) -> (GpuSnapshot, Option<u64>) {
            let mut gpu = GpuSnapshot {
                source: "windows-pdh",
                status: "unavailable",
                ..Default::default()
            };
            if self.query == 0 || unsafe { PdhCollectQueryData(self.query) } != 0 {
                return (gpu, None);
            }
            let private =
                read(self.counters[3])
                    .zip(read(self.counters[4]))
                    .and_then(|(ids, memory)| {
                        let instances: HashMap<_, _> = ids
                            .into_iter()
                            .map(|(name, id)| (name, id as u32))
                            .collect();
                        let mut found = HashSet::new();
                        let mut total = 0_u64;
                        for (name, bytes) in memory {
                            if let Some(pid) = instances.get(&name) {
                                if pids.contains(pid) && bytes >= 0.0 && found.insert(*pid) {
                                    total = total.saturating_add(bytes as u64);
                                }
                            }
                        }
                        // Do not publish a misleading partial sum when access was denied.
                        (found.len() == pids.len()).then_some(total)
                    });
            if self.warmed {
                if let Some(engines) = read(self.counters[0]) {
                    gpu.status = "available";
                    gpu.system_percent = engine_usage(&engines, None);
                    gpu.process_percent = engine_usage(&engines, Some(pids));
                }
                gpu.dedicated_memory_bytes =
                    read(self.counters[1]).map(|values| process_memory(&values, pids));
                gpu.shared_memory_bytes =
                    read(self.counters[2]).map(|values| process_memory(&values, pids));
            } else {
                gpu.status = "warming_up";
            }
            self.warmed = true;
            (gpu, private)
        }
    }
}

#[cfg(not(target_os = "windows"))]
mod platform {
    use super::*;
    #[derive(Default)]
    pub struct Sampler;
    impl Sampler {
        pub fn sample(&mut self, _: &HashSet<u32>) -> (GpuSnapshot, Option<u64>) {
            (
                GpuSnapshot {
                    source: "unavailable",
                    status: "unavailable",
                    ..Default::default()
                },
                None,
            )
        }
    }
}
pub use platform::Sampler;

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn gpu_aggregates_processes_per_engine_not_across_engines() {
        let values = vec![
            ("pid_1_luid_A_phys_0_eng_0_engtype_3D".into(), 40.0),
            ("pid_2_luid_A_phys_0_eng_0_engtype_3D".into(), 35.0),
            ("pid_1_luid_A_phys_0_eng_1_engtype_Copy".into(), 65.0),
            ("pid_1_luid_B_phys_0_eng_0_engtype_3D".into(), 20.0),
        ];
        assert_eq!(engine_usage(&values, None), Some(75.0));
        assert_eq!(engine_usage(&values, Some(&HashSet::from([1]))), Some(65.0));
        assert_eq!(engine_usage(&values, Some(&HashSet::from([9]))), Some(0.0));
        assert_eq!(
            process_memory(&[("pid_1_luid_A".into(), 4096.0)], &HashSet::from([2])),
            0
        );
    }
    #[test]
    #[ignore = "live OS counter smoke check"]
    fn live_counters() {
        let mut sampler = Sampler::default();
        let pids = HashSet::from([std::process::id()]);
        sampler.sample(&pids);
        std::thread::sleep(std::time::Duration::from_millis(1100));
        let (gpu, private) = sampler.sample(&pids);
        println!(
            "GPU={} private_resident_bytes={private:?}",
            serde_json::to_string(&gpu).unwrap()
        );
        for value in [gpu.system_percent, gpu.process_percent]
            .into_iter()
            .flatten()
        {
            assert!((0.0..=100.0).contains(&value));
        }
    }
}
