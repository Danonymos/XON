# XON 1.1 — Distant foliage update verification

31 October 2026. Commit `9b080ba` saves the accepted emitter/lantern/bloom build
before this update. Version 1.1 is retained. The preserved runtime baseline is
`XON-Shader-v1.1-before-distant-shading.zip`, SHA-256
`b6e878dfab4c16187110cf8a6ce3d336dacd468c0ff3becb320a0821949b9960`.

## Behavior and limits

The detailed shadow map defaults to 96 blocks, while the inspected client renders
15 chunks (240 blocks). Increasing the shadow rendering radius would require
more geometry work and/or lower map detail. This update retains that radius and
the 1024 map, instead improving the fallback outside valid shadow coverage.

Foliage uses its existing celestial facing, normal and skylight. The wrapped
diffuse facing is converted back to its original 0–1 range for this approximation.
A gentle sky-facing term and stronger key-facing term preserve some canopy shape.
The foliage radial transition spans about 69–94 blocks at the default setting;
the existing frustum fade can shorten detailed coverage. Ordinary terrain keeps
its original transition. The fallback has no procedural screen/camera noise.

This affects foliage, including cross-plants, when Sun & Moon Cast Shadows is on.
It retains existing ambient occlusion, cloud modulation, local lamps and colored
emissive lighting. It does not add accurate far tree/building cast shadows, expand
the local colored-light volume, or promise nearby detail at every render distance.

## GPU checks

`python tools/distant_shading_checks.py` uses the actual production terrain fragment
with controlled inputs, plus a visibility probe. It requires the preserved runtime
baseline above and the same Windows/OpenGL, NumPy and Pillow environment as the
other local GPU tools. Synthetic leaf-face panels are diagnostics, not gameplay.

All 31 new cases pass:

- Lit and fully occluded leaf probes at 8/32/64 blocks retain results within
  0.000001 in full map coverage. Ordinary opaque faces across 0–240 blocks,
  cave lamps, unlit caves and the shadows-disabled path retain results.
- Distant leaf-face sun/shade linear-luminance ratio rises from 1.379 to 1.534
  by day, and 1.121 to 1.143 under the moon. All tested far leaf faces retain
  at least 65% of the baseline signal; these are fixture-specific measurements.
- Range/frustum ramps have a largest visibility step of 0.000538 over roughly
  0.046 blocks. Far fallback has no radial bands and remains identical under
  the tested camera translations. Skylight probes stay bounded and add no light.

All 840 graphics compile/link configurations pass: 936 unique stages, zero warnings.
The prior 872 GPU regression cases and client mapping check also pass, for 903 GPU
cases plus one mapping check. This includes the existing 578 terrain-ring/contact
cases, cloud lighting, water, rays, AA, lamps, voxels and emissive material tests.

## Measured cost

RTX 5060 Ti / OpenGL 4.6 NVIDIA 621.01; 960×540 RGBA32F target, real production
terrain fragment, 32 interleaved queries per version, four draws per query after
warmup. These fixtures disable colored voxel lighting and ground clouds to isolate
this change, and use an opaque green texture with leaf material shading.

| Workload | Before ms | Updated ms |
| --- | ---: | ---: |
| Near foliage | 0.05313 | 0.05445 |
| Distant foliage | 0.04362 | 0.04451 |
| Mixed near/far foliage | 0.04697 | 0.04802 |
| Ordinary opaque terrain | 0.04654 | 0.04751 |

The measured median increase is about 0.0009–0.0013 ms in these isolated workloads.
Desktop/game activity affected p95 and timings vary by workload and hardware.
There is extra arithmetic but no new texture read, pass, image, geometry draw or
CPU frame loop. These results do not establish zero cost or full-game FPS parity.

## Live comparison still needed

Reload the updated 1.1 pack and compare a distant jungle from the same camera,
render distance, time and weather. Walk through the shadow transition, turn the
camera, and compare both sunlight and moonlight. Nearby trees should retain their
cast shadows; far trees should keep softer face contrast. Compare frame time as
well as FPS. Live appearance and full-game performance are not verified here.
