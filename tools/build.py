from pathlib import Path
import argparse
import hashlib
import json
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.3'

PROGRAMS = {
    'gbuffers_basic': ('geometry', ['XON_BASIC']),
    'gbuffers_line': ('geometry', ['XON_BASIC', 'XON_LINE']),
    'gbuffers_textured': ('geometry', ['XON_UNLIT']),
    'gbuffers_textured_lit': ('geometry', []),
    'gbuffers_terrain': ('geometry', ['XON_TERRAIN']),
    'gbuffers_damagedblock': ('geometry', ['XON_UNLIT']),
    'gbuffers_block': ('geometry', ['XON_ENTITY']),
    'gbuffers_entities': ('geometry', ['XON_ENTITY']),
    'gbuffers_entities_translucent': ('geometry', ['XON_ENTITY']),
    'gbuffers_block_translucent': ('geometry', ['XON_ENTITY']),
    'gbuffers_hand': ('geometry', ['XON_HAND']),
    'gbuffers_hand_water': ('geometry', ['XON_HAND']),
    'gbuffers_water': ('geometry', ['XON_WATER']),
    'gbuffers_weather': ('geometry', []),
    'gbuffers_clouds': ('geometry', ['XON_CLOUD']),
    'gbuffers_particles': ('geometry', []),
    'gbuffers_particles_translucent': ('geometry', []),
    'gbuffers_spidereyes': ('geometry', ['XON_UNLIT', 'XON_EMISSIVE']),
    'gbuffers_lightning': ('geometry', ['XON_BASIC', 'XON_EMISSIVE']),
    'gbuffers_beaconbeam': ('geometry', ['XON_UNLIT', 'XON_EMISSIVE']),
    'gbuffers_armor_glint': ('geometry', ['XON_UNLIT']),
    'gbuffers_skybasic': ('sky', []),
    'gbuffers_skytextured': ('sky', ['XON_SKY_TEXTURED']),
    'final': ('final', []),
    'deferred': ('deferred', []),
    'composite': ('composite', []),
    'composite1': ('composite1', []),
    'shadow': ('shadow', []),
}


def generate_programs():
    for directory, dimension in [('', 0), ('world-1', -1), ('world1', 1)]:
        target = ROOT / 'shaders' / directory
        target.mkdir(parents=True, exist_ok=True)
        for name, (source, flags) in PROGRAMS.items():
            for stage in ['vsh', 'fsh']:
                header = '#version 330 compatibility\n'
                header += f'#define XON_DIMENSION {dimension}\n'
                header += ''.join(f'#define {flag}\n' for flag in flags)
                if stage == 'fsh' and name != 'final':
                    targets = '0,4' if 'XON_HAND' in flags else {'deferred': '7', 'composite': '5', 'composite1': '5'}.get(name, '0')
                    header += f'/* RENDERTARGETS: {targets} */\n'
                stage_source = 'final' if stage == 'vsh' and name in ['deferred', 'composite', 'composite1'] else source
                header += f'#include "/program/{stage_source}.{stage}"\n'
                (target / f'{name}.{stage}').write_text(header, encoding='utf-8', newline='\n')
        csh_header = f'#version 430 compatibility\n#define XON_DIMENSION {dimension}\n#include "/program/shadowcomp.csh"\n'
        (target / 'shadowcomp.csh').write_text(csh_header, encoding='utf-8', newline='\n')


def package(output):
    generate_programs()
    files = [(p.relative_to(ROOT).as_posix(), p) for p in sorted((ROOT / 'shaders').rglob('*')) if p.is_file()]
    files += [('README.md', ROOT / 'docs/PACK-README.md'),
              ('CHANGELOG.md', ROOT / 'CHANGELOG.md'), ('LICENSE', ROOT / 'LICENSE')]
    temporary = output.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in files:
            info = zipfile.ZipInfo(name, (2026, 10, 28, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    temporary.replace(output)
    print(json.dumps({'package': str(output), 'files': len(files), 'bytes': output.stat().st_size,
                      'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build the original XON Shader beta pack.')
    parser.add_argument('--generate-only', action='store_true')
    args = parser.parse_args()
    if args.generate_only:
        generate_programs()
    else:
        package(ROOT.parent / f'XON-Shader-v{VERSION}.zip')
