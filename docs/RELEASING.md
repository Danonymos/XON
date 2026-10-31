# Prepare and publish a release

The shader source, project page and release notes are versioned together. A Git
push updates the repository; publishing a GitHub Release is a separate step.

## Build and check

From a clean checkout, with Python 3.10 or newer:

```sh
python tools/build.py
python tools/release_checks.py
```

The runtime ZIP is written one directory above the checkout. It contains shaders,
a compact README, CHANGELOG.md and LICENSE. Repository screenshots, developer
tools, local reports and machine settings are excluded. Do not upload GitHub's
source-code ZIP as an installable shader pack.

The **Build shader pack** workflow runs on main pushes, pull requests and manual
runs. It builds the runtime ZIP, checks source parity/entrypoints/includes/docs,
and uploads a downloadable artifact. It has read-only repository permissions
and does not publish a release or push code. Extract the Actions artifact's outer
container before installing the actual shader ZIP inside it.

## Before tagging

1. Match `VERSION` in `tools/build.py`, the README, pack guide and release notes.
2. Update CHANGELOG.md and document the checks actually performed in VERIFICATION.md.
3. Run the relevant local GPU tests when changing shaders. Actions checks package
   structure; they do not run the Windows GPU suite or Minecraft.
4. Commit the reviewed source/docs, then push main normally. Do not force-push.
5. Wait for the pack workflow and inspect the artifact. Check the target commit
   contains the intended shader changes before creating its release tag.

## Publish 1.0.9 through GitHub

1. Open https://github.com/Danonymos/XON/releases/new after pushing the prepared commits.
2. Choose a new **v1.0.9** tag targeting the reviewed main commit.
3. Title the release **XON Shader 1.0.9 — Balanced interiors, softer light**.
4. Paste [the prepared release body](releases/1.0.9.md).
5. Upload `XON-Shader-v1.0.9.zip` from the fresh build or verified workflow artifact.
6. Publish when ready. No release has been created by the local preparation steps.

For a checksum, run from the checkout:

```sh
python -c "import hashlib; from pathlib import Path; from tools.build import VERSION; p=Path('..') / f'XON-Shader-v{VERSION}.zip'; print(hashlib.sha256(p.read_bytes()).hexdigest(), p.name)"
```

Keep earlier test ZIPs private as diagnostic baselines. Source snapshots remain
available through GitHub's release source archives; keep the complete project
license with every distributed runtime pack.

## Push from any directory on the maintainer's Windows PC

```sh
git -C "G:/shaders/XON-Shader" push origin main
```

For another checkout, replace the path with its absolute location. The command
pushes the prepared local commits; Git may request your normal GitHub login.
