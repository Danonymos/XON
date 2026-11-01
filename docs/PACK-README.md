# XON Shader 1.2

Warm light, clear water and a world in motion. XON is an Iris shader pack for
Minecraft: Java Edition, with directional shadows, moving cloud shade, colored
ore illumination, layered water and built-in spatial edge smoothing.

## Install

1. Use a compatible Minecraft Java + Iris + Sodium installation. The development
   target is Minecraft Java 26.3, Iris 1.11.7 and Sodium 0.9.2.
2. Place XON-Shader-v1.2.zip directly in your instance's shaderpacks folder.
   Do not extract it or install it as a mod/resource pack.
3. Open Video Settings → Shader Packs, select XON and Apply.
4. Start with Balanced + Native. Speed lowers the effect budget.

## Highlights

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
- Built-in edge smoothing in every preset, with no AA toggle or quality selector.
- Motion filtering that shares the six camera-blur samples and protects held items.
- Gentler distant mip detail while preserving nearby textures and cutout coverage.
- Colored ore light with a three-block eased outer aura; default extent is about
  seven open blocks. Quartz illuminates nearby surfaces with violet light.
- Balanced, soft ground cloud shade drifting one block every two seconds, with
  brighter cool blue moonlit openings and corrected terrain self-shadow rings.
- Layered water waves, refraction, caustics and shadow-shaped underwater shafts.

## Performance and limits

Native is the default. Boost 85%/75% lowers world shading resolution and may look
softer. AA stays built in; camera blur and extra nearby surface filtering are
separate settings. Speed disables colored voxel lighting and expensive effects.

Colored light follows open voxel paths in a bounded player-centered volume.
Corners and the volume boundary shorten its reach. Mip stabilization needs the
existing game mip chain. Ground cloud shade is an artistic approximation. Spatial
AA cannot recover missing subpixel/temporal information. GPU tests do not guarantee
identical FPS or compatibility with every mod stack.
Ordinary lamps use the existing scalar lightmap. Jack-o-lantern and soul-lantern
auras additionally use the local colored-light volume. This does not add
directional lamp tracing or new source-cast shadows.
Bloom is a screen-space halo whose apparent world size depends on the view.
The specific reported moving quartz/wood/stone-brick flicker needs a live recheck.
Detailed cast shadows retain their bounded range; distant foliage uses approximate
canopy shading, not extra object-cast shadows across the full render distance.

## Project, support and license

Official source, screenshots and support: https://github.com/Danonymos/XON

Read CHANGELOG.md for the complete version history and LICENSE for the full terms.
Free personal, non-commercial gameplay use is permitted under XON's Personal Use
and Contribution License. Source contributions to the official project have a
specific exception; unrestricted reuse and redistribution are not granted.
