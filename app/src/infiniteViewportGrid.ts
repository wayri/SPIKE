// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import { viewportBackgroundColor, type ViewportBackground } from "./viewportEnvironment";

/** Two triangles, no world-size tessellation, textures, animation, or fit/pick bounds.
 * Ray/plane intersections are presentation only and never simulation geometry.
 */
export function createInfiniteViewportGrid(floorZ: number, background: ViewportBackground): THREE.Mesh {
  const material = new THREE.ShaderMaterial({
    // Opaque background queue: behind opaque AND translucent board/results.
    transparent: false, depthTest: false, depthWrite: false,
    uniforms: {
      inverseProjection: { value: new THREE.Matrix4() }, cameraWorld: { value: new THREE.Matrix4() },
      floorZ: { value: floorZ }, spacing: { value: 1 },
      ink: { value: new THREE.Color(background === "light" ? "#456575" : "#789da9") },
      ground: { value: new THREE.Color(viewportBackgroundColor(background)) },
    },
    vertexShader: `
      varying vec2 screenPoint;
      void main() { screenPoint = position.xy; gl_Position = vec4(position.xy, 1.0, 1.0); }
    `,
    fragmentShader: `
      uniform mat4 inverseProjection, cameraWorld;
      uniform float floorZ, spacing;
      uniform vec3 ink, ground;
      varying vec2 screenPoint;
      float lines(vec2 p) {
        vec2 derivative = max(fwidth(p), vec2(0.00001));
        vec2 distanceToLine = abs(fract(p - 0.5) - 0.5) / derivative;
        float coverage = 1.0 - min(min(distanceToLine.x, distanceToLine.y), 1.0);
        // Suppress subpixel grids rather than aliasing at grazing angles.
        return coverage * (1.0 - smoothstep(0.4, 1.5, max(derivative.x, derivative.y)));
      }
      void main() {
        vec4 a = inverseProjection * vec4(screenPoint, -1.0, 1.0);
        vec4 b = inverseProjection * vec4(screenPoint, 0.5, 1.0);
        vec3 start = (cameraWorld * vec4(a.xyz / a.w, 1.0)).xyz;
        vec3 finish = (cameraWorld * vec4(b.xyz / b.w, 1.0)).xyz;
        vec3 ray = normalize(finish - start);
        float horizon = 1.0 - smoothstep(0.0, 0.10, abs(ray.z));
        float alpha = horizon * 0.22;
        if (abs(ray.z) > 0.0001) {
          float t = (floorZ - start.z) / ray.z;
          if (t > 0.0) {
            vec2 point = (start + ray * min(t, 10000000.0)).xy;
            float level = log(max(spacing, 0.0001)) / log(10.0);
            float cell = pow(10.0, floor(level));
            float fine = lines(point / cell);
            float major = lines(point / (cell * 10.0));
            float coarse = lines(point / (cell * 100.0));
            float coverage = mix(max(fine * 0.38, major * 0.70), max(major * 0.38, coarse * 0.70), fract(level));
            float fade = smoothstep(0.006, 0.08, abs(ray.z)) * (1.0 - smoothstep(5000000.0, 10000000.0, t));
            alpha = max(alpha, coverage * fade);
          }
        }
        gl_FragColor = vec4(mix(ground, ink, alpha), 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  mesh.name = "infinite-orientation-grid";
  mesh.position.z = floorZ;
  mesh.frustumCulled = false;
  mesh.renderOrder = -1000;
  mesh.raycast = () => {};
  mesh.onBeforeRender = (_renderer, _scene, camera) => {
    material.uniforms.inverseProjection.value.copy(camera.projectionMatrixInverse);
    material.uniforms.cameraWorld.value.copy(camera.matrixWorld);
    // Camera-relative decade spacing; uniforms update without allocating geometry.
    const distance = Math.abs(camera.matrixWorld.elements[14] - floorZ);
    const ortho = camera as THREE.OrthographicCamera;
    const span = ortho.isOrthographicCamera ? Math.abs(ortho.top - ortho.bottom) / Math.max(ortho.zoom, 0.0001) : distance;
    material.uniforms.spacing.value = Math.max(span / 45, 0.0001);
  };
  return mesh;
}
