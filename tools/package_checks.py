"""Check runtime/source parity, declared options, defaults and untouched references."""

from pathlib import Path
import argparse
import hashlib
import json
import re
import zipfile
from build import VERSION

ROOT = Path(__file__).resolve().parents[1]


def run(installed_name=None):
    package = ROOT.parent / f'XON-Shader-v{VERSION}.zip'
    runtime = sorted(path for path in (ROOT / 'shaders').rglob('*') if path.is_file())
    expected = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in runtime}
    expected.update({name: (ROOT / name).read_bytes() for name in ['README.md', 'CHANGELOG.md']})
    with zipfile.ZipFile(package) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(expected):
            raise AssertionError('ZIP integrity or runtime file inventory mismatch')
        for name, content in expected.items():
            if archive.read(name) != content:
                raise AssertionError(f'ZIP differs from source: {name}')
    settings = (ROOT / 'shaders/lib/settings.glsl').read_text()
    for expression in [r'^#define XON_RENDER_MODE 0 ', r'^#define XON_MOTION_BLUR$',
                       r'^#define XON_BLUR_STRENGTH 1.50 ',
                       r'^//#define XON_AIR_FOG$']:
        if re.search(expression, settings, flags=re.M) is None:
            raise AssertionError(f'Default changed: {expression}')
    properties = (ROOT / 'shaders/shaders.properties').read_text()
    language = (ROOT / 'shaders/lang/en_US.lang').read_text()
    if any(name in settings + properties + language for name in ['XON_EDGE_AA', 'XON_AA_MODE']):
        raise AssertionError('Built-in AA must not have a player-facing toggle or quality selector')
    final = (ROOT / 'shaders/program/final.fsh').read_text()
    if 'color = xonEdgeAA(color, depth, motionPixels, handMask);' not in final:
        raise AssertionError('Built-in edge smoothing is missing from the final pass')
    defined = set(re.findall(r'^(?://)?#define (XON_\w+)', settings, flags=re.M))
    constants = set(re.findall(r'^const \w+ (\w+) = .+; // \[', settings, flags=re.M))
    source = '\n'.join(path.read_text() for path in runtime if path.suffix in ['.glsl', '.vsh', '.fsh'])
    boolean_guards = set(re.findall(r'^\s*#ifn?def\s+(XON_\w+)', source, flags=re.M))
    booleans = set(re.findall(r'^(?://)?#define (XON_\w+)$', settings, flags=re.M))
    menu_options = set()
    for line in properties.splitlines():
        if line.startswith('screen.'):
            for option in line.split('=', 1)[1].split():
                if option.startswith(('[', '<')):
                    continue
                menu_options.add(option)
                if option not in defined | constants or f'option.{option}=' not in language:
                    raise AssertionError(f'Unknown or untranslated menu option: {option}')
                if option in booleans and option not in boolean_guards:
                    raise AssertionError(f'Iris cannot discover the boolean option guard: {option}')
    references = ['36b0a50ff7918bf10e9422c401d93779f9d0088a26acea975b435243f96930b5',
                  '98ac741dee294d2a3c82d153349148c3bb7fb688c30eb3b49c3b9ac37e968c5a',
                  'da0929b38f5fd99befaaa8cd141cbf60e1fad05b92d916d0eeeee7c79f86c0fd',
                  '492f96583ba1061d67cb8337a6b37b7b8669533bb08fe0bfc22938d56670b8b9']
    for index, digest in enumerate(references, 1):
        if hashlib.sha256((ROOT.parent / f'{index}.zip').read_bytes()).hexdigest() != digest:
            raise AssertionError(f'Reference archive {index} changed')
    installed = Path('C:/Users/crypt/AppData/Roaming/ModrinthApp/profiles/Ziz/shaderpacks') / (installed_name or package.name)
    if installed.read_bytes() != package.read_bytes():
        raise AssertionError('Installed ZIP differs from the reviewed build')
    report = {'passed': True, 'runtime_files': len(expected), 'menu_options': sorted(menu_options),
              'sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
              'bytes': package.stat().st_size, 'installed_copy_matches': True, 'installed_path': str(installed),
              'reference_archives_unchanged': True, 'default_native_blur_aa_clear_air': True}
    (ROOT / 'validation-package.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed-name', help='Alternate installed ZIP name when the active pack is locked')
    run(parser.parse_args().installed_name)
