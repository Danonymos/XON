# XON Shader 1.0.4 - verification

Verified 30 October 2026 using an offscreen NVIDIA RTX 5060 Ti OpenGL 4.6 context,
driver 621.01. No game UI automation, live Iris reload or in-game FPS measurement.

## Passed checks

- 820 linked program configurations: 82 entrypoints across ten configurations,
  including all dimensions, Native/Boost, Speed, disabled effects, Cinematic,
  minimum shadows, and water with refraction/shadows disabled. Zero warnings/errors.
- 22 existing GPU feature checks: shadows/cutouts, fog/absorption, materials, AA,
  LUT, sky/weather, outlines and readability. The outdoor broad-veil guard passed.
- 12 final-pass checks: HDR, Boost mapping, motion blur and hand/teleport guards.
- 84 water-fragment cases: thin-water visibility and deep/underwater baseline parity.
- 13 new ray/light cases: day/night/darkness gates, water/lava/snow gates,
  underwater/master/shadow/intensity controls, shadowed openings shaping beams,
  foreground-depth clipping and bounded ray peaks. Lower light defaults reduce
  tested sun/torch surfaces to about 83% of their former HDR brightness; unlit
  shadow fill is identical. A 20% energy change is not a fixed 20% display change.

See local `validation-driver.json`, `validation-lighting.json`,
`validation-pixels.json`, `validation-shallow-water.json`, `validation-rays.json`
and `validation-package.json`. Older optimization/visual-update/performance
reports describe previous releases and are not current 1.0.4 evidence.

## Ray cost and limits

The existing half-resolution effects buffer is reused. Outdoors retains four
shadow comparisons; underwater uses six, limited to 32 blocks. No additional
render pass, history buffer or texture is introduced. Air ray peak is capped at
0.20 and underwater at 0.12 before tinting and tone mapping. The ray slider can
reduce intensity to zero. Disabling Shadows or Localized Sun Rays removes both
kinds of rays; the underwater toggle separately removes submerged rays.

Synthetic shaft-only medians (960x540, 48 timer samples, four draws per sample):

| Pass | Median GPU ms | p95 ms |
|---|---:|---:|
| 1.0.3.3 outdoor | 0.02082 | 0.02096 |
| 1.0.4 outdoor | 0.02485 | 0.05728 |
| 1.0.4 underwater | 0.03274 | 0.03283 |

These are isolated RGBA32F draws with synthetic all-lit inputs, sequential ordering
and concurrent desktop load. They exclude bloom, world/shadow geometry, the rest
of the frame and CPU work. They do not prove an FPS gain or identical frame pacing.
The new underwater effect has a real cost compared with the former disabled pass.

Underwater refraction assumes a flat water interface. Shadow comparisons still
use the existing straight sunlight shadow map; this is an artistic approximation,
not a physical simulation of wave focusing or refracted occluder shadows. At
shadow-map limits, shafts can fade or lose detail. Four/six steps can show sampling
noise on thin geometry; existing spatial softening reduces it. No temporal history
is added. Rays need sunlight and skylight and favor looking toward incoming light;
sealed dark rooms and nighttime do not emit sunbeams. Surface/ocean color, LUT,
blue shadow tint and water absorption are unchanged by the ray pass.

## Reproduce and player test

Run from the source folder:

```text
python tools/validate.py
python tools/render_checks.py
python tools/lighting_checks.py
python tools/shallow_water_checks.py
python tools/rays_checks.py
python tools/build.py
python tools/package_checks.py
```

The water/ray comparisons need the preserved 1.0.3 and 1.0.3.3 runtime ZIPs in the
parent folder. Package checks require the new ZIP copied to the Ziz shaderpacks
folder. No runtime Python dependency is added to Minecraft.

Select 1.0.4 and Apply. Compare sunlight through doors/roof gaps, a torchlit large
interior, shallow and deep daylight water, a dark underwater cave, nighttime,
and held-item movement. Try the ray slider at 0/1 and underwater toggle separately.
The installed pack carries forward the player's prior saved settings; new light
strengths default to 0.80. Iris active selection is left for the user. Actual FPS,
resource-pack behavior, other GPUs and live Iris patching await player testing.
