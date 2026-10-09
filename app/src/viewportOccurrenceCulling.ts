// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";

export type ViewportOccurrenceCullCandidate = {
  root: THREE.Object3D;
  /**
   * Caller-owned geometry revision. Increment it after late model children or
   * display geometry are attached; placement-only transforms reuse the cache.
   */
  geometryRevision: unknown;
};

export type ViewportOccurrenceCullPass = {
  tested: number;
  culled: number;
  cacheHits: number;
  cacheMisses: number;
  /** Restore every temporary visibility change. Safe to call more than once. */
  restore: () => void;
};

type CachedBounds = { geometryRevision: unknown; sphere: THREE.Sphere | null };

/**
 * Coarse, render-pass-only frustum culling for large occurrence subtrees.
 *
 * The cache retains only CPU bounding spheres in a WeakMap. It never clones,
 * disposes, uploads, or evicts geometry, materials, textures, or scene nodes.
 */
export class ViewportOccurrenceCuller {
  private bounds = new WeakMap<THREE.Object3D, CachedBounds>();
  private readonly viewProjection = new THREE.Matrix4();
  private readonly frustum = new THREE.Frustum();
  private readonly worldSphere = new THREE.Sphere();

  invalidate(root: THREE.Object3D): void {
    this.bounds.delete(root);
  }

  clear(): void {
    this.bounds = new WeakMap<THREE.Object3D, CachedBounds>();
  }

  begin(camera: THREE.Camera, candidates: readonly ViewportOccurrenceCullCandidate[]): ViewportOccurrenceCullPass {
    camera.updateWorldMatrix(true, false);
    this.viewProjection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    this.frustum.setFromProjectionMatrix(this.viewProjection);
    const changed: Array<{ root: THREE.Object3D; visible: boolean }> = [];
    const visited = new Set<THREE.Object3D>();
    let tested = 0, culled = 0, cacheHits = 0, cacheMisses = 0;

    for (const candidate of candidates) {
      const root = candidate.root;
      if (visited.has(root) || !root.visible) continue;
      visited.add(root);
      const cached = this.bounds.get(root);
      let localSphere: THREE.Sphere | null;
      if (cached && Object.is(cached.geometryRevision, candidate.geometryRevision)) {
        localSphere = cached.sphere;
        cacheHits += 1;
      } else {
        localSphere = occurrenceLocalSphere(root);
        this.bounds.set(root, { geometryRevision: candidate.geometryRevision, sphere: localSphere });
        cacheMisses += 1;
      }
      if (!localSphere) continue; // Unknown bounds fail open.
      root.updateWorldMatrix(true, false);
      this.worldSphere.copy(localSphere).applyMatrix4(root.matrixWorld);
      tested += 1;
      if (this.frustum.intersectsSphere(this.worldSphere)) continue;
      changed.push({ root, visible: root.visible });
      root.visible = false;
      culled += 1;
    }

    let restored = false;
    return {
      tested, culled, cacheHits, cacheMisses,
      restore: () => {
        if (restored) return;
        restored = true;
        for (let index = changed.length - 1; index >= 0; index -= 1) {
          const entry = changed[index];
          entry.root.visible = entry.visible;
        }
      },
    };
  }
}

function occurrenceLocalSphere(root: THREE.Object3D): THREE.Sphere | null {
  root.updateWorldMatrix(true, true);
  const inverseRoot = root.matrixWorld.clone().invert();
  const relative = new THREE.Matrix4();
  const localBox = new THREE.Box3();
  let unsupportedAnimatedGeometry = false;

  root.traverse(object => {
    if (unsupportedAnimatedGeometry) return;
    if (object instanceof THREE.SkinnedMesh
      || object instanceof THREE.Mesh && object.morphTargetInfluences !== undefined) {
      unsupportedAnimatedGeometry = true;
      return;
    }
    const geometry = (object as THREE.Mesh | THREE.Line | THREE.Points).geometry;
    if (!(geometry instanceof THREE.BufferGeometry)) return;
    let sourceBounds: THREE.Box3 | null;
    if (object instanceof THREE.InstancedMesh) {
      if (object.boundingBox === null) object.computeBoundingBox();
      sourceBounds = object.boundingBox;
    } else {
      if (geometry.boundingBox === null) geometry.computeBoundingBox();
      sourceBounds = geometry.boundingBox;
    }
    if (!sourceBounds || sourceBounds.isEmpty()) return;
    relative.multiplyMatrices(inverseRoot, object.matrixWorld);
    localBox.union(sourceBounds.clone().applyMatrix4(relative));
  });

  if (unsupportedAnimatedGeometry || localBox.isEmpty()) return null;
  const sphere = localBox.getBoundingSphere(new THREE.Sphere());
  return sphere.center.toArray().every(Number.isFinite) && Number.isFinite(sphere.radius) ? sphere : null;
}
