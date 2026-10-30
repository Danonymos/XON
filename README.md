# XON Shader - 1.0.4

An original performance-first Iris shader pack with warm directional sunlight,
5-stage time-of-day atmospheric moods (Early Morning, Noon, Warm Afternoon, Evening Sunset, Night),
real cast shadows, Photon-inspired cool readable dark-area shadow fill, 20-block Voronoi moving ground cloud shadows,
cylindrical chunk-border horizon fog, chiseled castle/surface micro-bevel lighting, waving foliage,
Voronoi cellular lava, underwater caustics, cosmic End aurora sky, glowing ore & royal purple amethyst veins,
Contrast-Adaptive Sharpening (CAS), 4-tap sub-pixel edge AA, and smooth camera motion blur.

## What changed in 1.0.4

- Soft blue-green underwater God rays with refracted light direction, shadow
  occlusion, foreground-depth clipping, daylight gating and a restrained cap.
- Outdoor rays have a subtle wider shoulder and activate at lower skylight levels,
  making sunbeams through building openings easier to see while keeping clear air.
- Direct sun/moon and local/held light contributions default to 80% of 1.0.3.3.
  Ambient shade and its subtle blue tint retain their previous values. This reduces
  light intensity rather than lowering the overall exposure or darkening shadows.
- New controls: Direct Sunlight Strength, Torch and Held Light Strength, God Ray
  Intensity, and Underwater God Rays. Ray effects require Shadows and Localized
  Sun Rays; Speed disables them. No additional render pass or history buffer.
- Includes the glow-lichen stability and visible shallow-water fixes.

The existing half-resolution ray pass uses four shadow samples outdoors and six
underwater, with a 32-block underwater range cap. This adds a small GPU cost;
see source `VERIFICATION.md` for measured synthetic pass timings. The underwater
refraction assumes a flat surface and is an artistic approximation.

## Shallow-water fix in 1.0.3.1

Thin water sheets viewed from outside the water now retain a subtle blue-green
surface tint, including indoor bucket spills. The extra tint fades smoothly to
zero at 1.5 blocks of view-depth thickness. Deeper water and underwater viewing
retain 1.0.3 shading. No new texture samples, passes or buffers are added.

## What changed in 1.0.3

- Light-oriented diffuse shaping gives block faces more definition; matte blocks
  no longer acquire camera-dependent rim shine.
- Warm simulated ground bounce and cooler sky fill give ledges and walls more
  depth. Night and cave fill remain readable.
- Subtle blue shade tint fades toward warm sunlight with nearly neutral luminance.
  Local warm lights are added afterward, keeping their warm color.
- Smoother local-light falloff with a restrained ivory core. This reshapes vanilla
  lightmap shading; it does not extend the world's light propagation radius.
- Smooth Camera Motion ON and Motion Blur Smoothness **1.50** by default.
- Rotating eight-color outline at half speed, 25% thicker selection lines, eased
  transitions and more consistent brightness. Debug-line width remains unchanged.

The 1.0.2 water/material optimizations, LUT, saturation, sky, native resolution,
shadow map size and sample budgets remain intact. No new render pass, texture
lookup, history buffer or tracing was added. Smooth Shadow Transitions remains
optional (OFF by default).

## Performance foundation from 1.0.2

This release preserves the 1.0.1 LUT, saturation, time-of-day colors, brightness,
water waves, cloud design, light radius, and quality defaults. It removes lighting
work discarded by lava, portal, froglight and refractive-water shading, and avoids
unused sky/reflection calculations underwater. No rendering resolution reduction
or feature removal is used to achieve these savings.

Lighting, Color & Shadows now offers **Smooth Shadow Transitions**. It blends the
filter shapes at 20 and 42 blocks to reduce moving shadow pops without increasing
the maximum sample count. It is OFF by default because additional filtering math
can cost GPU time; Cinematic enables it. Balanced/Speed/Vibrant leave it off.

Synthetic GPU comparisons show the largest savings on water and emissive materials.
They do not establish an in-game FPS gain. See `VERIFICATION.md` in the source.

## Install

1. Keep a working Fabric + Iris + matching Sodium installation. Initial target:
   Minecraft Java 26.3, Iris 1.11.7, Sodium 0.9.2.
2. Put `XON-Shader-v1.0.4.zip` directly in that installation's `shaderpacks`
   folder. Do not extract it and do not place it in `mods` or `resourcepacks`.
3. Open Video Settings → Shader Packs, select XON, and Apply.
4. Begin with the default Balanced preset and Native resolution. Select Speed if
   maximum frame rate is preferred over cast shadows and post effects.

## Defaults

- Native resolution; brightness 1.05; sunlight warmth 0.65; color saturation 70% (0.70).
- Subtle camera motion blur ON with adjustable Motion Blur Smoothness slider (default 1.50);
  blur radius is capped and held items use a dedicated exclusion mask.
- Block Selection Outline ON (default Rainbow Outline, switchable to Black Outline).
- Directional sun/moon shadows ON: 1024 map, 96-block distance, distance-adaptive 4/2/1-tap hardware-PCF,
  cross-foliage upward normals & self-shadow acne elimination, and entity shadows off by default.
- Rich day/night/golden-hour/sunset lighting transitions with subtle warm sky bounce and foliage subsurface scattering.
- Selective ore emission, 4-tap bloom, held light, an original 16-cube color LUT,
  soft layered clouds, organic non-repeating water waves/refraction, and sharp edge AA ON.
- Air fog OFF. Clear-weather distance haze is removed; water/lava/powder-snow
  absorption and blindness/darkness remain. Rays use 4 outdoor / 6 underwater steps with directional culling.
- Water refraction, bloom and sunlight shafts use half-resolution
  buffers. Edge AA shares the final pass and rejects texture-only edges.
- No voxel lighting, screen-space reflection tracing, temporal AA/history,
  external PBR textures, runtime downloads, or additional mod dependency.

## Performance controls

Balanced is the default visual upgrade. Speed removes shadow rendering, rays,
bloom, water refraction and procedural clouds while retaining richer directional
lighting, ore emission, the LUT and edge AA. Individual effects can also be
disabled in Shader Pack Settings. Shadow resolution and distance are deliberately
limited; higher settings spend more GPU time. Features cannot guarantee the same
FPS on every machine or make CPU simulation faster.

## Experimental Boost

Shader Options → Performance → Render Mode offers 85% and 75% world rendering.
The shader draws into a smaller region and spatially reconstructs at display
resolution, with restrained sharpening. Game UI stays at display resolution.
Native remains the default. Boost can look softer, especially in foliage and
thin geometry; it is not temporal super resolution and does not accelerate CPU
simulation or chunk generation. FPS gains are hardware/workload dependent and
are not promised.

## Test the beta

Compare the same position, resolution, render distance, weather, and camera
movement with shaders disabled, XON Native, and optionally XON Boost. Check a
daytime landscape, white blocks, indoors with a torch, sunset, night, an ocean,
underwater, rain, the Nether, and the End. Rotate the camera to check subtle blur
and confirm held items and crosshair remain clear. Do not change time/weather
on a multiplayer server just for this test.

## Known beta limits

Ore glow is emissive surface shading plus a small halo, rather than colored
light propagation into neighboring blocks. Vanilla block light remains smooth
and warm. Sun rays sample the shadow map; this is not global ray tracing.

Cast shadows fade before 96 blocks by default. Translucent blocks do not cast
colored shadows. The compact map can show fine-detail aliasing. Clouds use two
height layers rather than a volume simulation. Water reflects the sky/clouds
rather than buildings or off-screen geometry; the half-resolution refraction
copy can soften submerged texels. Edge AA handles visible geometric edges but
cannot recover unseen subpixel detail or provide temporal stability like TAA.
No independent moving-object blur. Unknown modded
dimensions use the Overworld fallback. Distant Horizons, Voxy, VR, Vulkan,
Bedrock, OptiFine, macOS, and older Minecraft versions are not certified.

Check `VERIFICATION.md` in the source folder for the checks actually performed.
A successful driver compile does not by itself prove an Iris/game load or an
FPS improvement. Send the XON-specific error from your instance's
`logs/latest.log` if loading fails.

## Source and build

All shader source in this pack was authored for XON. The four supplied shader
archives were used as study references; none of their code or textures is
included. No additional runtime dependency is required beyond the shader loader.

Run `python tools/build.py` from this source folder to generate the thin program
wrappers and produce the ZIP one directory above. Developer checks and reports
are excluded from the runtime pack.
