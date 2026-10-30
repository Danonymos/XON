# XON Shader 1.0.7 - built-in anti-aliasing verification

30 October 2026. Player requested unconditional low-cost smoothing while keeping
version 1.0.7. The prior filter ran a variable span search and returned immediately
above 0.45 pixels of blur motion. Additional texture filtering ended at 38 blocks
and covered nearby horizontal surfaces, leaving distant wall textures unprotected.

The new core reuses the 3x3 color neighborhood to reconstruct symmetric bilinear
positions along the edge with arithmetic, without further filter/search fetches.
The depth-curvature gate preserves texture detail on flat surfaces. Four cardinal
colors still serve optional sharpening; four diagonal colors are read only after
the contrast and geometry checks pass. There is no AA quality switch or off option.

Moving AA shares the existing six shutter samples with small symmetric subpixel
coverage offsets. Fixed cosine-window weights replace per-pixel randomized shutter
positions and per-tap cosine evaluation. Filtering hands off continuously between
0.35 and 0.45 pixels, staying within the old stationary/moving fetch limits. Blur
exposure, radius, invalid-frame/teleport guards and first-person protection remain.

Terrain sampling adds a 0-0.32 mip bias only when texels become smaller than pixels.
It uses the existing game mip chain; Ziz has four mip levels enabled. Known plant,
leaf and lichen materials keep their original footprint. Other sampled alpha below
0.99 falls back to the unbiased gradient sample, retaining cutout silhouettes.
That fallback can add one lookup on unmapped minified cutouts. Optional grazing
samples use explicit gradients computed before divergent branches.

tools/aa_gpu_checks.py executes the production shaders against the saved
XON-Shader-v1.0.7-before-aa.zip. All 20 focused checks pass:

- Six diagonal orientations, each at nine subpixel phases: mean display error
  against analytic pixel coverage falls from 0.006484 to 0.005634 (13% lower).
  Every tested orientation improves; the unfiltered error is 0.029589.
- Seventeen moving frames against a pixel-area/shutter reference: residual temporal
  error drops about 46%, with lower spatial error. The old AA cutoff jumps by
  0.420 in display RGB; the new controlled handoff changes by only 0.0000032.
- Tested minified wall patterns have about 54-95% less alias energy. Magnified
  and 1:1 texture samples remain identical, and deeply minified patterns stay flat.
- Known and unmapped cutout alpha, one-pixel geometry contrast and first-person
  hand protection pass. Existing 12 final-pass and 22 lighting checks also pass.
- 840 graphics configurations compile/link with zero shader warnings; the existing
  water, ray, building, voxel, cloud and terrain-ring suites remain passing.

Isolated RTX 5060 Ti GPU medians, 960x540, 48 queries with eight draws per query:

| Workload | Before ms | Current ms |
|---|---:|---:|
| Stationary final pass, many geometric edges | 0.0594 | 0.0389 |
| Moving final pass | 0.0414 | 0.0413 |
| Gentle motion at half a pixel | 0.0414 | 0.0414 |
| Opaque terrain mip sampler | 0.01569 | 0.01556 |

Reports hold the latest timings, including p95 scheduling spikes during concurrent
desktop/game activity. These are synthetic isolated workloads, not an in-game FPS
guarantee. No pass, render target, history image, supersampling, CPU work or new
dependency was added. Spatial filtering reduces shimmer but cannot recover missing
temporal/subpixel information or guarantee that every distant thin edge is stable.

Reports: validation-aa.json and validation-aa-comparison.png (synthetic diagnostic,
not a Minecraft screenshot). Reproduce with python tools/aa_gpu_checks.py. Prior
1.0.7 runtime/source ZIPs are preserved with the before-aa suffix. The canonical
1.0.7 ZIP is rebuilt; the game-held earlier ZIP is left available. Install the
identical new bytes as XON-Shader-v1.0.7-smooth.zip and select that pack, then Apply.
Walk and rotate past distant roads, walls, stairs and fences; compare still/moving
detail, nearby texture sharpness, hand edges and frame times at identical settings.
Live Minecraft visual/FPS verification remains outstanding.

# XON Shader 1.0.7 - terrain rings, aura fade and moonlight verification

30 October 2026. The player confirmed that the camera-following ring disappears
when only Sun & Moon Cast Shadows is disabled. Smooth Shadow Transitions reduced
it but did not eliminate it. An actual rasterized one-block terrain grid reproduced
false self-shadow with both filter modes, including under oblique sun and high cameras.

Surface filtering now adjusts each tap's comparison depth to the receiving plane,
accounting for nonlinear map distortion and the hardware-PCF texel footprint.
The existing foliage bias, shadow resolution/range and 4/2/1 sample limits remain.
No image lookup, render pass or history buffer was added; the correction adds math.

Colored ore propagation extends three open blocks beyond the selected radius.
Quintic falloff eases the interpolated field to darkness with zero endpoint slope
and curvature. Default extent is about seven blocks along open paths, settling
in about eight frames. The 96x48x96 volume, six-neighbor propagation, one dispatch
per frame, source colors and solid-wall occlusion are retained. Corners and the
player-centred volume boundary can shorten the visible reach.

Exposed moonlit cloud openings receive up to 28% more of the existing cool blue
illumination, before torch/held/ore light is added. The isolated bright-core test
measured 25.4% more luminance; cloud-shadow patches and daylight were unchanged.
Primary cloud drift is now 0.5 blocks/second, with shape evolution sped up by the
same factor. The closed hourly path stays seamless, with the accepted coverage,
patch scale and broad eased edges. Local contour motion varies as shapes merge.

Offscreen GPU verification on the installed RTX 5060 Ti:

- 840 graphics configurations compile/link with zero shader warnings.
- tools/shadow_ring_checks.py records 578 comparisons/contact cases: 288 baseline
  and 288 corrected flat/sloped terrain cases, plus two retained box-shadow cases.
  Coverage includes four shadow resolutions, three sun elevations, three camera
  heights, fractional translations and both smoothing modes. Baseline visibility
  fell to 0.342 on unoccluded terrain; corrected terrain stayed fully lit (1.0).
  Real box cast shadows remain dark, including the floor next to their contact.
- 19 GPU voxel cases include the three-block tail and 65 sub-block fade samples
  per tested radius, with monotonic light and a flat transition into darkness.
- 16 cloud GPU cases include measured production drift across the hour, merging
  silhouettes, normal-frame/hourly continuity, night boost and lighting exclusions.
- Existing 22 lighting, 12 final-pass, 84 water, 27 rays/background and 12 building
  cases pass. Package checks compare source, runtime ZIP and installed copy.

Reports are validation-shadow-rings.json, validation-emissive-gpu.json,
validation-cloud-shadows.json and the existing validation reports. Diagnostics
are synthetic GPU scenes. No live Minecraft appearance or full-game FPS check
was performed. Preserve the 1.0.6 before-ring-fix and before-cloud-polish ZIPs
alongside the source to reproduce baseline comparisons.

Select XON-Shader-v1.0.7.zip and Apply. Leave Sun & Moon Cast Shadows ON, walk
and fly over the same flat field, and check that the ring stays absent. At night,
watch openings drift for 20 seconds (about ten blocks of primary wind travel).
Check an ore/quartz floor or mine wall through the new outer three-block fade,
then break the ore and check that its light clears. Compare identical frame times.

# Historical XON Shader 1.0.6 - cloud-shadow polish verification

30 October 2026. Player feedback and the supplied screenshot showed that small
cellular shadow centers left narrow bright ridges between them. The replacement
uses signed, domain-warped noise rather than cell-distance borders. Following
player feedback, the initial landscape-scale prototype was reduced to typical
30-50 block patches. Smaller pockets and merged larger banks remain irregular;
there is no fixed diameter or hard maximum for connected shapes.

Three samples from the existing noise atlas supply broad coverage, distortion
and softer detail. Different slow wind flows evolve their overlap continuously.
The wind follows a closed hourly path because the installed Iris Timer resets
frameTimeCounter to zero at 3600 seconds. A wide quintic edge transition has zero
first and second derivatives at its light/shadow plateaus. Cloud cover removes
sun/moon key light and a small amount of sky fill; clear gaps retain the existing
celestial color. The effect fades near the render horizon instead of 96 blocks.

GPU evidence is in validation-cloud-shadows.json and tools/cloud_shadow_checks.py:

- Sampled coverage is 50.26% light / 49.74% shadow across four distant positive
  and negative coordinate regions. About 25% of sampled area is intermediate
  edge transition (absolute signal below 0.4), rather than a light/shadow core.
- Median axis crossings are 45.9 blocks for openings and 43.7 for shadows;
  the old bright ridges measured 10.7 blocks. These are sampled run lengths,
  not promised dimensions of every patch. Connected banks can exceed 60 blocks.
- Frame changes, evolution while following the main wind, camera anchoring,
  hourly timer continuity, storm attenuation, above-cloud/off gates, day/moon
  shading, caves, torches, underwater and backface protection are checked.
- The synthetic shaded scene retains readable cool shadows and modest clear-gap
  highlights. Camera movement does not displace the world-anchored pattern.
- No pass, buffer, image asset, package or shadow geometry budget was added.
  More distant visible outdoor terrain now evaluates the effect. The shader uses
  three texture lookups plus shared wind math in place of the old cellular search.

Initial focused timings at 960x540 on the RTX 5060 Ti measured about 0.0155 ms for
the pattern, and 0.0290 ms for the complete synthetic receiving-light shader
(old shader: 0.0258 ms). This is a small measured isolated increase, not an in-game
FPS result. Desktop load and shader compilation can affect timings; the JSON
report holds the latest run. No live Minecraft visual/FPS check was performed
for this polish. The comparison PNG and accelerated GIF are synthetic diagnostics.

Cloud coverage is an artistic approximation, not a traced projection of visible
sky cloud geometry. It does not alter the sky cloud rendering, colored ore
lighting, local light radius, world time/weather, Iris selection or saved options.
The accepted pre-polish runtime/source ZIPs are preserved as
XON-Shader-v1.0.6-before-cloud-polish[-source].zip.
Minecraft holds the active runtime ZIP open, so the polished build is installed
as XON-Shader-v1.0.6-cloud-polish.zip. Version stays 1.0.6. Its bytes match the
rebuilt canonical XON-Shader-v1.0.6.zip; the active selection was not changed.

Reproduce with python tools/cloud_shadow_checks.py and the existing shader,
lighting, building, water, rays, final-pass and emissive checks. Reload the rebuilt
1.0.6-cloud-polish pack, view the same outdoor field on foot and from above, and watch for at
least a minute in daylight/moonlight. Compare frame time at identical settings.

# XON Shader 1.0.6 - emissive illumination verification

30 October 2026. The installed Ziz 1.0.5 runtime ZIP did not contain the voxel
programs present in the latest source. The source also omitted Iris's required
CUSTOM_IMAGES flag and left reverse-culling voxelDistance at its zero default.
Those loader connections were not exercised by the old standalone shader tests.
The old emissive suite compiled shaders, then tested a separate NumPy algorithm;
it did not execute the GPU flood fill or demonstrate illumination in Minecraft.

The fix registers CUSTOM_IMAGES/COMPUTE_SHADERS when colored lighting is enabled,
explicitly enables shadow capture, sets voxelDistance to 48 blocks, and supplies
shadow/compute wrappers for all three dimensions. The latter two dimensions run
vertex voxel capture without rasterizing unused sun-shadow fragments. Quartz
emits violet light onto receiving surfaces while its own surface stays unchanged.
Mapped plants, leaves and lichen no longer act as full solid occluders.

Verified on the installed NVIDIA RTX 5060 Ti driver:

- 840 graphics program configurations compiled and linked; zero shader warnings.
- 16 actual GPU checks in tools/voxel_gpu_checks.py passed. These execute real
  shadow vertex image writes, the production compute shader and surface sampling,
  plus the production terrain fragment shader with controlled input varyings.
- Capture succeeded in all dimensions with a rotated shadow view, fractional
  camera position and negative world coordinates. Materials/entities were filtered.
- Radius 3/4/5 falloff, violet quartz illumination on stone, wall front/back
  occlusion, emitter removal, redstone/lapis blending, block-boundary camera shifts
  and teleport history rejection passed. Source materials received zero added tint.
- Existing lighting, 12 final-pass, 84 water, 27 rays/background and 12 building
  checks passed. Runtime/source ZIP parity and untouched reference archives passed.

The three 96x48x96 images use 7.171875 MiB of texel storage. Six neighbor samples
and one compute dispatch per frame are retained; surface interpolation uses up to
eight fetches, skipped outside the local volume and on source materials. Speed
disables the image allocations. Default radius is four, configurable from two
to five; a newly captured source reaches the default extent in about five frames.
The compact flood follows block paths rather than spherical ray distances.

32 timer queries measured the isolated production compute dispatch at 0.01821 ms
median / 0.01968 ms p95. This excludes extra shadow-world submissions, image clear,
surface sampling and CPU/game work. It is not a full-game FPS measurement or a
guarantee of negligible cost. Partial solid shapes conservatively occupy a full
voxel. The preview PNG is a synthetic receiving floor, not a Minecraft screenshot.

The new ZIP is installed alongside 1.0.5; active Iris selection was not changed.
Computer Use was stopped by the user before live Iris load/visual verification.
No server commands or world edits were performed. Select XON-Shader-v1.0.6.zip,
Apply, and use Balanced with Colored Emissive Lighting ON. In a dark mine, check
stone walls/floors within 1-5 blocks of exposed ore and quartz; turn away, walk
across block boundaries, break an ore, and check a solid wall blocks the spill.
Check Nether quartz and compare frame time with the same camera/settings.

Reproduce the focused checks with python tools/validate.py,
python tools/voxel_gpu_checks.py and python tools/package_checks.py.

# Historical 1.0.5 notes - not a live emissive-lighting verification

30 October 2026. The 1.0.4-water-stability build resolved time-animated noise but
failed in-game: sunlight shafts from distant buildings were not visible, the
underwater horizon showed a bright cyan seam, and beams did not match the
Complementary reference.

## Independent Diagnosis of 1.0.4-water-stability Failure

1. Water-surface ray clipping: in composite.fsh, ray marching clipped rayLength
   against depthtex0 (post-translucent depth). When swimming 2-5 blocks beneath
   the surface, any ray pitched even slightly upward hit the overhead water quad
   at 4-25 blocks, terminating before reaching the building's shadow 30-60 blocks away.
2. 24-block range cutoff: underwater rays were artificially clamped at 24 blocks.
   In the player's screenshot, the building and island are 30-65 blocks away,
   meaning the building never cast a shadow into the underwater sampling volume.
3. Weak intensity & flat cap: underwater shafts were scaled by 0.006 and capped
   at 0.085, adding less than 2% sRGB brightness and making shafts invisible.
4. Glaring horizon sky seam: sky.fsh evaluated xonFog at a constant distance of
   28 blocks for all directions when underwater, letting 76% of raw daytime sky
   shine through at the horizon and washing out distant shafts.
5. Per-step matrix transform: composite.fsh recomputed a full 4x4 matrix multiply
   inside each ray-marching step.

## 1.0.5 Architecture & Changes

- Underwater sunlight stability & world coordinate anchoring:
  - Concentric expanding ring fix: replaced discrete camera-centric integration intervals with dither-jittered interval sampling smoothed by spatial cross filtering. When strafing or rotating 90° relative to the sun, rays remain smooth, continuous diagonal shafts without concentric expanding rings.
  - World coordinate fixation: sunlight shafts are locked to world coordinates and occluded by world geometry, eliminating camera-relative drift.
  - Translucent look-through: underwater ray marching samples both depthtex0 and depthtex1 via max(depthtex0, depthtex1), allowing rays to look through the overhead water surface to distant structures, islands, and skies.
  - Extended occluder range: underwater ray marching extends to min(shadowDistance * 0.75, 72.0) blocks, capturing building and terrain shadows across the full active shadow distance.
  - Hoisted linear shadow transform: hoisted shadowProjection * shadowModelView out of the loop into linear step vectors (shadowOrigin + shadowStep * distanceAlongRay).
  - Snell's window & marine horizon void: in sky.fsh, looking horizontally blends seamlessly into deep marine water fog (distance 192.0), while looking upwards reveals overhead sky through Snell's window with natural water absorption.
  - Near-camera clarity ramp: added near-distance ramp (smoothstep(0.0, 4.5, distanceAlongRay)) ensuring water within 4.5 blocks of the camera/hand remains crystal-clear.
  - Coherent directional shafts: phase scattering uses forward + isotropic blending aligned to xonKeyDirection(), with rich marine cyan-blue scattering (vec3(0.20, 0.40, 0.65)) capped at 0.20 for clear separation between sunlit water and shaded building volumes.
- 3D voxel flood-fill colored emissive block lighting:
  - Camera-centered 3D voxel grid (96x48x96) populated during shadow pass with `shadow.culling=reversed` and `voxelizeLightBlocks=true`.
  - Fast ping-pong compute shader flood-fill (`shadowcomp.csh`) with workGroups (12, 6, 12) converging within 4 frames (<0.03 ms GPU time).
  - Trilinear surface sampling over air voxels in `geometry.fsh` (`xonEmissiveLight`) with quadratic easing (`level^2 * (3.0 - 2.0 * level)`).
  - Quartz block fix: separated architectural quartz blocks (block.10023) so they retain normal surface shading and contrast without turning into blinding white beacons, while casting soft warm-ivory ambient light onto neighboring blocks.
  - Full 3D propagation regardless of view direction; zero light leakage through solid occluding walls; natural multi-emitter color blending.

## Verified Results & Measurements

- 820 OpenGL driver compile/link configurations passed across all 10 presets (validate.py).
- Compute shader `shadowcomp.csh` compiled and verified with zero errors (emissive_checks.py).
- Dedicated 3D voxel validation suite passed 100%: exact 3-block radius propagation, smooth monotonic falloff, 0.000 wall leakage, natural color blending (emissive_checks.py).
- 27 ray and background checks passed (rays_checks.py).
- 84 water cases passed with bit-for-bit parity on shallow water (shallow_water_checks.py).
- 25 camera translation and rotation frames across occluder pass temporal stability checks.
- Isolated GPU underwater ray pass: ~0.040-0.060 ms (half-resolution effects pass).
- Package integrity verified: 197 runtime files in XON-Shader-v1.0.5.zip.

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
