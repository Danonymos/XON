# XON Shader 1.7

Warm light, clear water and a world in motion. XON is an Iris shader pack for
Minecraft: Java Edition, with directional shadows, moving cloud shade, colored
ore illumination, layered water, volumetric light shafts and built-in anti-aliasing.

## Install

1. Use a compatible Minecraft Java + Iris + Sodium installation. The development
   target is Minecraft Java 26.3, Iris 1.11.7 and Sodium 0.9.2.
2. Place XON-Shader-v1.7.zip directly in your instance's shaderpacks folder.
   Do not extract it or install it as a mod/resource pack.
3. Open Video Settings → Shader Packs, select XON and Apply.
4. Start with Balanced + Native. Speed lowers the effect budget.

## Highlights

- More depth in indoor lamp lighting, with stronger face contrast and soft contact
  shade around solid walls, pillars, beams and corners.
- Shape-aware occlusion and corrected receiver sampling prevent false full-block
  contact shadows and repeating self-shadow patches on partial or inset surfaces.
- Existing lamp strength, propagation ranges, source glow and warm colors are retained.
- Additional geometry occlusion uses Colored Block Light; Speed keeps its lighter path.
- Temporal anti-aliasing with eight jitter positions, sharp history reconstruction,
  depth/visibility checks and protection for held items. Uses standard GLSL across GPU vendors.
- Camera & Detail → Anti-Aliasing offers Temporal (default), Fast (Speed preset) and Off.
- Evaluate Balanced + Native + Temporal with external upscaling disabled first.
- The final partial-shape correction has GPU coverage; its live visual recheck,
  full-game FPS and AMD/Intel hardware testing remain outstanding.
- Optional LabPBR 1.3 and OldPBR materials for resource packs such as Primes HD Textures.
- Cleaner POM with filtered height/color sampling, adaptive tracing and refined intersections.
- Atlas bounds, distance fades and nearly edge-on fading keep surface relief controlled.
- GGX highlights respect material reflectance, skylight and shadow visibility.
- Lower exposure calibrated against 1.3, preserving the warm 1.4 colors, grading texture and atmosphere.

Enable Shader Settings → Materials & PBR → Advanced Materials with a compatible
resource pack. It defaults to Off; Cinematic enables it. POM needs height-map data
and adds GPU work. Flat or missing height maps remain flat.

- Volumetric light shafts with dual-lobe scattering that stream and wrap around building silhouettes.
- Directional ground bounce and vertical skylight gradient giving backlit structures rich 3D depth.
- Stratified height-density atmosphere and solar in-scattering aura preserving crystal-clear clarity.
- Edge-preserving bilateral depth filter for rays in composite1, preventing beam leakage across silhouettes.
- Blue-violet End galaxies with magenta clouds, pale star bands and dark dust lanes.
- A luminous black hole with offline-traced disk images, redshift and Doppler brightness.
- Cumulus, cloudlets and veils blending through a seamless 15-minute cloud cycle.
- Adjustable lava glow, using the existing bloom passes and preserving dark crust.
- Focused settings pages with wide controls, short labels and hover explanations.
- Colored block-light saturation defaults to 135%, with luminance-preserving
  color limits. Set Light Saturation to 100% for the previous color response.
- Amber jack-o-lantern spill and cyan-teal soul-lantern spill on nearby blocks.
- Soft distant-foliage shading that follows the sun/moon, with a broader shadow handoff.
- Purple amethyst blocks, mint glow lichen, warm glow berries and cyan sculk veins.
- Violet quartz stairs/slabs, extending the existing full-block quartz aura.
- Brighter regular/soul lantern cores with normally shaded metal frames.
- Compact, smoothly eased bloom with about 30% more shared bloom energy.
- Occluder-edge light sampling fades tiny contributions instead of amplifying flashes.
- Gentler indoor lamps and held lights, with smooth falloff into readable shade.
- Continuous indoor/outdoor blending, quieter daylight and balanced Nether/End fill.
- Pale golden light, teal-blue shade, deeper blue nights and a gentler base exposure.
- Shadow-aware moon glints and block-surface relief aligned with the active light.
- Exact foliage work skips, without extra passes, images or texture lookups.
- Temporal AA in Balanced/Vibrant/Cinematic; Fast spatial AA in Speed.
- Motion filtering that shares the six camera-blur samples and protects held items.
- Gentler distant mip detail while preserving nearby textures and cutout coverage.
- Colored ore light with a three-block eased outer aura; default extent is about
  seven open blocks. Quartz illuminates nearby surfaces with violet light.
- Balanced, soft ground cloud shade drifting one block every two seconds, with
  brighter cool blue moonlit openings and corrected terrain self-shadow rings.
- Layered water waves, refraction, caustics and shadow-shaped underwater shafts.

## Performance and limits

Native is the default. Boost 85%/75% lowers world shading resolution and may look
softer. Temporal AA adds one full-resolution pass and a persistent RGBA16F history
buffer pair (about 32 MiB at 1080p, before driver overhead). Fast omits that pass;
camera blur and extra nearby surface filtering are separate settings.
Speed disables colored voxel lighting and expensive effects.
It also omits the End galaxy and black hole. Sky & Atmosphere contains the new
Cloud Formations and End Sky pages; Lava Glow is under Colored Block Light.

Colored light follows open voxel paths in a bounded player-centered volume.
Corners and the volume boundary shorten its reach. Mip stabilization needs the
existing game mip chain. Ground cloud shade is an artistic approximation. Temporal
AA can soften detail or leave trails; animated surfaces use less history because
there are no per-object motion vectors. Fast cannot recover temporal information.
Avoid stacking XON Temporal with another temporal AA/upscaler. GPU tests do not guarantee
identical FPS or compatibility with every mod stack.
Ordinary lamps use the existing scalar lightmap. Jack-o-lantern and soul-lantern
auras additionally use the local colored-light volume. This does not add
directional lamp tracing or new source-cast shadows.
Indoor geometry occlusion reuses that volume, accepts verified full-cube blockers,
and fades near its boundary. Partial/unknown shapes do not cast this extra contact
shade. It adds local sampling work without another pass or volume allocation.
Bloom is a screen-space halo whose apparent world size depends on the view.
The specific reported moving quartz/wood/stone-brick flicker needs a live recheck.
Detailed cast shadows retain their bounded range; distant foliage uses approximate
canopy shading, not extra object-cast shadows across the full render distance.
The black hole is a fixed celestial thin-disk view baked into a small lookup,
not a scene-wide relativistic simulation. It adds about 4 MiB of texture storage
before driver overhead/mipmaps. New sky math costs GPU time; live FPS varies.

## Project, support and license

Official source, screenshots and support: https://github.com/Danonymos/XON

Read CHANGELOG.md for the complete version history and LICENSE for the full terms.
Free personal, non-commercial gameplay use is permitted under XON's Personal Use
and Contribution License. Source contributions to the official project have a
specific exception; unrestricted reuse and redistribution are not granted.
