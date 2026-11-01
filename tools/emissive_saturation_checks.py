"""Exercise 1.2 saturation and lamp spill on the actual OpenGL shaders against 1.1."""
import ctypes as ct
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from validate import Driver, SHADERS, expand, variant_source
from voxel_gpu_checks import VoxelRenderer

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT.parent / 'XON-Shader-v1.1.zip'
LUMA = np.array([.2126, .7152, .0722])
VERTEX = '''#version 330 compatibility
out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels; out vec4 xonVertexColor;
out vec3 xonViewPosition,xonPlayerPosition,xonWorldNormal; flat out float xonMaterial;
uniform float testMaterial,testBlock; uniform vec3 testPosition;
void main(){
 xonTexCoord=gl_MultiTexCoord0.xy;xonAtlasBounds=vec4(0);xonLightLevels=vec2(testBlock,0);xonVertexColor=vec4(1);
 xonViewPosition=vec3(0,0,-5);xonPlayerPosition=testPosition;xonWorldNormal=vec3(0,1,0);
 xonMaterial=testMaterial;gl_Position=vec4(gl_Vertex.xy*2-1,0,1);
}'''


def run():
    driver = Driver()
    renderer = VoxelRenderer(driver)
    archive = zipfile.ZipFile(BASELINE)
    client = zipfile.ZipFile(Path.home() / 'AppData/Roaming/ModrinthApp/meta/versions/26.3-0.20.1/26.3-0.20.1.jar')
    stages, programs, checks = [], [], []

    def saved(name):
        source = archive.read('shaders/' + name).decode().replace('\r\n', '\n')
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda match: saved(match[1].lstrip('/')), source, flags=re.M)

    def program(parts):
        compiled = []
        for source, kind in parts:
            if kind == '.csh':
                handle = driver.create_shader(0x91B9)
                data = source.encode()
                pointer, length = ct.c_char_p(data), ct.c_int(len(data))
                driver.shader_source(handle, 1, ct.byref(pointer), ct.byref(length))
                driver.compile_shader(handle)
                status, log = ct.c_int(), ct.create_string_buffer(65536)
                driver.get_shader(handle, 0x8B81, ct.byref(status))
                driver.shader_log(handle, len(log), None, log)
                assert status.value and not log.value, log.value.decode()
            else:
                handle, warning = driver.compile(source, kind, '1.2 emissive saturation')
                assert not warning, warning
            stages.append(handle)
            compiled.append(handle)
        selected = driver.create_program()
        for handle in compiled:
            driver.attach_shader(selected, handle)
        driver.link_program(selected)
        status, log = ct.c_int(), ct.create_string_buffer(65536)
        driver.get_program(selected, 0x8B82, ct.byref(status))
        driver.program_log(selected, len(log), None, log)
        assert status.value and not log.value, log.value.decode()
        programs.append(selected)
        return selected

    def draw(selected, material=0, block=0, position=(1.5, -.5, .5)):
        renderer.setup(selected)
        renderer.uniform1i(renderer.location('frameCounter'), renderer.frame - 1)
        renderer.uniform1f(renderer.location('testMaterial'), material)
        renderer.uniform1f(renderer.location('testBlock'), block)
        renderer.uniform1f(renderer.location('alphaTestRef'), .1)
        renderer.uniform1f(renderer.location('far'), 1024)
        renderer.uniform3f(renderer.location('testPosition'), *position)
        return renderer.draw(raw=True)[..., :3]

    try:
        renderer.width, renderer.height = 64, 64
        renderer.active_texture(0x84C0)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, 64, 64, 0, 0x1908, 0x1406, None)

        random = np.random.default_rng(120035).uniform(0, 4, (64, 64, 4)).astype(np.float32)
        random[..., 3] = 1
        random[0, :8, :3] = [[0, 0, 0], [1, 1, 1], [.001, .001, .001], [1, 0, 0],
                              [0, 1, 0], [0, 0, 1], [1, .5, .1], [.4, .8, .6]]
        renderer.texture(8, random)
        original = random[..., :3]
        y = original @ LUMA
        chroma = original - y[..., None]
        for gain in ['1.00', '1.15', '1.25', '1.35', '1.50']:
            settings = re.sub(r'^#define XON_EMISSIVE_SATURATION .*$',
                              '#define XON_EMISSIVE_SATURATION ' + gain,
                              expand(SHADERS / 'lib/settings.glsl'), flags=re.M)
            source = '#version 330 compatibility\n' + settings + '\nuniform vec3 cameraPosition;\n'
            source += expand(SHADERS / 'lib/emissive_light.glsl')
            source += '\nin vec2 xonUV;uniform sampler2D gtexture;out vec4 result;void main(){result=vec4(xonSaturateEmitterColor(texture(gtexture,xonUV).rgb),1);}'
            selected = program([(expand(SHADERS / 'final.vsh'), '.vsh'), (source, '.fsh')])
            actual = draw(selected)
            actual_y = actual @ LUMA
            actual_chroma = actual - actual_y[..., None]
            assert np.isfinite(actual).all() and np.min(actual) >= 0
            assert np.max(np.abs(actual_y - y)) < .000002
            assert np.max(np.abs(np.cross(chroma, actual_chroma))) < .00001
            lengths = np.linalg.norm(chroma, axis=2)
            changed_lengths = np.linalg.norm(actual_chroma, axis=2)
            assert np.all(changed_lengths >= lengths - .000003)
            assert np.all(changed_lengths <= lengths * float(gain) + .000003)
            uncapped = np.min(actual, axis=2) > y * .011 + .00001
            assert np.max(np.abs(changed_lengths[uncapped] - lengths[uncapped] * float(gain))) < .000003
            capped = ~uncapped & (np.min(original, axis=2) >= y * .01) & (lengths > .00001)
            assert np.all(np.min(actual, axis=2)[capped] >= y[capped] * .01 - .000001)
            if gain == '1.00':
                assert np.array_equal(actual, original)
            checks.append({'case': '4096 HDR/neutral/primary colors preserve luminance, hue and nonnegative channels',
                           'saturation': gain, 'max_luminance_error': float(np.max(np.abs(actual_y - y)))})

        old_compute = program([(saved('shadowcomp.csh'), '.csh')])
        original_compute = program([(variant_source(SHADERS / 'shadowcomp.csh', {'XON_EMISSIVE_SATURATION': '1.00'}), '.csh')])
        compute = program([(variant_source(SHADERS / 'shadowcomp.csh', {}), '.csh')])
        fields = []
        for selected in [old_compute, original_compute, compute]:
            renderer.reset()
            for index, identifier in enumerate(range(2, 15)):
                renderer.voxels[12 + (index // 4) * 20, 24, 18 + (index % 4) * 20] = identifier
            renderer.upload(0, renderer.voxels)
            for _ in range(16):
                renderer.step(selected)
            fields.append(renderer.current())
        assert np.array_equal(fields[0], fields[1]), '100% must reproduce the 1.1 volume exactly'
        assert np.array_equal(fields[0][..., 3], fields[2][..., 3]), 'Reach/falloff changed'
        before_y = fields[0][..., :3] @ LUMA
        after_y = fields[2][..., :3] @ LUMA
        lit = before_y > .0001
        relative_error = float(np.max(np.abs(after_y[lit] / before_y[lit] - 1)))
        assert relative_error < .004, relative_error
        checks.append({'case': 'all 13 existing emitter families retain exact 1.1 falloff and 100% volume parity',
                       'maximum_luminance_error_after_half_float_storage': relative_error})

        flags = {'XON_SHADOWS': False, 'XON_CAUSTICS': False, 'XON_CLOUD_STYLE': 0, 'XON_ANISOTROPIC': 0}
        terrain = [program([(VERTEX, '.vsh'), (variant_source(SHADERS / folder / 'gbuffers_terrain.fsh', flags), '.fsh')])
                   for folder in ['', 'world-1', 'world1']]
        captures = [program([(variant_source(SHADERS / folder / 'shadow.vsh', {}), '.vsh'),
                             (variant_source(SHADERS / folder / 'shadow.fsh', {}), '.fsh')])
                    for folder in ['', 'world-1', 'world1']]
        selectors = (SHADERS / 'block.properties').read_text()
        for name, material in [('jack_o_lantern', 10027), ('soul_lantern', 10026)]:
            client.read('assets/minecraft/blockstates/' + name + '.json')
            matches = re.findall(r'^block\.(\d+)=.*\bminecraft:' + name + r'(?=\s|$)', selectors, re.M)
            assert matches == [str(material)], (name, matches)
        for dimension, caster, receiver in zip([0, -1, 1], captures, terrain):
            for material, identifier, name in [(10027, 15, 'jack_o_lantern'), (10026, 16, 'soul_lantern')]:
                renderer.reset()
                voxel = renderer.capture(caster, material, stage=1 if material == 10027 else 3)
                assert renderer.read(0)[voxel] == identifier
                for _ in range(12):
                    renderer.step(compute)
                renderer.texture(8, np.full((2, 2, 4), [.55, .55, .55, 1], np.float32))
                floor = draw(receiver, block=9 / 15)[0, 0]
                if material == 10026:
                    assert floor[2] > floor[1] > floor[0], floor
                else:
                    assert floor[0] > floor[1] > floor[2], floor
                checks.append({'case': 'real capture, compute and production receiving floor with ordinary lamp light present',
                               'block': name, 'dimension': dimension, 'linear_rgb': floor.tolist()})

        renderer.reset()
        renderer.voxels[48, 24, 48] = 16
        renderer.voxels[:, :, 50] = 1
        renderer.upload(0, renderer.voxels)
        for _ in range(16):
            renderer.step(compute)
        assert np.max(renderer.current()[:, :, 51:, :3]) == 0
        checks.append({'case': 'cyan soul light does not propagate through a solid wall'})

        old_fragment = saved('gbuffers_terrain.fsh')
        for key, value in dict(flags, XON_COLORED_EMISSIVE_LIGHTING=False).items():
            old_fragment = re.sub(rf'^(?://)?#define {key}(?:[^\n]*)?$',
                                  '#undef ' + key if value is False else f'#define {key} {value}', old_fragment, flags=re.M)
        old_terrain = program([(VERTEX, '.vsh'), (old_fragment, '.fsh')])
        current_terrain = program([(VERTEX, '.vsh'), (variant_source(SHADERS / 'gbuffers_terrain.fsh', dict(flags, XON_COLORED_EMISSIVE_LIGHTING=False)), '.fsh')])
        for name, before_material, after_material in [('jack_o_lantern', 10002, 10027), ('soul_lantern', 10026, 10026),
                                                     ('lantern', 10025, 10025), ('torch', 10002, 10002), ('end_rod', 10002, 10002)]:
            texture = np.asarray(Image.open(io.BytesIO(client.read('assets/minecraft/textures/block/' + name + '.png'))).convert('RGBA'))[:16].astype(np.float32) / 255
            renderer.texture(8, texture)
            before = draw(old_terrain, before_material, .8)
            after = draw(current_terrain, after_material, .8)
            error = float(np.max(np.abs(before - after)))
            assert error < .000001, (name, error)
            checks.append({'case': 'source texture/core/frame and ordinary lamp lighting match 1.1 with colored light disabled',
                           'block': name, 'maximum_error': error})

        assert renderer.get_error() == 0
        report = {'passed': True, 'gpu': driver.get_string(0x1F01).decode(), 'checks': checks,
                  'baseline_sha256': hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
                  'scope': 'Actual GLSL execution, compute volumes and production terrain on controlled inputs. Not a live-world visual or FPS comparison.'}
        (ROOT / 'validation-emissive-saturation.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        client.close()
        archive.close()
        for selected in programs:
            driver.delete_program(selected)
        for selected in stages:
            driver.delete_shader(selected)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    run()
