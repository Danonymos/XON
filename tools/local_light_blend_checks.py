"""Reproduce ambient-mask bands and opaque decorative-source interpolation leaks."""
import argparse
import ctypes as ct
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from PIL import Image

from brightness_checks import display_luma
from lamp_gpu_checks import LampRenderer
from pbr_checks import VERTEX
from validate import Driver, SHADERS, expand

ROOT = Path(__file__).resolve().parents[1]


def run(baseline):
    driver = Driver()
    renderer = LampRenderer(driver)
    archive = zipfile.ZipFile(baseline)
    shaders, programs, checks, cache = [], [], [], {}
    lut = np.asarray(Image.open(SHADERS / 'textures/xon-grade.png'), float) / 255

    def source(name, old=False):
        if not old:
            return expand(SHADERS / name)
        if name not in cache:
            text = archive.read('shaders/' + name).decode().replace('\r', '')
            cache[name] = re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                lambda match: source(match[1].lstrip('/'), True), text, flags=re.M)
        return cache[name]

    def program(parts):
        handles = []
        for text, stage in parts:
            handle, warning = driver.compile(text, stage, 'local-light blend regression')
            shaders.append(handle)
            assert not warning, warning
            handles.append(handle)
        handle, warning = driver.link(*handles, 'local-light blend regression')
        programs.append(handle)
        assert not warning, warning
        return handle

    def terrain(old, vertex=VERTEX, fragment=None):
        text = source('gbuffers_terrain.fsh', old) if fragment is None else fragment
        for key, value in {'XON_SHADOWS': False, 'XON_CLOUD_STYLE': 0,
                           'XON_ANISOTROPIC': 0, 'XON_ADVANCED_MATERIALS': False}.items():
            text = re.sub(rf'^(?://)?#define {key}\b[^\n]*$',
                          '#undef ' + key if value is False else f'#define {key} {value}', text, flags=re.M)
        return program([(vertex, '.vsh'), (text, '.fsh')])

    def upload(alpha, rgb=(0, 0, 0)):
        field = renderer.empty_light.copy()
        field[:] = [*rgb, alpha]
        for index in range(2):
            renderer.active_texture(0x84CD + index)
            renderer.bind_texture(0x806F, renderer.lamps[index])
            renderer.sub3d(0x806F, 0, 0, 0, 0, 96, 48, 96, 0x1908, 0x1406, field.ctypes.data)
        renderer.barrier(0xFFFFFFFF)
        renderer.frame = 2

    def draw(selected, block=.7, sky=0, vision=0, normal=(1, 0, 0), material=0, position=(1.001, 2.5, .5)):
        renderer.setup(selected)
        renderer.uniform1i(renderer.location('frameCounter'), renderer.frame - 1)
        for name, value in [('testBlock', block), ('testSky', sky), ('testAO', 1), ('testMaterial', material),
                            ('testTangent', 1), ('alphaTestRef', .1), ('far', 1024),
                            ('fogStart', 800), ('fogEnd', 1024), ('nightVision', vision)]:
            renderer.uniform1f(renderer.location(name), value)
        for name, value in [('testPosition', position), ('testNormal', normal), ('sunPosition', (30, 90, 20))]:
            renderer.uniform3f(renderer.location(name), *value)
        return renderer.draw(raw=True)[..., :3]

    def luma(image):
        return display_luma(image, lut, .83, True)

    def compute(old):
        selected = driver.create_program()
        programs.append(selected)
        handle = driver.create_shader(0x91B9)
        shaders.append(handle)
        encoded = source('shadowcomp.csh', old).encode()
        pointer, length = ct.c_char_p(encoded), ct.c_int(len(encoded))
        driver.shader_source(handle, 1, ct.byref(pointer), ct.byref(length))
        driver.compile_shader(handle)
        status, log = ct.c_int(), ct.create_string_buffer(65536)
        driver.get_shader(handle, 0x8B81, ct.byref(status))
        driver.shader_log(handle, len(log), None, log)
        assert status.value and not log.value, log.value.decode()
        driver.attach_shader(selected, handle)
        driver.link_program(selected)
        driver.get_program(selected, 0x8B82, ct.byref(status))
        driver.program_log(selected, len(log), None, log)
        assert status.value and not log.value, log.value.decode()
        return selected

    try:
        renderer.texture(8, np.full((16, 16, 4), [.85, .83, .78, 1], np.float32))
        terrains = [terrain(old) for old in [True, False]]
        normals = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
        for material in [0, 10023, 10028]:
            for normal in normals:
                colors = [[], []]
                for alpha in [0, 132, 63, 184, 188]:
                    upload(alpha)
                    for version, selected in enumerate(terrains):
                        colors[version].append(draw(selected, normal=normal, material=material)[0, 0])
                ranges = [float(np.max(np.ptp(np.array(values), axis=0))) for values in colors]
                assert ranges[0] > .1 and ranges[1] < 2e-6, (material, normal, ranges)
                checks.append({'case': 'ambient invariant to lamp metadata at equal native and colored light',
                               'material': material, 'normal': normal, 'before_after_linear_range': ranges})
        for rgb in [(0.02, .03, .035), (.10, .25, .30)]:
            colors = []
            for alpha in [63, 184, 188]:
                upload(alpha, rgb)
                colors.append(draw(terrains[1])[0, 0])
            assert np.max(np.ptp(colors, axis=0)) < 2e-6
        checks.append({'case': 'colored radiance remains invariant to native-source metadata'})
        with zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.8.4-r5.zip') as r5:
            def r5_source(name):
                text = r5.read('shaders/' + name).decode().replace('\r', '')
                return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                              lambda match: r5_source(match[1].lstrip('/')), text, flags=re.M)
            r5_terrain = terrain(False, fragment=r5_source('gbuffers_terrain.fsh'))
        for sky, block in [(0.0, 0.0), (.2, .7), (.4, .7), (.6, .7), (.85, .7), (1.0, .7)]:
            colors = [[], []]
            for alpha in [0, 132, 63, 184, 188]:
                upload(alpha)
                for version, selected in enumerate([r5_terrain, terrains[1]]):
                    colors[version].append(draw(selected, sky=sky, block=block)[0, 0])
            ranges = [float(np.max(np.ptp(values, axis=0))) for values in colors]
            assert (sky == .2 or ranges[0] > .01) and ranges[1] < 2e-6, (sky, ranges)
            checks.append({'case': 'R5 mixed-skylight source-identity bands reproduced and removed',
                           'skylight': sky, 'native_block_light': block, 'before_after_linear_range': ranges})
        for label, options in [('open sky without block light', {'sky': 1, 'block': 0}), ('night vision', {'vision': 1}),
                               ('unlit interior', {'block': 0}),
                               ('outside volume', {'position': (60, 0, 0)}),
                               ('bright sea-lantern surface', {'material': 10032})]:
            error = 0.0
            for alpha in ([0] if label == 'unlit interior' else [0, 132, 184]):
                upload(alpha)
                pair = [draw(selected, **options)[0, 0] for selected in terrains]
                error = max(error, float(np.max(np.abs(pair[1] - pair[0]))))
            assert error < 2e-6, (label, error)
            checks.append({'case': label + ' preserves R2 pixels', 'maximum_linear_error': error})
        upload(0)
        edge = [float(luma(draw(terrains[1], position=(float(x), 0, .5)))[0, 0])
                for x in np.linspace(39, 48, 91)]
        assert min(np.diff(edge)) > -1e-6 and max(np.diff(edge)) < .015
        checks.append({'case': 'ambient replacement fades smoothly at the volume boundary',
                       'largest_display_step_per_tenth_block': float(max(np.diff(edge)))})
        pool = []
        for level in [0, .02, .05, .10, .25, .50]:
            upload(184, np.array([.68, .94, 1]) * level)
            pool.append(float(luma(draw(terrains[1]))[0, 0]))
        assert min(np.diff(pool)) > 0 and pool[-1] - pool[0] > .25, pool
        checks.append({'case': 'colored source pools retain strong monotonic contrast', 'display_luminance': pool})
        computes = [compute(old) for old in [True, False]]
        for occupancy in [134, 135, 136]:
            renderer.reset()
            renderer.voxels[48, 24, 48] = occupancy
            renderer.upload(0, renderer.voxels)
            for _ in range(16):
                renderer.step(computes[1])
            field = renderer.lamp_field()
            assert field[48, 24, 48, 3] < 0
            assert np.max(field[renderer.voxels == 0, :3]) > .001
            checks.append({'case': 'opaque decorative source is closed while outward aura survives', 'occupancy': occupancy})
        vertex = VERTEX.replace('xonViewPosition=testPosition;xonPlayerPosition=testPosition;',
                                'xonPlayerPosition=vec3(1.001,uv.y*5.0,uv.x);xonViewPosition=xonPlayerPosition;')
        vertex = vertex.replace('xonLightLevels=vec2(testBlock,testSky);',
                                'xonLightLevels=vec2(clamp((15.0-uv.y*5.0-.5)/15.0,0,1),testSky);')
        pillar = terrain(False, vertex)
        gradients = []
        for selected in computes:
            renderer.reset()
            renderer.voxels[:, :24, :] = 255
            renderer.voxels[:, :, 48] = 255
            renderer.voxels[48, 24:30, 48] = 136
            renderer.voxels[:, 29, :] = 255
            renderer.voxels[48, 23, 49] = 139
            renderer.voxels[48, 24, 49] = 136
            renderer.upload(0, renderer.voxels)
            for _ in range(20):
                renderer.step(selected)
            image = luma(draw(pillar, material=10023))
            gradients.append(float(np.max(np.abs(np.diff(image[:, renderer.width // 2])))))
        assert gradients[0] > .014 and gradients[1] < .004, gradients
        checks.append({'case': 'surface interpolation no longer samples a lamp through opaque quartz',
                       'before_after_maximum_display_step': gradients})
        prefix = '#version 330 compatibility\n' + source('lib/settings.glsl')
        prefix += '\nuniform vec3 cameraPosition;uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n'
        prefix += source('lib/emissive_light.glsl') + '''
out vec4 result;
void main(){
 uint state=uint(gl_FragCoord.x),open=0u,terminals=0u;
 for(uint corner=0u;corner<8u;++corner){
  uint kind=state%3u;state/=3u;
  if(kind==1u)open|=1u<<corner;
  if(kind==2u)terminals|=1u<<corner;
 }
 result=vec4(float(xonVisibleLampCorners(open,terminals,uint(gl_FragCoord.y))));
}
'''
        graph = program([(source('final.vsh'), '.vsh'), (prefix, '.fsh')])
        renderer.width, renderer.height = 6561, 8
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, 6561, 8, 0, 0x1908, 0x1406, None)
        renderer.setup(graph)
        actual = renderer.draw(raw=True)[..., 0].astype(int)
        expected = np.zeros((8, 6561), int)
        for state in range(6561):
            kinds = [(state // 3 ** corner) % 3 for corner in range(8)]
            for anchor in range(8):
                visited, visible = set(), set()
                pending = [anchor] if kinds[anchor] == 1 else []
                if kinds[anchor] == 2:
                    visible.add(anchor)
                while pending:
                    corner = pending.pop()
                    if corner in visited:
                        continue
                    visited.add(corner)
                    visible.add(corner)
                    for axis in [1, 2, 4]:
                        neighbor = corner ^ axis
                        if kinds[neighbor] == 1 and neighbor not in visited:
                            pending.append(neighbor)
                        elif kinds[neighbor] == 2:
                            visible.add(neighbor)
                expected[anchor, state] = sum(1 << corner for corner in visible)
        assert np.array_equal(actual, expected)
        checks.append({'case': 'all 52488 air/solid/emitter stencil cases match independent terminal graph traversal'})
        report = {'passed': True, 'baseline': str(baseline), 'checks': checks,
                  'scope': 'Production terrain and compute on controlled inputs; actual room approval remains pending.'}
        (ROOT / 'validation-local-light-blend.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        for handle in programs:
            driver.delete_program(handle)
        for handle in shaders:
            driver.delete_shader(handle)
        renderer.close()
        driver.close()
        archive.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=ROOT.parent / 'XON-Shader-v1.8.4.zip')
    run(parser.parse_args().baseline)
