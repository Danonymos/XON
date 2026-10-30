# XON 1.0.3.3 - lichen and shallow-water fixes

Includes stationary glow lichen and stronger blue tint for thin water sheets. Deep water and underwater clarity remain unchanged.

# XON 1.0.3.2 - glow lichen fix

Glow lichen now uses a stationary material rather than the waving cross-plant group. This prevents wind moving its thin faces into the supporting block and restores its face normals. Other plants retain wind. Includes the shallow-water fix.

# 1.0.3.1

- Keep thin refractive water visible indoors using a restrained blue-green surface tint, smoothly fading out by 1.5 blocks of view-depth thickness.
- Preserve deep-water shading, underwater clarity, lighting, rainbow outline and camera defaults from 1.0.3. No additional texture samples or render passes.

# 1.0.3

- Refine light-oriented diffuse shading and warm simulated ground bounce; replace camera-dependent matte rim shine with light-dependent form.
- Add subtle luminance-balanced blue shade tint, applied before warm local lights. Modestly lift readable night/cave fill.
- Reshape block-light falloff and soften orange highlights with a restrained ivory core; no change to light propagation radius.
- Skip view-vector normalization on non-foliage surfaces after removing their camera-dependent rim term.
- Set Smooth Camera Motion ON and Motion Blur Smoothness 1.50 by default.
- Add eight smoothly interpolated outline colors, half-speed rotation, brightness equalization and 25% thicker selection lines. Preserve debug lines.
- Retain 1.0.2 water/material optimizations, quality budgets, LUT and saturation. Add visual/exposure, nighttime readability and local-light monotonicity checks against 1.0.2.

# 1.0.2

- Preserve the accepted 1.0.1 color LUT, atmosphere palettes, saturation, exposure defaults, light radius, clouds, water waves, AA and motion blur.
- Skip discarded diffuse lighting and architectural relief work for lava, Nether portals, and froglights. Refractive water evaluates only the receiver shadow needed for glints; non-refractive water retains its diffuse lighting.
- Skip unused sky evaluation in water/lava/snow fog and unused water reflections when submerged. Simplify horizon-direction normalization with pixel parity checks.
- Add optional Smooth Shadow Transitions (default OFF; ON in Cinematic), continuously morphing 4/2/1-tap filtering at 20/42 blocks with no extra shadow samples. Off preserves 1.0.1 filtering and avoids its measured extra GPU cost.
- Replace reversed-edge portal smoothstep with its defined inverse form for portability.
- Add reproducible 1.0.1/1.0.2 GPU pixel comparisons, timing queries and shadow continuity tests. Expand compilation to ten configurations; correctly override const shader options in the validator.

# 1.0.1

- Add 5-stage Time-of-Day Mood & Vibe system (`xonTimePhases` in `atmosphere.glsl`, `clouds.glsl`, `lighting.glsl`): distinguishes Early Morning / Dawn (pearlescent rose-gold sun, rose-azure horizon, dewy cyan shade), High Noon (crisp cobalt sky, balanced warm-white sun), Warm Afternoon (honey-gold grazing light, deep cobalt-indigo shadows), Evening Sunset / Dusk (copper-amber western glow, royal twilight violet sky/void/undersides), and Night (midnight sapphire sky with silver-blue lunar glow).
- Add ~20-block-radius moving & gradually morphing 2D Voronoi ground cloud shadow and zenith highlight system (`xonCloudGroundLight`), distance-culled beyond 128 blocks and optimized with a 2x2 nearest-quadrant pure-ALU hash (zero `sin()`/`sqrt()` SFU stalls).
- Add Photon-style Dark Area & Cave Visibility (`shadowDeficit` + `XON_DARK_LIFT` + `isDarkArea` dark-albedo toe lift) so zero-skylight overhangs, giant tree stems, and caves stay readable without overexposing bright/sunlit surfaces.
- Add always-on cylindrical chunk-border horizon fog (`borderFog` in `atmosphere.glsl`) that smoothly blends the outer edge of the player's render distance (`far`) into the directional horizon sky across both terrain and water.
- Add architectural castle/surface lighting polish: tighter close-range shadow normal bias (`0.048` blocks) with 4-tap rotated orthogonal hardware-PCF within 28 blocks, 6-axis directional face separation, wrapped grazing sunlight, arch upward ground-bounce, and zero-mean screen-space derivative (`dFdx`/`dFdy`) stone brick micro-bevels.
- Anti-stutter & FPS optimization pass: replace `3x3` transcendental `sin()` Worley/Voronoi loops with `2x2` nearest-quadrant ALU-only hashes, increase `shadowIntervalSize` (`2.0` -> `4.0`) to halve Sodium shadow chunk re-culling spikes, distance-cull cross-plants (`block.10004`) in `shadow.vsh` beyond 44 blocks, discard unlit daytime star quads in `sky.fsh`, and skip cardinal neighbor fetches on sky/hand pixels in `antialiasing.glsl`.
- Expand Shader Pack Settings with 10 intuitive customization sliders (`XON_CONTRAST`, `XON_SHARPNESS`, `XON_BLOOM_STRENGTH`, `XON_DARK_LIFT`, `XON_BLOCKLIGHT_WARMTH`, `XON_TIME_MOOD`, `XON_CLOUD_DENSITY`, `XON_GROUND_SHADOW_STRENGTH`, `XON_WAVE_HEIGHT`, `XON_END_AURORA`), 4 one-click Profiles (`Speed`, `Balanced`, `Vibrant Fantasy`, `Cinematic Ultra`), and detailed tooltips in `en_US.lang`.

# 1.0.0

- Fix End dimension sky (`world1/gbuffers_skytextured` + `blend.world1/gbuffers_skytextured=off`): replace Minecraft's pixelated `end_sky.png` quad dome with XON's smooth dark purplish-black void, animated cosmic aurora ribbons, and twinkling star specks.
- Add Voronoi cellular lava shader (`block.10005` in `geometry.fsh`): multi-layered scrolling convection cells with dark cooling basalt crust, warm orange magma scatter, and white-hot glowing fissures.
- Upgrade clouds (`clouds.glsl`) to a spherical-dome Perlin-Worley 3D cumulus + high-altitude cirrus system with rounded cellular cauliflower domes, cerulean-lavender shaded undersides, and golden-ivory sunlit crowns.
- Upgrade water surface (`geometry.fsh`) with a 3-tier wave hierarchy (wind swell, trochoidal sharpened wavelets, and capillary surface ripples), turquoise wave-crest subsurface glow, bounce-stabilized cloud reflections, and dual sun/moon water glitter.
- Fix Amethyst shards (`block.10019`): separate amethyst clusters/buds & purple portals from sculk/accent blocks (`block.10020`), remap pale whitish crystal tips into rich royal amethyst purple, and cap peak luminance below the white bloom threshold.
- Keep opaque terrain blocks (carpets, wood, stone) naturally matte by restricting specular reflections to water.
- Add Enhanced Ambient Occlusion (`separateAo=true` + `XON_AO_STRENGTH` slider), Vertex-Stage Waving Foliage (`XON_WAVING_FOLIAGE`) synchronized across both `geometry.vsh` and `shadow.vsh`, and Underwater Light Caustics (`XON_CAUSTICS`).
- Fix unlit additive/multiplicative passes (`gbuffers_damagedblock`, `gbuffers_armor_glint`, `gbuffers_spidereyes`, `gbuffers_beaconbeam`) so fog color never corrupts their blend equations underwater or in the Nether.
- Fix false-positive `isCrossPlant` normal/AO overrides on diagonal non-plant blocks.
- Major FPS & AA optimization: eliminate redundant per-fragment `xonSunDirection()` matrix transforms, unify Boost reconstruction and 4-tap sub-pixel Edge AA cardinal neighbor fetches in `antialiasing.glsl`, and add a stationary camera fast-path in `xonCameraVelocity`.

# 0.4.0 beta

- Fix moving shadow band on wheat/crop fields and grass (`block.10004` + cross-quad detection): assign upward surface normals (`vec3(0,1,0)`), slope-scaled shadow normal bias, and shadow-frustum box fade (`edgeDist`) so crops no longer self-shadow within the camera-following shadow map.
- Fix underwater visibility: add a 6-block clear near-zone, lower underwater fog density (`0.016`) and cap maximum opacity at `82%`, add cyan-teal underwater ambient fill in `lighting.glsl`, and prevent double-darkening when looking up at the water surface from underwater.
- Fix Nether darkness and red-void cutoff: restore Nether distance fog (`XON_DIMENSION == -1`) so distant chunks blend seamlessly into the biome horizon, brighten Nether ambient and ceiling/wall shading (`netherVertical`), and add warm upward lava bounce fill.
- Add dark purplish-black End aura sky (`XON_DIMENSION == 1`): deep void black-to-violet gradient with animated multi-layered cosmic purple/magenta aurora ribbons and twinkling star specks.
- Enhance day/night cycle and golden-hour lighting: add multi-stage noon/afternoon/golden-hour/dusk/night sunlight and sky ambient transitions, subtle warm bounce light in open shade, and foliage subsurface scattering.
- Upgrade shadow filtering to a rotated 2-tap hardware-PCF kernel, refine depth-curvature edge AA, and replace transcendental `pow()` calls with fast multiply chains across sky, clouds, water, lighting, and sun rays.

# 0.3.0 beta

- Add Color Saturation slider (`XON_SATURATION`) defaulting to 70% (`0.70`), allowing users to desaturate to 0% or boost to 100%+ of the 0.2 baseline and up to 140%.
- Add Motion Blur Smoothness slider (`XON_BLUR_STRENGTH`) to adjust camera motion blur intensity and radius.
- Fix block selection outline visibility and geometry expansion (`gbuffers_line`), and add `XON_BLOCK_OUTLINE` option for Black Outline or animated Rainbow Outline.
- Replace repetitive three-cosine water waves with non-repeating multi-scale organic domain-warped water waves.
- Improve GPU/CPU performance: reduce default shadow distance to 64 blocks, disable entity shadow draw calls by default (`shadowEntities=false`), optimize shadow receiver to 2-tap diagonal hardware PCF with squared-distance early exit, cone-cull sun shafts and optimize to 4 jittered steps, reduce bloom prefilter to 4 bilinear taps, and cache hand mask & skip sky in final pass.

# 0.2.0 beta

- Add real 1024-pixel directional sun/moon shadows with a bounded 80-block range.
- Strengthen warm sunlight, cool shade and smooth warm block light; retain vanilla AO.
- Add selectively emissive ore veins and restrained half-resolution bloom.
- Add a highlight-preserving filmic curve and an original color LUT for richer color.
- Add soft layered clouds, cloud occlusion of stars/sun/moon, and darker storm clouds.
- Add three-wave water detail, cloud reflections, depth absorption and optional refraction.
- Add lightweight depth-guided edge AA in the existing final pass, enabled by default.
- Disable air haze by default; preserve underwater absorption and status effects.
- Add localized shadow-map sunlight rays and Speed/Balanced presets.
- Retain default subtle camera blur, Native resolution and optional spatial Boost.

# 0.1.0 beta

- Add original forward lighting with warm sun, cool sky fill, vanilla AO, and held light.
- Add an analytic sky, relit vanilla clouds, rain/thunder response, and dimension palettes.
- Add bounded analytic water waves, depth-sensitive color, and sky reflections.
- Add default five-tap camera blur with hand exclusion and discontinuity guards.
- Add experimental 85%/75% spatial Boost modes; default remains Native.
- Keep the native pipeline to one HDR scene color attachment, one small hand mask,
  and a single final post pass, with no temporal history or shadow maps.
