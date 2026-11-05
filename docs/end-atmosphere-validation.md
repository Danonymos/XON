# End atmosphere — 1.8.1

4 November 2026. Compared with the accepted `XON-Shader-v1.8.zip`.

## Design and rendering cost

`lib/end_atmosphere.glsl` supplies a world-oriented lavender hemispheric fill
and a separate violet-magenta haze. It is included by `atmosphere.glsl` and
compiled only in the End. `lighting.glsl` uses the fill before existing local
light, vision and emissive-core handling. There is no surface-position light
pattern or per-block density quantization.

The haze's height density is a compact smoothstep layer centered at Y=56,
with an 88-block half-height. Its cubic density is integrated analytically
along the view segment, with a stable horizontal-path limit. Two broad,
path-averaged sinusoidal veils add gentle variation. Height and veil optical
depths add, so positive density cannot make a longer path less opaque.
Radiance blends violet and magenta as the veils drift; this is an artistic
scattering approximation, without shadow-traced beams or lamp-scattered fog.

The first eight blocks receive no added haze. Higher viewpoints see less of
the island-height layer. Exponential transmission gives continuous distance
buildup. The 180/300-second veil periods both meet at Iris's hourly timer reset.
Existing render-border fades hide terrain limits against a dark violet void
color. The sky programs, galaxies, star fields, black-hole texture and native
cube/flash blend states are untouched.

There is no new pass, loop, texture read, custom image, history or CPU update.
The fog path replaces the old terrain call to the procedural End sky with
bounded analytic math. Atmosphere Density scales the new haze; zero removes it.
Fog Density also scales optical depth. Existing Speed uses zero atmosphere;
the End's revised ambient light and border-fog palette remain.

## GPU evidence

On RTX 5060 Ti / NVIDIA 621.01, `tools/end_atmosphere_checks.py` passes 84 cases:

- 129,600 height paths agree with independent piecewise Gaussian quadrature
  within 0.0003 mean density, including nearly horizontal rays.
- Haze opacity builds monotonically along horizontal, rising and falling rays
  at six camera heights, with an exact clear near zone.
- Adjacent animation frames and the hourly timer seam remain continuous.
- End sky pixels match 1.8 at four times and two flash intensities.
- All six emissive face cores match; ordinary faces retain readable energy
  while their blue-to-green ratio moves toward violet.
- Production Overworld/Nether lighting, sky and fog match across four media.
- End underwater/lava/powder-snow fog matches; vision and flash boundaries
  remain finite and nonnegative. Density zero removes the added haze.
- Sky, source-specific lamp/ore transport, geometry, PBR settings, render-pass
  configuration, exposure/grade texture and noise/black-hole assets are retained.

Paired 1080p GPU timer queries for isolated End lighting and fog measured
0.061832 ms before / 0.061820 ms after (paired median ratio 0.9998).
This is within measurement noise, not a full-game FPS result. Each of 24
alternating batches times four draws after warm-up. Synthetic inputs, clocks
and concurrent desktop load limit interpretation.

`tools/validate.py` passes 2,088 graphics compile/link configurations (2,310
unique shader stages), with zero warnings or failures. The native End sky
blend suite passes 12 cases, including masked flashes, underlying-color rejection
and both Boost modes. Its original pre-fix 1.3 End fixture is retained. The new
`--overworld-baseline` option compares Overworld preservation with accepted 1.8;
the legacy default's 1.3 cloud comparison fails identically on untouched 1.8
(maximum raw error 0.0340601), so it is not a 1.8.1 regression. No assertion
is relaxed or removed.

Reports and synthetic previews stay local and are excluded from the runtime ZIP.
The synthetic block-island preview checks the production lighting/fog functions;
it is not a Minecraft screenshot or final visual approval.

## Reproduce and inspect

```sh
python tools/end_atmosphere_checks.py --baseline ../XON-Shader-v1.8.zip
python tools/validate.py
python tools/end_sky_pipeline_checks.py --overworld-baseline ../XON-Shader-v1.8.zip
python tools/build.py
python tools/release_checks.py
```

In Minecraft select `XON-Shader-v1.8.1.zip`, Balanced + Native. Inspect nearby
end stone, side/under-island faces, obsidian pillars, end rods, purpur interiors
and islands at several distances/heights while moving and turning. Check
Atmosphere Density at Off, 50%, 100% and 150%. Confirm the existing galaxy and
black hole stay crisp.

## Live check

Iris loaded `XON-Shader-v1.8.1.zip` in the End with no subsequent shader errors
in the inspected log. The active pack retains the user's saved Advanced
Materials, 4x filtering, 0.40 parallax depth and 25% sharpening settings. The
live near-island/chorus view was inspected; no new block-shaped haze patches
or sky split were visible in that view. Detailed visual approval, controlled
full-frame FPS comparisons and AMD/Intel hardware remain unverified.
