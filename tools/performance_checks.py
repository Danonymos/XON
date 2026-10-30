"""GPU timer-query microbenchmarks; deliberately not a Minecraft FPS estimate."""

from pathlib import Path
import ctypes as ct
import json
import re
import zipfile
import numpy as np
from PIL import Image

from validate import Driver, SHADERS, variant_source
from render_checks import Renderer

ROOT = Path(__file__).resolve().parents[1]


def run():
    driver = Driver()
    renderer = Renderer(driver, 1920, 1080)
    stages, programs = [], []
    output = {'kind': 'synthetic GPU pass timing, concurrent desktop load; not Minecraft FPS',
              'resolution': [1920, 1080], 'samples_per_pass': 32, 'passes': {}}
    try:
        height, width = renderer.height, renderer.width
        yy, xx = np.indices((height, width))
        pattern = ((xx // 16 + yy // 16) % 2).astype(bool)
        scene = np.ones((height, width, 4), dtype=np.float32)
        scene[..., :3] = np.where(pattern[..., None], [.16, .36, .22], [.8, 1.6, 2.5])
        renderer.texture(0, scene)
        renderer.active_texture(0x84C0)
        renderer.tex_image(0x0DE1, 0, 0x881A, width, height, 0, 0x1908, 0x1406, scene.ctypes.data)
        renderer.texture(1, np.zeros((height, width), dtype=np.float32))
        renderer.texture(2, np.where(pattern, .99, .9995))
        renderer.texture(3, np.full((height // 2, width // 2, 4), [.02, .04, .03, .001], dtype=np.float32))
        renderer.texture(4, np.asarray(Image.open(SHADERS / 'textures' / 'xon-grade.png').convert('RGBA')) / 255)
        depth = np.ones((1024, 1024), dtype=np.float32)
        renderer.active_texture(0x84C7)
        renderer.bind_texture(0x0DE1, renderer.textures[7])
        renderer.tex_image(0x0DE1, 0, 0x8CAC, 1024, 1024, 0, 0x1902, 0x1406, depth.ctypes.data)
        renderer.tex_parameter(0x0DE1, 0x884C, 0x884E)
        renderer.tex_parameter(0x0DE1, 0x884D, 0x0203)

        def program(sources, name):
            pair = []
            for source, stage in zip(sources, ['.vsh', '.fsh']):
                shader, warning = driver.compile(source, stage, name)
                if warning:
                    raise RuntimeError(warning)
                stages.append(shader)
                pair.append(shader)
            result, warning = driver.link(*pair, name)
            if warning:
                raise RuntimeError(warning)
            programs.append(result)
            return result

        with zipfile.ZipFile(ROOT.parent / 'XON-Shader-v0.1.0-source.zip') as baseline:
            def old_source(name):
                source = baseline.read(name).decode('utf-8')
                return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                              lambda match: old_source('shaders/' + match[1].lstrip('/')), source, flags=re.M)
            old_final = program([old_source('shaders/final.' + stage) for stage in ['vsh', 'fsh']], '0.1 baseline final')
        new_programs = {name: program([variant_source(SHADERS / f'{name}.{stage}', {}) for stage in ['vsh', 'fsh']], name)
                        for name in ['final', 'deferred', 'composite', 'composite1']}

        f = driver.function
        gen_queries = f('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin_query = f('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end_query = f('glEndQuery', None, ct.c_uint)
        query_result = f('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete_queries = f('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        uniform2i = f('glUniform2i', None, ct.c_int, ct.c_int, ct.c_int)

        def quad():
            renderer.begin(0x0007)
            for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                renderer.tex_coord(x, y)
                renderer.vertex(x, y)
            renderer.end()

        def measure(name, selected, half=False, moving=False):
            renderer.setup(selected)
            renderer.uniform3f(renderer.location('sunPosition'), 0, 14, -99)
            uniform2i(renderer.location('eyeBrightnessSmooth'), 240, 240)
            if moving:
                renderer.uniform3f(renderer.location('previousCameraPosition'), -.06, 0, 0)
            for uniform, value in [('shadowModelView', np.eye(4)), ('shadowProjection', np.diag([.0125, .0125, .0125, 1]))]:
                data = np.ascontiguousarray(value.T, dtype=np.float32)
                renderer.uniform_matrix(renderer.location(uniform), 1, 0, data.ctypes.data)
            draw_width, draw_height = (width // 2, height // 2) if half else (width, height)
            renderer.active_texture(0x84CB)
            renderer.bind_texture(0x0DE1, renderer.textures[11])
            renderer.tex_image(0x0DE1, 0, 0x881A, draw_width, draw_height, 0, 0x1908, 0x1406, None)
            renderer.viewport(0, 0, draw_width, draw_height)
            for _ in range(12):
                quad()
            queries = (ct.c_uint * 32)()
            gen_queries(32, queries)
            for query in queries:
                begin_query(0x88BF, query)
                quad()
                end_query(0x88BF)
            samples = []
            for query in queries:
                value = ct.c_uint64()
                query_result(query, 0x8866, ct.byref(value))
                samples.append(value.value / 1e6)
            delete_queries(32, queries)
            error = renderer.get_error()
            if error:
                raise RuntimeError(f'{name}: OpenGL error {error:#x}')
            output['passes'][name] = {'median_gpu_ms': round(float(np.median(samples)), 4),
                                      'p95_gpu_ms': round(float(np.percentile(samples, 95)), 4)}

        measure('0.1 final, stationary', old_final)
        measure('1.0 final, stationary, AA/LUT/soft-effects enabled', new_programs['final'])
        measure('0.1 final, camera motion', old_final, moving=True)
        measure('1.0 final, camera motion, AA/LUT/soft-effects enabled', new_programs['final'], moving=True)
        measure('1.0 opaque refraction copy, half resolution', new_programs['deferred'], half=True)
        measure('1.0 bloom and four-sample cone-culled rays, half resolution', new_programs['composite'], half=True)
        measure('1.0 effect softening, half resolution', new_programs['composite1'], half=True)
        output['limitations'] = ['Excludes shadow-world geometry rendering, main geometry lighting, procedural sky and game CPU work.',
                                  'Synthetic texture/depth inputs and RGBA16F targets; concurrent GPU clocks/load affect results.',
                                  'Per-pass medians are not an end-to-end frame time or evidence of preserved 130 FPS.']
    finally:
        for selected in programs:
            driver.delete_program(selected)
        for shader in stages:
            driver.delete_shader(shader)
        renderer.close()
        driver.close()
    (ROOT / 'validation-performance.json').write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    run()
