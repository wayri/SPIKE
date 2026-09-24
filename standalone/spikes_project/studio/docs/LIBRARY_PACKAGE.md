# Data-only library packages and local store

`spikes_studio.library_package` preserves the `spikes/library-package/v1`
`.spklib` JSON exchange format. It contains bounded `records` and `symbols`
collections. Import validates their generic model families, execution status,
geometry, and metadata; it never executes model code or downloads dependencies.
These are generic engineering presets, not manufacturer-qualified parts.

`LibraryStore(root)` adds a local index without changing the exchange file.
The application chooses `root`. The `installed`, `project`, and `user` scopes
live in separate subdirectories. Each has an atomic `index.json` and
SHA-256-named, canonical JSON blobs under `blobs/`. The index tracks package
ID, semantic version, active version, bounded rollback history, and content
hash. IDs and versions are restricted to safe ASCII identifiers; neither is
used as a filesystem path. The index is limited to 2 MiB, 1,024 packages,
and 128 versions per package. Each exchange package is limited to 32 MiB.

```python
from spikes_studio.library_package import LibraryStore

store = LibraryStore(application_library_root)
store.import_package("incoming.spklib", "generic.passives", "1.0.0", scope="user")
records = store.get_package("generic.passives", scope="user")["records"]
store.export_package("shared.spklib", "generic.passives", scope="user")
store.activate("generic.passives", "1.0.0", scope="user")
```

A new import activates its version by default. Use `activate=False` to stage
it, `activate` to change the selected version, and `rollback` to restore the
previous active version. Re-importing identical content at the same ID/version
is idempotent; changed content at that identity is rejected. Reads and exports
verify stored bytes against their index hash before returning data. `search`
is a bounded, case-insensitive package-ID query (at most 1,000 results), not a
record-level search; the existing `CatalogIndex` handles record filtering.

The store does not merge active packages automatically. Callers must use
`merge` to detect conflicting record or symbol IDs before exposing a combined
catalog. A corrupted package should be re-imported from a trusted source;
recovery does not silently accept changed bytes. The index is not signed, so
the hash detects accidental or out-of-band blob changes but does not
authenticate a malicious actor able to rewrite the index and blobs together.
The application must choose and protect its own root directory. Concurrent
writers to one scope are not supported in this stage.
