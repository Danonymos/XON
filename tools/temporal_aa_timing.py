"""Measure AA pass cost with valid history; this is not a Minecraft FPS benchmark."""
import argparse
import ctypes as ct
import json
import re
import zipfile

import numpy as np

from temporal_aa_checks import ROOT, OPTIONS, TemporalRenderer
from validate import Driver, SHADERS, variant_source


def run(width, height):
    driver = Driver()
    renderer = TemporalRenderer(driver, width, height)
    stages, programs = [], []
    try:
        yy, xx = np.indices((height, width))
        pattern = (xx // 8 + yy // 8) % 2 == 0
        scene = np.ones((height, width, 4), dtype=np.float32)
        scene[..., :3] = np.where(pattern[..., None], [.025, .03, .045], [.9, .8, .65])
        depth = np.full((height, width), .98, dtype=np.float32)
        history = scene.copy()
        history[..., 3] = .05 * 1024 / (1024 - .98 * (1024 - .05))
        history[0, 0] = [width % 1024, height % 1024, width // 1024 + height // 1024 * 32, -120]
        renderer.texture(0, scene)
        renderer.tex_image(0x0DE1, 0, 0x881A, width, height, 0, 0x1908, 0x1406, scene.ctypes.data)
        renderer.texture(1, np.zeros((height, width), dtype=np.float32))
        renderer.texture(2, depth)
        renderer.tex_parameter(0x0DE1, 0x2801, 0x2600)
        renderer.tex_parameter(0x0DE1, 0x2800, 0x2600)
        renderer.texture(6, history)
        renderer.tex_image(0x0DE1, 0, 0x881A, width, height, 0, 0x1908, 0x1406, history.ctypes.data)
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x881A, width, height, 0, 0x1908, 0x1406, None)

        with zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.5.zip') as archive:
            def saved(name):
                text = archive.read('shaders/' + name).decode()
                return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                              lambda m: saved(m[1].lstrip('/')), text, flags=re.M)
            selections = {}
            for name, entrypoint, options in [
                ('v1.5 final', 'final', None), ('v1.6 temporal resolve', 'composite2', {}),
                ('v1.6 temporal final', 'final', {}), ('v1.6 fast final', 'final', {'XON_AA': 1})]:
                pair = []
                for suffix in ['vsh', 'fsh']:
                    if options is None:
                        source = saved(entrypoint + '.' + suffix)
                        for option in OPTIONS:
                            source = re.sub(rf'^(?://)?#define {option}(?:[^\n]*)$', '#undef ' + option, source, flags=re.M)
                    else:
                        source = variant_source(SHADERS / (entrypoint + '.' + suffix), dict(OPTIONS, **options))
                    shader, warning = driver.compile(source, '.' + suffix, name)
                    assert not warning, warning
                    stages.append(shader)
                    pair.append(shader)
                program, warning = driver.link(*pair, name)
                assert not warning, warning
                programs.append(program)
                selections[name] = program

        f = driver.function
        gen = f('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin = f('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end = f('glEndQuery', None, ct.c_uint)
        result = f('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete = f('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        renderer.viewport(0, 0, width, height)

        def quad():
            renderer.begin(0x0007)
            for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                renderer.tex_coord(x, y)
                renderer.vertex(x, y)
            renderer.end()

        timings = {}
        for motion in [False, True]:
            for name, program in selections.items():
                renderer.setup(program)
                if motion:
                    renderer.uniform3f(renderer.location('previousCameraPosition'), -.003, -.002, 0)
                count = 2 if 'resolve' in name else 1
                renderer.draw_buffers(count, (ct.c_uint * count)(*[0x8CE0 + i for i in range(count)]))
                for _ in range(12):
                    quad()
                queries = (ct.c_uint * 32)()
                gen(32, queries)
                for query in queries:
                    begin(0x88BF, query)
                    quad()
                    end(0x88BF)
                samples = []
                for query in queries:
                    elapsed = ct.c_uint64()
                    result(query, 0x8866, ct.byref(elapsed))
                    samples.append(elapsed.value / 1e6)
                delete(32, queries)
                assert renderer.get_error() == 0
                timings[name + (' moving' if motion else ' stationary')] = {
                    'median_ms': float(np.median(samples)), 'p95_ms': float(np.percentile(samples, 95))}
        report = {'scope': 'Synthetic GPU pass timing with valid RGBA16F history and targets; excludes game/geometry costs',
                  'driver': driver.get_string(0x1F01).decode(), 'resolution': [width, height],
                  'samples_per_pass': 32, 'passes': timings}
        (ROOT / 'validation-temporal-aa-timing.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        for program in programs:
            driver.delete_program(program)
        for shader in stages:
            driver.delete_shader(shader)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    args = parser.parse_args()
    run(args.width, args.height)
