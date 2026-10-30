# Engineering notes

Current architecture for **XON Shader 1.0.7**. See [VERIFICATION.md](../VERIFICATION.md)
for measured GPU checks and the distinction between driver tests and live gameplay.

| Area | Source | Current design |
| --- | --- | --- |
| Settings and profiles | `shaders/lib/settings.glsl`, `shaders/shaders.properties` | Native/85%/75% render scales; four presets; built-in AA in every preset. |
| Directional shadows | `shaders/lib/shadows.glsl` | Bounded 1024 map and 96-block defaults, adaptive 4/2/1 PCF lookups, receiver-plane depth correction and range/frustum fades. |
| Colored block light | `shaders/lib/emissive_light.glsl`, `shaders/program/shadow.vsh`, `shadowcomp.csh` | 96×48×96 local occupancy/history images, six-neighbor flood fill, eight-fetch interpolation and quintic falloff; all three dimensions. |
| Cloud ground shade | `shaders/lib/clouds.glsl`, `lighting.glsl` | Three existing noise samples, balanced warped coverage, broad eased boundaries and independent wind layers; 0.5-block/second primary motion. |
| Static AA | `shaders/lib/antialiasing.glsl` | Shared cardinal sharpening samples, depth-curvature gate and bounded 3×3 edge reconstruction; no span walk or temporal history. |
| Moving AA and camera | `shaders/program/final.fsh` | Six symmetric shutter reads with subpixel coverage, smooth handoff and hand/frame/teleport guards. |
| Terrain sampling | `shaders/program/geometry.fsh` | Up to 0.32 mip levels of minification bias, conservative alpha fallback and explicit gradients for optional nearby grazing taps. |
| Water and materials | `shaders/program/geometry.fsh` | Layered normals, sky/cloud reflections, half-resolution refraction, depth absorption, caustics and dedicated emissive material paths. |
| Shafts and bloom | `shaders/program/composite.fsh`, `composite1.fsh` | Existing half-resolution buffers; outdoor four-step and underwater twelve-step shadow sampling with bounded ranges. |
| Foliage and atmosphere | `shaders/program/geometry.vsh`, `shadow.vsh`, `shaders/lib/atmosphere.glsl` | Synchronized wind, dimension palettes, weather, clear near air and render-border/medium fog. |

## Work budgets

Colored lighting retains one compute dispatch per frame and about 7.17 MiB of
image texel storage. Its default extent takes roughly eight frames to settle.
Propagation follows open block paths and conservatively treats solid voxels as
occluders. It is not global ray tracing.

The AA update adds no draw pass, history image or CPU frame work. It replaces
expensive spatial searches with bounded reconstruction and shares the motion
kernel's existing reads. An unmapped minified cutout can require one additional
unbiased sample. Rendering cost still depends on hardware, resolution and scene.

Ground shade is world anchored, but its field is not a traced projection of the
visible sky-cloud geometry. Spatial AA cannot provide full temporal reconstruction.

## Build and validation

- [Build and package checks](RELEASING.md) use only Python's standard library and run in GitHub Actions.
- Driver/GPU tools require Windows, a compatible OpenGL context, NumPy and Pillow.
- Comparison suites also need preserved historical ZIPs in the checkout's parent
  directory. They are local developer diagnostics, not dependencies of the game.
- The Actions badge reports packaging and repository checks, not in-game visual,
  frame-rate or hardware certification.
