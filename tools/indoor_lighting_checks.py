"""Compare production terrain shading with an explicit pre-change shader ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from PIL import Image

from brightness_checks import display_luma
from pbr_checks import VERTEX
from validate import Driver, SHADERS, expand
from voxel_gpu_checks import VoxelRenderer

ROOT = Path(__file__).resolve().parents[1]
NORMALS = [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]


def run(baseline):
    driver = Driver()
    renderer = VoxelRenderer(driver)
    stages, programs, checks = [], [], []
    archive = zipfile.ZipFile(baseline)
    lut = np.asarray(Image.open(SHADERS / 'textures/xon-grade.png'), dtype=float) / 255

    def source(name, old):
        text = archive.read('shaders/' + name).decode() if old else (SHADERS / name).read_text()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda m: source(m[1].lstrip('/'), old), text, flags=re.M)

    def program(old, dimension, pbr, colored, ao=1):
        folder = '' if dimension == 0 else f'world{dimension}/'
        fragment = source(folder + 'gbuffers_terrain.fsh', old)
        options = {'XON_SHADOWS': False, 'XON_CLOUD_STYLE': 0, 'XON_PARALLAX': 0,
                   'XON_ADVANCED_MATERIALS': 1 if pbr else False,
                   'XON_COLORED_EMISSIVE_LIGHTING': 1 if colored else False,
                   'XON_AO_STRENGTH': f'{ao:.2f}'}
        for key, value in options.items():
            fragment = re.sub(rf'^(?://)?#define {key}\b(?:[^\n]*)?$',
                              '#undef ' + key if value is False else f'#define {key} {value}',
                              fragment, flags=re.M)
        pair = []
        for text, stage in [(VERTEX, '.vsh'), (fragment, '.fsh')]:
            handle, warning = driver.compile(text, stage, 'indoor production terrain')
            assert not warning, warning
            pair.append(handle)
            stages.append(handle)
        handle, warning = driver.link(*pair, 'indoor production terrain')
        assert not warning, warning
        programs.append(handle)
        return handle

    def draw(selected, block=.8, sky=0, ao=1, normal=(0, 1, 0), material=0, vision=0, held=0):
        renderer.setup(selected)
        for name, value in [('normals', 10), ('specular', 0)]:
            renderer.uniform1i(renderer.location(name), value)
        renderer.uniform1i(renderer.location('heldBlockLightValue'), held)
        for name, value in [('testBlock', block), ('testSky', sky), ('testAO', ao),
                            ('testTangent', 1), ('testMaterial', material), ('alphaTestRef', .1),
                            ('far', 1024), ('fogStart', 800), ('fogEnd', 1024), ('nightVision', vision)]:
            renderer.uniform1f(renderer.location(name), value)
        for name, value in [('testNormal', normal), ('testPosition', (0, 0, -8)),
                            ('testView', (.3, .15, -1)), ('sunPosition', (30, 90, 20))]:
            renderer.uniform3f(renderer.location(name), *value)
        return renderer.draw(raw=True)[..., :3].mean(axis=(0, 1), dtype=np.float64)

    def equal(label, pair, **options):
        before, after = [draw(p, **options) for p in pair]
        error = float(np.max(np.abs(after - before)))
        assert error < 2e-6, (label, error)
        checks.append({'case': label, 'maximum_linear_error': error})

    try:
        renderer.texture(8, np.full((16, 16, 4), [.5, .48, .44, 1], dtype=np.float32))
        renderer.texture(10, np.full((16, 16, 4), [128 / 255, 128 / 255, 1, 1], dtype=np.float32))
        renderer.texture(0, np.full((16, 16, 4), [0, 0, 0, 1], dtype=np.float32))
        colored_field = renderer.empty_light.copy()
        colored_field[:] = [.15, .75, .85, .65]
        renderer.upload(1, colored_field)
        renderer.upload(2, colored_field)
        for dimension in [0, -1, 1]:
            for pbr, colored in [(False, False), (True, False), (True, True)]:
                pair = [program(old, dimension, pbr, colored) for old in [True, False]]
                label = f'dimension {dimension}, PBR {pbr}, colored {colored}'
                before, after = [np.array([draw(p, normal=n) for n in NORMALS]) for p in pair]
                mean_ratio = float(after.mean() / before.mean())
                assert abs(mean_ratio - 1) < .003, (label, mean_ratio)
                display = [display_luma(v, lut, .83, True) for v in [before, after]]
                assert abs(float(display[1].mean() / display[0].mean()) - 1) < .015
                assert np.ptp(display[1]) > np.ptp(display[0]) + .025
                checks.append({'case': 'stronger face contrast with balanced mean energy / ' + label,
                               'mean_linear_ratio': mean_ratio,
                               'mean_display_ratio': float(display[1].mean() / display[0].mean()),
                               'display_face_range_before_after': [float(np.ptp(v)) for v in display]})
                for n in NORMALS:
                    equal('open skylight unchanged / ' + label, pair, sky=1, normal=n, ao=.6)
                    equal('night vision unchanged / ' + label, pair, vision=1, normal=n, ao=.6)
                for material in [10002, 10003, 10004, 10022, 10024, 10027]:
                    equal('emissive or plant behavior retained / ' + label + f' / {material}',
                          pair, material=material, ao=.6)
                old_ratio, new_ratio = [float(draw(p, ao=.6).mean() / draw(p).mean()) for p in pair]
                assert .65 < new_ratio / old_ratio < .90, (label, old_ratio, new_ratio)
                checks.append({'case': 'deeper contact shade with readable recesses / ' + label,
                               'cavity_to_open_ratio_before_after': [old_ratio, new_ratio]})
                if not colored:
                    equal('unlit cave unchanged / ' + label, pair, block=0, ao=.6)
                    equal('held light unchanged / ' + label, pair, block=0, held=15, ao=.6)
                    levels = np.linspace(0, 1, 65)
                    ramp = np.array([draw(pair[1], block=float(b)) for b in levels])
                    assert np.min(np.diff(ramp, axis=0)) >= -2e-6
                    assert np.max(np.abs(np.diff(ramp, n=2, axis=0))) < .003
                    checks.append({'case': 'smooth monotonic light response / ' + label})
                    for n in NORMALS:
                        unlit, edge = [draw(pair[1], block=b, normal=n) for b in [0, .04]]
                        assert np.all(edge > unlit), (label, n, unlit, edge)
                    checks.append({'case': 'faint light retains reach on every face / ' + label})
                doorway = np.array([draw(pair[1], sky=float(s)) for s in np.linspace(0, 1, 129)])
                assert np.max(np.abs(np.diff(doorway, n=2, axis=0))) < .01
                checks.append({'case': 'smooth doorway transition / ' + label})
                renderer.texture(8, np.full((16, 16, 4), [.98, .97, .96, 1], dtype=np.float32))
                for material in [10025, 10026]:
                    equal('lantern core retained / ' + label + f' / {material}', pair, material=material, ao=.6)
                renderer.texture(8, np.full((16, 16, 4), [.5, .48, .44, 1], dtype=np.float32))
        ao_off = [program(old, 0, True, False, ao=0) for old in [True, False]]
        cavity_ratios = [draw(p, ao=.6) / draw(p) for p in ao_off]
        assert np.max(np.abs(cavity_ratios[0] - cavity_ratios[1])) < 2e-5, cavity_ratios
        checks.append({'case': 'AO strength zero retains original contact shading response'})
        for name in ['lib/settings.glsl']:
            assert archive.read('shaders/' + name).replace(b'\r\n', b'\n') == (SHADERS / name).read_bytes().replace(b'\r\n', b'\n')
        old_map = archive.read('shaders/block.properties').decode().splitlines()
        current_map = (SHADERS / 'block.properties').read_text().splitlines()
        assert [line for line in current_map if not line.startswith('block.10028=')] == old_map
        compute = (SHADERS / 'program/shadowcomp.csh').read_text()
        compute = compute.replace('if (data == XON_VOXEL_OCCLUDER) {\n        light.a = -2.0;\n    } else if (data >= XON_VOXEL_FIRST_EMITTER)',
                                  'if (data >= XON_VOXEL_FIRST_EMITTER)')
        assert compute == archive.read('shaders/program/shadowcomp.csh').decode().replace('\r\n', '\n')
        emissive = (SHADERS / 'lib/emissive_light.glsl').read_text()
        original_emissive = archive.read('shaders/lib/emissive_light.glsl').decode().replace('\r\n', '\n')
        start = emissive.index('float xonIndoorOcclusion(')
        end = emissive.index('// Trilinear blend', start)
        retained = (emissive[:start] + emissive[end:]).replace('const uint XON_VOXEL_OCCLUDER = 255u;\n', '')
        assert retained == original_emissive
        checks.append({'case': 'source mappings, intensities, falloff, volume size and propagation unchanged'})
        report = {'passed': True, 'baseline': str(baseline),
                  'baseline_sha256': hashlib.sha256(baseline.read_bytes()).hexdigest(), 'checks': checks,
                  'scope': 'Synthetic OpenGL production terrain fragments in all three dimensions; controlled AO, lightmap, flat PBR and colored volume. Form/contact shading, not individual lamp shadow tracing or a Minecraft visual approval.'}
        (ROOT / 'validation-indoor-lighting.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': True, 'checks': len(checks), 'report': str(ROOT / 'validation-indoor-lighting.json')}, indent=2))
    finally:
        archive.close()
        for handle in programs:
            driver.delete_program(handle)
        for handle in stages:
            driver.delete_shader(handle)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    run(parser.parse_args().baseline)
