# 1.8 lamp-lighting validation

4 November 2026. These checks use the installed NVIDIA RTX 5060 Ti OpenGL driver.
The comparison baseline is the exact source before the 1.8 rework, including the
preceding warm-outdoor/darker-night adjustments, saved locally as XON-1.8-before.zip.

## Source and GPU checks

The final source passes 2,088 graphics compile/link configurations across all
three dimensions and the existing PBR/AA variants, with zero warnings/failures.
Compute compilation and execution are additionally exercised by the lamp suite.

`tools/lamp_source_checks.py` validates 188 new state selectors in 66 material
groups against installed Minecraft 26.3 assets, including all 16 candle colors,
counts, lit states, wet pickles, charges and copper variants. Wire power and
invisible light levels use their explicit legal 1–15 ranges because those values
are not represented in model variants. Existing plant/lantern mappings are retained.
The full-cube blocker map is regenerated and checked at 471 selectors.

`tools/lamp_gpu_checks.py` executes actual shadow capture, compute transport,
volume interpolation and production terrain shading. Its 119 checks cover:

- 75 finite, monotonic source profiles, with softer/smaller lichen and berries.
- Every source material in all three dimensions, negative world coordinates,
  translucent emitter capture and transparent non-emitter exclusion.
- Bit-for-bit retention of all eight ore transport families against the baseline.
- Separate lamp/ore fields, solid walls, removed sources and teleport rejection.
- Decorative auras retain colored spill without claiming native block-light coverage.
- Fractional/negative camera movement and immediate block-boundary reprojection.
- Continuous warm/cyan transitions and stable settled mixed-light history.
- Thin/inset/full receiver sampling in all six face directions, compared with
  the first 1.8 pool build saved as XON-1.8-first-pools.zip. Uniform light could
  previously fall below 10% on a thin surface; corrected lamp and ore samples
  retain the full uniform field. Quartz excludes its own decorative aura but
  continues to receive sea-lantern light.
- Six lanterns, three blocks above a 20×20 floor, with spatially varying native
  light levels evaluated per pixel for both production fragments.

The room's display-luminance p10/p95 ratio changes from **0.608 to 0.470**.
The candidate p10/p50/p95 values are **0.256 / 0.282 / 0.545**: more separation,
bright pools and a retained readable shade floor. This is a synthetic flat-material
test, not a screenshot of the user's room or a guarantee of aesthetic preference.

`tools/indoor_shape_checks.py` retains all 55 partial/full-shape assertions. Its
capture fixture binds the added lamp images and expects the new lantern source
code. The rejected historical flat-surface occlusion still reproduces at 0.28;
the corrected receivers remain at visibility 1 across all six face directions.

## Bounded cost and limits

Interleaved synthetic GPU timer queries measured the 1080p room fragment around
**0.46 ms before / 0.64 ms after**, and a 96×48×96 compute dispatch around
**0.012 / 0.023 ms**. Timings vary with clock/load and show scheduling outliers;
they exclude game CPU cost, extra translucent terrain submission, overdraw,
post-processing and the rest of the Minecraft frame. They are not FPS claims.

The extra RGBA16F lamp history pair costs **6.75 MiB** of image texels, with
**13.92 MiB** occupancy/ore/lamp texels before driver overhead. The subsequent
optimization adds a **1.69 MiB** contact cache, for **15.61 MiB** total. One compute
dispatch is retained; receiving surfaces add eight volume fetches. Speed omits
the colored fields and keeps scalar lighting. The figures above describe the
pre-optimization build; current before/after results are in the
[optimization record](lighting-optimization.md).

Transport follows six-neighbor block paths with a strongest-source approximation.
It does not recover a spherical source radius, physical energy conservation,
arbitrary translucent attenuation or individual ray-traced lamp shadows.
Different colors interpolate at cell boundaries; very complex source mixtures
can differ from additive lighting. History can take up to 15 frames to settle.
The volume edge and unsupported/unseen sources fall back to the native lightmap.
Block-entity-only emitters without terrain geometry (for example ender chests)
keep scalar lighting; no guessed animated-model location is injected.

The initial 1.8 pack loaded successfully in Iris. The user reported that the
lighting looked much nicer, with Night Vision's effect disabled by a mod, then
supplied screenshots of thin-surface lines and rectangular light patches. The
correction applies the outward receiver-cell adjustment to both light samplers,
uses geometric normals for voxel selection, excludes decorative self-lighting
and prevents decorative auras from claiming native lightmap coverage.
Following the user's refinement, lamp spill is 15% lower in linear radiance and
indoor gaps receive up to 15% less base fill. The near-pool fill, emissive cores,
unlit cave visibility and open outdoor lighting are protected. The user
subsequently reported improved lighting and visuals in gameplay; controlled
before/after screenshots for every supplied location are not recorded.

Full-game frame-rate, motion in the supplied interiors, all source layouts,
PBR resource packs, AMD/Intel hardware and arbitrary mods need live testing.
Historical test tools expecting the old non-ore emitter codes are not evidence
for the new source profiles; the 1.8 suite compares actual ore fields directly.

Local reports, screenshots, client assets and baseline ZIPs are diagnostic inputs,
not runtime dependencies or packaged source assets. GPU tools use the existing
NumPy/Pillow environment; packaging needs only Python's standard library.
