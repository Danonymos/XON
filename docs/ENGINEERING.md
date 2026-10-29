# Engineering notes

These observations are based on the supplied XON 1.0.0 source. They are not a driver compile report, an in-game test result, or a benchmark.

| Area | Source | Verified structure |
| --- | --- | --- |
| Defaults and profiles | `shaders/lib/settings.glsl`, `shaders/shaders.properties` | Balanced/Speed profiles, 1024 shadow map, 96-block default range; 1.0/0.85/0.75 render scale. |
| Shadow receivers | `shaders/lib/shadows.glsl` | Two rotated hardware-filtered samples, distance/frustum exits and fades. |
| Post effects | `shaders/program/composite.fsh`, `composite1.fsh` | Four bloom prefilter taps, four cone-culled sunlight samples, and an additional softening pass; effect buffers configured at half resolution. |
| AA and reconstruction | `shaders/lib/antialiasing.glsl` | Shared cardinal samples, depth-curvature gating, optional reconstruction sharpening; no temporal history accumulation. |
| Camera blur | `shaders/program/final.fsh` | Stationary-camera early exit, bounded radius, hand exclusion and depth guards. |
| Clouds | `shaders/lib/clouds.glsl` | Layered noise and cellular dome heightfields, directional probes, distance fading, and separate ground-light approximation. |
| Water and materials | `shaders/program/geometry.fsh` | Distance-aware multi-scale water normals, sky/cloud reflection evaluation, refraction/absorption, lava, ore/crystal effects, and caustics. |
| Foliage | `shaders/program/geometry.vsh`, `shadow.vsh` | Matching vertex animation in geometry and shadow passes. |
| Atmosphere | `shaders/lib/atmosphere.glsl` | Analytic palettes, weather response, dimension-specific skies and absorption. |

## Limits

GPU work still has a cost. Procedural clouds, extra geometry passes, and post effects can reduce FPS depending on the workload. CPU limits and frame caps can obscure GPU differences. Establish performance with controlled comparisons before advertising a measured improvement.

Some legacy option comments and beta terminology in the original bundled documentation are older than the current code. The code and current settings are the source for the values above. `PACK-README.md` preserves that original documentation for reference.
