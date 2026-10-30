# Changelog

Player-facing changes from the first XON beta to the current **1.0.7** build.
Versions describe the final behavior of each build; experimental implementations
that were later corrected are identified below. Validation details and measured
limits are recorded in [VERIFICATION.md](https://github.com/Danonymos/XON/blob/main/VERIFICATION.md).

## 1.0.7 — Smoother edges, softer light, moving moonlit landscapes

### Added and improved

- Built-in adaptive spatial anti-aliasing in every preset, replacing the selectable
  FXAA/SMAA-style span searches with bounded edge reconstruction.
- Subpixel coverage filtering shared with the existing six motion-blur samples,
  symmetric shutter weights and a smooth transition between static and moving AA.
- Minification-only terrain mip stabilization, including distant walls. Preserve
  close texture detail, known foliage coverage and unmapped cutout alpha.
- Three extra open blocks of softly eased colored ore light. Quintic falloff and
  spatial interpolation let the aura blend into darkness; the default setting now
  reaches about seven blocks along open paths.
- Cloud-shadow drift at **one block every two seconds**, with proportionally faster
  merging and separation, broad eased edges and a seamless hourly animation cycle.
- Up to **28% brighter cool blue moonlight** in exposed cloud openings, while
  retaining shaded patches, local lights and the accepted daytime palette.

### Fixed

- Reproduced camera-following terrain shadow rings caused by incorrect filtered
  surface-depth comparisons. Surface-plane correction accounts for nonlinear
  shadow-map distortion and the hardware filtering footprint.
- Abrupt ore-light cutoff and the hard AA handoff during gentle camera movement.
- First-person hand boundaries remain protected from camera/filter smearing.

### Performance and checks

- Keep existing shadow resolution/range, render passes and light-volume storage.
  Reuse filtering samples and the game's mip chain; add no temporal-history buffer.
- Retain camera blur controls and optional nearby surface filtering. AA itself is
  now built in, with no player-facing on/off or quality selector.
- Add actual GPU coverage, movement, alpha, hand, thin-line, shadow-ring and aura
  regression tests. The current source passes 840 graphics configurations and
  790 GPU cases/comparisons; live Minecraft/FPS verification is still separate.

## 1.0.6 — Working colored ore light and evolving cloud shade

### Fixed

- Connect the voxel-lighting implementation to Iris's required custom-image and
  compute features, enable capture and keep nearby emitters in the shadow draw list.
- Add shadow/capture and compute entrypoints for the Overworld, Nether and End.
- Preserve source textures while quartz ore and architectural quartz cast violet
  light onto neighboring surfaces.
- Keep mapped plants, leaves and lichen from becoming solid light blockers.

### Improved

- Replace dark cellular spots and thin bright ridges with balanced, irregular
  cloud-light and shadow patches, typically 30–50 blocks across.
- Add broad quintic edge transitions and independently moving layers so patches
  drift, join and separate. Keep the hourly timer reset seamless.
- Extend ground-cloud modulation toward the render horizon and use the existing
  sun/moon palette instead of an unrelated additive highlight.
- Retain the compact 96×48×96 light volume, six-neighbor propagation, interpolated
  surface sampling, solid-wall blocking and stale-history rejection.
- Add real GPU capture/compute/terrain tests, including light removal, mixed
  colors, camera movement and all three dimensions.

## 1.0.5 — Underwater shafts and the initial voxel-lighting implementation

- Let underwater rays look through the water surface to solid scene depth, so
  overhead water no longer truncates sunlight shafts close to the camera.
- Extend underwater sampling toward distant shadow casters, within the existing
  shadow-map range; use a bounded near-camera clarity ramp and marine scattering.
- Hoist the shadow transform out of the ray loop and improve underwater background
  and horizon blending while preserving surface transmission.
- Introduce the camera-centered voxel capture, ping-pong flood fill and colored
  surface sampling. This was the initial implementation; missing loader/capture
  connections were repaired in **1.0.6** before working environmental spill was confirmed.
- Separate architectural quartz from emissive surface shading to preserve building detail.

## 1.0.4 — Readable building shadows and underwater lighting

Includes the revised and water-stability builds prepared during development.

- Add adjustable outdoor and underwater sunlight shafts, respecting shadow
  occlusion, water/depth boundaries, medium and user settings.
- Use Iris's active sun/moon direction for surface lighting. Keep opaque backfaces
  dark, restrict wrapped lighting and reduce wall ambient fill that flattened form.
- Improve readable shade and night-vision contrast; reduce default direct and
  local-light intensity to 80% of the earlier setting.
- Refine normal bias and range fading within the existing shadow-map budget.
- Replace the rejected smoky underwater field with shadow-defined scattering;
  improve depth stability, marine absorption and the clear near-camera region.
- Add building, camera-motion, water and ray regression scenes. Later 1.0.5 work
  further improves the underwater surface-depth look-through and distant reach.

## 1.0.3.3 — Combined lichen and shallow-water fixes

- Ship stationary glow lichen and visible thin-water tint together.
- Preserve deep-water clarity, existing lighting and camera defaults.

## 1.0.3.2 — Stationary glow lichen

- Remove glow lichen from waving cross-plants, preserving its face normals and
  keeping thin faces from moving into the supporting block.
- Retain wind animation for actual plants and foliage.

## 1.0.3.1 — Visible shallow water

- Add restrained blue-green tint to thin water sheets, including indoor spills.
- Fade the extra film tint out by 1.5 blocks of view-depth thickness, preserving
  deeper water and underwater viewing without extra passes or texture samples.

## 1.0.3 — Lighting shape and camera polish

- Refine light-oriented diffuse shading, warm bounce and cool directional sky fill.
- Replace camera-dependent matte rim shine with light-dependent surface form.
- Improve night/cave readability, local-light falloff and restrained ivory light cores.
- Set smooth camera motion ON with default smoothness 1.50.
- Add an eased eight-color rotating outline at half speed, with more consistent
  brightness and 25% thicker selection lines; preserve debug-line width.

## 1.0.2 — Performance groundwork

- Skip lighting and reflection work discarded by independent emissive materials,
  refractive water and underwater composition.
- Simplify horizon evaluation and avoid unused calculations with parity checks.
- Add optional smooth shadow-filter transitions at 20 and 42 blocks without
  increasing the maximum lookup count.
- Correct the portal smoothstep expression and broaden shader/pixel validation.

## 1.0.1 — Time-of-day moods and architectural detail

- Add distinct early-morning, noon, afternoon, sunset and night atmosphere palettes.
- Introduce the original moving ground-cloud light field, later redesigned in 1.0.6.
- Add cool readable dark-area fill, cylindrical render-border fog and surface relief.
- Optimize cellular searches, foliage shadow capture and unnecessary post work.
- Expand the shader controls and the Speed, Balanced, Vibrant and Cinematic presets.

## 1.0.0 — XON's visual foundation

- Add a purple End aurora, layered cumulus/cirrus sky and cellular lava fissures.
- Build layered organic water waves, crest color and sun/moon surface glints.
- Improve crystal, portal and froglight material handling; keep solid terrain matte.
- Add ambient-occlusion controls, synchronized foliage animation and water caustics.
- Correct unlit/additive blending and non-plant cross-quad detection.
- Share reconstruction samples and add a stationary-camera blur early exit.

## 0.4.0 beta — Dimension and shadow fixes

- Improve crop/grass shadow normals and self-shadow bias.
- Add clearer nearby underwater visibility and brighter readable Nether lighting.
- Introduce the End atmosphere, softer directional shadows and weather transitions.

## 0.3.0 beta — Color and camera controls

- Add saturation, blur smoothness and customizable black/rainbow block outlines.
- Replace repetitive water waves with layered, warped motion.
- Reduce shadow/post costs and share AA/reconstruction work.

## 0.2.0 beta — Shadows, atmosphere and materials

- Add directional sun/moon shadows, ore surface glow, local bloom and a color LUT.
- Add layered clouds, weather response, water depth/refraction and localized rays.
- Introduce the Speed/Balanced presets and lightweight spatial edge smoothing.

## 0.1.0 beta — First shader pack

- Add warm directional lighting, cool fill, vanilla AO and held light.
- Add analytic skies, weather/dimension palettes and bounded water motion.
- Add protected camera motion blur and experimental 85%/75% spatial Boost rendering.
