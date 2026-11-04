# 1.8 lighting optimization

4 November 2026. The baseline is the accepted, corrected 1.8 runtime pack saved
locally as `XON-1.8-before-optimization.zip`. This is a performance refinement of
1.8, with the same lighting profiles, quality options, image size and update rate.

## Work removed

- A shared lighting evaluator gathers lamp and ore fields together, reusing
  coordinate/bounds/interpolation work. Material classification is shared, unused
  material paths exit early, and zero-weight fetches are skipped exactly.
- Contact shading rejects complete layers outside the original hemisphere or
  support radius on axis-aligned faces. Slanted surfaces retain the full kernel.
- An R32UI cache stores 27 contact-plane occupancy bits per voxel. Empty planes
  prove visibility is exactly 1; occupied planes supply blocker bits directly to
  the unchanged kernel. The compute pass builds the cache every frame from a
  cooperative 10×10×10 shared occupancy tile per 8×8×8 workgroup, including halo
  cells. No sampling rate, temporal approximation or shadow detail is reduced.
- Clipped non-emitting translucent shadow vertices skip unnecessary transforms.
- POM retains its adaptive quality and five refinement steps, using its actual
  loop bound directly and computing the view-vector length once.

The cache adds **1.6875 MiB**, bringing local image texels to **15.609375 MiB**
before driver overhead. A workgroup uses 4,000 bytes of shared occupancy memory.
It adds bounded compute work and saves repeated fragment
work, without an additional compute dispatch or rendering pass. Speed omits the
colored-light images and cache as before.

## Output checks

`tools/lighting_optimization_checks.py` passes **279** checks against the accepted
1.8 baseline on NVIDIA RTX 5060 Ti / OpenGL 4.6 / driver 621.01:

- All 75 lamp transport/metadata fields match bit for bit, as do the mixed-scene
  ore and lamp fields.
- A CPU oracle checks every cache bit at all 442,368 voxels in six layouts,
  including sparse/dense/full/empty occupancy, unknown partial blockers and
  immediate removal. Only verified full cubes enter the cache.
- Kernel and production-terrain comparisons cover six axis directions, slanted
  and camera-roundtrip normals, partial heights, the three dimensions, PBR, daylight, night vision,
  quartz, lamps and independent emissive materials.
- Actual Primes HD height maps produce bit-identical POM intersections across
  three materials, six view angles and depth settings 0.20 and 0.50.
- The largest linear terrain-pixel difference is **1.1920929e-7**, consistent
  with reordered floating-point addition. No quality control is lowered.

The existing **119** lamp/transport/receiver checks and **55** partial-shape checks
also pass. The six-lantern room's p10/p50/p95 display luminance is unchanged at
**0.256390 / 0.281749 / 0.545134**. The full driver compile suite is run separately.

## Controlled GPU timings

Paired timer queries alternate before/after order, with 24 batches of four draws
per version. Both shaders use the same textures, volumes, framebuffer and options.
The terrain benchmarks run at 1920×1080; PBR uses real Primes height data.

| Work | Accepted 1.8 | Optimized | Median paired ratio |
| --- | ---: | ---: | ---: |
| Contact kernel | 0.1580 ms | 0.0630 ms | 0.400 |
| Terrain fragment | 0.7683 ms | 0.5253 ms | 0.651 |
| PBR terrain fragment | 1.1766 ms | 0.8239 ms | 0.695 |
| Existing compute dispatch, including new cache | 0.0183 ms | 0.0266 ms | 1.447 |
| Occupied-plane kernel, presence-only cache → bitmap cache | 0.1007 ms | 0.0737 ms | 0.731 |

Across repeated runs, contact shading is roughly 60% cheaper and the tested
terrain paths roughly 25–37% cheaper. Compute rises by about 0.008 ms in this
scene. GPU scheduling/clocks and concurrent Minecraft activity cause outliers;
these figures describe controlled passes, not the complete frame.

The user's reported 100→70 FPS loss is not a measured controlled baseline here.
A local JFR inspection found the running client was background-limited during
that sample, so its FPS is not used as an optimization claim. No game settings,
resolution, lighting ranges, profile defaults or POM quality are reduced.

The first optimized pack loaded in Iris without a reported shader error, with
the same effective saved settings (Advanced Materials on; POM depth 0.50).
The user reported approximately **+10 FPS indoors and +20–25 FPS outdoors**.
These are user observations, separate from the controlled GPU timings above.
The user subsequently reported further improvement with the final refinement;
no controlled FPS result is recorded for that refinement.
Its plane-cache test also admits small normalized camera-roundtrip components
when the sampling point lies exactly on an axis boundary. The hemisphere/support
tests still admit precisely the same plane; the original normal and weights are
retained. Other positions fall back to the original stencil.

Full-game FPS recovery requires the same foreground view, settings, resolution,
weather and resource packs before/after. AMD/Intel hardware, arbitrary geometry
and a live artifact recheck remain outside this driver test. The cache does not
reduce the existing costs of world simulation, mod code, particles or chunk work.
Local JFR files, generated reports, client assets and baseline ZIPs are not
included in the runtime package.
