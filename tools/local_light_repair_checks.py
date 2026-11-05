"""Reproduce blocked-light fallback, quartz coverage seams and stale-wall history."""
import argparse
import ctypes as ct
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from PIL import Image, ImageDraw

from brightness_checks import display_luma
from lamp_gpu_checks import LampRenderer
from pbr_checks import VERTEX
from validate import Driver, SHADERS, expand

ROOT = Path(__file__).resolve().parents[1]


def run(baseline):
    archive = zipfile.ZipFile(baseline)
    driver = Driver()
    renderer = LampRenderer(driver)
    shaders, programs, checks = [], [], []
    cache = {}

    def source(name, old=False):
        if not old:
            return expand(SHADERS / name)
        if name not in cache:
            value = archive.read('shaders/' + name).decode()
            cache[name] = re.sub(r'^\s*#include\s+"([^"]+)"\s*$', lambda m: source(m[1].lstrip('/'), True), value, flags=re.M)
        return cache[name]

    def program(parts):
        selected = driver.create_program()
        programs.append(selected)
        for value, kind in parts:
            if kind == '.csh':
                handle = driver.create_shader(0x91B9)
                encoded = value.encode()
                pointer, length = ct.c_char_p(encoded), ct.c_int(len(encoded))
                driver.shader_source(handle, 1, ct.byref(pointer), ct.byref(length))
                driver.compile_shader(handle)
                status, log = ct.c_int(), ct.create_string_buffer(65536)
                driver.get_shader(handle, 0x8B81, ct.byref(status))
                driver.shader_log(handle, len(log), None, log)
                assert status.value and not log.value, log.value.decode()
            else:
                handle, warning = driver.compile(value, kind, 'local-light repair')
                assert not warning, warning
            shaders.append(handle)
            driver.attach_shader(selected, handle)
        driver.link_program(selected)
        status, log = ct.c_int(), ct.create_string_buffer(65536)
        driver.get_program(selected, 0x8B82, ct.byref(status))
        driver.program_log(selected, len(log), None, log)
        assert status.value and not log.value, log.value.decode()
        return selected

    def sampler(old):
        prefix = '#version 330 compatibility\n' + source('lib/settings.glsl', old)
        prefix += '\nuniform vec3 cameraPosition;uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n'
        prefix += source('lib/emissive_light.glsl', old)
        body = '''
uniform vec3 testPosition,testNormal;
uniform uint testReceiver;
out vec4 result;
void main(){result=xonLampLight(testPosition,testNormal,testReceiver);}
'''
        return program([(source('final.vsh'), '.vsh'), (prefix + body, '.fsh')])

    def terrain(old, vertex=VERTEX):
        text = source('gbuffers_terrain.fsh', old)
        for name, value in {'XON_SHADOWS': False, 'XON_ANISOTROPIC': 0, 'XON_CLOUD_STYLE': 0,
                            'XON_ADVANCED_MATERIALS': False}.items():
            text = re.sub(rf'^(?://)?#define {name}\b[^\n]*$', '#undef ' + name if value is False else f'#define {name} {value}', text, flags=re.M)
        return program([(vertex, '.vsh'), (text, '.fsh')])

    def resize(width, height):
        renderer.width, renderer.height = width, height
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, width, height, 0, 0x1908, 0x1406, None)
        renderer.viewport(0, 0, width, height)

    def upload_lamp(field):
        for index in range(2):
            renderer.active_texture(0x84CD + index)
            renderer.bind_texture(0x806F, renderer.lamps[index])
            renderer.sub3d(0x806F, 0, 0, 0, 0, 96, 48, 96, 0x1908, 0x1406, field.ctypes.data)
        renderer.barrier(0xFFFFFFFF)
        renderer.frame = 2

    def settle(selected, steps=20):
        renderer.upload(0, renderer.voxels)
        for _ in range(steps):
            renderer.step(selected)

    def sample(selected, position, normal=(0, 1, 0), receiver=0):
        renderer.sample(selected, position, normal)
        uniform_ui(renderer.location('testReceiver'), receiver)
        return renderer.draw(raw=True)[0, 0].copy()

    def shade_setup(selected, position=(.85, 0, .85), normal=(0, 1, 0), block=.85, material=0):
        renderer.setup(selected)
        renderer.uniform1i(renderer.location('frameCounter'), renderer.frame - 1)
        for name, value in [('testBlock', block), ('testSky', 0), ('testAO', 1), ('testMaterial', material),
                            ('testTangent', 1), ('alphaTestRef', .1), ('far', 1024), ('fogStart', 800), ('fogEnd', 1024)]:
            renderer.uniform1f(renderer.location(name), value)
        for name, value in [('testPosition', position), ('testNormal', normal), ('sunPosition', (30, 90, 20))]:
            renderer.uniform3f(renderer.location(name), *value)

    def shade(selected, **options):
        shade_setup(selected, **options)
        return renderer.draw(raw=True)[..., :3]

    def quad():
        renderer.begin(0x0007)
        for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
            renderer.tex_coord(x, y)
            renderer.vertex(x, y)
        renderer.end()

    def timing(actions):
        f = driver.function
        gen = f('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin = f('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end = f('glEndQuery', None, ct.c_uint)
        read = f('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete = f('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        queries = (ct.c_uint * 48)()
        gen(48, queries)
        try:
            for prepare, action in actions:
                prepare()
                for _ in range(12):
                    action()
            for batch in range(24):
                for version in ([0, 1] if batch % 2 == 0 else [1, 0]):
                    prepare, action = actions[version]
                    prepare()
                    begin(0x88BF, queries[batch * 2 + version])
                    for _ in range(4):
                        action()
                    end(0x88BF)
            times = [[], []]
            for batch in range(24):
                for version in [0, 1]:
                    value = ct.c_uint64()
                    read(queries[batch * 2 + version], 0x8866, ct.byref(value))
                    times[version].append(value.value / 4e6)
            return {'before_ms': float(np.median(times[0])), 'after_ms': float(np.median(times[1])),
                    'paired_median_ratio': float(np.median(np.array(times[1]) / times[0]))}
        finally:
            delete(48, queries)

    try:
        uniform_ui = driver.function('glUniform1ui', None, ct.c_int, ct.c_uint)
        computes = [program([(source('shadowcomp.csh', old), '.csh')]) for old in [True, False]]
        samplers = [sampler(old) for old in [True, False]]
        terrains = [terrain(old) for old in [True, False]]
        renderer.texture(8, np.full((16, 16, 4), [.85, .83, .78, 1], np.float32))
        lut = np.asarray(Image.open(SHADERS / 'textures/xon-grade.png'), float) / 255
        graph_source = '#version 330 compatibility\n' + source('lib/settings.glsl')
        graph_source += '\nuniform vec3 cameraPosition;uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n'
        graph_source += source('lib/emissive_light.glsl') + '''
out vec4 result;
void main(){result=vec4(float(xonConnectedLightCorners(uint(gl_FragCoord.x),uint(gl_FragCoord.y))));}
'''
        graph = program([(source('final.vsh'), '.vsh'), (graph_source, '.fsh')])
        resize(256, 8)
        renderer.setup(graph)
        actual = renderer.draw(raw=True)[..., 0].astype(int)
        expected = np.zeros((8, 256), int)
        for mask in range(256):
            for anchor in range(8):
                visited = {anchor} if mask & (1 << anchor) else set()
                pending = list(visited)
                while pending:
                    cell = pending.pop()
                    for axis in [1, 2, 4]:
                        neighbor = cell ^ axis
                        if mask & (1 << neighbor) and neighbor not in visited:
                            visited.add(neighbor)
                            pending.append(neighbor)
                expected[anchor, mask] = sum(1 << cell for cell in visited)
        assert np.array_equal(actual, expected)
        checks.append({'case': 'all 2048 corner-connectivity cases agree with independent CPU graph traversal'})
        resize(1, 1)
        field = renderer.empty_light.copy()
        field[:] = [.12, .18, .20, 188]
        upload_lamp(field)
        clear = [sample(p, (.85, 0, .85)) for p in samplers]
        assert np.max(np.abs(clear[0] - clear[1])) < 1e-6
        checks.append({'case': 'open colored pool and native coverage retained'})
        field[:] = [.025, .025, .025, 188]
        field[49, 24, 48] = [.8, .6, .2, 188]
        field[49, 24, 49] = [0, 0, 0, -1]
        upload_lamp(field)
        steps = []
        for selected in samplers:
            left = sample(selected, (.999, 0, .8))
            right = sample(selected, (1.001, 0, .8))
            steps.append(float(np.max(np.abs(left[:3] - right[:3]))))
        assert steps[0] > .05 and steps[1] < .003, steps
        checks.append({'case': 'crossing an open-cell boundary no longer changes the visible interpolation component', 'old_new_raw_rgb_step': steps})
        field[:] = [.12, .18, .20, 188]
        field[48, 24, 48] = [0, 0, 0, -1]
        upload_lamp(field)
        blocked = [sample(p, (.85, 0, .85)) for p in samplers]
        assert max(abs(blocked[0][:3])) == max(abs(blocked[1][:3])) == 0
        assert blocked[0][3] == 0 and blocked[1][3] > .4, blocked
        colors = [shade(p)[0, 0] for p in terrains]
        lumas = [float(display_luma(c[None, None], lut, .83, True)[0, 0]) for c in colors]
        assert lumas[1] < lumas[0] * .8, lumas
        checks.append({'case': 'blocked colored light no longer restores bright scalar fallback',
                       'old_new_coverage': [float(v[3]) for v in blocked], 'old_new_display_luminance': lumas})
        for occupancy in [1, 255, 136, 6, 139]:
            for channel in ['lamp', 'ore']:
                if channel == 'ore' and occupancy == 6:
                    continue
                ghosts = []
                for selected in computes:
                    renderer.reset()
                    renderer.voxels[48, 24, 48] = occupancy
                    renderer.upload(0, renderer.voxels)
                    field.fill(0)
                    field[48, 24, 48] = [1.25, .8375, .375, 63 if channel == 'lamp' else 1]
                    if channel == 'lamp':
                        upload_lamp(field)
                    else:
                        renderer.upload(1, field)
                        renderer.upload(2, field)
                    renderer.frame = 1
                    renderer.step(selected)
                    current = renderer.lamp_field() if channel == 'lamp' else renderer.current()
                    ghosts.append(float(np.max(current[renderer.voxels == 0, :3])))
                assert ghosts[0] > .1 and ghosts[1] == 0, (occupancy, channel, ghosts)
                checks.append({'case': 'new block rejects stale light on the next compute step', 'occupancy': occupancy,
                               'channel': channel, 'old_new_leak': ghosts})
        coverages = []
        for version, selected in enumerate(computes):
            renderer.reset()
            renderer.voxels[:, :24, :] = 255
            renderer.voxels[:, :, 48] = 255
            renderer.voxels[48, 24:35, 48] = 136
            renderer.voxels[48, 23, 49] = 139
            settle(selected)
            value = sample(samplers[version], (1.001, 7.25, .5), (1, 0, 0), 8)
            coverages.append(float(value[3]))
        assert coverages[0] == 0 and coverages[1] > .25, coverages
        checks.append({'case': 'quartz glow cannot erase real lamp coverage beyond the colored radius', 'old_new_coverage': coverages})
        vertex = VERTEX.replace('xonViewPosition=testPosition;xonPlayerPosition=testPosition;',
                                'xonPlayerPosition=vec3(1.001,uv.y*5.0,uv.x);xonViewPosition=xonPlayerPosition;')
        vertex = vertex.replace('xonLightLevels=vec2(testBlock,testSky);',
                                'xonLightLevels=vec2(clamp((15.0-uv.y*5.0-.5)/15.0,0,1),testSky);')
        pillar_programs = [terrain(old, vertex) for old in [True, False]]
        resize(160, 480)
        images = []
        metrics = []
        for base_block in [False, True]:
            for version, selected in enumerate(computes):
                renderer.reset()
                renderer.voxels[:, :24, :] = 255
                renderer.voxels[:, :, 48] = 255
                renderer.voxels[48, 24:30, 48] = 136
                renderer.voxels[:, 29, :] = 255
                renderer.voxels[48, 23, 49] = 139
                if base_block:
                    renderer.voxels[48, 24, 49] = 136
                settle(selected)
                image = shade(pillar_programs[version], normal=(1, 0, 0), material=10023)
                images.append(image)
                lum = display_luma(image, lut, .83, True)
                center = lum[:, 80]
                jumps = np.abs(np.diff(center))
                metrics.append({'quartz_base': base_block, 'version': version, 'largest_display_step': float(jumps.max()),
                                'row_luminance': [float(center[i]) for i in [120, 192, 240, 288, 336, 384, 432]]})
                if version == 1:
                    assert float(jumps.max()) < .012, (base_block, jumps.max())
                    assert center[120] > center[384], (base_block, center[120], center[384])
        sheet = Image.new('RGB', (640, 504))
        draw = ImageDraw.Draw(sheet)
        for i, value in enumerate(images):
            color = value * (.83 * 1.05)
            color = color * (2.51 * color + .03) / (color * (2.43 * color + .59) + .14)
            color = np.clip(color, 0, 1) ** (1 / 2.2)
            sheet.paste(Image.fromarray(np.uint8(color[::-1] * 255)), (160 * i, 24))
            draw.text((160 * i + 3, 6), ('1.8.3' if i % 2 == 0 else 'Repair') + (' / base' if i >= 2 else ' / open'), fill='white')
        sheet.save(ROOT / 'validation-local-light-repair.png')
        checks.append({'case': 'quartz pillar with and without covering base', 'metrics': metrics})
        resize(1920, 1080)
        timings = {}
        actions = []
        for p in terrains:
            def prepare(p=p):
                shade_setup(p, position=(1.001, 2.5, .5), normal=(1, 0, 0), material=10023)
            actions.append((prepare, quad))
        timings['terrain_1080p'] = timing(actions)
        timings['compute'] = timing([(lambda: None, lambda p=p: renderer.step(p)) for p in computes])
        report = {'passed': True, 'baseline': str(baseline), 'checks': checks, 'timings': timings,
                  'scope': 'Controlled GPU transport and production terrain pixels; not full-game FPS or live screenshot approval.'}
        (ROOT / 'validation-local-light-repair.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        for selected in programs:
            driver.delete_program(selected)
        for handle in shaders:
            driver.delete_shader(handle)
        renderer.close()
        driver.close()
        archive.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=ROOT.parent / 'XON-Shader-v1.8.3.zip')
    run(parser.parse_args().baseline)
