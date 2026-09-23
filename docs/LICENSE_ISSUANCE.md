# License Issuance

SPIKE entitlements are signed offline with the isolated issuer utility in
`tools/license-issuer`. The issuer is a separate Rust package and is never a
binary target, resource, or dependency of the desktop application.

This procedure is suitable for engineering previews and internal development.
Production issuance additionally requires an activation service, protected key
management, revocation, audit retention, recovery policy, and security review.

## Create an issuer key

Store the private key outside the repository, build tree, synchronized project
folders, and installer inputs:

```powershell
cargo run --manifest-path tools/license-issuer/Cargo.toml -- `
  init D:\SPIKE-Secrets\preview-issuer.key
```

The command prints `SPIKE_LICENSE_PUBLIC_KEY_B64URL` and
`SPIKE_LICENSE_KEY_ID`. Put only those public values into the controlled desktop
build environment. Never put the private key in source control or a CI log.

The engineering-preview build reads its checked-in public key from
`config/license-preview-public.json`. On the designated development machine the
matching private key is stored outside the repository at
`%LOCALAPPDATA%\SPIKE\issuer\preview-issuer.key`. That key is for preview and
internal development entitlements only; it is not a commercial production root.

## Create claims

The issuer validates the claim document before signing. Unknown claim fields,
invalid device-binding hashes, missing expiry for temporary/timed/developer
licenses, and a developer license without the developer tier are rejected.

Create a JSON document conforming to
`schemas/license-entitlement-v1.schema.json`. Obtain the target binding from
**Settings > License > Export device request**. A machine-and-user entitlement
must use the exact binding digest from that request.

Temporary and timed licenses require an expiry. Developer licenses must be
named, signed, machine-and-user bound, and time limited. Production builds have
no unsigned developer bypass.

## Sign an entitlement

```powershell
cargo run --manifest-path tools/license-issuer/Cargo.toml -- `
  issue D:\SPIKE-Secrets\preview-issuer.key `
  D:\SPIKE-Issuance\claims.json `
  D:\SPIKE-Issuance\entitlement.json `
  spike-license-root-v1
```

The issuer refuses to overwrite an existing private key or entitlement. Deliver
only the generated entitlement to the licensed user. Retain the claims, license
ID, device request digest, issuance time, and operator identity in the licensing
audit system.

## One-seat boundary

The desktop cryptographically rejects a valid entitlement on a different
machine or operating-system user. An offline file cannot prevent an issuer from
creating two different valid licenses for one purchased seat. Strict one-seat
assignment therefore remains a server-side atomic activation and revocation
requirement for commercial production.

## Key rotation

The current contract carries `key_id`, but production rotation is not complete.
Do not replace a trusted public key in an already distributed build without a
documented overlap, revocation, rollback, and customer-recovery procedure.
