<p align="center">
  <img src="docs/images/xon.jpg" alt="XON Shader" width="136">
</p>
<h1 align="center">XON Shader</h1>
<p align="center"><strong>Warm light. Clear water. A world in motion.</strong></p>
<p align="center">An Iris shader pack for Minecraft: Java Edition.</p>
<p align="center">
  <a href="#install">Install</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="docs/releases/1.0.7.md">1.0.7 release notes</a> ·
  <a href="https://github.com/Danonymos/XON/issues/new/choose">Report an issue</a>
</p>
<p align="center">
  <img src="https://img.shields.io/badge/build-1.0.7-35b8b0?style=flat-square" alt="Current build: 1.0.7">
  <img src="https://img.shields.io/badge/loader-Iris-6177b9?style=flat-square" alt="Shader loader: Iris">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-personal_use-c39a61?style=flat-square" alt="Personal use and contribution license"></a>
  <a href="https://github.com/Danonymos/XON/actions/workflows/build.yml"><img src="https://img.shields.io/github/actions/workflow/status/Danonymos/XON/build.yml?branch=main&amp;label=pack%20build&amp;style=flat-square" alt="Pack build status"></a>
</p>

![Island builds, clear water and soft daylight in XON](docs/images/island.jpg)

XON brings warm sunlight, cool readable shade, moving cloud shadows and glowing
ore light to your worlds. Water stays clear, the atmosphere changes throughout
the day, and edges receive built-in smoothing. Native resolution is the default.

The gallery uses existing XON gameplay captures. It illustrates the pack's visual
direction; it is not a controlled comparison or proof of the latest fixes.

## What's new in 1.0.7

- **Smoother edges by default.** Built-in spatial anti-aliasing and shared
  motion-blur filtering reduce jaggies and moving noise. Distant terrain uses
  gentler mip sampling; close texture detail and cutout coverage are preserved.
- **Softer colored ore light.** Three extra open blocks ease the aura into
  darkness. The default setting reaches about seven blocks along open paths;
  quartz casts violet light onto neighboring surfaces.
- **Cloud shadows with visible movement.** Balanced light and dark patches drift,
  merge and separate at one block every two seconds. Typical widths are around
  30–50 blocks, with smaller pockets and larger connected banks.
- **Clearer moonlit openings.** Exposed cloud gaps receive up to 28% more cool
  blue moonlight, retaining the dark patches and broad, eased boundaries.
- **Terrain shadow correction.** Surface-aware filtering fixes the reproduced
  camera-following sun/moon shadow rings while retaining real object shadows.

Read the [complete changelog](CHANGELOG.md) for every version from the first beta
through 1.0.7, including the underwater, material and lighting improvements.

## The XON look

| Feature | In the world |
| --- | --- |
| Light and atmosphere | Directional sunlight and moonlight, warm bounce, cool readable shade and five time-of-day moods. |
| Colored emissive light | Ore and crystal glow with local colored spill onto walls and floors in all three dimensions. |
| Sky and terrain | Layered cumulus and cirrus clouds, evolving ground cloud shade and waving foliage. |
| Water | Layered waves, refraction, depth absorption, caustics and shadow-shaped underwater sunlight shafts. |
| Materials and dimensions | Moving lava fissures, natural pale amethyst tips, restrained froglights and a purple End aurora. |
| Camera and clarity | Built-in edge smoothing, optional sharpening, protected held items and adjustable camera motion blur. |

<details>
<summary><strong>More from the gallery</strong></summary>

![Warm fields, a stone castle and water in XON](docs/images/fields.jpg)

</details>

## Install

1. Use a compatible **Minecraft: Java Edition + Iris + Sodium** installation.
2. Get a packaged `XON-Shader-v1.0.7.zip` from [official releases](https://github.com/Danonymos/XON/releases).
   If a release has not been published yet, use the [source build](#build-from-source)
   or a successful [pack-build artifact](https://github.com/Danonymos/XON/actions/workflows/build.yml).
3. Place the **shader-pack ZIP** directly in your instance's `shaderpacks` folder.
   Leave it zipped. GitHub's **Code → Download ZIP** is source code, not an installable pack.
4. Open **Video Settings → Shader Packs**, select XON, then **Apply**.
5. Start with **Balanced + Native**. Use **Speed** for a lighter effect budget.

The separately named `XON-Shader-v1.0.7-smooth.zip` is the same 1.0.7 smoothing
build used for side-by-side installation. Select that filename if an earlier
1.0.7 pack is already open in the game. When downloading an Actions artifact,
extract the artifact container and install the shader ZIP inside it.

### Compatibility

| Area | Current scope |
| --- | --- |
| Development target | Minecraft Java 26.3, Iris 1.11.7 and Sodium 0.9.2. |
| Dimensions | Overworld, Nether and End; unknown modded dimensions use the Overworld fallback. |
| Colored ore lighting | Requires Iris custom images and compute-shader support; disabled by Speed. |
| Distant texture stabilization | Uses the game's existing mip chain. |
| Other environments | Older versions, OptiFine, Bedrock, macOS, VR, Vulkan, Distant Horizons and Voxy are not certified. |

## Choose your balance

| Preset | Intended use |
| --- | --- |
| **Balanced** | The default visual upgrade, with bounded shadows, colored ore light and half-resolution effects. |
| **Speed** | Removes costly shadow, voxel-lighting and post-effect work while keeping directional lighting, ore surface glow, color grading and built-in edge smoothing. |
| **Vibrant Fantasy** | Richer color, stronger bloom and more pronounced atmosphere. |
| **Cinematic Ultra** | More expensive shadows and surface filtering for machines with headroom. |

Native renders the world at full resolution. Experimental **Boost 85% / 75%**
reduces world shading resolution and reconstructs it; the game UI stays native.
Boost can look softer and does not accelerate CPU simulation or chunk generation.
AA is built in, with no on/off or quality selector. Camera blur and nearby
anisotropic surface filtering remain separate controls.

## Performance and verification

XON uses bounded shadow maps, a compact local light volume, shared filtering
samples and half-resolution post effects. These choices control cost; they do
not make shader rendering free or guarantee a particular frame rate.

The current shader source passed **840 OpenGL compile/link configurations** and
**790 GPU regression cases/comparisons**, including terrain rings, ore propagation,
cloud motion, AA, water, rays and hand protection. Those checks use controlled
inputs on an RTX 5060 Ti. They do not certify every mod stack or replace live
Minecraft visual and FPS testing. See [the verification record](VERIFICATION.md)
for methodology, timings and remaining checks.

Colored light follows open voxel paths rather than spherical ray tracing. The
local volume and corners can shorten its reach. Cloud ground shade is an artistic
approximation, not a traced projection of the visible sky clouds. Spatial AA
reduces shimmer but cannot recover missing subpixel information like temporal AA.

## Build from source

Python **3.10 or newer** is sufficient to package the shader; no Python packages
are required for the build.

```sh
git clone https://github.com/Danonymos/XON.git
cd XON
python tools/build.py
python tools/release_checks.py
```

The installable ZIP is written **one directory above the checkout**. The build
includes the shaders, a compact installation guide, the changelog and the license.
Screenshots, test tools, local reports and source-only documentation stay outside
the runtime ZIP. The GitHub workflow runs the same build and integrity checks;
it does not run the local GPU suite.

## Help improve XON

[Report a rendering bug or performance regression](https://github.com/Danonymos/XON/issues/new/choose)
with your versions, GPU/driver, settings and clear reproduction steps. Controlled
before/after captures are especially useful.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes. Technical details
live in [engineering notes](docs/ENGINEERING.md); maintainers can follow the
[release guide](docs/RELEASING.md).

## License

XON is **source available**, with free personal, non-commercial gameplay use under
its [Personal Use and Contribution License](LICENSE). The license includes a
specific exception for forks and pull requests that contribute to this official
repository. It is not an unrestricted open-source license. Read the full terms
before modifying, redistributing or reusing any part of the pack.

Minecraft belongs to its respective owners. XON is an independent shader project.
