"""Exercise indoor geometry occlusion against the first indoor test ZIP on OpenGL."""
import argparse
import ctypes as ct
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from PIL import Image, ImageDraw

from brightness_checks import display_luma
from pbr_checks import VERTEX
from validate import Driver, SHADERS, expand
from voxel_gpu_checks import VoxelRenderer, HALF

ROOT = Path(__file__).resolve().parents[1]


def run(baseline):
    driver = Driver()
    renderer = VoxelRenderer(driver)
    stages, programs, checks = [], [], []
    archive = zipfile.ZipFile(baseline)
    lut = np.asarray(Image.open(SHADERS / 'textures/xon-grade.png'), dtype=float) / 255

    def saved(name):
        text = archive.read('shaders/' + name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda m: saved(m[1].lstrip('/')), text, flags=re.M)

    def program(fragment, vertex=VERTEX):
        handles = []
        for text, stage in [(vertex, '.vsh'), (fragment, '.fsh')]:
            handle, warning = driver.compile(text, stage, 'indoor geometry occlusion')
            assert not warning, warning
            stages.append(handle)
            handles.append(handle)
        handle, warning = driver.link(*handles, 'indoor geometry occlusion')
        assert not warning, warning
        programs.append(handle)
        return handle

    def terrain(old, dimension=0, vertex=VERTEX):
        folder = '' if dimension == 0 else f'world{dimension}/'
        name = folder + 'gbuffers_terrain.fsh'
        text = saved(name) if old else expand(SHADERS / name)
        for key, value in {'XON_SHADOWS': False, 'XON_CLOUD_STYLE': 0, 'XON_PARALLAX': 0,
                           'XON_ADVANCED_MATERIALS': 1}.items():
            text = re.sub(rf'^(?://)?#define {key}\b[^\n]*$',
                          '#undef ' + key if value is False else f'#define {key} {value}', text, flags=re.M)
        return program(text, vertex)

    def upload(walls=0):
        field = renderer.empty_light.copy()
        field[:, :HALF[1], :, 3] = -2
        if walls >= 1:
            field[:, :, :HALF[0], 3] = -2
        if walls >= 2:
            field[:HALF[2] - 8, :, :, 3] = -2
        renderer.upload(1, field)
        renderer.upload(2, field)

    def draw(selected, position=(.1, 0, -7.9), camera=(0, 0, 0), sky=0, material=0,
             vision=0, normal=(0, 1, 0), image=False):
        renderer.setup(selected)
        renderer.uniform1i(renderer.location('normals'), 10)
        renderer.uniform1i(renderer.location('specular'), 0)
        for name, value in [('testBlock', .95), ('testSky', sky), ('testAO', 1),
                            ('testTangent', 1), ('testMaterial', material), ('alphaTestRef', .1),
                            ('far', 1024), ('fogStart', 800), ('fogEnd', 1024), ('nightVision', vision)]:
            renderer.uniform1f(renderer.location(name), value)
        for name, value in [('testPosition', position), ('testNormal', normal),
                            ('testView', (.3, .15, -1)), ('sunPosition', (30, 90, 20)), ('cameraPosition', camera)]:
            renderer.uniform3f(renderer.location(name), *value)
        result = renderer.draw(raw=True)[..., :3]
        return result if image else result.mean(axis=(0, 1), dtype=np.float64)

    try:
        for unit, value in [(8, [.5, .48, .44, 1]), (10, [128 / 255, 128 / 255, 1, 1]), (0, [0, 0, 0, 1])]:
            renderer.texture(unit, np.full((16, 16, 4), value, dtype=np.float32))
        for dimension in [0, -1, 1]:
            pair = [terrain(old, dimension) for old in [True, False]]
            for walls in [0, 1, 2]:
                upload(walls)
                before, after = [draw(p) for p in pair]
                display = [float(display_luma(v, lut, .83, True)) for v in [before, after]]
                ratio = display[1] / display[0]
                if walls == 0:
                    assert np.max(np.abs(after - before)) < 2e-6
                else:
                    assert ratio < (.94 if walls == 1 else .88), (dimension, walls, display, ratio)
                    assert display[1] > .35, (dimension, walls, display)
                checks.append({'case': f'{walls} walls, full vertex AO, high block light / dimension {dimension}',
                               'display_luma_before_after': display, 'display_ratio': ratio})
            for options in [{'sky': 1}, {'vision': 1}, {'material': 10002}, {'material': 10024}]:
                before, after = [draw(p, **options) for p in pair]
                assert np.max(np.abs(after - before)) < 2e-6, (dimension, options, before, after)
                checks.append({'case': 'outdoor/vision/emitter/foliage exclusion', 'dimension': dimension, 'options': options})
            for position in [(3, 0, -5), (48, 0, -8)]:
                before, after = [draw(p, position=position) for p in pair]
                assert np.max(np.abs(after - before)) < 2e-6
                checks.append({'case': 'open surface or volume boundary unchanged', 'dimension': dimension, 'position': position})

        prefix = '#version 330 compatibility\n' + expand(SHADERS / 'lib/settings.glsl')
        prefix += '\nuniform vec3 cameraPosition; uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n'
        prefix += expand(SHADERS / 'lib/emissive_light.glsl')
        probe = program(prefix + '''
uniform vec3 testPosition, testNormal;
out vec4 result;
void main(){result=vec4(vec3(xonIndoorOcclusion(testPosition,testNormal)),1);}
''', expand(SHADERS / 'final.vsh'))
        upload(2)
        samples = [draw(probe, position=(float(x), 0, -7.9))[0] for x in np.linspace(.01, 3, 301)]
        assert np.min(samples) >= .28 and np.max(samples) <= 1
        assert np.max(np.abs(np.diff(samples))) < .025
        checks.append({'case': 'continuous world-space falloff across voxel stencil changes', 'maximum_step': float(np.max(np.abs(np.diff(samples))))})
        reference = draw(probe)
        for camera in [(.1, .2, .3), (.8, .1, .7)]:
            point = np.array([.1, 0, -7.9]) - camera
            value = draw(probe, position=point, camera=camera)
            assert np.max(np.abs(reference - value)) < 2e-6
        checks.append({'case': 'sub-block camera motion retains world-space occlusion'})
        # Two views of the same uniformly lit floor; no vertex AO is supplied.
        floor_vertex = VERTEX.replace('xonViewPosition=testPosition;xonPlayerPosition=testPosition;',
                                      'xonPlayerPosition=vec3(uv.x*4.0,0,-8.0+uv.y*4.0);xonViewPosition=xonPlayerPosition;')
        pair = [terrain(old, vertex=floor_vertex) for old in [True, False]]
        images = [draw(p, image=True) for p in pair]
        sheet = Image.new('RGB', (1280, 390))
        painter = ImageDraw.Draw(sheet)
        for index, raw in enumerate(images):
            hdr = raw * .83 * 1.05
            tone = np.clip(hdr * (2.51 * hdr + .03) / (hdr * (2.43 * hdr + .59) + .14), 0, 1) ** (1 / 2.2)
            sheet.paste(Image.fromarray(np.uint8(np.clip(tone[::-1], 0, 1) * 255)), (index * 640, 30))
            painter.text((index * 640 + 12, 8), 'Synthetic floor, uniform light / ' + ('first patch' if index == 0 else 'geometry occlusion'), fill='white')
        sheet.save(ROOT / 'validation-indoor-occlusion.png')
        renderer.width, renderer.height = 1920, 1080
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, 1920, 1080, 0, 0x1908, 0x1406, None)
        f = driver.function
        gen = f('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin = f('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end = f('glEndQuery', None, ct.c_uint)
        read = f('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete = f('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))

        def quad():
            renderer.begin(0x0007)
            for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                renderer.tex_coord(x, y)
                renderer.vertex(x, y)
            renderer.end()

        queries = (ct.c_uint * 32)()
        gen(32, queries)
        for selected in pair:
            draw(selected)
            for _ in range(8):
                quad()
        for iteration in range(16):
            for version in ([0, 1] if iteration % 2 == 0 else [1, 0]):
                draw(pair[version])
                begin(0x88BF, queries[iteration * 2 + version])
                for _ in range(4):
                    quad()
                end(0x88BF)
        times = [[], []]
        for iteration in range(16):
            for version in [0, 1]:
                value = ct.c_uint64()
                read(queries[iteration * 2 + version], 0x8866, ct.byref(value))
                times[version].append(value.value / 4e6)
        delete(32, queries)
        timing = [{'median_ms': float(np.median(t)), 'p95_ms': float(np.percentile(t, 95))} for t in times]
        report = {'passed': True, 'checks': checks, 'baseline': str(baseline),
                  'synthetic_1080p_terrain_gpu_before_after': timing,
                  'scope': 'Synthetic production terrain/PBR with actual occupancy/light volumes; not a Minecraft screenshot. Coarse solid-voxel occlusion, no source-specific ray traced shadows.'}
        (ROOT / 'validation-indoor-occlusion.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': True, 'checks': len(checks), 'report': str(ROOT / 'validation-indoor-occlusion.json')}, indent=2))
    finally:
        archive.close()
        for p in programs:
            driver.delete_program(p)
        for s in stages:
            driver.delete_shader(s)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    run(parser.parse_args().baseline)
