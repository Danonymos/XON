# Contributing to XON

Focused improvements, reproducible bug reports, and careful performance work are welcome. XON is source available under a restrictive personal-use license, with a specific exception for contributions to this official repository. Read [LICENSE](LICENSE) first.

## Report a problem

Use the issue templates. Include Minecraft, Iris and Sodium versions; GPU and driver; operating system; selected preset and render mode; resolution; render distance; relevant mods/resource packs; clear steps; and expected versus actual behavior. Add an unedited screenshot and the relevant XON error when available. Remove personal information from logs.

For performance issues, use the same position, weather, time, resolution, and render distance. Compare shaders off, Balanced + Native, and Speed + Native after warm-up. Include average FPS and frame-time information if measured. Label estimates as estimates.

## Prepare a pull request

1. Discuss larger visual or architectural changes in an issue first.
2. Fork this repository and clearly identify it as an unofficial contribution fork.
3. Make a branch with one focused change. Keep existing shader options and program wrappers consistent across Overworld, Nether, and End.
4. Retain the license and notices. Do not import code or assets you lack permission to contribute.
5. Test with Minecraft Java 26.3, Iris, and Sodium. Check Balanced/Speed and Native; test Boost if your change touches resolution or sampling. Inspect logs for shader compilation/link errors.
6. Check daylight, sunset, night, rain, water/underwater, foliage, held items, Nether, and End where relevant. Describe exactly what you tested and what remains untested.
7. Submit a pull request describing the problem, change, tradeoffs, and validation. Include comparison screenshots or controlled performance measurements where appropriate.

Do not claim a compile or performance improvement without evidence. Do not publish standalone shader binaries from your contribution fork; the license permits private test builds and source changes for official-project contributions.

By submitting, you confirm that you have rights to your contribution, license it under the project terms, and permit the maintainer to use, modify, and distribute it as part of XON Shader as described in LICENSE. You retain copyright in your original work. Acceptance is at the maintainer's discretion.
