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

function resourcesOf(root: THREE.Object3D): Resources {
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  const textures = new Set<THREE.Texture>();
  const buffers = new Set<ArrayBufferLike>();
  root.traverse(object => {
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
  for (const material of materials) for (const value of Object.values(material)) {
    if (value instanceof THREE.Texture) textures.add(value);
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

type Entry = { loading: Promise<THREE.Object3D>; resources?: Resources; users: number };

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

  private trim() {
    // Only inspect evictable sources. Scanning every pinned part on each load
    // would turn an assembly with many unique models into quadratic work.
    while (this.idle.size && (this.retainedBytes > this.maximumBytes || this.entries.size > this.maximumEntries)) {
      const [key, entry] = this.idle.entries().next().value!;
      this.idle.delete(key);
      this.entries.delete(key);
      this.retainedBytes -= entry.resources!.bytes;
      disposeResources(entry.resources!);
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
      const materials = new Map<THREE.Material, THREE.Material>();
      const independent = (material: THREE.Material) => {
        let copy = materials.get(material);
        if (!copy) { copy = material.clone(); materials.set(material, copy); }
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
        if (!pinned.users) this.idle.set(url, pinned);
        this.trim();
      });
      this.trim();
      return clone;
    } catch (error) {
      pinned.users -= 1;
      this.activeUsers -= 1;
      if (this.entries.get(url) === pinned && !pinned.resources) this.entries.delete(url);
      else if (!pinned.users && pinned.resources) this.idle.set(url, pinned);
      this.trim();
      throw error;
    }
  }
}
