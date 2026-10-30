"""Rasterize block-sized terrain into the real shadow map and inspect self-shadow rings."""
import ctypes as ct
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from validate import Driver, SHADERS, expand, variant_source
from render_checks import Renderer
from scene_checks import look_at

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT.parent / 'XON-Shader-v1.0.6-before-ring-fix.zip'
BODY = '''
in vec2 xonUV; out vec4 result;
uniform float testHeight, testSpan;
uniform vec3 testNormal, testSlope;
void main() {
    vec2 xz=(xonUV-.5)*testSpan;
    vec3 p=vec3(xz.x,-testHeight+dot(xz,testSlope.xz),xz.y);
    float facing=max(dot(testNormal,xonKeyDirection()),0.0);
    result=vec4(vec3(xonShadowVisibility(p,testNormal,facing,1.0,0.0)),1.0);
}
'''


def run():
    driver = Driver()
    renderer = Renderer(driver, 512, 512)
    archive = zipfile.ZipFile(BASELINE)
    stages, programs, checks = [], [], []
    shadow_fbo = ct.c_uint()
    f = driver.function
    mode = f('glMatrixMode', None, ct.c_uint)
    load = f('glLoadMatrixf', None, ct.c_void_p)
    enable = f('glEnable', None, ct.c_uint)
    clear = f('glClear', None, ct.c_uint)
    clear_depth = f('glClearDepth', None, ct.c_double)
    draw_buffer = f('glDrawBuffer', None, ct.c_uint)
    read_buffer = f('glReadBuffer', None, ct.c_uint)
    vertex_pointer = f('glVertexPointer', None, ct.c_int, ct.c_uint, ct.c_int, ct.c_void_p)
    enable_client = f('glEnableClientState', None, ct.c_uint)
    disable_client = f('glDisableClientState', None, ct.c_uint)
    draw_arrays = f('glDrawArrays', None, ct.c_uint, ct.c_int, ct.c_int)

    def old_source(name):
        source = archive.read('shaders/' + name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda match: old_source(match[1].lstrip('/')), source, flags=re.M)

    def compile_program(vertex, fragment):
        pair = []
        for source, kind in [(vertex, '.vsh'), (fragment, '.fsh')]:
            stage, warning = driver.compile(source, kind, 'terrain self-shadow test')
            assert not warning, warning
            stages.append(stage)
            pair.append(stage)
        handle, warning = driver.link(*pair, 'terrain self-shadow test')
        assert not warning, warning
        programs.append(handle)
        return handle

    def matrix(name, value):
        array = np.ascontiguousarray(value.T, dtype=np.float32)
        renderer.uniform_matrix(renderer.location(name), 1, 0, array.ctypes.data)

    def receiver(old, smooth, resolution):
        source = '#version 330 compatibility\n#define XON_DIMENSION 0\n'
        for name in ['settings', 'uniforms', 'math', 'shadows']:
            source += '\n' + (old_source(f'lib/{name}.glsl') if old else expand(SHADERS / f'lib/{name}.glsl'))
        source = source.replace('const int shadowMapResolution = 1024;', f'const int shadowMapResolution = {resolution};')
        if smooth:
            source = source.replace('//#define XON_SMOOTH_SHADOW_LOD', '#define XON_SMOOTH_SHADOW_LOD')
        return compile_program(expand(SHADERS / 'final.vsh'), source + '\n' + BODY)

    coordinates = np.arange(-144, 144, dtype=np.float32)
    xx, zz = np.meshgrid(coordinates, coordinates)
    centers = np.stack([xx.ravel(), np.zeros(xx.size), zz.ravel()], axis=-1)
    corners = np.array([[0, 0, 0], [0, 0, 1], [1, 0, 1], [1, 0, 0]], dtype=np.float32)
    terrain = np.ascontiguousarray((centers[:, None, :] + corners).reshape(-1, 3), dtype=np.float32)
    projection = np.diag([1 / 96, 1 / 96, -1 / 256, 1])
    span = 196
    axis = (np.arange(renderer.width) + .5) / renderer.width * span - span / 2
    gx, gz = np.meshgrid(axis, axis)
    radius = np.sqrt(gx * gx + gz * gz)
    pictures = []
    try:
        caster = compile_program(variant_source(SHADERS / 'shadow.vsh', {'XON_COLORED_EMISSIVE_LIGHTING': False}),
                                 variant_source(SHADERS / 'shadow.fsh', {'XON_COLORED_EMISSIVE_LIGHTING': False}))
        renderer.texture(8, np.ones((2, 2, 4), dtype=np.float32))
        renderer.gen_framebuffers(1, ct.byref(shadow_fbo))
        for resolution in [512, 1024, 1536, 2048]:
            receivers = [(old, smooth, receiver(old, smooth, resolution)) for old in [True, False] for smooth in [False, True]]
            for sun in [(0.45, 0.35, 0.82), (0.3, 0.8, 0.5), (0.95, 0.12, 0.28)]:
                sun = np.array(sun, dtype=float)
                sun /= np.linalg.norm(sun)
                view = look_at([0, 0, 0], -sun)
                for height in [4, 32, 80]:
                    for translation, slope in [((0, 0), (0, 0)), ((0, 0), (.08, -.05)),
                                               ((.37, .61), (-.08, .05)), ((.37, .61), (0, 0))]:
                        normal = np.array([-slope[0], 1, -slope[1]], dtype=float)
                        normal /= np.linalg.norm(normal)
                        actual_view = view.copy()
                        actual_view[:3, 3] = view[:3, :3] @ np.array([-translation[0], 0, -translation[1]])
                        renderer.active_texture(0x84C7)
                        renderer.bind_texture(0x0DE1, renderer.textures[7])
                        renderer.tex_image(0x0DE1, 0, 0x8CAC, resolution, resolution, 0, 0x1902, 0x1406, None)
                        renderer.tex_parameter(0x0DE1, 0x884C, 0x884E)
                        renderer.tex_parameter(0x0DE1, 0x884D, 0x0203)
                        renderer.bind_framebuffer(0x8D40, shadow_fbo)
                        renderer.attach_texture(0x8D40, 0x8D00, 0x0DE1, renderer.textures[7], 0)
                        draw_buffer(0)
                        read_buffer(0)
                        assert renderer.check_framebuffer(0x8D40) == 0x8CD5
                        renderer.setup(caster)
                        for selected_mode, value in [(0x1700, actual_view), (0x1701, projection)]:
                            mode(selected_mode)
                            array = np.ascontiguousarray(value.T, dtype=np.float32)
                            load(array.ctypes.data)
                        renderer.viewport(0, 0, resolution, resolution)
                        enable(0x0B71)
                        clear_depth(1)
                        clear(0x00000100)
                        terrain[:, 1] = -height + terrain[:, 0] * slope[0] + terrain[:, 2] * slope[1]
                        enable_client(0x8074)
                        vertex_pointer(3, 0x1406, 0, terrain.ctypes.data)
                        draw_arrays(0x0007, 0, len(terrain))
                        disable_client(0x8074)
                        renderer.disable(0x0B71)
                        renderer.bind_framebuffer(0x8D40, renderer.framebuffer)
                        draw_buffer(0x8CE0)
                        read_buffer(0x8CE0)
                        images = []
                        for old, smooth, program in receivers:
                            renderer.setup(program)
                            for name, value in [('shadowModelView', actual_view), ('shadowModelViewInverse', np.linalg.inv(actual_view)),
                                                ('shadowProjection', projection)]:
                                matrix(name, value)
                            renderer.uniform3f(renderer.location('shadowLightPosition'), *sun * 100)
                            renderer.uniform3f(renderer.location('testNormal'), *normal)
                            renderer.uniform3f(renderer.location('testSlope'), slope[0], 0, slope[1])
                            renderer.uniform1f(renderer.location('testHeight'), height)
                            renderer.uniform1f(renderer.location('testSpan'), span)
                            pixels = renderer.draw(raw=True)[..., 0]
                            bins = [float(np.mean(pixels[(radius >= r) & (radius < r + 1)])) for r in range(94)]
                            checks.append({'old': old, 'smooth': smooth, 'sun_y': float(sun[1]), 'height': height,
                                           'translation': translation, 'slope': slope, 'resolution': resolution,
                                           'minimum_visibility': float(np.min(pixels)),
                                           'mean_visibility': float(np.mean(pixels[radius < 80])),
                                           'worst_radial_mean': min(bins[:80]),
                                           'largest_radial_band_step': float(np.max(np.abs(np.diff(bins))))})
                            if not old:
                                assert np.min(pixels) >= .9999, checks[-1]
                            images.append(pixels)
                        if resolution == 1024 and height == 32 and translation == (0, 0) and slope == (0, 0):
                            pictures.append(images)
        # The same correction must retain real shadows where a box meets the receiving floor.
        # Keep this fixture inside full map coverage, away from the intentional frustum fade.
        height = 32
        terrain[:, 1] = -height
        box = np.array([
            [[4, 0, -2], [8, 0, -2], [8, 3, -2], [4, 3, -2]],
            [[4, 0, 2], [8, 0, 2], [8, 3, 2], [4, 3, 2]],
            [[4, 0, -2], [4, 0, 2], [4, 3, 2], [4, 3, -2]],
            [[8, 0, -2], [8, 0, 2], [8, 3, 2], [8, 3, -2]],
            [[4, 0, -2], [8, 0, -2], [8, 0, 2], [4, 0, 2]],
            [[4, 3, -2], [8, 3, -2], [8, 3, 2], [4, 3, 2]],
        ], dtype=np.float32).reshape(-1, 3)
        box[:, 1] -= height
        renderer.bind_framebuffer(0x8D40, shadow_fbo)
        draw_buffer(0)
        read_buffer(0)
        renderer.setup(caster)
        renderer.viewport(0, 0, resolution, resolution)
        enable(0x0B71)
        clear(0x00000100)
        enable_client(0x8074)
        vertex_pointer(3, 0x1406, 0, terrain.ctypes.data)
        draw_arrays(0x0007, 0, len(terrain))
        vertex_pointer(3, 0x1406, 0, box.ctypes.data)
        draw_arrays(0x0007, 0, len(box))
        disable_client(0x8074)
        renderer.disable(0x0B71)
        renderer.bind_framebuffer(0x8D40, renderer.framebuffer)
        draw_buffer(0x8CE0)
        read_buffer(0x8CE0)
        points = np.stack([gx, np.full_like(gx, -height), gz], axis=-1)
        a = (np.array([4, -height, -2]) - points) / sun
        b = (np.array([8, 3 - height, 2]) - points) / sun
        expected = np.min(np.maximum(a, b), axis=-1) > np.maximum(np.max(np.minimum(a, b), axis=-1), .001)
        core = expected.copy()
        for dz in [-2, -1, 0, 1, 2]:
            for dx in [-2, -1, 0, 1, 2]:
                core &= np.roll(expected, (dz, dx), axis=(0, 1))
        contact = expected & (gx > 2.5) & (gx < 3.5) & (np.abs(gz) < 1)
        assert np.any(core) and np.any(contact)
        for old, smooth, program in receivers:
            if old:
                continue
            renderer.setup(program)
            for name, value in [('shadowModelView', actual_view), ('shadowModelViewInverse', np.linalg.inv(actual_view)),
                                ('shadowProjection', projection)]:
                matrix(name, value)
            renderer.uniform3f(renderer.location('shadowLightPosition'), *sun * 100)
            renderer.uniform3f(renderer.location('testNormal'), 0, 1, 0)
            renderer.uniform1f(renderer.location('testHeight'), height)
            renderer.uniform1f(renderer.location('testSpan'), span)
            pixels = renderer.draw(raw=True)[..., 0]
            shadow = float(np.mean(pixels[core]))
            at_contact = float(np.mean(pixels[contact]))
            assert shadow < .10 and at_contact < .25, (smooth, shadow, at_contact)
            checks.append({'case': 'real box cast/contact shadow retained', 'smooth': smooth,
                           'shadow_core_visibility': shadow, 'near_contact_visibility': at_contact})
        sheet = Image.new('RGB', (2048, len(pictures) * 540))
        painter = ImageDraw.Draw(sheet)
        for row, images in enumerate(pictures):
            for column, values in enumerate(images):
                grey = np.repeat(np.flipud(values)[..., None], 3, axis=-1)
                sheet.paste(Image.fromarray((np.clip(grey, 0, 1) * 255).astype(np.uint8)), (column * 512, row * 540 + 28))
                painter.text((column * 512 + 8, row * 540 + 8), ['Old / default', 'Old / smooth ON', 'Current / default', 'Current / smooth ON'][column], fill='white')
        sheet.save(ROOT / 'validation-shadow-ring-comparison.png')
        report = {'passed': True, 'kind': 'real rasterized terrain shadow map; synthetic camera and terrain', 'checks': checks}
        (ROOT / 'validation-shadow-rings.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(checks, indent=2))
    finally:
        archive.close()
        renderer.delete_framebuffers(1, ct.byref(shadow_fbo))
        for program in programs:
            driver.delete_program(program)
        for shader in stages:
            driver.delete_shader(shader)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    run()
