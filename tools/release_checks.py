"""Verify a distributable pack and repository documentation without a GPU or extra packages."""
from pathlib import Path
import argparse
import hashlib
import json
import py_compile
import re
import unicodedata
from urllib.parse import unquote, urlsplit
import zipfile

from build import ROOT, VERSION, PROGRAMS


def check(package):
    shader_root = ROOT / 'shaders'
    runtime = {p.relative_to(ROOT).as_posix(): p.read_bytes()
               for p in shader_root.rglob('*') if p.is_file()}
    expected = dict(runtime, **{'README.md': (ROOT / 'docs/PACK-README.md').read_bytes(),
                               'CHANGELOG.md': (ROOT / 'CHANGELOG.md').read_bytes(),
                               'LICENSE': (ROOT / 'LICENSE').read_bytes()})
    with zipfile.ZipFile(package) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(expected) or set(archive.namelist()) != set(expected):
            raise AssertionError('Runtime ZIP inventory/integrity mismatch')
        for name, content in expected.items():
            if archive.read(name) != content:
                raise AssertionError(f'Runtime ZIP differs from source: {name}')

    entrypoints = 0
    for folder, dimension in [('', 0), ('world-1', -1), ('world1', 1)]:
        for program in PROGRAMS:
            for stage in ['vsh', 'fsh']:
                path = shader_root / folder / f'{program}.{stage}'
                text = path.read_text(encoding='utf-8')
                if not text.startswith('#version 330 compatibility\n') or f'#define XON_DIMENSION {dimension}\n' not in text:
                    raise AssertionError(f'Incorrect runtime wrapper: {path.relative_to(ROOT)}')
            entrypoints += 1
        compute = (shader_root / folder / 'shadowcomp.csh').read_text(encoding='utf-8')
        if not compute.startswith('#version 430 compatibility\n') or f'#define XON_DIMENSION {dimension}\n' not in compute:
            raise AssertionError(f'Incorrect compute wrapper for dimension {dimension}')
    if entrypoints != 84:
        raise AssertionError(f'Expected 84 graphics entrypoints, got {entrypoints}')

    include_pattern = re.compile(r'^\s*#include\s+"([^"]+)"', re.M)
    visited = set()

    def includes(path, stack=()):
        if path in stack:
            raise AssertionError(f'Shader include cycle: {path.relative_to(ROOT)}')
        if path in visited:
            return
        for target in include_pattern.findall(path.read_text(encoding='utf-8')):
            child = (shader_root / target.lstrip('/') if target.startswith('/') else path.parent / target).resolve()
            if not child.is_relative_to(shader_root.resolve()) or not child.is_file():
                raise AssertionError(f'Broken shader include in {path.relative_to(ROOT)}: {target}')
            includes(child, stack + (path,))
        visited.add(path)

    for path in shader_root.rglob('*'):
        if path.suffix in ['.vsh', '.fsh', '.csh', '.glsl']:
            includes(path.resolve())
    python_files = list((ROOT / 'tools').rglob('*.py'))
    for path in python_files:
        py_compile.compile(str(path), doraise=True)

    documents = [ROOT / name for name in ['README.md', 'CHANGELOG.md', 'CONTRIBUTING.md', 'VERIFICATION.md']]
    documents += sorted((ROOT / 'docs').rglob('*.md'))
    links = 0
    for path in documents:
        text = path.read_text(encoding='utf-8')
        targets = re.findall(r'!?\[[^\]]*\]\(([^\s)]+)', text)
        targets += re.findall(r'(?:src|href)="([^"]+)"', text)
        for target in targets:
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            resolved = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path.resolve()
            if not resolved.is_relative_to(ROOT.resolve()) or not resolved.is_file():
                raise AssertionError(f'Broken local documentation target in {path.relative_to(ROOT)}: {target}')
            if parsed.fragment and resolved.suffix == '.md':
                headings = re.findall(r'^#{1,6}\s+(.+)$', resolved.read_text(encoding='utf-8'), re.M)
                slugs = {''.join(c for c in heading.lower() if not unicodedata.category(c).startswith('P') or c in '-_').replace(' ', '-') for heading in headings}
                if parsed.fragment not in slugs:
                    raise AssertionError(f'Broken Markdown anchor in {path.relative_to(ROOT)}: {target}')
            links += 1
    for name in ['README.md', 'docs/PACK-README.md', 'CHANGELOG.md', f'docs/releases/{VERSION}.md']:
        if VERSION not in (ROOT / name).read_text(encoding='utf-8'):
            raise AssertionError(f'Current version missing from {name}')
    report = {'passed': True, 'version': VERSION, 'runtime_files': len(expected),
              'graphics_entrypoints': entrypoints, 'compute_entrypoints': 3,
              'shader_files_checked': len(visited), 'python_files_compiled': len(python_files),
              'local_document_links_checked': links, 'license_included': True,
              'sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
              'scope': 'Pack/source/documentation integrity only; no GPU compilation or Minecraft runtime test.'}
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=ROOT.parent / f'XON-Shader-v{VERSION}.zip')
    check(parser.parse_args().package)
