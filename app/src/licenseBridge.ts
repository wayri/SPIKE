import { invoke } from "@tauri-apps/api/core";
import type { AppSettings } from "./appSettings";

export type NativeLicense = AppSettings["license"];

export type DeviceLicenseRequest = {
  schema: "spike/license-device-request/v1";
  devicePublicKeySha256: string;
  product: "SPIKE";
  productMajor: number;
};

function hasNativeHost(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function readNativeLicense(): Promise<NativeLicense> {
  if (!hasNativeHost()) {
    return {
      tier: "evaluation",
      status: "unlicensed",
      licensee: "Browser preview",
      source: "none",
      expiresAt: null,
      capabilities: ["project.read"],
      errorCode: "SPIKE-FE-SECURITY-E-0001",
      message: "License verification requires the SPIKE desktop host.",
    };
  }
  return invoke<NativeLicense>("license_status");
}

export async function activateNativeLicense(entitlementJson: string): Promise<NativeLicense> {
  if (!hasNativeHost()) throw new Error("SPIKE-FE-SECURITY-E-0001: license activation requires the SPIKE desktop host");
  return invoke<NativeLicense>("license_activate", { entitlementJson });
}

export async function deactivateNativeLicense(): Promise<NativeLicense> {
  if (!hasNativeHost()) throw new Error("SPIKE-FE-SECURITY-E-0001: license deactivation requires the SPIKE desktop host");
  return invoke<NativeLicense>("license_deactivate");
}

export async function readDeviceLicenseRequest(): Promise<DeviceLicenseRequest> {
  if (!hasNativeHost()) throw new Error("SPIKE-FE-SECURITY-E-0001: device binding requires the SPIKE desktop host");
  return invoke<DeviceLicenseRequest>("license_device_request");
}

/** Raw signed entitlement installed on this machine, for a portable backup file. */
export async function exportNativeLicense(): Promise<string> {
  if (!hasNativeHost()) throw new Error("SPIKE-FE-SECURITY-E-0001: license export requires the SPIKE desktop host");
  return invoke<string>("license_file_export");
}
