"""Exercise model-derived partial cells, sealed faces and inset receivers on the GPU."""
import ctypes as ct
import json
from pathlib import Path
import re
import zipfile
import numpy as np
from lamp_gpu_checks import LampRenderer
from pbr_checks import VERTEX
from validate import Driver, SHADERS, expand, variant_source

ROOT = Path(__file__).resolve().parents[1]


def run():
    driver = Driver()
    renderer = LampRenderer(driver)
    stages, programs, checks = [], [], []
    archive = zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.8.4-r6.zip')
    masks = [int(v) for v in re.search(r'\]\(([^)]*)\)', (SHADERS / 'lib/block_shapes.glsl').read_text())[1].replace('u', '').split(',')]

    def saved(name):
        text = archive.read('shaders/' + name).decode().replace('\r', '')
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$', lambda m: saved(m[1].lstrip('/')), text, flags=re.M)

    def program(parts):
        selected = driver.create_program()
        programs.append(selected)
        for text, kind in parts:
            if kind == '.csh':
                handle = driver.create_shader(0x91B9)
                encoded = text.encode()
                pointer, length = ct.c_char_p(encoded), ct.c_int(len(encoded))
                driver.shader_source(handle, 1, ct.byref(pointer), ct.byref(length))
                driver.compile_shader(handle)
                status, log = ct.c_int(), ct.create_string_buffer(65536)
                driver.get_shader(handle, 0x8B81, ct.byref(status))
                driver.shader_log(handle, len(log), None, log)
                assert status.value and not log.value, log.value.decode()
            else:
                handle, warning = driver.compile(text, kind, 'partial light shape')
                assert not warning, warning
            stages.append(handle)
            driver.attach_shader(selected, handle)
        driver.link_program(selected)
        status, log = ct.c_int(), ct.create_string_buffer(65536)
        driver.get_program(selected, 0x8B82, ct.byref(status))
        driver.program_log(selected, len(log), None, log)
        assert status.value and not log.value, log.value.decode()
        return selected

    def sampler(old=False):
        source = saved if old else lambda name: expand(SHADERS / name)
        prefix = '#version 330 compatibility\n' + source('lib/settings.glsl')
        prefix += '\nuniform vec3 cameraPosition;uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n'
        prefix += source('lib/emissive_light.glsl')
        prefix += '\nuniform vec3 testPosition,testNormal;out vec4 result;void main(){result=xonLampLight(testPosition,testNormal);}'
        return program([(source('final.vsh'), '.vsh'), (prefix, '.fsh')])

    def upload_lamp(field):
        for index in range(2):
            renderer.active_texture(0x84CD + index)
            renderer.bind_texture(0x806F, renderer.lamps[index])
            renderer.sub3d(0x806F, 0, 0, 0, 0, 96, 48, 96, 0x1908, 0x1406, field.ctypes.data)
        renderer.barrier(0xFFFFFFFF)
        renderer.frame = 2

    def contact(data):
        renderer.active_texture(0x84CF)
        renderer.bind_texture(0x806F, renderer.contact[0])
        renderer.sub3d(0x806F, 0, 0, 0, 0, 96, 48, 96, 0x8D94, 0x1405, data.ctypes.data)
        renderer.barrier(0xFFFFFFFF)

    try:
        compute = program([(expand(SHADERS / 'shadowcomp.csh'), '.csh')])
        caster = program([(variant_source(SHADERS / 'shadow.vsh', {}), '.vsh'), (variant_source(SHADERS / 'shadow.fsh', {}), '.fsh')])
        trapdoor_masks = [85, 170, 51, 204, 15, 240]
        captures = [(i, mask, 10 + i, [11000 + i, 11100 + i], False) for i, mask in enumerate(masks)]
        captures += [(masks.index(mask), mask, 64 + i, [11200 + i], True) for i, mask in enumerate(trapdoor_masks)]
        for index, mask, occupancy, materials, thin in captures:
            for material in materials:
                renderer.reset()
                cell = renderer.capture(caster, material)
                assert renderer.read(0)[cell] == occupancy
            for axis in range(3):
                for sign in [-1, 1]:
                    renderer.reset()
                    renderer.voxels[:] = 255
                    renderer.voxels[48, 24, 48] = occupancy
                    source = [48, 24, 48]
                    source[2 - axis] += sign
                    renderer.voxels[tuple(source)] = 132
                    renderer.upload(0, renderer.voxels)
                    for _ in range(4):
                        renderer.step(compute)
                    value = renderer.lamp_field()[48, 24, 48]
                    assert np.signbit(value[3]), (mask, value)
                    rgb = value[:3]
                    if axis == 0 and sign == -1:
                        metadata = renderer.contact_fallback.copy()
                        renderer.active_texture(0x84CF)
                        renderer.bind_texture(0x806F, renderer.contact[0])
                        renderer.get_texture(0x806F, 0, 0x8D94, 0x1405, metadata.ctypes.data)
                        packed = int(metadata[48, 24, 48])
                        assert packed >> 27 == index + 1
                        assert bool(packed & (1 << 13)) == thin
                        if thin:
                            packed &= ~(1 << 13)
                        expected_contact = 0
                        for plane in range(3):
                            for v in range(-1, 2):
                                for u in range(-1, 2):
                                    offset = [(0, u, v), (u, 0, v), (u, v, 0)][plane]
                                    cell = (48 + offset[2], 24 + offset[1], 48 + offset[0])
                                    if renderer.voxels[cell] == 255:
                                        expected_contact |= 1 << (plane * 9 + (v + 1) * 3 + u + 1)
                        assert packed & ((1 << 27) - 1) == expected_contact
                    face = [bit for bit in range(8) if bool(bit & (1 << axis)) == (sign > 0)]
                    expected = any(not mask & (1 << bit) for bit in face)
                    assert (max(rgb) > 0) == expected, (mask, axis, sign, rgb, expected)
            checks.append({'case': 'captured shape receives light only through open faces', 'mask': mask, 'thin': thin})
        panels = [(51, 1, 1), (204, 1, -1), (85, 0, 1), (170, 0, -1), (15, 2, 1), (240, 2, -1)]
        for thin, mask, axis, sign in [(thin, *panel) for thin in [False, True] for panel in panels]:
            renderer.reset()
            centre = [48, 24, 48]
            plane = [slice(None)] * 3
            plane[2 - axis] = centre[2 - axis]
            renderer.voxels[tuple(plane)] = 64 + trapdoor_masks.index(mask) if thin else 10 + masks.index(mask)
            source = centre.copy()
            source[2 - axis] += sign
            renderer.voxels[tuple(source)] = 132
            renderer.upload(0, renderer.voxels)
            for _ in range(20):
                renderer.step(compute)
            sealed = [slice(None)] * 3 + [slice(None, 3)]
            sealed[2 - axis] = slice(None, centre[2 - axis]) if sign > 0 else slice(centre[2 - axis] + 1, None)
            assert np.max(renderer.lamp_field()[tuple(sealed)]) == 0
            checks.append({'case': 'continuous partial panel seals its solid side', 'mask': mask, 'thin': thin})
        samplers = [sampler(True), sampler(False)]
        terrains = []
        for old in [True, False]:
            text = saved('gbuffers_terrain.fsh') if old else expand(SHADERS / 'gbuffers_terrain.fsh')
            for name, value in {'XON_SHADOWS': False, 'XON_CLOUD_STYLE': 0, 'XON_ANISOTROPIC': 0, 'XON_ADVANCED_MATERIALS': False}.items():
                text = re.sub(rf'^(?://)?#define {name}\b[^\n]*$', '#undef ' + name if value is False else f'#define {name} {value}', text, flags=re.M)
            terrains.append(program([(VERTEX, '.vsh'), (text, '.fsh')]))
        renderer.width, renderer.height = 1, 1
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, 1, 1, 0, 0x1908, 0x1406, None)
        receiver_cases = 0
        minimum = 1.0
        for index, mask in enumerate(masks):
            for bit in range(8):
                if not mask & (1 << bit):
                    continue
                for axis in range(3):
                    neighbor = bit ^ (1 << axis)
                    if mask & (1 << neighbor):
                        continue
                    sign = 1 if neighbor & (1 << axis) else -1
                    point = [.25 + .5 * ((bit >> a) & 1) for a in range(3)]
                    point[axis] = .5
                    normal = np.eye(3)[axis] * sign
                    field = renderer.empty_light.copy()
                    field[:] = [.12, .18, .20, 188]
                    blocked = [48, 24, 48]
                    blocked[2 - axis] += sign
                    field[tuple(blocked)] = [0, 0, 0, -1]
                    field[48, 24, 48, 3] = -188
                    upload_lamp(field)
                    meta = renderer.contact_fallback.copy()
                    meta[48, 24, 48] = (index + 1) << 27
                    contact(meta)
                    before, after = [renderer.sample(p, point, normal) for p in samplers]
                    assert np.max(before) == 0 and np.min(after) > .05, (mask, point, normal, before, after)
                    minimum = min(minimum, float(np.min(after)))
                    receiver_cases += 1
        checks.append({'case': 'R6 dark inset faces reproduced and lit inside the actual empty half', 'faces': receiver_cases, 'minimum_channel': minimum})
        thin_cases = 0
        for mask, axis, sign in panels:
            index = masks.index(mask)
            for corner in range(4):
                point = [.25, .25, .25]
                tangents = [a for a in range(3) if a != axis]
                for n, tangent in enumerate(tangents):
                    point[tangent] += .5 * ((corner >> n) & 1)
                point[axis] = 3 / 16 if sign > 0 else 13 / 16
                normal = np.eye(3)[axis] * sign
                field = renderer.empty_light.copy()
                field[:] = [.12, .18, .20, 188]
                blocked = [48, 24, 48]
                blocked[2 - axis] += sign
                field[tuple(blocked)] = [0, 0, 0, -1]
                field[48, 24, 48, 3] = -188
                upload_lamp(field)
                meta = renderer.contact_fallback.copy()
                meta[48, 24, 48] = ((index + 1) << 27) | (1 << 13)
                contact(meta)
                before, after = [renderer.sample(p, point, normal) for p in samplers]
                assert np.max(before) == 0 and np.min(after) > .05, (mask, point, normal, before, after)
                thin_cases += 1
        checks.append({'case': '3/16 trapdoor surfaces sample their empty side in all six orientations', 'faces': thin_cases})
        face_shader = '#version 330 compatibility\n' + expand(SHADERS / 'lib/block_shapes.glsl') + '''
out vec4 result;
void main(){
 uint count=uint(XON_SHAPE_COUNT),test=uint(gl_FragCoord.x),a=test%count,b=(test/count)%count,face=test/(count*count);
 result=vec4(float(xonShapeFaceOpen(255u^XON_SHAPE_SOLID[a],255u^XON_SHAPE_SOLID[b],int(face/2u),(face&1u)!=0u)));
}
'''
        face_program = program([(expand(SHADERS / 'final.vsh'), '.vsh'), (face_shader, '.fsh')])
        renderer.width, renderer.height = len(masks) ** 2 * 6, 1
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, renderer.width, 1, 0, 0x1908, 0x1406, None)
        renderer.setup(face_program)
        actual = renderer.draw(raw=True)[0, :, 0]
        for test in range(renderer.width):
            first, second, face = test % len(masks), (test // len(masks)) % len(masks), test // len(masks) ** 2
            axis, positive = face // 2, bool(face & 1)
            expected = False
            for octant in range(8):
                coordinate = [(octant >> a) & 1 for a in range(3)]
                if bool(coordinate[axis]) != positive or masks[first] & (1 << octant):
                    continue
                coordinate[axis] = 1 - coordinate[axis]
                neighbor = sum(value << a for a, value in enumerate(coordinate))
                expected |= not bool(masks[second] & (1 << neighbor))
            assert bool(actual[test]) == expected, (first, second, face)
        checks.append({'case': 'all shape pairs match geometric face apertures', 'pairs': renderer.width})
        renderer.width, renderer.height = 1920, 1080
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, 1920, 1080, 0, 0x1908, 0x1406, None)
        renderer.viewport(0, 0, 1920, 1080)
        field = renderer.empty_light.copy()
        field[:] = [.12, .18, .20, 188]
        upload_lamp(field)
        contact(renderer.contact_fallback)
        renderer.upload(1, renderer.empty_light)
        renderer.upload(2, renderer.empty_light)
        renderer.texture(8, np.full((16, 16, 4), [.85, .83, .78, 1], np.float32))
        query = ct.c_uint()
        gen = driver.function('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin = driver.function('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end = driver.function('glEndQuery', None, ct.c_uint)
        read = driver.function('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete = driver.function('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        gen(1, ct.byref(query))
        timings = [[], [], [], []]
        try:
            for repeat in range(26):
                for version in ([0, 1, 2, 3] if repeat % 2 == 0 else [3, 2, 1, 0]):
                    renderer.setup((samplers + terrains)[version])
                    renderer.uniform1i(renderer.location('frameCounter'), 1)
                    renderer.uniform3f(renderer.location('testPosition'), .5, 0, .5)
                    renderer.uniform3f(renderer.location('testNormal'), 0, 1, 0)
                    renderer.uniform3f(renderer.location('sunPosition'), 30, 90, 20)
                    for name, value in [('testBlock', .7), ('testAO', 1), ('alphaTestRef', .1), ('far', 1024), ('fogStart', 800), ('fogEnd', 1024)]:
                        renderer.uniform1f(renderer.location(name), value)
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
                        timings[version].append(value.value / 4e6)
        finally:
            delete(1, ct.byref(query))
        timing = {'kind': '1080p open-air sampler proxy, not full-game FPS',
                  'R6_ms': float(np.median(timings[0])), 'candidate_ms': float(np.median(timings[1])),
                  'paired_median_ratio': float(np.median(np.array(timings[1]) / timings[0]))}
        timing['terrain_R6_ms'] = float(np.median(timings[2]))
        timing['terrain_candidate_ms'] = float(np.median(timings[3]))
        timing['terrain_paired_ratio'] = float(np.median(np.array(timings[3]) / timings[2]))
        result = {'passed': True, 'checks': checks, 'timing': timing, 'scope': 'Model/capture/compute/sampler GPU fixtures; live room verification remains pending.'}
        (ROOT / 'validation-partial-light.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({'passed': True, 'shape_classes': len(masks), 'inset_faces': receiver_cases, 'timing': timing}))
    finally:
        for p in programs:
            driver.delete_program(p)
        for s in stages:
            driver.delete_shader(s)
        renderer.close()
        driver.close()
        archive.close()


if __name__ == '__main__':
    run()
