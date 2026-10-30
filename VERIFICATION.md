# XON Shader 1.0.3.1 - shallow-water hotfix

30 October 2026. A localized change to refractive water: an above-water-only tint
for thin sheets, fading smoothly to zero at 1.5 blocks of view-depth thickness.
No new render pass, sample or buffer. No game UI automation or FPS claim.

`python tools/shallow_water_checks.py` tests the real water fragment against the
preserved 1.0.3 ZIP: 84 combinations of light/dark floor colors, indoor/outdoor
skylight, thin/deep layers and above/below-water viewing. All passed. Deep water
and underwater outputs match within 0.000001 HDR error; thin indoor sheets show
measurable colored absorption. Refractive composition remains opaque to avoid
double blending. Existing non-refractive fallback is untouched.

The shader compiler matrix and existing lighting checks are rerun for this fix.
See `validation-driver.json`, `validation-lighting.json`,
`validation-shallow-water.json` and `validation-package.json` for current results.
Other reports below describe the preceding 1.0.3 release, not new tests of this fix.

Final player check: place a bucket on a pale floor and a dark wooden floor indoors;
check source and thin flowing edges, then compare an ocean and underwater clarity.
The tint also affects shallow shorelines; it does not identify water flow itself.
Actual visibility in the user's resource packs and Iris runtime needs their test.

---

# XON Shader 1.0.3 — verification

30 October 2026. This is a visual shading update built on 1.0.2. Validation uses
the NVIDIA RTX 5060 Ti native OpenGL driver (621.01), not a live Minecraft session.
No computer-use automation or game reload was performed; the player performs the
final Iris load and gameplay comparison.

## Intended appearance

Directional diffuse shaping and a light-oriented rim term replace camera-dependent
shine on matte blocks. Warm simulated ground bounce complements cool sky fill.
Slight blue tint is baked into the ambient/fill coefficients, so it needs no extra
full-screen grading pass. Local lights retain warm falloff with a gentler ivory
core; readable night/cave fill is modestly brighter. These are artistic lightmap
and ambient approximations, not traced GI or an increased block-light radius.

The original LUT and saturation are unchanged. New shading alters the colors of
surfaces according to their illumination. Shadow-map resolution/distance and
sample limits are unchanged. Optional Smooth Shadow Transitions remains OFF by
default for performance; the default upgrade is in shadow tone and surface form.

Smooth Camera Motion is ON with strength 1.50 by default. The rainbow selection
outline rotates at 0.675 cycles/second (formerly 1.35), uses eight eased color
stops, and has more balanced brightness. Selection line width is 2.5 instead of
2.0; debug-line width and color are preserved. “50%” was interpreted as half
animation speed, not a smaller selection box.

## Checks

See the generated reports for the exact results:

- `validation-driver.json`: 82 programs across ten configurations, all dimensions,
  both Boost scales, effects off, Speed, larger/minimum shadows, optional smooth
  shadow transitions, and water with refraction/shadows disabled.
- `validation-pixels.json`: 12 final-pass checks at the new default blur strength.
- `validation-lighting.json`: 22 existing material/lighting/AA/sky/outline checks.
- `validation-visual-update.json`: 41 comparisons/continuity/readability checks
  against 1.0.2. Lighting is intentionally different: tests constrain the exposure
  envelope, verify measurable changes, keep nighttime shade readable, and require
  monotonic local-light falloff. Unchanged fog, refractive water, lava, portal and
  froglight outputs retain pixel parity in the sampled scenes.
- `validation-package.json`: ZIP/source/installed-copy parity, declared controls,
  native rendering, blur ON/1.50 defaults, and unchanged reference archives.

`validation-lighting-comparison.png` is a synthetic surface study, not a Minecraft
screenshot. Top row is 1.0.2, bottom row 1.0.3; columns are daylight, dusk and night
with the same weak local light. It was used to inspect tonal changes.

## Performance scope

No new render pass, texture sample, history buffer, tracing or shadow-map upgrade
was added. Removing non-foliage view-vector normalization offsets some new shading
math. The 1.0.2 water and emissive-material shortcuts are retained. These facts do
not guarantee identical FPS: GPU compiler allocation, the scene and other mods
matter. Synthetic 1080p timings, including medians and noisy p95 values, are recorded
in `validation-visual-update.json`; they exclude world draw calls and CPU simulation.
No measured in-game FPS gain or universal cost-free improvement is claimed.

Historical reports `validation-optimization.json` and `validation-performance.json`
refer to older versions. Use the visual-update report for this release.

## Reproduce

From `G:/shaders/XON-Shader`:

```text
python tools/validate.py
python tools/render_checks.py
python tools/lighting_checks.py
python tools/optimization_checks.py --visual-update
python tools/build.py
python tools/package_checks.py
```

Package checking expects the ZIP installed in the Ziz profile shaderpacks folder.
The installed 1.0.3 options carry forward brightness 0.80, sharpening 0.25, air fog
ON and blur strength 1.50. Iris's active pack is left unchanged. Previous packs and
source archives remain available.

For the final player test, select 1.0.3 and Apply. Compare a sunlit build and its
shaded walls, torchlit interiors, night, water and camera movement from the same
position/settings as 1.0.2. Watch the selection outline while standing still and
moving. Report visual differences and FPS; avoid changing server weather/time.
Other GPU vendors, live Iris patching and all possible scenes remain unverified.
