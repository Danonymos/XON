"""Compare real terrain fragments against the preserved 1.1 pack on the GPU."""
import ctypes as ct
import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from validate import Driver, SHADERS, expand, variant_source
from render_checks import Renderer

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT.parent / 'XON-Shader-v1.1-before-distant-shading.zip'
VERTEX = '''#version 330 compatibility
out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels; out vec4 xonVertexColor;
out vec3 xonViewPosition, xonPlayerPosition, xonWorldNormal; flat out float xonMaterial;
uniform float testStart, testEnd, testSky, testBlock, testMaterial;
uniform vec3 testNormal;
void main() {
    vec2 uv=gl_MultiTexCoord0.xy;
    xonTexCoord=uv; xonAtlasBounds=vec4(0); xonLightLevels=vec2(testBlock,testSky);
    xonVertexColor=vec4(1); xonWorldNormal=testNormal; xonMaterial=testMaterial;
    xonPlayerPosition=vec3(mix(testStart,testEnd,uv.x),-2,-4);
    xonViewPosition=xonPlayerPosition; gl_Position=vec4(gl_Vertex.xy*2-1,0,1);
}'''
VISIBILITY = '''
in vec2 xonUV; out vec4 result;
uniform float testStart, testEnd, testSky, testMaterial;
uniform vec3 testNormal;
void main() {
    vec3 p=vec3(mix(testStart,testEnd,xonUV.x),-2,-4)-cameraPosition;
    float foliage=float(testMaterial==10003.0);
    float facing=max(dot(testNormal,xonKeyDirection()),0.0);
    facing=mix(facing,facing*.48+.52,foliage);
    result=vec4(vec3(xonShadowVisibility(p,testNormal,facing,testSky,foliage)),1);
}'''


def run():
    driver = Driver()
    renderer = Renderer(driver, 960, 540)
    shaders, programs, checks, pictures = [], [], [], []
    with zipfile.ZipFile(BASELINE) as archive:
        previous = archive.read('shaders/lib/shadows.glsl').decode()
    current = expand(SHADERS / 'lib/shadows.glsl')

    def compile_pair(vertex, fragment):
        pair = []
        for text, kind in [(vertex, '.vsh'), (fragment, '.fsh')]:
            shader, warning = driver.compile(text, kind, 'distant foliage')
            assert not warning, warning
            shaders.append(shader)
            pair.append(shader)
        program, warning = driver.link(*pair, 'distant foliage')
        assert not warning, warning
        programs.append(program)
        return program

    def terrain_pair(shadows=True):
        fragment = variant_source(SHADERS / 'gbuffers_terrain.fsh', {
            'XON_COLORED_EMISSIVE_LIGHTING': False, 'XON_SHADOWS': shadows,
            'XON_CLOUD_STYLE': 0})
        assert current in fragment
        return [compile_pair(VERTEX, fragment.replace(current, value)) for value in [previous, current]]

    def setup(program, start=160, end=None, normal=(1, 0, 0), material=10003,
              sky=1, block=0, night=False, camera=(0, 0, 0), map_radius=512):
        renderer.setup(program)
        for name, value in [('testStart', start), ('testEnd', start if end is None else end),
                            ('testSky', sky), ('testBlock', block), ('testMaterial', material),
                            ('alphaTestRef', .1), ('far', 512)]:
            renderer.uniform1f(renderer.location(name), value)
        renderer.uniform3f(renderer.location('testNormal'), *normal)
        renderer.uniform3f(renderer.location('sunPosition'), *((-50, -80, -20) if night else (50, 80, 20)))
        renderer.uniform3f(renderer.location('shadowLightPosition'), 50, 80, 20)
        renderer.uniform3f(renderer.location('cameraPosition'), *camera)
        for name, value in [('gbufferModelView', np.eye(4)), ('shadowModelView', np.eye(4)),
                            ('shadowModelViewInverse', np.eye(4)),
                            ('shadowProjection', np.diag([1/map_radius, 1/map_radius, -1/512, 1]))]:
            data = np.ascontiguousarray(value.T, dtype=np.float32)
            renderer.uniform_matrix(renderer.location(name), 1, 0, data.ctypes.data)

    def images(pair, **options):
        result = []
        for program in pair:
            setup(program, **options)
            result.append(renderer.draw(raw=True))
        return result

    def equal(label, pair, **options):
        values = images(pair, **options)
        error = float(np.max(np.abs(values[0] - values[1])))
        assert error < .000001, (label, error)
        checks.append({'case': label, 'maximum_error': error})

    def benchmark(pair, **options):
        f = driver.function
        handles = (ct.c_uint * 64)()
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

        gen(64, handles)
        try:
            for program in pair:
                setup(program, **options)
                for _ in range(12):
                    quad()
            for index in range(32):
                for version in ([0, 1] if index % 2 == 0 else [1, 0]):
                    setup(pair[version], **options)
                    begin(0x88BF, handles[index * 2 + version])
                    for _ in range(4):
                        quad()
                    end(0x88BF)
            samples = [[], []]
            for index in range(32):
                for version in [0, 1]:
                    value = ct.c_uint64()
                    read(handles[index * 2 + version], 0x8866, ct.byref(value))
                    samples[version].append(value.value / 4e6)
            return [{'median_ms': float(np.median(v)), 'p95_ms': float(np.percentile(v, 95))} for v in samples]
        finally:
            delete(64, handles)

    try:
        renderer.texture(8, np.full((2, 2, 4), [.20, .40, .10, 1], dtype=np.float32))
        renderer.active_texture(0x84C7)
        renderer.bind_texture(0x0DE1, renderer.textures[7])
        data = np.ones((1024, 1024), dtype=np.float32)
        renderer.tex_image(0x0DE1, 0, 0x8CAC, 1024, 1024, 0, 0x1902, 0x1406, data.ctypes.data)
        renderer.tex_parameter(0x0DE1, 0x884C, 0x884E)
        renderer.tex_parameter(0x0DE1, 0x884D, 0x0203)
        pair = terrain_pair()
        for distance in [8, 32, 64]:
            equal(f'near leaves unchanged at {distance} blocks', pair, start=distance)
        renderer.active_texture(0x84C7)
        renderer.bind_texture(0x0DE1, renderer.textures[7])
        data.fill(0)
        renderer.tex_image(0x0DE1, 0, 0x8CAC, 1024, 1024, 0, 0x1902, 0x1406, data.ctypes.data)
        for distance in [8, 32, 64]:
            equal(f'occluded near leaves unchanged at {distance} blocks', pair, start=distance)
        renderer.active_texture(0x84C7)
        renderer.bind_texture(0x0DE1, renderer.textures[7])
        data.fill(1)
        renderer.tex_image(0x0DE1, 0, 0x8CAC, 1024, 1024, 0, 0x1902, 0x1406, data.ctypes.data)
        for normal in [(0, 1, 0), (1, 0, 0), (-1, 0, 0)]:
            equal(f'opaque terrain unchanged, normal={normal}', pair, start=0, end=240,
                  material=0, normal=normal)
        equal('indoor lamp unchanged', pair, sky=0, block=.85)
        equal('unlit cave unchanged', pair, sky=0)
        equal('shadows-disabled preset unchanged', terrain_pair(False), start=0, end=240)

        for night in [False, True]:
            means = []
            for normal in [(0, 1, 0), (1, 0, 0), (-1, 0, 0)]:
                values = images(pair, night=night, normal=normal)
                luma = [float(np.mean(v[..., :3] @ [.2126, .7152, .0722])) for v in values]
                assert .65 < luma[1] / luma[0] < 1, (night, normal, luma)
                means.append(luma)
                checks.append({'case': f'distant foliage retains readable directional shade; night={night}, normal={normal}',
                               'linear_luma_before_current': luma})
                display = [np.uint8(np.clip(v[..., :3] ** (1/2.2), 0, 1) * 255) for v in values]
                pictures.append((f'{"Moon" if night else "Sun"} / face {normal}', display))
            contrast = [means[1][i] / means[2][i] for i in [0, 1]]
            assert contrast[1] > contrast[0] * 1.015, contrast
            checks.append({'case': f'distant sun-facing/shade-facing contrast improves; night={night}',
                           'contrast_before_current': contrast})

        fragment = '#version 330 compatibility\n#define XON_DIMENSION 0\n'
        fragment += '\n'.join(expand(SHADERS / f'lib/{name}.glsl') for name in ['settings', 'uniforms', 'math', 'shadows'])
        visibility_pair = [compile_pair(expand(SHADERS / 'final.vsh'), fragment.replace(current, value) + VISIBILITY)
                           for value in [previous, current]]
        for map_radius in [96, 512]:
            values = images(visibility_pair, start=64, end=108, map_radius=map_radius)
            step = float(np.max(np.abs(np.diff(values[1][renderer.height // 2, :, 0]))))
            assert step < .004, step
            checks.append({'case': f'range/frustum blend has no hard visibility step; map radius={map_radius}',
                           'largest_0_046_block_step': step})
        values = images(visibility_pair, start=120, end=400)
        flatness = float(np.ptp(values[1][..., 0]))
        assert flatness < .000001, flatness
        checks.append({'case': 'far fallback has no radial rings', 'visibility_range': flatness})
        setup(visibility_pair[1])
        reference = renderer.draw(raw=True)
        for camera in [(.49, 0, .49), (12, 0, 12), (-20, 8, -20)]:
            setup(visibility_pair[1], camera=camera)
            error = float(np.max(np.abs(renderer.draw(raw=True) - reference)))
            assert error < .000001, (camera, error)
            checks.append({'case': f'distant fallback stable under camera movement {camera}', 'maximum_error': error})
        for sky in [0, .5, .7, .85, 1]:
            values = images(visibility_pair, sky=sky)
            assert np.min(values[1]) >= 0 and np.max(values[1]) <= 1
            assert np.max(values[1][..., :3] - values[0][..., :3]) <= .000001
            checks.append({'case': f'fallback bounded and never adds light; skylight={sky}',
                           'visibility': float(values[1][0, 0, 0])})
        benchmarks = {label: benchmark(pair, **options) for label, options in [
            ('near foliage', {'start': 32}), ('distant foliage', {'start': 160}),
            ('mixed near/far foliage', {'start': 0, 'end': 240}),
            ('opaque terrain', {'start': 0, 'end': 240, 'material': 0})]}
        canvas = Image.new('RGB', (660, len(pictures) * 62 + 30), '#161a20')
        draw = ImageDraw.Draw(canvas)
        draw.text((230, 8), 'Before / Updated 1.1 (synthetic leaf faces)', fill='white')
        for index, (label, display) in enumerate(pictures):
            y = 30 + index * 62
            draw.text((8, y + 16), label, fill='white')
            for version in [0, 1]:
                canvas.paste(Image.fromarray(display[version]).resize((210, 54)), (230 + version * 215, y))
        canvas.save(ROOT / 'validation-distant-shading.png')
        report = {'passed': True, 'kind': 'real terrain fragment checks and interleaved GPU queries; not Minecraft FPS',
                  'baseline_sha256': hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
                  'resolution': [renderer.width, renderer.height], 'checks': checks, 'benchmarks': benchmarks}
        (ROOT / 'validation-distant-shading.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        for program in programs:
            driver.delete_program(program)
        for shader in shaders:
            driver.delete_shader(shader)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    run()
