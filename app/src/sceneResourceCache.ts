import * as THREE from "three";

type Resources = {
  geometries: Set<THREE.BufferGeometry>;
  materials: Set<THREE.Material>;
  textures: Set<THREE.Texture>;
  bytes: number;
};
const sharedGeometries = new WeakSet<THREE.BufferGeometry>();
const sharedTextures = new WeakSet<THREE.Texture>();
const releases = new WeakMap<THREE.Object3D, () => void>();

function collectNestedTextures(value: unknown, textures: Set<THREE.Texture>, visited: Set<object>) {
  if (value instanceof THREE.Texture) { textures.add(value); return; }
  if (!value || typeof value !== "object" || visited.has(value)) return;
  visited.add(value);
  if (Array.isArray(value)) value.forEach(item => collectNestedTextures(item, textures, visited));
  else Object.values(value).forEach(item => collectNestedTextures(item, textures, visited));
}

function restoreSharedNestedTextures(copy: unknown, source: unknown, visited: WeakMap<object, WeakSet<object>>): unknown {
  if (source instanceof THREE.Texture) return source;
  if (!copy || !source || typeof copy !== "object" || typeof source !== "object") return copy;
  let destinations = visited.get(source);
  if (destinations?.has(copy)) return copy;
  if (!destinations) { destinations = new WeakSet<object>(); visited.set(source, destinations); }
  destinations.add(copy);
  if (Array.isArray(copy) && Array.isArray(source)) {
    for (let index = 0; index < Math.min(copy.length, source.length); index++) {
      const restored = restoreSharedNestedTextures(copy[index], source[index], visited);
      if (restored !== copy[index]) copy[index] = restored;
    }
  } else {
    for (const key of Object.keys(source)) if (key in copy) {
      const target = copy as Record<string, unknown>;
      const original = source as Record<string, unknown>;
      const restored = restoreSharedNestedTextures(target[key], original[key], visited);
      if (restored !== target[key]) target[key] = restored;
    }
  }
  return copy;
}

function restoreSharedSceneTextures(copy: THREE.Object3D, source: THREE.Object3D) {
  if (copy instanceof THREE.Scene && source instanceof THREE.Scene) {
    if (source.background instanceof THREE.Texture) copy.background = source.background;
    if (source.environment instanceof THREE.Texture) copy.environment = source.environment;
  }
  for (let index = 0; index < Math.min(copy.children.length, source.children.length); index++) {
    restoreSharedSceneTextures(copy.children[index], source.children[index]);
  }
}

function resourcesOf(root: THREE.Object3D): Resources {
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();
  const buffers = new Set<ArrayBufferLike>();
  root.traverse(object => {
    if (object instanceof THREE.Scene) {
      if (object.background instanceof THREE.Texture) textures.add(object.background);
      if (object.environment instanceof THREE.Texture) textures.add(object.environment);
    }
    if (object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Points) {
      geometries.add(object.geometry);
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) materials.add(material);
    } else if (object instanceof THREE.Sprite) materials.add(object.material);
  });
  for (const geometry of geometries) {
    const attributes = [...Object.values(geometry.attributes), ...Object.values(geometry.morphAttributes).flat()];
    if (geometry.index) attributes.push(geometry.index);
    for (const attribute of attributes) buffers.add(attribute.array.buffer);
  }
  let bytes = 0;
  buffers.forEach(buffer => { bytes += buffer.byteLength; });
  for (const material of materials) {
    for (const value of Object.values(material)) if (value instanceof THREE.Texture) textures.add(value);
    if (material instanceof THREE.ShaderMaterial) {
      const visited = new Set<object>();
      collectNestedTextures(material.uniforms, textures, visited);
      collectNestedTextures(material.uniformsGroups, textures, visited);
    }
  }
  // Include decoded texture storage (plus mipmaps), rather than compressed GLB size.
  for (const texture of textures) {
    const images = Array.isArray(texture.image) ? texture.image : [texture.image];
    for (const image of images) if (image) bytes += Math.ceil((image.data?.byteLength ?? (image.width || 0) * (image.height || 0) * 4) * 4 / 3);
  }
  return { geometries, materials, textures, bytes };
}

function disposeResources(resources: Resources) {
  resources.geometries.forEach(geometry => geometry.dispose());
  resources.materials.forEach(material => material.dispose());
  resources.textures.forEach(texture => texture.dispose());
}

/** Dispose owned resources once, then release any cached scenes below this root.
 * Live occurrences share immutable geometry/textures, but own their materials.
 */
export function disposeScene(root: THREE.Object3D) {
  const release: (() => void)[] = [];
  root.traverse(object => {
    if (object instanceof THREE.InstancedMesh) object.dispose();
    const callback = releases.get(object);
    if (callback) { releases.delete(object); release.push(callback); }
  });
  const resources = resourcesOf(root);
  resources.geometries.forEach(geometry => { if (!sharedGeometries.has(geometry)) geometry.dispose(); });
  resources.materials.forEach(material => material.dispose());
  resources.textures.forEach(texture => { if (!sharedTextures.has(texture)) texture.dispose(); });
  root.clear();
  release.forEach(callback => callback());
}

type Entry = { loading: Promise<THREE.Object3D>; resources?: Resources; users: number; releaseWhenIdle?: boolean };

/** LRU retention budget. Active scenes are pinned and released when their last
 * occurrence leaves the viewport; eviction never invalidates another part.
 */
export class SceneResourceCache {
  private readonly entries = new Map<string, Entry>();
  private readonly idle = new Map<string, Entry>();
  private retainedBytes = 0;
  private activeUsers = 0;
  private readonly load: (url: string) => Promise<THREE.Object3D>;
  private readonly maximumBytes: number;
  private readonly maximumEntries: number;
  constructor(load: (url: string) => Promise<THREE.Object3D>, maximumBytes = 256 * 1024 ** 2, maximumEntries = 24) {
    this.load = load;
    this.maximumBytes = maximumBytes;
    this.maximumEntries = maximumEntries;
  }

  get stats() {
    return { entries: this.entries.size, bytes: this.retainedBytes, users: this.activeUsers };
  }

  /** Drop retained sources when a viewport closes. Active clones and pending
   * loads remain pinned; their sources are released after the final user exits.
   * New loads after this call use the normal retention budget.
   */
  releaseIdle() {
    for (const [key, entry] of this.entries) {
      entry.releaseWhenIdle = true;
      if (!entry.users && entry.resources) this.evict(key, entry);
    }
  }

  private evict(key: string, entry: Entry) {
    if (entry.users || !entry.resources || this.entries.get(key) !== entry) return;
    this.idle.delete(key);
    this.entries.delete(key);
    this.retainedBytes -= entry.resources.bytes;
    disposeResources(entry.resources);
  }

  private retainOrRelease(key: string, entry: Entry) {
    if (entry.users || !entry.resources) return;
    if (entry.releaseWhenIdle) this.evict(key, entry);
    else this.idle.set(key, entry);
  }

  private trim() {
    // Only inspect evictable sources. Scanning every pinned part on each load
    // would turn an assembly with many unique models into quadratic work.
    while (this.idle.size && (this.retainedBytes > this.maximumBytes || this.entries.size > this.maximumEntries)) {
      const [key, entry] = this.idle.entries().next().value!;
      this.evict(key, entry);
    }
  }

  async clone(url: string): Promise<THREE.Object3D> {
    let entry = this.entries.get(url);
    if (!entry) {
      entry = { loading: Promise.resolve().then(() => this.load(url)), users: 0 };
      const created = entry;
      created.loading = created.loading.then(source => {
        created.resources = resourcesOf(source);
        this.retainedBytes += created.resources.bytes;
        created.resources.geometries.forEach(geometry => sharedGeometries.add(geometry));
        created.resources.textures.forEach(texture => sharedTextures.add(texture));
        return source;
      });
    }
    this.entries.delete(url);
    this.entries.set(url, entry);
    this.idle.delete(url);
    entry.users += 1;
    this.activeUsers += 1;
    const pinned = entry;
    try {
      const source = await entry.loading;
      const clone = source.clone(true);
      restoreSharedSceneTextures(clone, source);
      const materials = new Map<THREE.Material, THREE.Material>();
      const independent = (material: THREE.Material) => {
        let copy = materials.get(material);
        if (!copy) {
          copy = material.clone();
          if (material instanceof THREE.ShaderMaterial && copy instanceof THREE.ShaderMaterial) {
            restoreSharedNestedTextures(copy.uniforms, material.uniforms, new WeakMap<object, WeakSet<object>>());
            restoreSharedNestedTextures(copy.uniformsGroups, material.uniformsGroups, new WeakMap<object, WeakSet<object>>());
          }
          materials.set(material, copy);
        }
        return copy;
      };
      clone.traverse(object => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Points) {
          object.material = Array.isArray(object.material) ? object.material.map(independent) : independent(object.material);
        } else if (object instanceof THREE.Sprite) object.material = independent(object.material) as THREE.SpriteMaterial;
      });
      releases.set(clone, () => {
        pinned.users -= 1;
        this.activeUsers -= 1;
        this.retainOrRelease(url, pinned);
        this.trim();
      });
      this.trim();
      return clone;
    } catch (error) {
      pinned.users -= 1;
      this.activeUsers -= 1;
      if (this.entries.get(url) === pinned && !pinned.resources) this.entries.delete(url);
      else this.retainOrRelease(url, pinned);
      this.trim();
      throw error;
    }
  }
}
