# Local lighting repair — 1.9

5 November 2026. Compared with the preserved `XON-Shader-v1.8.3.zip`.

Public version **1.9** promotes the final private **1.8.4-r9** shader assets
unchanged. The revision history below records development and measured limits;
the public upload filename is **XON-Shader-v1.9.zip**.

**Live status: the user reports R7 fixed the earlier artifacts; R8 improved trapdoors but left adjacent pillar bands. R9 awaits that live comparison.** The user rejected both the first
candidate and R2. Paired diagnostic screenshots with/without the quartz bases
now show the largest changes in colored light and the replacement mask, while
native light and both AO views remain comparatively smooth. R3 targets that
blend and opaque-source sampling. The complete patch is not an approved release yet.

## Reproduced causes

The 1.8.3 surface filter chose the nearest voxel corner as an anchor, then
required every intermediate corner toward each sample to be open. Moving over
a block boundary changed that anchor abruptly. Two adjacent open anchors could
therefore accept different samples even though they belonged to the same air
space, producing rectangular brightness/tint bands near obstacles.

`xonConnectedLightCorners` now finds the face-connected open component within
the same eight fetched corners. Adjacent open anchors select the same component.
This removes the discontinuity while retaining barriers between disconnected
regions. The filter needs at most seven small integer expansion steps; fully
open footprints take a direct fast path. No extra volume fetch is added.

Visible radiance and native-source coverage previously shared the occlusion
confidence. Blocking radiance could erase coverage and restore broad warm scalar
fill. Coverage now interpolates independently while RGB remains visibility gated.
Coverage only suppresses fallback; it cannot illuminate the other side of a wall.

Decorative quartz previously used a small score multiplier rather than an
explicit priority class. After real lamp RGB reached its shorter colored-radius
limit, decorative glow could win despite remaining native lamp coverage. Real
sources now retain priority while their native level remains positive.

Current occupancy also rejects stale lamp/ore history inside newly placed
blockers or changed source types. The opposite-direction additive blend is
removed: the dominant-source field has no individual source identity, so it
could count two paths from one lamp as separate illumination. Circular
26-neighbor propagation and the existing isotropic RGB filter remain.

The candidate retains shade gain 0.72, all 75 source color/radius/level profiles,
bright cores, grade, PBR/POM, water, temporal AA and End atmosphere. R3 changes
the indoor indirect-light composition described below. It adds no texture
fetch, image, render pass or per-frame CPU work to the runtime pack.

## R3: separate indirect light from dominant-source identity

Previously, identical native light and identical sampled RGB could produce
different ambient brightness solely because a voxel stored a decorative lamp,
a real lamp or no lamp. The reconstructed level/native-level ratio selected
between the bright native fill and its much darker replacement. The diagnostic
mask exposed this on the quartz shelves, pillars and ceiling.

Inside the volume, surfaces with native block light now use consistent indoor
replacement coverage. Colored radiance still supplies local pools and their
smooth falloff; a native-level-proportional indirect floor of 0.44 preserves
readability when a source is covered. Replacement fades over the outer 2–8
blocks of the volume and blends back to the previous outdoor path with skylight.
Emissive cores, full Night Vision and unlit native-level-zero interiors retain
their previous behavior. This is not a new light source or ray-tracing pass.

Opaque decorative source cells also now have negative packed alpha in the lamp
texture, matching their closed status in propagation. Their own history state
is restored to positive for propagation, so outward decorative glow survives.
During surface interpolation these cells are terminal emitters: they can
contribute their own radiance, but cannot connect an air sample to another
sample through solid quartz. Own-aura exclusion remains intact.

`tools/local_light_blend_checks.py` passes 31 groups against the preserved R2 ZIP:

- Across six face normals and three receiver material groups, changing only
  lamp metadata previously changed linear RGB by 0.352–0.477. The corrected
  variation is exactly zero for the same native light and radiance.
- Open-sky, full Night Vision, unlit, outside-volume and bright sea-lantern
  fixtures retain R2 pixels exactly. Radiance remains monotonic and retains
  a 0.456–0.820 display-luminance range in the controlled source sweep.
- All 52,488 air/solid/emitter stencil configurations match an independent CPU
  graph traversal in which emitters are endpoints, not traversable cells.
- Applying the same R3 terrain shader to the old/new source-cell encoding
  reduces the covered-quartz fixture's largest display step from 0.02145 to
  0.00350. Outward glow survives for all three opaque decorative families.

These checks reproduce the component faults, not the exact multiplayer room.
The user's normal-view comparison with bases in place remains necessary.

## Controlled evidence

`tools/local_light_repair_checks.py` passes 15 aggregate cases, including:

- All 2,048 open-mask/anchor combinations agree exactly with an independent CPU
  graph traversal.
- A 0.002-block move across an open-cell boundary reproduces a raw RGB jump of
  0.136956 in 1.8.3; the corrected change is 0.000450, with the same source field.
- The old blocked sample loses native coverage; the corrected sample retains
  coverage while blocked RGB stays exactly zero.
- Nine stale-history fixtures reproduce old lamp/ore leakage after placing
  solid/quartz/ore blocks or changing a source. The corrected next-step leak
  from the stale cell is zero in each isolated fixture.
- A tall quartz pillar retains native coverage beyond the colored pool instead
  of switching to decorative glow. Dense pillar sweeps with/without a covering
  base stay finite and within the recorded continuity bounds.

`tools/circular_light_checks.py --baseline ../XON-Shader-v1.8.3.zip` passes all
12 aggregate cases: 75 lamp families, eight ore families, capture in three
dimensions, circular floor pools, planar/diagonal/corner/alcove barriers, quartz
walls, self-exclusion, stable ping-pong history, teleport reset, a six-lantern
20x20 room and non-lamp PBR/POM/AA parity. With R3 the room p10/p95 is 0.4961
(p10 0.2219, p95 0.4473), within the unchanged brightness/contrast bounds.

Partial-shape checks pass 55 cases and validate 471 installed full-cube selectors.
The final native driver compile/link suite is recorded in `validation-driver.json`.

Historical R2 paired isolated 1080p terrain sampling measured 0.690956 ms before / 0.694116 ms
after (paired ratio 1.0057). The populated 24-lamp compute fixture measured
0.11658 / 0.10227 ms (ratio 0.8781). A small covered-pillar compute fixture is
about 0.003 ms slower because it exercises additional occupancy validation with
little overlap work to remove. These are RTX 5060 Ti / NVIDIA 621.01 GPU workloads,
not full-game FPS guarantees. Concurrent desktop load affects timings; unrelated
passes retain identical source and their noisy timing differences are not attributed
to this patch.

## Reproduce and live scope

```sh
python tools/local_light_repair_checks.py
python tools/local_light_blend_checks.py
python tools/circular_light_checks.py --baseline ../XON-Shader-v1.8.3.zip
python tools/indoor_shape_checks.py
python tools/validate.py
python tools/build.py
python tools/release_checks.py
```

Generated reports and synthetic previews stay local. The earlier private
brightness adjustment was rejected in live screenshots; its extra darkening
is absent from the revised patch. Final visual approval must compare the supplied
pillars/ceiling with bases present and removed, then check closed walls, corners
and mixed-light rooms at matching settings. The conservative one-block volume
cannot resolve every hole in arbitrary partial/modded geometry or trace individual
lamp shadows. Controlled fixtures alone do not certify the user's whole room.

## Live component isolation

`python tools/build_light_diagnostic.py` creates the separate
`../XON-Lighting-Diagnostic.zip` from the R2 archive without editing production
shader sources or changing the active Iris pack. Its six labeled views display
native Minecraft light, sampled colored light, the native replacement weight,
native vertex AO, applied voxel contact AO, and the shaded scene. The same camera
view with the quartz bases present and removed was supplied by the user and
motivated the R3 component fixes above.

The diagnostic graphics compile/link in 12 dimension/material configurations
without warnings. A native GPU pixel test verifies routing of the five component
panels with maximum error 2.99e-8. Live Iris allocation and the actual pillar room
remain unverified. The extra diagnostic buffers are not part of the release or a
performance measurement. No game control is required to build/install this pack.

The first diagnostic failed during Iris directive parsing: its new
`colortex2ClearColor = vec4(0.0)` declaration was valid GLSL but Iris required four
explicit arguments. The diagnostic now spells out all four zeroes. Its builder
checks all four clear-color declarations before compiling; a regression check
rejects the exact original declaration. Native compile and panel-routing checks
pass again. The user confirmed the corrected diagnostic loaded and provided
both component screenshots. The user subsequently confirmed that R3 resolved
the pillar-room banding, with reduced sea-lantern illumination when full quartz
bases cover the sources.

## R4: small decorations must not become whole-cube blockers

The next screenshots show square missing-light patches behind pots and hanging
chains. The capture path treated unrecognized solid-layer terrain as occupancy
1, a closed full voxel. This overestimated the size of small open decorations.

`tools/small_light_shapes.py` derives a separate material group from installed
Minecraft models. All component models must fit within the block, have small
combined bounds, and contain no element spanning two whole block axes. Existing
material assignments are preserved. The generated group contains 127 selectors,
including flower pots and iron/copper chain variants. Full stone/quartz cubes,
closed doors, slabs, stairs and structural stone walls are not included.

The voxelizer omits this group from coarse local-light blocking. Native shape AO
and the existing sun-shadow rasterization remain active. This is a bounded
approximation for open decoration, not sub-block ray-traced shadows; arbitrary
half blocks and custom resource-pack geometry are not all resolved by this map.
The change adds no images, sampling taps, compute passes or dynamic CPU work.
Lamp radiance, radius, color, ambient balance and the R3 fixes are unchanged.

The shape suite now passes 57 groups, including actual GPU capture of the new
material as empty occupancy and a soul-lantern transport comparison against the
old full-voxel blocker. The 471 verified full-cube selectors remain unchanged.
The circular/source/wall/room/parity suite also passes against R3. Live comparison
of the pots and hanging soul lanterns remains pending for R4.

## R5: planted pots and remaining soul-lantern investigation

Live R4 feedback confirmed the empty-pot improvement but showed a planted-pot
shadow square and remaining uneven soul-lantern illumination. The user identified
the wall behind those lanterns as stone, so a partial-wall diagnosis is unproven.

The model classifier now ignores zero-volume flower/leaf planes when the same
model contains a solid pot. Plane-only chain models retain their previous path.
The generated group has 164 selectors, covering 38 planted-pot variants. The
39th, potted brown mushroom, retains its existing explicit emissive-material
assignment. An assertion checks that every installed planted-pot block has an
explicit classification. The 57 shape/capture/transport groups pass again.

Only block.properties changes in the normal R5 runtime ZIP compared with R4.
The updated six-panel diagnostic is built from this candidate and passes its
12 native graphics configurations, clear-color parser checks and panel-routing
pixel check. It is installed separately as XON-Lighting-Diagnostic-R5.zip for a
stone-wall soul-lantern screenshot. The remaining soul-lantern artifact is not
claimed fixed; current evidence does not yet isolate its failing component.

## R6: source-independent composition with window skylight

The supplied R5 diagnostic shows unevenness in colored radiance and replacement
coverage, with comparatively smooth native light and AO. R3 had stabilized the
blend only in fully indoor conditions; partial skylight still mixed the original
dominant-source ratio back into the ambient replacement. This was an incomplete
fix for rooms with windows.

R6 removes that ratio from surface composition entirely. Replacement confidence
now follows volume validity, native block light, emission and Night Vision, not
the family/remaining-level field. This applies at every skylight level, including
outdoor block-light contributions; skylight/sun/moon calculations themselves are
unchanged. Metadata alone can no longer darken an unlit surface either. Emissive
cores, volume-edge transitions and the planted-pot map remain protected.

The new mixed-skylight tests compare actual R5 terrain against the candidate.
At skylight 0.4/0.6/0.85/1.0, fixed native light and RGB previously varied by
0.0522/0.2354/0.4924/0.4546 linear RGB solely due to metadata; R6 variation is
zero in each fixture. The circular/source/wall/room suite passes against R5.
The full source profiles and radiance sampler remain unchanged. This establishes
the ambient-mask repair, not that every colored-field patch in the multiplayer
scene is resolved. A normal-view soul-lantern comparison is still required.

## R7: model-derived stair and slab apertures

The R6 normal-view screenshots still show dark recessed stair faces, ceiling
sections and adjacent wall/pillar patches. Capture and sampling disagreed with
the actual geometry: stairs/slabs were closed whole cells, and the sampler
projected their inset faces to the outer cube boundary. A neighboring solid
cell could then remove every colored-light sample from an exposed stair face.

`tools/partial_light_shapes.py` derives 26 half-grid occupancy masks from the
installed client's native stair/slab models and blockstate rotations, covering
4,082 state selectors. Cardinal transport crosses only matching empty face
apertures; diagonals cannot skip a partial cell's solid portion. The sampler
uses the real inset surface and matches those same apertures between samples.
Unknown geometry remains conservative. Small decoration and planted-pot
classification from R4/R5 remains in place.

Shape identity uses the five spare bits in the existing R32UI contact cache;
its original 27 AO bits remain intact. Signed alpha, including signed zero,
marks partial-cell samples in the existing half-float volumes. Shape decoding
is deferred until a stencil encounters a marked cell. There are no additional
images, compute passes, shared-memory allocations or per-frame CPU operations.
Conditional cache reads and additional shader work are required near shapes.
Full quartz keeps its decorative aura; partial quartz receives neighboring
light but no longer originates a full-cell decorative aura. Source profiles,
open-air circular falloff and R6 ambient composition are unchanged.

Verified on the native NVIDIA driver:

- All 26 masks capture correctly; all six faces accept light only through their
  open parts. GPU metadata readback preserves the shape code and all AO bits.
- Both continuous slab orientations seal their solid side.
- All 4,056 shape-pair face apertures match independent geometric enumeration.
- 104 exposed inset-face cases reproduce black R6 output and receive light with
  the candidate. This is a controlled reproduction, not a recreation of the room.
- The 37 composition groups and 52,488 terminal-stencil cases pass. The circular,
  source-family, wall-sealing, room-contrast and rendering-parity suite passes.
- All 2,310 unique shader stages compile and all 24 x 87 graphics pairs link,
  with no driver warnings or errors.

Interleaved 1080p open-air proxy timing was 0.062816 / 0.070668 ms for the local
sampler and 0.468892 / 0.498772 ms for production terrain (R6 / R7). The populated
24-lamp compute fixture was 0.10180 / 0.11481 ms. These are small measured costs,
not a claim of identical FPS or a measurement of the live partial-heavy room.
The earlier, slower shape implementation was optimized before packaging.

Use `python tools/partial_light_shapes.py` to verify checked-in mappings and
`python tools/partial_light_checks.py` for the GPU reproduction and timings.
The installed candidate is `XON-Shader-v1.8.4-r7.zip`; the canonical R2 archive
and R3–R6 candidates remain intact. Live verification of the reported stair,
soul-lantern wall and covered-pillar views is pending. Arbitrary modded or
resource-pack model geometry is outside the native half-grid mapping's scope.

## R8: trapdoor orientations and thin-face sampling

Following the user's R7 confirmation, the model classifier now includes all
22 native trapdoor types and their 352 top/bottom, open/closed and facing states.
The combined map contains 4,434 state selectors and 30 masks, within the existing
five-bit cache field. A thin panel conservatively occupies its intersected half
of the voxel; it is not treated as a whole cube or made wholly transparent.
This preserves closed-side barriers while leaving the correct side open.
Texture cutout holes and arbitrary custom model geometry are not resolved by
this coarse volume.

Trapdoor faces are 3/16 of a block thick, unlike the half-block stair/slab faces.
Their local-light sample moves to the empty half-cell boundary instead of
remaining inside the conservative blocker. The existing stair/slab sampling,
light profiles, pass count, volume storage and AO bit layout remain intact.

The native GPU fixtures pass for all 30 captured masks, all six continuous
panel barriers, 5,400 shape-pair apertures, 120 half-grid inset faces and 24
actual 3/16 trapdoor-face positions. The 471 full-cube mappings and 57 existing
shape groups also pass. The 1080p open-air terrain proxy measured 0.471300 ms
for R6 and 0.603324 ms for this candidate; this is a controlled shader workload,
not a full-game FPS guarantee. Final shader validation is recorded separately
in `validation-driver.json`. The candidate is `XON-Shader-v1.8.4-r8.zip`;
R7 remains available. In-game open/closed trapdoor comparison is pending.

## R9: distinguish thin panels from solid half blocks

The user's R8 screenshots show remaining rectangular bands on the pillar beside
the trapdoor. The sampler's receiver exclusion still used the conservative
half-cell mask: a nearby exposed surface between 3/16 and 1/2 of the block was
classified as inside the panel, discarding all colored radiance. R8's direct
trapdoor-face correction did not cover adjacent full-block receivers.

Trapdoors now have six distinct capture materials/occupancy values. They retain
the same conservative transport apertures, but the sampler tests the anchor
against the native panel's actual 3/16 bounds. Genuine slabs retain the half-cell
solid test. The 352 native state selectors are verified from model geometry;
the generator asserts the native thin-panel dimensions before assigning them.

The existing cache tags thin panels in bit 13, one of its repeated centre AO
bits. That bit is always zero for partial cells. AO decoding restores this zero
only when a shape code is present; full-block centre occlusion and every other
contact bit retain their original meaning. Native GPU readback verifies both
the thin tag and all original AO values. No image, render pass, shared-memory
allocation or volume fetch is added relative to R8.

`python tools/trapdoor_light_checks.py --reproduce` reproduces the R8 rejection.
The normal run compares the archived R8 sampler and current production sampler:
72 falsely black receiver positions are repaired across six panel orientations
and four adjacent receiver normals per orientation. The constant-radiance RGB
step drops from 0.199951 to zero. Points inside the actual panel and true half
slabs remain blocked. The tag does not generate contact AO. This fixture isolates
the defect; it does not reconstruct the multiplayer room.

The wider suite passes 36 ordinary/thin capture groups, 12 continuous solid-side
barriers, 5,400 aperture pairs, 120 half-grid faces and 24 thin-panel faces.
The circular/source/sealed-wall/room suite passes against R8. Native compilation
passes 2,310 unique stages and 24 x 87 graphics pairs without warnings/errors.

Interleaved 1080p adjacent-panel sampler timing is 0.145488 / 0.147060 ms
(R8 / R9; paired ratio 1.01076). The populated compute proxy is
0.11511 / 0.12822 ms. These controlled measurements are not full-game FPS.
The candidate is `XON-Shader-v1.8.4-r9.zip`, installed beside R8 with matching
settings. The real open/closed trapdoor and pillar view remains to be checked.
