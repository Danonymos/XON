# XON Shader 1.0.4 water-stability correction - verification

30 October 2026. Player screenshots and motion reports showed that the previous
animated noise field looked like white smoke and morphed while swimming. The
earlier stationary checks passed but did not establish acceptable moving visuals.

## Current implementation and evidence

- Remove the underwater noise field entirely. Scatter blue sunlight according to
  actual shadow-map visibility, using the same source direction as those shadows.
- Eight fixed three-block intervals, clipped at foreground depth and 24 blocks.
  No underwater screen jitter, time animation or large-world-coordinate phase.
  Changing depth affects the final interval rather than rescaling every sample.
- Two hardware-PCF lookups per step soften visibility. Keep the existing
  half-resolution integration and spatial-softening passes, 96-block shadow map
  range and map resolution. Cap underwater alpha at 0.085 instead of 0.28.
- Lower pale water-background scattering. Reuse the existing fog transmission
  for approximate red/green/blue absorption, with multiplication and one square
  root; no additional exponential evaluations. The six-block clear near zone,
  shallow-water surface tint and outdoor color/lighting remain intact.
- 820 driver-linked program configurations pass. Rendering checks: 22 lighting,
  12 final-pass, 84 water-surface, 27 ray/background, and 12 building cases.
- New checks cover stationary time, world-origin relocation near the supplied
  screenshot coordinates, eight foreground depths, and 25 translating/rotating
  camera frames against a 128-step integration reference with fixed occlusion.
  Maximum open-water depth-sweep alpha error: 0.000147. Worst moving-frame p99
  alpha error: 0.00484; worst frame-difference p99 error: 0.00690. These are
  integration error bounds for synthetic inputs, not proof of flicker-free play.
- Background checks preserve near-water, air, lava and powder-snow behavior;
  distant water becomes bluer and less washed out without a black clamp.

Shaft-only GPU queries at 960x540, 48 queries/four draws each, RTX 5060 Ti:
previous smoky underwater median 0.03931 ms / p95 0.03946 ms; corrected underwater
median 0.04349 ms / p95 0.04460 ms. The isolated increase is about 0.0042 ms.
No full-game FPS improvement or identical FPS is established. Timings exclude
world geometry, CPU, bloom and background fog; desktop load/clocks affect results.

Current reproduction commands are the same as the historical commands below.
The ray checks additionally need the preserved `XON-Shader-v1.0.4-revised.zip`.
Reports remain local and excluded from source/runtime archives. The comparison
PNG now contrasts the rejected smoke field with occluder-defined scattering on a
constant backdrop; it is a diagnostic, not a Minecraft scene or reference match.

Select **XON-Shader-v1.0.4-water-stability.zip** and Apply. Swim forward/backward,
strafe and rotate at the supplied location, then compare under building edges and
in unobstructed water. Check the blue background, nearby visibility, ray intensity
0/1 and FPS with identical settings. Uniformly lit open water is intentionally
subtle; visible shafts need occlusion contrast. Fine geometry/shadow-map changes
can still alias within this small sample budget. Shadow rays assume straight
sunlight and do not simulate wave-refraction or multiple scattering. No live
Minecraft reload, final appearance check or game FPS measurement was performed.

The new ZIP is installed alongside the previous pack with copied shader-option
preferences. Active Iris selection is unchanged. The runtime ZIP and a matching
source archive use the `1.0.4-water-stability` filename.

# Historical 1.0.4-revised verification (superseded underwater implementation)

30 October 2026. Builds on player screenshots showing flat building shade and
missing underwater beams. Offscreen checks use the installed RTX 5060 Ti OpenGL
4.6 driver (621.01). There was no Minecraft UI automation, live reload or game FPS
measurement. The original runtime ZIP is preserved as
`../XON-Shader-v1.0.4-original.zip`; the revised runtime has its own filename.

## Diagnosis and changes

The original already computed a directional diffuse term, but wall ambient fill,
simulated bounce, cloud highlights and the night-vision bright floor could obscure
its contrast. Lighting now follows the same active celestial source as Iris's
shadow pass, using [shadowLightPosition](https://shaders.properties/current/reference/uniforms/world/).
That input is transformed from view to player space; camera-rotation tests verify
that the key does not rotate with the camera. Wrapped direct light is zero on
opaque backfaces. Cloud highlight energy is gated by facing and shadow visibility.

Sky fill is hemisphere-weighted and simulated bounce is more restrained, with the
existing minimum cave/shadow fill retained. Backlit white walls become visibly
blue-gray rather than black. Night vision adds visibility while preserving light
ratios instead of imposing the former 0.78 bright floor. Distance bias now grows
linearly rather than as r^1.5, reducing far-receiver detachment. Range fade starts
at 88% rather than 72% of the configured distance; map-edge fade still applies.

Underwater rays were culled outside an upward-facing cone and also suppressed by
low eye skylight. Those assumptions fail in horizontal swimming views. Water rays
now scatter at all view angles and use per-sample shadow occlusion instead of an
eye-skylight gate. A projected moving surface field from XON's original noise
creates distinct transmission shafts in open water; it adds six noise lookups to
the existing six shadow steps. Lower background underwater fill improves beam
separation. This is an artistic surface-transmission approximation, not a physical
water simulation or copied Complementary implementation.

## Verification

- 820 linked program configurations across all dimensions and ten settings sets.
- 22 material/lighting/sky/AA feature checks, including clear-air and readable
  zero-skylight surfaces. The cloud field test retains its movement/contrast
  assertions but now isolates the field from its redesigned lighting response;
  new building checks cover the resulting shaded-surface response.
- 12 final-pass motion/Boost/hand/discontinuity checks.
- 84 shallow-water cases; water composition, thin-water tint and submerged surface
  transparency remain intact.
- 16 ray/light checks, including zero eye skylight while swimming horizontally
  toward/away from high and low sun, depth clipping, solid occlusion, light-shaping
  openings, daytime/medium/option gates and unchanged minimum unlit fill.
- 12 building-scene checks with real shadow-map rasterization, XON receiver
  shading, filmic mapping and LUT: front/behind sun, camera rotation, cloud movement,
  readable shade and contrast with night vision enabled.

Reports are local `validation-driver.json`, `validation-lighting.json`,
`validation-pixels.json`, `validation-shallow-water.json`, `validation-rays.json`,
`validation-scenes.json` and `validation-package.json`. Older performance and
visual-update reports belong to earlier releases.

The two comparison PNGs are synthetic diagnostics, not Minecraft screenshots:
`validation-building-comparison.png` shows the same white building under front and
rear sunlight, before/after; `validation-underwater-comparison.png` shows ray
composition over a constant underwater backdrop. The underwater preview omits the
following spatial-softening pass and the world scene. It can expose more sampling
noise than the final pack. Neither image establishes the exact result in the
player's resource pack or shader-mod stack.

## Performance evidence

No new draw pass, history buffer, shadow resolution or shadow-rendering distance.
Six noise lookups are added only while underwater with rays enabled. Outdoors
retains four shadow samples. Underwater remains six shadow samples, with a
40-block range and 0.28 peak cap; outdoor cap remains 0.20. Spatial softening uses
the existing pass. No identical-FPS guarantee or measured in-game gain is claimed.

Shaft-only timer queries, 960x540, 48 samples with four draws each:

| Pass | Median ms | p95 ms |
|---|---:|---:|
| 1.0.3.3 outdoor | 0.02090 | 0.02110 |
| original 1.0.4 underwater | 0.03276 | 0.03282 |
| 1.0.4 outdoor | 0.02382 | 0.02442 |
| 1.0.4 underwater | 0.03955 | 0.08978 |

Synthetic building shading timings at 640x360:

| Version / sun | Median ms | p95 ms |
|---|---:|---:|
| original 1.0.4 / sun in front | 0.01438 | 0.01468 |
| original 1.0.4 / sun behind building | 0.01422 | 0.01449 |
| revised 1.0.4 / sun in front | 0.01478 | 0.01508 |
| revised 1.0.4 / sun behind building | 0.01461 | 0.01635 |

These timings exclude actual world geometry submissions, shadow-world draw cost,
bloom and CPU simulation. Clock changes, ordering and concurrent desktop work can
affect the numbers. They are costs of synthetic workloads, not FPS forecasts.

## Limits and final player check

Cast occluder shadows remain limited to the configured shadow map (96 blocks by
default). The revision does not trace distant occluders beyond its map. Directional
face shading continues beyond that range. Higher Shadow Distance can cover more
of a large distant build, at an increased rendering cost. No automatic distance
increase is imposed. The active sun/moon is supplied by Minecraft/Iris; the pack's
existing sunPathRotation remains -25 degrees.

The underwater field assumes a flat interface and is procedural. The shadow map
still represents straight sunlight, not refracted shadows through actual waves.
Six steps can show banding/noise on thin occluders; spatial softening reduces it,
without temporal history. Closed-roof occlusion is tested through the shadow map;
there is no voxel model of spaces outside that map. Other GPUs, live Iris patching,
exact resource-pack interactions and real-world FPS require player testing.

Reproduce from the source directory:

```text
python tools/validate.py
python tools/lighting_checks.py
python tools/render_checks.py
python tools/shallow_water_checks.py
python tools/rays_checks.py
python tools/scene_checks.py
python tools/build.py
python tools/package_checks.py
```

Historical comparison tests require the original 1.0.3, 1.0.3.3 and preserved
1.0.4-original runtime ZIPs in the parent folder. The game needs none of these
Python tools. Package checks expect the revised ZIP installed in Ziz/shaderpacks.

Select **XON-Shader-v1.0.4-revised.zip** and Apply. Revisit the same rear building
view with the sun behind it; check shaded windows/walls, cave readability and
night vision. Then swim horizontally at the supplied underwater location and
turn toward/away from sunlight. Toggle God Ray Intensity 0/1 for comparison and
check beneath a solid roof. Compare FPS under the same settings. The previous
pack and saved settings remain available; active shader selection is not changed.
