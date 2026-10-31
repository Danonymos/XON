# Engineering notes

Current architecture for **XON Shader 1.1**. See [VERIFICATION.md](../VERIFICATION.md)
for measured GPU checks and the distinction between driver tests and live gameplay.

| Area | Source | Current design |
| --- | --- | --- |
| Settings and profiles | `shaders/lib/settings.glsl`, `shaders/shaders.properties` | Native/85%/75% render scales; four presets; built-in AA in every preset. |
| Directional shadows | `shaders/lib/shadows.glsl` | Bounded 1024 map and 96-block defaults, adaptive 4/2/1 PCF lookups, receiver-plane depth correction, range/frustum fades and directional far-foliage approximation. |
| Colored block light | `shaders/lib/emissive_light.glsl`, `shaders/program/shadow.vsh`, `shadowcomp.csh` | 96×48×96 local occupancy/history images, six-neighbor flood fill, eight-fetch interpolation and quintic falloff; all three dimensions. |
| Cloud ground shade | `shaders/lib/clouds.glsl`, `lighting.glsl` | Three existing noise samples, balanced warped coverage, broad eased boundaries and independent wind layers; 0.5-block/second primary motion. |
| Static AA | `shaders/lib/antialiasing.glsl` | Shared cardinal sharpening samples, depth-curvature gate and bounded 3×3 edge reconstruction; no span walk or temporal history. |
| Moving AA and camera | `shaders/program/final.fsh` | Six symmetric shutter reads with subpixel coverage, smooth handoff and hand/frame/teleport guards. |
| Terrain sampling | `shaders/program/geometry.fsh` | Up to 0.32 mip levels of minification bias, conservative alpha fallback and explicit gradients for optional nearby grazing taps. |
| Water and materials | `shaders/program/geometry.fsh` | Layered normals, sky/cloud reflections, half-resolution refraction, depth absorption, caustics and dedicated emissive material paths. |
| Shafts and bloom | `shaders/program/composite.fsh`, `composite1.fsh` | Existing half-resolution buffers; outdoor four-step and underwater twelve-step shadow sampling with bounded ranges. |
| Foliage and atmosphere | `shaders/program/geometry.vsh`, `shadow.vsh`, `shaders/lib/atmosphere.glsl` | Synchronized wind, dimension palettes, weather, clear near air and render-border/medium fog. |
| Exposure and grade | `shaders/lib/grading.glsl`, `shaders/textures/xon-grade.png` | Private 0.90 base exposure, unchanged brightness control, existing 16-cubed LUT and two-fetch grading budget. |

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

Outside valid shadow coverage, foliage modulates the existing skylight fallback
with the unwrapped celestial facing and a mild sky-facing term. Its radial handoff
starts at 72% of shadowDistance, versus 88% for ordinary terrain; both finish at
98%, with the existing frustum fade still applied. Valid full-coverage nearby
shadows retain their samples and result. No extra shadow geometry, pass, image or
texture read is added. This cannot recover distant object occluders. See the
[GPU checks and timings](distant-shading-validation.md).

Foliage skips receiver-plane gradient evaluation when its final multiplier is
zero, and skips view-dependent backlight math under full occlusion. These are
exact work skips; shadow filtering and light budgets are retained. Surface relief
uses Iris's active celestial direction, while water glints apply shadow visibility
to both sun and moon. Palette colors and saturation are baked into existing
lighting constants and the LUT; `python tools/make_textures.py --grade-only`
regenerates that LUT without rewriting the noise atlas.

Ordinary lamps use the interpolated block-light coordinate. The cubic response
blends its shoulder from 0.35 indoors to the original 0.72 outdoors, using the
existing smooth skylight curve. Peak local energy blends from 0.80 to 0.90 of
1.0.8; held-light energy shares that gain. No source vectors are inferred from
the scalar lightmap. Minecraft's actual propagation radius/gameplay values and
the separate colored ore volume remain intact.

Day key/fill gains are 0.92/0.94; daytime cave fill is 0.92. Constant folding keeps
these adjustments inside the existing math. The lunar coefficient compensates
the shared key multiplier so moonlight stays stable. Night cave fill is retained;
Nether/End ambient gains are 0.84/0.90. The benchmark tool accepts --candidate to
test an uninstalled library, and interleaves before/current 1080p timer queries
for lighting kernels and actual terrain fragments.

## Build and validation

The 1.1 emitter map reuses amethyst/sculk families and adds IDs 13/14 in the byte
occupancy image for lichen/berries. Capture classifies emitters before excluding
ordinary foliage. Berry-bearing states preserve cross-plant wind, shadow normals
and cutout filtering. Attached lichen retains its separate non-waving material.
Selectors follow [Iris block-state syntax](https://shaders.properties/current/reference/miscellaneous/block_properties/).

Lantern material IDs 10025/10026 use texture-color masks to separate the emitting
core from the metal, with pale-core support. Unusual resource packs can need mask
tuning. They retain vanilla block-light propagation and the accepted 1.0.9 room
balance. Bloom remains shared: the soft knee spans linear peaks 0.90–1.30; the
five-tap RGB blur weights center/corners 0.36/0.16 while shaft alpha retains its
old filter. Resolve gain is 0.208 versus 0.16, with unchanged texture-fetch budgets.
This halo is screen-space rather than a fixed world-radius light volume.

Colored-light interpolation uses a smooth confidence fade below 0.5 total open
weight. This suppresses the previous near-zero-weight normalization flash while
keeping fully open sampling and the existing falloff. The complete new suite is
`tools/emissive_material_checks.py`; it accepts --minecraft-jar for local original
texture/state inputs. Client assets are read for testing and are not packaged.

- [Build and package checks](RELEASING.md) use only Python's standard library and run in GitHub Actions.
- Driver/GPU tools require Windows, a compatible OpenGL context, NumPy and Pillow.
- Comparison suites also need preserved historical ZIPs in the checkout's parent
  directory. They are local developer diagnostics, not dependencies of the game.
- The Actions badge reports packaging and repository checks, not in-game visual,
  frame-rate or hardware certification.
