"""Execute 1.8 lamp transport, ore isolation and a six-lantern 20x20 room on OpenGL."""
import ctypes as ct
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from PIL import Image, ImageDraw

from brightness_checks import display_luma
from pbr_checks import VERTEX
from validate import Driver, SHADERS, expand, variant_source
from voxel_gpu_checks import VoxelRenderer, SIZE, HALF

ROOT = Path(__file__).resolve().parents[1]


class LampRenderer(VoxelRenderer):
    def __init__(self, driver):
        super().__init__(driver)
        self.contact = (ct.c_uint * 1)()
        self.gen_textures(1, self.contact)
        self.contact_fallback = np.zeros(self.voxels.shape, dtype=np.uint32)
        self.active_texture(0x84CF)
        self.bind_texture(0x806F, self.contact[0])
        for axis in [0x2800, 0x2801]:
            self.tex_parameter(0x806F, axis, 0x2600)
        for axis in [0x2802, 0x2803, 0x8072]:
            self.tex_parameter(0x806F, axis, 0x812F)
        self.image3d(0x806F, 0, 0x8236, *SIZE, 0, 0x8D94, 0x1405, self.contact_fallback.ctypes.data)
        self.bind_image(5, self.contact[0], 0, 1, 0, 0x88BA, 0x8236)
        self.lamps = (ct.c_uint * 2)()
        self.gen_textures(2, self.lamps)
        for index in range(2):
            self.active_texture(0x84CD + index)
            self.bind_texture(0x806F, self.lamps[index])
            for axis in [0x2800, 0x2801]:
                self.tex_parameter(0x806F, axis, 0x2600)
            for axis in [0x2802, 0x2803, 0x8072]:
                self.tex_parameter(0x806F, axis, 0x812F)
            self.image3d(0x806F, 0, 0x881A, *SIZE, 0, 0x1908, 0x1406, self.empty_light.ctypes.data)
            self.bind_image(index + 3, self.lamps[index], 0, 1, 0, 0x88BA, 0x881A)

    def setup(self, selected):
        super().setup(selected)
        for name, unit in [('xonLampTex0', 13), ('xonLampTex1', 14), ('xonLampImg0', 3), ('xonLampImg1', 4)]:
            self.uniform1i(self.location(name), unit)
        self.uniform1i(self.location('xonContactTex'), 15)
        self.uniform1i(self.location('xonContactImg'), 5)

    def reset(self):
        super().reset()
        self.active_texture(0x84CF)
        self.bind_texture(0x806F, self.contact[0])
        self.sub3d(0x806F, 0, 0, 0, 0, *SIZE, 0x8D94, 0x1405, self.contact_fallback.ctypes.data)
        for index in range(2):
            self.active_texture(0x84CD + index)
            self.bind_texture(0x806F, self.lamps[index])
            self.sub3d(0x806F, 0, 0, 0, 0, *SIZE, 0x1908, 0x1406, self.empty_light.ctypes.data)
        self.barrier(0xFFFFFFFF)

    def lamp_field(self):
        index = (self.frame - 1) & 1
        self.active_texture(0x84CD + index)
        self.bind_texture(0x806F, self.lamps[index])
        data = np.empty_like(self.empty_light)
        self.get_texture(0x806F, 0, 0x1908, 0x1406, data.ctypes.data)
        return data

    def upload_contact(self, blocked):
        mask = np.zeros(blocked.shape, dtype=np.uint32)
        for axis in range(3):
            tangents = [a for a in range(3) if a != axis]
            for u in [-1, 0, 1]:
                for v in [-1, 0, 1]:
                    offset = np.zeros(3, dtype=int)
                    offset[tangents] = [u, v]
                    origin, target = [], []
                    for step, length in zip(offset[::-1], blocked.shape):
                        origin.append(slice(max(step, 0), length + min(step, 0)))
                        target.append(slice(max(-step, 0), length - max(step, 0)))
                    bit = axis * 9 + (v + 1) * 3 + u + 1
                    mask[tuple(target)] |= blocked[tuple(origin)].astype(np.uint32) << bit
        self.active_texture(0x84CF)
        self.bind_texture(0x806F, self.contact[0])
        self.sub3d(0x806F, 0, 0, 0, 0, *SIZE, 0x8D94, 0x1405, mask.ctypes.data)
        self.barrier(0xFFFFFFFF)

    def close(self):
        self.delete_textures(1, self.contact)
        self.delete_textures(2, self.lamps)
        super().close()


def run():
    driver = Driver()
    renderer = LampRenderer(driver)
    stages, programs, checks = [], [], []
    archive = zipfile.ZipFile(ROOT.parent / 'XON-1.8-before.zip')

    def saved(name):
        text = archive.read('shaders/' + name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$', lambda m: saved(m[1].lstrip('/')), text, flags=re.M)

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
                handle, warning = driver.compile(source, kind, 'lamp 1.8 GPU')
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

    def settle(selected, count=16):
        renderer.upload(0, renderer.voxels)
        for _ in range(count):
            renderer.step(selected)

    def terrain(old, vertex=VERTEX, room=False):
        source = saved('gbuffers_terrain.fsh') if old else expand(SHADERS / 'gbuffers_terrain.fsh')
        for key, value in {'XON_SHADOWS': False, 'XON_ANISOTROPIC': 0, 'XON_CLOUD_STYLE': 0,
                           'XON_ADVANCED_MATERIALS': False}.items():
            source = re.sub(rf'^(?://)?#define {key}\b[^\n]*$', '#undef ' + key if value is False else f'#define {key} {value}', source, flags=re.M)
        if room:
            prefix, body = source.rsplit('void main() {', 1)
            source = prefix + '''void main() {
 vec3 lamps[6]=vec3[6](vec3(-6,3,-6),vec3(0,3,-6),vec3(6,3,-6),vec3(-6,3,6),vec3(0,3,6),vec3(6,3,6));
 float distanceToLamp=100;
 for(int i=0;i<6;++i){vec3 d=abs(xonPlayerPosition+vec3(0,.5,0)-(lamps[i]+.5));distanceToLamp=min(distanceToLamp,d.x+d.y+d.z);}
 vec2 roomLightLevels=vec2(clamp((15-distanceToLamp)/15,0,1),0);
''' + body.replace('xonLightLevels', 'roomLightLevels')
        return program([(vertex, '.vsh'), (source, '.fsh')])

    def draw(selected):
        renderer.setup(selected)
        renderer.uniform1i(renderer.location('frameCounter'), renderer.frame - 1)
        for name, value in [('testBlock', .9), ('testSky', 0), ('testAO', 1), ('testMaterial', 0),
                            ('testTangent', 1), ('alphaTestRef', .1), ('far', 1024), ('fogStart', 800), ('fogEnd', 1024)]:
            renderer.uniform1f(renderer.location(name), value)
        for name, value in [('testPosition', (0, 0, -8)), ('testNormal', (0, 1, 0)), ('sunPosition', (30, 90, 20))]:
            renderer.uniform3f(renderer.location(name), *value)
        return renderer.draw(raw=True)[..., :3]

    def measure(actions, batches=16, repetitions=4):
        f = driver.function
        gen = f('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin = f('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end = f('glEndQuery', None, ct.c_uint)
        read = f('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete = f('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        queries = (ct.c_uint * (batches * len(actions)))()
        gen(len(queries), queries)
        for setup, action in actions:
            setup()
            for _ in range(8):
                action()
        for iteration in range(batches):
            order = range(len(actions)) if iteration % 2 == 0 else reversed(range(len(actions)))
            for version in order:
                setup, action = actions[version]
                setup()
                begin(0x88BF, queries[iteration * len(actions) + version])
                for _ in range(repetitions):
                    action()
                end(0x88BF)
        times = [[] for _ in actions]
        for iteration in range(batches):
            for version in range(len(actions)):
                value = ct.c_uint64()
                read(queries[iteration * len(actions) + version], 0x8866, ct.byref(value))
                times[version].append(value.value / (repetitions * 1e6))
        delete(len(queries), queries)
        return [{'median_ms': float(np.median(t)), 'p95_ms': float(np.percentile(t, 95))} for t in times]

    try:
        before_compute = program([(saved('shadowcomp.csh'), '.csh')])
        compute = program([(expand(SHADERS / 'shadowcomp.csh'), '.csh')])
        for folder in ['', 'world-1/', 'world1/']:
            caster = program([(expand(SHADERS / (folder + 'shadow.vsh')), '.vsh'),
                              (expand(SHADERS / (folder + 'shadow.fsh')), '.fsh')])
            legacy = [(10006, 1), (10024, 2), (10025, 3), (10026, 4), (10027, 5),
                      (10019, 6), (10020, 7), (10023, 8), (10005, 24), (10021, 41)]
            for material, family in legacy + [(id, id - 10021) for id in range(10030, 10097)]:
                renderer.reset()
                cell = renderer.capture(caster, material, world_block=(-3, 1, -4), camera=(-2.2, .1, -1.9))
                assert renderer.read(0)[cell] == 128 + family, (folder, material)
            for material, expected in [(10021, 169), (10005, 152), (0, 0)]:
                renderer.reset()
                cell = renderer.capture(caster, material, stage=4)
                assert renderer.read(0)[cell] == expected
            checks.append({'case': 'all source IDs captured at negative world coordinates; translucent sources included without water/glass occupancy',
                           'dimension_folder': folder, 'source_materials': 77})
        peaks, reaches = {}, {}
        for family in range(1, 76):
            renderer.reset()
            renderer.voxels[48, 24, 48] = 128 + family
            settle(compute)
            field = renderer.lamp_field()
            line = field[48, 24, 48:64, :3]
            luminance = line @ np.array([.2126, .7152, .0722])
            assert np.isfinite(field).all() and np.min(field[..., :3]) >= 0
            assert np.max(np.diff(luminance)) <= .00001, (family, luminance)
            assert luminance[0] > 0 and luminance[-1] == 0
            assert np.max(np.abs(renderer.current()[..., :3])) == 0, 'Lamp leaked into ore field'
            peaks[family] = float(luminance[0])
            reaches[family] = int(np.max(np.where(luminance > .0001)[0]))
            checks.append({'case': 'finite monotonic source-specific pool, no ore contamination', 'family': family,
                           'peak_linear_luminance': peaks[family], 'visible_axis_extent': reaches[family]})
        assert peaks[1] < peaks[2] < peaks[3]
        assert reaches[1] < reaches[2] < reaches[3]
        checks.append({'case': 'lichen and berries are softer and smaller than lanterns'})

        for emitter in range(2, 10):
            fields = []
            for selected in [before_compute, compute]:
                renderer.reset()
                renderer.voxels[48, 24, 48] = emitter
                renderer.voxels[:, :, 52] = 255
                settle(selected)
                fields.append(renderer.current())
            assert np.array_equal(fields[0], fields[1]), emitter
            assert np.max(renderer.lamp_field()[..., :3]) == 0, 'Ore leaked into lamp field'
            checks.append({'case': 'ore transport bit-for-bit retained, with wall', 'emitter': emitter})

        renderer.reset()
        renderer.voxels[48, 24, 48] = 131
        renderer.voxels[:, :, 51] = 255
        settle(compute)
        assert np.max(renderer.lamp_field()[:, :, 52:, :3]) == 0
        renderer.voxels.fill(0)
        settle(compute)
        assert np.max(renderer.lamp_field()[..., :3]) == 0
        checks.append({'case': 'solid wall blocking and removed-lamp history clearing'})

        prefix = '#version 330 compatibility\n' + expand(SHADERS / 'lib/settings.glsl')
        prefix += '\nuniform vec3 cameraPosition;uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n'
        prefix += expand(SHADERS / 'lib/emissive_light.glsl')
        sampler = program([(expand(SHADERS / 'final.vsh'), '.vsh'), (prefix + '''
uniform vec3 testPosition,testNormal;
out vec4 result;
void main(){result=xonLampLight(testPosition,testNormal);}
''', '.fsh')])
        for family in [6, 7, 8, 21]:
            renderer.reset()
            renderer.voxels[48, 24, 48] = 128 + family
            settle(compute)
            rgb = renderer.sample(sampler, (.5, -.5, .5))
            assert np.max(rgb) > 0
            assert renderer.draw(raw=True)[0, 0, 3] == 0
        checks.append({'case': 'decorative quartz/crystal/sculk/wire auras never claim native block-light coverage'})
        renderer.reset()
        renderer.voxels[48, 24, 48] = 131
        settle(compute)
        reference = renderer.sample(sampler, (1.73, -.5, .51))
        for camera in [(.1, -.2, .3), (.99, -.99, .49), (1.01, -1.01, .51), (-1.01, 1.01, -.51)]:
            renderer.reset()
            cell = HALF - np.floor(camera).astype(int)
            renderer.voxels[tuple(cell[::-1])] = 131
            renderer.upload(0, renderer.voxels)
            previous = (0, 0, 0)
            for _ in range(16):
                renderer.step(compute, camera, previous)
                previous = camera
            actual = renderer.sample(sampler, np.array([1.73, -.5, .51]) - camera, camera=camera)
            assert np.max(np.abs(actual - reference)) < .001, (camera, actual, reference)
        checks.append({'case': 'stable world-space lamp sampling across fractional and negative camera coordinates'})

        renderer.reset()
        renderer.voxels[48, 24, 48] = 131
        settle(compute)
        renderer.voxels.fill(0)
        renderer.voxels[48, 24, 47] = 131
        renderer.upload(0, renderer.voxels)
        renderer.step(compute, (1.1, 0, 0), (0, 0, 0))
        actual = renderer.sample(sampler, (.63, -.5, .51), camera=(1.1, 0, 0))
        assert np.max(np.abs(actual - reference)) < .001, (actual, reference)
        checks.append({'case': 'history reprojects immediately when crossing a block boundary'})

        renderer.reset()
        renderer.voxels[48, 24, 45] = 131
        renderer.voxels[48, 24, 51] = 132
        settle(compute)
        samples = np.array([renderer.sample(sampler, (x, -.5, .5)) for x in np.linspace(-4, 5, 181)])
        assert np.isfinite(samples).all() and np.min(samples) >= 0
        assert np.max(np.abs(np.diff(samples, axis=0))) < .07
        assert samples[15, 0] > samples[15, 2] and samples[-16, 2] > samples[-16, 0], samples[[15, -16]]
        steady = renderer.lamp_field()
        for _ in range(16):
            renderer.step(compute)
            assert np.array_equal(renderer.lamp_field(), steady), 'Steady mixed lights flicker'
        renderer.step(compute, (100, 100, 100))
        assert np.max(renderer.lamp_field()[renderer.voxels == 0, :3]) == 0
        checks.append({'case': 'warm/cyan boundary interpolates continuously; teleport rejects stale history',
                       'maximum_subblock_rgb_step': float(np.max(np.abs(np.diff(samples, axis=0))))})

        first_archive = zipfile.ZipFile(ROOT.parent / 'XON-1.8-first-pools.zip')

        def first_saved(name):
            value = first_archive.read('shaders/' + name).decode()
            return re.sub(r'^\s*#include\s+"([^"]+)"\s*$', lambda m: first_saved(m[1].lstrip('/')), value, flags=re.M)

        def surface_probe(old, ore=False):
            text = '#version 330 compatibility\n' + (first_saved('lib/settings.glsl') if old else expand(SHADERS / 'lib/settings.glsl'))
            text += '\nuniform vec3 cameraPosition;uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n'
            text += first_saved('lib/emissive_light.glsl') if old else expand(SHADERS / 'lib/emissive_light.glsl')
            call = 'vec4(xonEmissiveLight(testPosition,testNormal),0)' if ore else ('xonLampLight(testPosition,testNormal)' if old else 'xonLampLight(testPosition,testNormal,uint(testFamily))')
            text += '''
uniform vec3 testPosition,testNormal;uniform float testFamily;uniform int testAlpha;
out vec4 result;
void main(){vec4 light=''' + call + ''';result=testAlpha==1?vec4(light.aaa,1):vec4(light.rgb,1);}
'''
            return program([(expand(SHADERS / 'final.vsh'), '.vsh'), (text, '.fsh')])

        probes = [[surface_probe(old, ore) for old in [True, False]] for ore in [False, True]]
        first_archive.close()

        def lamp_upload(field):
            for index in range(2):
                renderer.active_texture(0x84CD + index)
                renderer.bind_texture(0x806F, renderer.lamps[index])
                renderer.sub3d(0x806F, 0, 0, 0, 0, *SIZE, 0x1908, 0x1406, field.ctypes.data)
            renderer.barrier(0xFFFFFFFF)

        coordinates = np.indices(renderer.voxels.shape)
        old_minimum = 1.0
        for axis in range(3):
            for sign in [-1, 1]:
                normal = np.eye(3)[axis] * sign
                mask = coordinates[2 - axis] <= HALF[axis] if sign > 0 else coordinates[2 - axis] >= HALF[axis]
                lamp_field = renderer.empty_light.copy()
                lamp_field[...] = [.8, .55, .2, 63]
                lamp_field[mask] = [0, 0, 0, -1]
                lamp_upload(lamp_field)
                ore_field = renderer.empty_light.copy()
                ore_field[...] = [.8, .55, .2, 1]
                ore_field[mask] = [0, 0, 0, -1]
                renderer.upload(1, ore_field)
                renderer.upload(2, ore_field)
                for height in [1 / 16, .125, .5, 1.0]:
                    point = np.full(3, .5)
                    point[axis] = height if sign > 0 else 1 - height
                    for ore, pair_probes in enumerate(probes):
                        before, after = [renderer.sample(p, point, normal) for p in pair_probes]
                        expected = np.array([.8, .55, .2])
                        assert np.max(np.abs(after - expected)) < .001, (axis, sign, height, ore, after)
                        old_minimum = min(old_minimum, float(before[0] / .8))
                    checks.append({'case': 'lamp and ore sampling stays uniform on thin/inset/full receivers',
                                   'axis': axis, 'sign': sign, 'height': height})
        assert old_minimum < .1
        checks.append({'case': 'first 1.8 thin-surface darkening reproduced before correction',
                       'minimum_old_uniform_light_ratio': old_minimum})

        lamp_field[...] = [.15, .08, .22, 143]
        lamp_upload(lamp_field)
        renderer.setup(probes[0][1])
        renderer.uniform1f(renderer.location('testFamily'), 8)
        own = renderer.sample(probes[0][1], (.5, 1, .5))
        assert np.max(own) == 0
        lamp_field[...] = [.68, .94, 1, 191]
        lamp_upload(lamp_field)
        other = renderer.sample(probes[0][1], (.5, 1, .5))
        assert other[2] > other[0] > 0
        renderer.uniform1f(renderer.location('testFamily'), 0)
        checks.append({'case': 'quartz excludes its own decorative aura while retaining incoming sea-lantern light'})

        room_vertex = VERTEX.replace('xonViewPosition=testPosition;xonPlayerPosition=testPosition;', '''
 xonPlayerPosition=vec3((uv.x-.5)*20,0,(uv.y-.5)*20);xonViewPosition=xonPlayerPosition+vec3(0,-3,-18);
''')
        pair = [terrain(old, room_vertex, room=True) for old in [True, False]]
        renderer.texture(8, np.full((16, 16, 4), [.55, .52, .46, 1], dtype=np.float32))
        renderer.reset()
        renderer.voxels[:, :HALF[1], :] = 255
        for x in [-6, 0, 6]:
            for z in [-6, 6]:
                renderer.voxels[z + HALF[2], 3 + HALF[1], x + HALF[0]] = 131
        settle(compute)
        images = [draw(p) for p in pair]
        lut = np.asarray(Image.open(SHADERS / 'textures/xon-grade.png'), dtype=float) / 255
        lumas = [display_luma(v, lut, .83, True) for v in images]
        ratios = [float(np.percentile(v, 10) / np.percentile(v, 95)) for v in lumas]
        assert ratios[1] < ratios[0] * .85, ratios
        assert np.percentile(lumas[1], 10) > .23
        assert np.percentile(lumas[1], 95) > .50
        checks.append({'case': 'six lanterns in a 20x20 room retain readable shade and bright pools',
                       'shade_to_pool_ratio_before_after': ratios,
                       'display_luminance_p10_p50_p95_after': [float(np.percentile(lumas[1], p)) for p in [10, 50, 95]]})
        sheet = Image.new('RGB', (1280, 390))
        painter = ImageDraw.Draw(sheet)
        for index, raw in enumerate(images):
            color = np.maximum(raw * (1.05 * .83), 0)
            color = color * (2.51 * color + .03) / (color * (2.43 * color + .59) + .14)
            tile = np.uint8(np.clip(color, 0, 1)[::-1] ** (1 / 2.2) * 255)
            sheet.paste(Image.fromarray(tile), (index * 640, 30))
            painter.text((index * 640 + 12, 8), ['1.7 shared fill / six lanterns', '1.8 source pools / six lanterns'][index] + ' / synthetic 20x20 floor', fill='white')
        sheet.save(ROOT / 'validation-lamp-room.png')

        renderer.width, renderer.height = 1920, 1080
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, 1920, 1080, 0, 0x1908, 0x1406, None)

        def quad():
            renderer.begin(0x0007)
            for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                renderer.tex_coord(x, y)
                renderer.vertex(x, y)
            renderer.end()

        terrain_times = measure([(lambda p=p: draw(p), quad) for p in pair])
        compute_times = measure([(lambda p=p: renderer.setup(p), lambda: (renderer.dispatch(12, 6, 12), renderer.barrier(0xFFFFFFFF)))
                                 for p in [before_compute, compute]])
        report = {'passed': True, 'checks': checks, 'storage_mib': np.prod(SIZE).item() * 37 / 1048576,
                  'synthetic_1080p_terrain_gpu_before_after': terrain_times,
                  'synthetic_room_compute_gpu_before_after': compute_times,
                  'scope': 'Actual source compute and production terrain pixels; dominant-source approximation with block-path distances. Not a Minecraft visual approval or FPS claim.'}
        (ROOT / 'validation-lamp-families.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': True, 'checks': len(checks), 'room': checks[-1],
                          'terrain_gpu': terrain_times, 'compute_gpu': compute_times}, indent=2))
    finally:
        archive.close()
        for selected in programs:
            driver.delete_program(selected)
        for handle in stages:
            driver.delete_shader(handle)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    run()
