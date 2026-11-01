"""Exercise production sky vertices/fragments with native cube/celestial blending."""
import ctypes as ct
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from render_checks import Renderer
from validate import Driver, SHADERS, variant_source

ROOT = Path(__file__).resolve().parents[1]


def run():
    driver = Driver()
    renderer = Renderer(driver, 480, 270)
    baseline = zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.3-before-end-sky-fix.zip')
    stages, programs, checks = [], [], []
    f = driver.function
    enable = f('glEnable', None, ct.c_uint)
    blend = f('glBlendFuncSeparate', None, ct.c_uint, ct.c_uint, ct.c_uint, ct.c_uint)
    uniform4i = f('glUniform4i', None, ct.c_int, ct.c_int, ct.c_int, ct.c_int, ct.c_int)
    matrix_mode = f('glMatrixMode', None, ct.c_uint)
    load_matrix = f('glLoadMatrixf', None, ct.c_void_p)
    vertex = f('glVertex3f', None, ct.c_float, ct.c_float, ct.c_float)
    color = f('glColor4f', None, ct.c_float, ct.c_float, ct.c_float, ct.c_float)

    def old(name):
        source = baseline.read('shaders/' + name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda m: old(m[1].lstrip('/')), source, flags=re.M)

    def program(name, previous=False, mode=0):
        pair = []
        for suffix in ['vsh', 'fsh']:
            source = (old(name + '.' + suffix) if previous else
                      variant_source(SHADERS / (name + '.' + suffix), {'XON_RENDER_MODE': mode}))
            if previous:
                source = source.replace('#version 330 compatibility',
                                        '#version 330 compatibility\n#define MC_RENDER_STAGE_SUNSET 2\n#define MC_RENDER_STAGE_STARS 6', 1)
            handle, warning = driver.compile(source, '.' + suffix, name)
            assert not warning, warning
            stages.append(handle)
            pair.append(handle)
        selected, warning = driver.link(*pair, name)
        assert not warning, warning
        programs.append(selected)
        return selected

    def draw(selected, backdrop, destination=771, flash=False, intensity=1,
             direction=(-.35046, .42055, .83609), medium=0, rain=0, blind=0):
        renderer.texture(11, backdrop)
        renderer.setup(selected)
        renderer.uniform1i(renderer.location('xonBlackHoleLUT'), 10)
        renderer.uniform1i(renderer.location('renderStage'), 1)
        renderer.uniform1i(renderer.location('isEyeInWater'), medium)
        uniform4i(renderer.location('blendFunc'), 770, destination, 1, 0 if destination == 1 else 771)
        for name, value in [('alphaTestRef', 0), ('far', 1024), ('rainStrength', rain),
                            ('blindness', blind)]:
            renderer.uniform1f(renderer.location(name), value)
        renderer.uniform3f(renderer.location('sunPosition'), 30, 70, 20)
        forward = np.asarray(direction, float)
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, [0, 1, 0])
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        model = np.eye(4, dtype=np.float32)
        model[:3, :3] = np.array([right, up, -forward])
        projection = np.array([[1.0, 0, 0, 0], [0, 16 / 9, 0, 0],
                               [0, 0, -1.0001, -.1], [0, 0, -1, 0]], np.float32)
        for mode, matrix in [(0x1701, projection), (0x1700, model)]:
            matrix_mode(mode)
            data = np.ascontiguousarray(matrix.T)
            load_matrix(data.ctypes.data)
        for name, matrix in [('gbufferModelViewInverse', np.linalg.inv(model)),
                              ('gbufferModelView', model), ('gbufferProjection', projection),
                              ('gbufferProjectionInverse', np.linalg.inv(projection))]:
            data = np.ascontiguousarray(matrix.T, dtype=np.float32)
            renderer.uniform_matrix(renderer.location(name), 1, 0, data.ctypes.data)
        renderer.viewport(0, 0, renderer.width, renderer.height)
        enable(0x0BE2)
        blend(770, destination, 1, 0 if destination == 1 else 771)
        color(intensity, intensity, intensity, intensity)
        renderer.begin(0x0007)
        if flash:
            for u, v in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                point = model[:3, :3].T @ np.array([(u - .5) * 90, (v - .5) * 60, -100])
                renderer.tex_coord(u, v)
                vertex(*point)
        else:
            for axis in range(3):
                for sign in [-1, 1]:
                    for u, v in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                        point = np.zeros(3)
                        point[axis] = sign * 100
                        point[(axis + 1) % 3] = (u * 2 - 1) * 100
                        point[(axis + 2) % 3] = (v * 2 - 1) * 100
                        renderer.tex_coord(u * 16, v * 16)
                        vertex(*point)
        renderer.end()
        output = np.empty_like(backdrop)
        renderer.read_pixels(0, 0, renderer.width, renderer.height, 0x1908, 0x1406, output.ctypes.data)
        renderer.disable(0x0BE2)
        assert renderer.get_error() == 0 and np.isfinite(output).all()
        return output

    try:
        for unit, name in [(5, 'xon-noise.png'), (10, 'xon-black-hole.png')]:
            renderer.texture(unit, np.asarray(Image.open(SHADERS / 'textures' / name).convert('RGBA'), np.float32) / 255)
        renderer.active_texture(0x84C5)
        for axis in [0x2802, 0x2803]:
            renderer.tex_parameter(0x0DE1, axis, 0x2901)
        uv = np.linspace(-1, 1, 64)
        x, y = np.meshgrid(uv, uv)
        alpha = np.clip(1 - (x * x + y * y) * 2, 0, 1)
        texture = np.ones((64, 64, 4), np.float32)
        texture[..., :3] = [.7, .4, .85]
        texture[..., 3] = alpha
        renderer.texture(8, texture)
        dark = np.zeros((270, 480, 4), np.float32)
        dark[..., 3] = 1
        layered = dark.copy()
        layered[135:, :, :3] = [.06, .04, .08]
        before = program('world1/gbuffers_skytextured', previous=True)
        after = program('world1/gbuffers_skytextured')
        reference = draw(after, dark)
        bad = draw(before, layered, destination=1)
        good = draw(after, layered)
        error = float(np.max(np.abs(good - reference)))
        old_error = float(np.max(np.abs(bad[..., :3] - reference[..., :3])))
        assert old_error > .07 and error < .000001, (old_error, error)
        checks.append({'case': 'native cube blend removes reproduced upper-half veil',
                       'old_maximum_error': old_error, 'fixed_maximum_error': error})
        basic = program('world1/gbuffers_skybasic')
        assert np.max(np.abs(draw(basic, dark) - reference)) < .000001
        checks.append({'case': 'production basic and textured End backgrounds agree'})
        for direction in [(0, .8, -1), (.885, .46, .05), (0, -.4, -1)]:
            a, b = draw(after, dark, direction=direction), draw(after, layered, direction=direction)
            assert np.max(np.abs(a - b)) < .000001
        checks.append({'case': 'six-face cube overwrites underlying haze through horizon and rotated views'})
        bad = draw(before, reference, destination=1, flash=True, intensity=0)
        old_error = float(np.max(np.abs(bad[..., :3] - reference[..., :3])))
        assert old_error > .01
        checks.append({'case': 'pre-fix zero-intensity flash reproduces a bright galaxy rectangle',
                       'maximum_error': old_error})
        for intensity in [0, .2, .8, 1]:
            actual = draw(after, reference, destination=1, flash=True, intensity=intensity)
            delta = actual[..., :3] - reference[..., :3]
            assert np.max(np.abs(delta[:60])) < .000001
            assert np.max(np.abs(delta[110:115, 137:142])) < .000001
            if intensity == 0:
                assert np.max(np.abs(delta)) < .000001
            else:
                assert np.max(delta) > .0001
            checks.append({'case': 'flash keeps transparent corners and obeys intensity', 'intensity': intensity})
        for medium, blind in [(2, 0), (3, 0), (0, 1)]:
            actual = draw(after, reference, destination=1, flash=True, intensity=1, medium=medium, blind=blind)
            assert np.max(np.abs(actual[..., :3] - reference[..., :3])) < .000001
        checks.append({'case': 'flash respects lava/snow blindness gates'})
        old_sun, new_sun = program('gbuffers_skytextured', previous=True), program('gbuffers_skytextured')
        for medium in range(4):
            for rain in [0, 1]:
                a = draw(old_sun, layered, destination=1, flash=True, medium=medium, rain=rain)
                b = draw(new_sun, layered, destination=1, flash=True, medium=medium, rain=rain)
                assert np.array_equal(a, b)
        checks.append({'case': 'native Overworld celestial overlay preserves previous pixels through weather/media'})
        for mode, scale in [(1, .85), (2, .75)]:
            selected = program('world1/gbuffers_skytextured', mode=mode)
            a = draw(selected, layered)
            h = int(np.count_nonzero(np.arange(270) + .5 < 270 * scale))
            w = int(np.count_nonzero(np.arange(480) + .5 < 480 * scale))
            assert np.array_equal(a[h:], layered[h:]) and np.array_equal(a[:, w:], layered[:, w:])
            b = draw(selected, dark)
            assert np.max(np.abs(a[:h, :w] - b[:h, :w])) < .000001
        checks.append({'case': 'Boost modes retain inactive-region guards and opaque background coverage'})
        properties = (SHADERS / 'shaders.properties').read_text()
        assert not re.search(r'^blend\.(?:world1/)?gbuffers_skytextured=', properties, re.M)
        checks.append({'case': 'native End cube and celestial blend states are not overridden'})
        report = {'passed': True, 'checks': checks,
                  'scope': 'Production sky vertex/fragment programs, synthetic six-face cube and masked flash, real OpenGL blending. Not a live Minecraft reload.'}
        (ROOT / 'validation-end-sky-pipeline.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        baseline.close()
        for selected in programs:
            driver.delete_program(selected)
        for stage in stages:
            driver.delete_shader(stage)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    run()
