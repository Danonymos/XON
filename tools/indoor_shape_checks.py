"""Reproduce partial-shape occlusion artifacts and verify capture/propagation metadata."""
import ctypes as ct
import json
from pathlib import Path
import zipfile

import numpy as np
from indoor_block_shapes import CLIENT, run as check_map
from validate import Driver, SHADERS, expand, variant_source
from voxel_gpu_checks import HALF
from lamp_gpu_checks import LampRenderer

ROOT = Path(__file__).resolve().parents[1]


def run():
    check_map(CLIENT)
    driver = Driver()
    renderer = LampRenderer(driver)
    stages, programs, checks = [], [], []

    def program(parts):
        handles = []
        for source, kind in parts:
            if kind == '.csh':
                handle = driver.create_shader(0x91B9)
                encoded = source.encode()
                pointer, length = ct.c_char_p(encoded), ct.c_int(len(encoded))
                driver.shader_source(handle, 1, ct.byref(pointer), ct.byref(length))
                driver.compile_shader(handle)
                status, log = ct.c_int(), ct.create_string_buffer(65536)
                driver.get_shader(handle, 0x8B81, ct.byref(status))
                driver.shader_log(handle, len(log), None, log)
                assert status.value and not log.value, log.value.decode()
            else:
                handle, warning = driver.compile(source, kind, 'indoor shape regression')
                assert not warning, warning
            handles.append(handle)
            stages.append(handle)
        selected = driver.create_program()
        for handle in handles:
            driver.attach_shader(selected, handle)
        driver.link_program(selected)
        status, log = ct.c_int(), ct.create_string_buffer(65536)
        driver.get_program(selected, 0x8B82, ct.byref(status))
        driver.program_log(selected, len(log), None, log)
        assert status.value and not log.value, log.value.decode()
        programs.append(selected)
        return selected

    def probe(library):
        text = '#version 330 compatibility\n' + expand(SHADERS / 'lib/settings.glsl')
        text += '\nuniform vec3 cameraPosition;uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n'
        text += library + '''
uniform vec3 testPosition,testNormal;
out vec4 result;
void main(){result=vec4(vec3(xonIndoorOcclusion(testPosition,testNormal)),1);}
'''
        return program([(expand(SHADERS / 'final.vsh'), '.vsh'), (text, '.fsh')])

    def upload(field):
        renderer.upload(1, field)
        renderer.upload(2, field)
        renderer.upload_contact(field[..., 3] < -1.5)

    try:
        with zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.6-indoor-lighting-r2.zip') as archive:
            before = probe(archive.read('shaders/lib/emissive_light.glsl').decode())
        after = probe(expand(SHADERS / 'lib/emissive_light.glsl'))
        coordinates = np.indices(renderer.voxels.shape)
        old_minimum = 1.0
        for axis in range(3):
            for sign in [-1, 1]:
                normal = np.eye(3)[axis] * sign
                for height in [1 / 16, 1 / 8, .5, 1.0]:
                    for verified in [False, True]:
                        field = renderer.empty_light.copy()
                        mask = coordinates[2 - axis] <= HALF[axis] if sign > 0 else coordinates[2 - axis] >= HALF[axis]
                        field[mask, 3] = -2 if verified else -1
                        upload(field)
                        values = []
                        for tangent in [.125, .5, .875]:
                            point = np.array([tangent, tangent, tangent])
                            point[axis] = height if sign > 0 else 1 - height
                            value = float(renderer.sample(after, point, normal)[0])
                            assert abs(value - 1) < 2e-6, (axis, sign, height, verified, tangent, value)
                            values.append(value)
                            old_minimum = min(old_minimum, float(renderer.sample(before, point, normal)[0]))
                        checks.append({'case': 'flat partial/full receiver has no self-shadow pattern',
                                       'axis': axis, 'sign': sign, 'height': height, 'verified_blocker': verified,
                                       'maximum_error': float(np.max(np.abs(np.array(values) - 1)))})
        assert old_minimum < .6, old_minimum
        checks.append({'case': 'r2 artifact reproduced before fix', 'minimum_old_flat_surface_visibility': old_minimum})

        field = renderer.empty_light.copy()
        field[:, :HALF[1], :, 3] = -2
        field[HALF[2], HALF[1], HALF[0] - 1, 3] = -1
        upload(field)
        point = (.1, 0, .5)
        assert abs(float(renderer.sample(after, point)[0]) - 1) < 2e-6
        field[HALF[2], HALF[1], HALF[0] - 1, 3] = -2
        upload(field)
        assert float(renderer.sample(after, point)[0]) < .85
        checks.append({'case': 'partial neighboring blocker excluded; full neighboring block retains shade'})
        field[:, :, :HALF[0], 3] = -2
        upload(field)
        reference = renderer.sample(after, (.1, 1, .5))[0]
        for height in [1 / 16, .125, .5]:
            value = renderer.sample(after, (.1, height, .5))[0]
            assert abs(float(value - reference)) < 2e-6
        checks.append({'case': 'structural wall shade retained on inset receivers'})

        caster = program([(variant_source(SHADERS / 'shadow.vsh', {}), '.vsh'),
                          (variant_source(SHADERS / 'shadow.fsh', {}), '.fsh')])
        compute = program([(expand(SHADERS / 'shadowcomp.csh'), '.csh')])
        for material, code, alpha in [(0, 1, -1), (10028, 255, -2), (10025, 131, 0), (10029, 0, 0)]:
            renderer.reset()
            cell = renderer.capture(caster, material)
            assert renderer.read(0)[cell] == code
            renderer.step(compute)
            assert renderer.current()[cell][3] == alpha
            if material == 10025:
                assert renderer.lamp_field()[cell][3] == 63
            checks.append({'case': 'actual shadow capture and compute marker', 'material': material,
                           'occupancy': code, 'alpha': alpha})
        from small_light_shapes import selectors
        small = selectors()
        mapped = next(line.split('=', 1)[1].split() for line in (SHADERS / 'block.properties').read_text().splitlines()
                      if line.startswith('block.10029='))
        assert mapped == small
        assert 'minecraft:flower_pot' in small and 'minecraft:iron_chain' in small
        assert not any(name in small for name in ['minecraft:stone', 'minecraft:quartz_pillar',
                                                  'minecraft:oak_door', 'minecraft:cobblestone_wall'])
        fields = []
        for material in [10029, 0]:
            renderer.reset()
            cell = renderer.capture(caster, material)
            renderer.voxels = renderer.read(0)
            source_cell = list(cell)
            source_cell[2] -= 1
            renderer.voxels[tuple(source_cell)] = 132
            renderer.upload(0, renderer.voxels)
            for _ in range(16):
                renderer.step(compute)
            fields.append(renderer.lamp_field())
        receiver = list(cell)
        receiver[2] += 1
        assert np.linalg.norm(fields[0][tuple(receiver)][:3]) > np.linalg.norm(fields[1][tuple(receiver)][:3])
        checks.append({'case': 'model-verified small objects preserve direct soul-light paths', 'selectors': len(small)})
        transported = []
        for code in [1, 255]:
            renderer.reset()
            renderer.voxels[:, :, HALF[0] - 1] = code
            renderer.voxels[HALF[2], HALF[1], HALF[0] + 2] = 2
            renderer.upload(0, renderer.voxels)
            for _ in range(10):
                renderer.step(compute)
            transported.append(renderer.current())
        assert np.max(np.abs(transported[0][..., :3] - transported[1][..., :3])) == 0
        levels = [np.maximum(v[..., 3], 0) for v in transported]
        assert np.array_equal(levels[0], levels[1])
        checks.append({'case': 'verified marker retains identical colored-light propagation and radius'})
        report = {'passed': True, 'checks': checks,
                  'scope': 'Real OpenGL receiver/capture/compute tests, six face directions and partial heights; Minecraft screenshot comparison remains pending.'}
        (ROOT / 'validation-indoor-shapes.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': True, 'checks': len(checks), 'old_flat_visibility_minimum': old_minimum}, indent=2))
    finally:
        for selected in programs:
            driver.delete_program(selected)
        for handle in stages:
            driver.delete_shader(handle)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    run()
