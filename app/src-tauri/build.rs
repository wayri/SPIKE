fn main() {
    println!("cargo:rerun-if-env-changed=SPIKE_PACKAGE_TRUSTED_KEYS_JSON");
    println!("cargo:rerun-if-env-changed=SPIKE_PACKAGE_KEY_ID");
    println!("cargo:rerun-if-env-changed=SPIKE_PACKAGE_PUBLIC_KEY_B64URL");
    tauri_build::build()
}
