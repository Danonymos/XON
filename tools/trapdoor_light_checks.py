"""Reproduce trapdoor half-cell bands on adjacent solid receiver faces."""
import ctypes as ct
import json
from pathlib import Path
import re
import sys
import zipfile

import numpy as np
from lamp_gpu_checks import LampRenderer
from validate import Driver, SHADERS, expand

ROOT = Path(__file__).resolve().parents[1]


def run(reproduce=False):
    driver = Driver()
    renderer = LampRenderer(driver)
    programs, stages, checks = [], [], []
    archive = zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.8.4-r8.zip')

    def saved(name):
        text = archive.read('shaders/' + name).decode().replace('\r', '')
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$', lambda m: saved(m[1].lstrip('/')), text, flags=re.M)

    def program(source, ao=False):
        text = '#version 330 compatibility\n' + source('lib/settings.glsl')
        text += '\nuniform vec3 cameraPosition;uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n'
        text += source('lib/emissive_light.glsl')
        result = 'vec4(xonIndoorOcclusion(testPosition,testNormal))' if ao else 'xonLampLight(testPosition,testNormal)'
        text += '\nuniform vec3 testPosition,testNormal;out vec4 result;void main(){result=' + result + ';}'
        pair = []
        for code, kind in [(source('final.vsh'), '.vsh'), (text, '.fsh')]:
            shader, warning = driver.compile(code, kind, 'trapdoor adjacent receiver')
            assert not warning, warning
            stages.append(shader)
            pair.append(shader)
        selected, warning = driver.link(*pair, 'trapdoor adjacent receiver')
        assert not warning, warning
        programs.append(selected)
        return selected

    def upload(mask, normal_axis, normal_sign, thin=True):
        field = renderer.empty_light.copy()
        field[:] = [.12, .18, .20, 188]
        blocked = [slice(None)] * 3
        centre = [48, 24, 48]
        blocked[2 - normal_axis] = slice(None, centre[2 - normal_axis]) if normal_sign > 0 else slice(centre[2 - normal_axis] + 1, None)
        field[tuple(blocked)] = [0, 0, 0, -1]
        field[48, 24, 48, 3] = -188
        for index in range(2):
            renderer.active_texture(0x84CD + index)
            renderer.bind_texture(0x806F, renderer.lamps[index])
            renderer.sub3d(0x806F, 0, 0, 0, 0, 96, 48, 96, 0x1908, 0x1406, field.ctypes.data)
        metadata = renderer.contact_fallback.copy()
        metadata[48, 24, 48] = ((masks.index(mask) + 1) << 27) | ((1 << 13) if thin else 0)
        renderer.active_texture(0x84CF)
        renderer.bind_texture(0x806F, renderer.contact[0])
        renderer.sub3d(0x806F, 0, 0, 0, 0, 96, 48, 96, 0x8D94, 0x1405, metadata.ctypes.data)
        renderer.barrier(0xFFFFFFFF)
        renderer.frame = 2

    try:
        masks = [int(v) for v in re.search(r'\]\(([^)]*)\)', (SHADERS / 'lib/block_shapes.glsl').read_text())[1].replace('u', '').split(',')]
        samplers = [program(saved), program(lambda name: expand(SHADERS / name))]
        ao = program(lambda name: expand(SHADERS / name), True)
        renderer.width = renderer.height = 1
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, 1, 1, 0, 0x1908, 0x1406, None)
        repaired = 0
        for mask, thin_axis, side in [(85, 0, 1), (170, 0, -1), (51, 1, 1), (204, 1, -1), (15, 2, 1), (240, 2, -1)]:
            for normal_axis in [a for a in range(3) if a != thin_axis]:
                for normal_sign in [-1, 1]:
                    normal = np.eye(3)[normal_axis] * normal_sign
                    upload(mask, normal_axis, normal_sign)
                    values = [[], []]
                    for distance in [.22, .35, .49, .51, .65, .78]:
                        point = [.5, .5, .5]
                        point[normal_axis] = 0 if normal_sign > 0 else 1
                        point[thin_axis] = distance if side > 0 else 1 - distance
                        pair = [renderer.sample(p, point, normal) for p in samplers]
                        for version in range(2):
                            values[version].append(pair[version])
                        if distance < .5:
                            assert max(pair[0]) == 0, (mask, point, pair)
                            if not reproduce:
                                assert min(pair[1]) > .05, (mask, point, pair)
                            repaired += 1
                    before_step, after_step = [float(np.max(np.abs(np.diff(v, axis=0)))) for v in values]
                    assert before_step > .1
                    if not reproduce:
                        assert after_step < .00001, (mask, normal_axis, normal_sign, after_step)
                    point[thin_axis] = .1 if side > 0 else .9
                    assert max(renderer.sample(samplers[1], point, normal)) == 0, 'Actual panel solid must still block the receiver'
                    upload(mask, normal_axis, normal_sign, thin=False)
                    point[thin_axis] = .35 if side > 0 else .65
                    assert max(renderer.sample(samplers[1], point, normal)) == 0, 'A genuine half slab must remain solid'
                    checks.append({'mask': mask, 'normal_axis': normal_axis, 'normal_sign': normal_sign,
                                   'before_after_max_rgb_step': [before_step, after_step]})
        for thin in [False, True]:
            upload(51, 1, 1, thin)
            value = renderer.sample(ao, [.5, 0, .5], [0, 1, 0])
            if not reproduce:
                assert np.max(np.abs(value - 1)) < 1e-6, 'Thin metadata must not become contact AO'
        timing = None
        if not reproduce:
            upload(51, 0, 1)
            renderer.width, renderer.height = 1920, 1080
            renderer.active_texture(0x84CB)
            renderer.bind_texture(0x0DE1, renderer.textures[11])
            renderer.tex_image(0x0DE1, 0, 0x8814, 1920, 1080, 0, 0x1908, 0x1406, None)
            renderer.viewport(0, 0, 1920, 1080)
            query = ct.c_uint()
            gen = driver.function('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
            begin = driver.function('glBeginQuery', None, ct.c_uint, ct.c_uint)
            end = driver.function('glEndQuery', None, ct.c_uint)
            read = driver.function('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
            delete = driver.function('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
            gen(1, ct.byref(query))
            samples = [[], []]
            try:
                for repeat in range(26):
                    for version in ([0, 1] if repeat % 2 == 0 else [1, 0]):
                        renderer.setup(samplers[version])
                        renderer.uniform1i(renderer.location('frameCounter'), 1)
                        renderer.uniform3f(renderer.location('testPosition'), 0, .35, .5)
                        renderer.uniform3f(renderer.location('testNormal'), 1, 0, 0)
                        begin(0x88BF, query)
                        for _ in range(4):
                            renderer.begin(0x0007)
                            for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                                renderer.tex_coord(x, y)
                                renderer.vertex(x, y)
                            renderer.end()
                        end(0x88BF)
                        value = ct.c_uint64()
                        read(query, 0x8866, ct.byref(value))
                        if repeat >= 4:
                            samples[version].append(value.value / 4e6)
            finally:
                delete(1, ct.byref(query))
            timing = {'kind': '1080p adjacent-panel sampler proxy; not full-game FPS',
                      'R8_ms': float(np.median(samples[0])), 'candidate_ms': float(np.median(samples[1])),
                      'paired_median_ratio': float(np.median(np.array(samples[1]) / samples[0]))}
        report = {'passed': not reproduce, 'R8_band_reproduced': True, 'receiver_cases': repaired,
                  'checks': checks, 'timing': timing,
                  'scope': 'Production sampler with controlled radiance and solid receiver geometry; live view still required.'}
        if not reproduce:
            (ROOT / 'validation-trapdoor-light.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': report['passed'], 'R8_band_reproduced': True, 'receiver_cases': repaired,
                          'first_case': checks[0], 'timing': timing}))
    finally:
        for p in programs:
            driver.delete_program(p)
        for s in stages:
            driver.delete_shader(s)
        renderer.close()
        driver.close()
        archive.close()


if __name__ == '__main__':
    run('--reproduce' in sys.argv)
