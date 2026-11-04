# Engineering notes

## Source-specific lamp lighting in 1.8

`lib/lamp_light.glsl` defines 75 source/state profiles separately from the eight
ore families. `tools/lamp_source_checks.py` validates the state selectors against
installed client assets. New materials use IDs 10030–10096 alongside retained
plant/lantern/crystal IDs. Occupancy codes 129–203 identify lamp families; 255
remains the verified full-cube blocker. The regenerated blocker map has 471
selectors because newly assigned lamps no longer belong to that map.

One existing compute dispatch updates independent ore and lamp history pairs.
Lamp RGB stores shaped radiance; alpha packs `family * 16 + remainingLevel` as
an exactly representable half-float integer. Six-neighbor open-path propagation
decrements the level; profile-specific quintic easing shapes the visible pool.
The strongest luminance candidate wins, with remaining level breaking ties.
Eight open-cell fetches interpolate radiance and predicted block-light coverage.
This avoids unbounded additive accumulation but approximates mixed-source transport.

Decorative quartz, amethyst-block, sculk and wire auras do not claim native
block-light coverage. Quartz/amethyst/sculk metadata stops at the visible aura range.
Where the prediction accounts for the lightmap, a smooth coverage ratio replaces
much of the scalar warm fill with the lamp pool. Weak predictions, unknown sources
and volume edges blend back to the scalar fallback. Ambient visibility remains,
and night vision bypasses fill reduction. Lamp & Held Strength scales the new
pools; the existing emissive radius/intensity/saturation settings now label their
ore-only scope. The actual ore transport is unchanged.

Both light samplers now start outside the receiver's coarse owner cell, matching
the existing contact-occlusion correction. Geometric normals select cells; PBR
normals retain surface form shading without changing that selection. This avoids
partial-height dark bands and texture-dependent voxel selection. Decorative
quartz/crystal/sculk materials reject their own aura while receiving other light.
Lamp spill uses a 0.85 linear multiplier. Indoor gaps have a separate bounded
0.85 base-fill gain that fades out around bright pools, outdoors and night vision.

The extra RGBA16F pair costs 6.75 MiB. A 1.69 MiB R32UI contact-plane cache brings
total local-volume texels to 15.61 MiB.
There is no additional dispatch or screen pass; surface shading adds eight fetches
and compute adds bounded neighbor work. History takes up to 15 frames to settle,
reprojects using integer camera deltas and rejects teleports above 16 blocks.
Translucent terrain is submitted for capture but clipped before sun-shadow rasterization.
Block-entity-only sources lacking terrain geometry keep scalar lighting; no
unsafe source position is inferred from animated models. See
[Iris capture directives](https://shaders.properties/current/reference/shadersproperties/ordering/)
and [measurements](lamp-lighting-validation.md).

### 1.8 optimization

`xonSampleLocalLights` shares coordinates, interpolation weights and bounds work
between the two light fields. Zero interpolation weights skip fetches exactly.
Production geometry gathers once, classifies materials once, and keeps fewer
intermediate values live across lighting/PBR work. Independent emissive materials
skip unused light evaluation. Small addition-order differences stay at float
rounding scale in the parity suite; source fields and POM hits match bit for bit.

Contact shading rejects whole non-facing/out-of-radius layers for axis-aligned
faces. Arbitrary normals retain the complete original kernel. The compute pass
also caches 27 occupancy bits per voxel: nine bits for each 3×3 axis plane.
A cooperative 10×10×10 shared tile supplies occupancy to each 8×8×8 workgroup,
including its halo, using 4,000 bytes of shared memory. At an exact axis boundary,
an empty plane proves visibility is exactly 1. Occupied planes supply their
blocker bits directly to the unchanged weights, avoiding repeated texture reads.
Other positions use the original stencil. Near-axis camera-roundtrip normals
retain the same weights at an exact boundary. The mask is rebuilt every frame,
with no history delay or quality/sample reduction. Compute work rises slightly while
fragment work falls.

The sampling boundary gates prove the following stencil is in bounds, removing
redundant per-fetch checks. Translucent shadow vertices that cannot capture a
source return before transforms. The POM ray loop uses its existing adaptive
quality bound directly, retains all refinements, and reuses its vector length.
See [pixel, cache-oracle and timing results](lighting-optimization.md).

## Indoor lighting in 1.7

`xonLocalLightForm` adds world-normal face contrast to scalar block lighting and
colored spill. The six axis-aligned gains average to unity; the factor fades with
skylight and excludes foliage, emissive surfaces and night vision. Existing local
strength, lightmap falloff and colored-light reach settings are unchanged.

Terrain adds contact occlusion inside the existing local volume while Colored
Block Light is enabled. A compact 3x3x3 candidate stencil samples only the outward
hemisphere within 1.5 blocks; the kernel vanishes at its support boundary and
fades at the volume edge. Receiver sampling starts outside the coarse owner cell,
including inset surfaces. This is local contact shading, without source vectors
or individual lamp-shadow tracing. It adds local sampling work but no pass/image.

`block.10028` identifies verified full-cube shapes, including explicitly matched
full-block states. `tools/indoor_block_shapes.py` generates/checks its 485 selectors
against installed Minecraft 26.3 model inheritance. Unknown and partial shapes
are excluded from extra contact occlusion. Voxel marker 255 and light alpha -2
identify verified opaque cubes; ordinary solid marker 1 retains alpha -1. Both
block flood-fill transport exactly as before, and negative alpha remains excluded
from colored-light interpolation. Source emitter IDs/colors are unchanged.

The local tests and remaining live checks are recorded in
[VERIFICATION.md](../VERIFICATION.md). Historical architecture notes follow.

## Earlier architecture notes

Architecture notes originating with **XON Shader 1.3**. See [VERIFICATION.md](../VERIFICATION.md)
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

End sky details are isolated in `lib/end_sky.glsl`, called only by the End sky
program. Terrain/fog lighting retains the existing cheaper atmosphere functions.
Four reused noise-atlas reads shape a great-circle galaxy, dust lanes and colored
nebulae. Two bounded ALU star fields use footprint filtering. A projected black-hole
region samples one 1024-square RGBA8 map: RGB encodes sqrt(linear radiance/16),
alpha contains horizon/disk occlusion. This is about 4 MiB of additional texture
texels before driver overhead/mipmaps, omitted when Black Hole is disabled.

End cube and celestial draws retain their different native blend states. The
End textured fragment uses blendFunc's additive destination factor to identify
flashes and preserve their texture alpha/intensity, rather than drawing another
opaque galaxy patch. No blanket sky-texture blend override is installed.

`tools/make_black_hole.py` solves `u'' + u = 1.5 u^2`, using Schwarzschild-radius
units and RK4. Critical impact is sqrt(27)/2; the disk extends from the Schwarzschild
ISCO at 3 radii to 12 radii and is inclined 86 degrees. Three disk crossings,
gravitational redshift and approximate orbital Doppler transfer generate the image.
Emissivity, color temperature and gas opacity are shaped for the visual target.
The result is a fixed observer transfer image, not an evolving physical simulation
or gravitational lensing of arbitrary world geometry. See the
[Schwarzschild light-path derivation](https://doi.org/10.1088/0004-637X/800/1/77)
and [visual checks](visual-polish-validation.md).

Cloud formations blend shape/threshold/relief parameters before opacity, sharing
the existing three heightfield reads, Worley evaluations and lighting probes.
Independent detail drift supplies shape evolution. A 900-second formation cycle
and 3600-second closed wind path meet continuously at Iris's hourly timer reset.
Ground cloud shade retains its prior independent artistic field. Lava glow adds
only a heat-weighted gain in the lava branch while Bloom is enabled; no global
bloom threshold/kernel, image or pass is added.

Settings retain stable option IDs, explicit page columns and concise value
translations. Release checks validate navigation, option coverage, slider values
and hover help. The overview uses two columns; setting pages use one.

Emitter saturation is evaluated only when injecting source colors in the compute
pass. Chroma is scaled around Rec.709 linear luminance, with gain limited to
retain a faint channel floor (1% of luminance); colors already below that floor
retain their original saturation. The default requests 1.35; 1.00 returns the original
color exactly. Source strengths, propagation and receiving math are retained.
Jack-o-lantern material 10027 maps to voxel ID 15 (amber); existing soul-lantern
material 10026 maps to ID 16 (cyan). Regular lanterns, torches and end rods retain
scalar lamp lighting. Jack surface emission and soul core/frame masks are retained.

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

Ordinary lamps use the interpolated block-light coordinate; jack/soul lanterns
also contribute their new local colored auras. The cubic response
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
