"""Compare lighting pixels and interleaved GPU timings against accepted 1.8."""
import ctypes as ct
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from PIL import Image

from lamp_gpu_checks import LampRenderer
from pbr_checks import VERTEX
from validate import Driver, SHADERS, expand
from voxel_gpu_checks import SIZE, HALF

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT.parent / 'XON-1.8-before-optimization.zip'
GRID_VERTEX = VERTEX.replace('xonViewPosition=testPosition;xonPlayerPosition=testPosition;', '''
 vec3 reference=abs(testNormal.y)>.9?vec3(1,0,0):vec3(0,1,0);
 vec3 tangent=normalize(cross(testNormal,reference));vec3 bitangent=cross(testNormal,tangent);
 xonPlayerPosition=testPosition+(uv.x-.5)*12*tangent+(uv.y-.5)*12*bitangent;
 xonViewPosition=xonPlayerPosition+vec3(0,-3,-18);
''')


def run():
    driver = Driver()
    renderer = LampRenderer(driver)
    archive = zipfile.ZipFile(BASELINE)
    stages, programs, checks = [], [], []
    cache = {}

    def saved(name):
        if name not in cache:
            text = archive.read('shaders/' + name).decode()
            cache[name] = re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                                 lambda m: saved(m[1].lstrip('/')), text, flags=re.M)
        return cache[name]

    def source(name, old, options=None):
        value = saved(name) if old else expand(SHADERS / name)
        for key, setting in (options or {}).items():
            replacement = '#undef ' + key if setting is False else '#define ' + key
            if not isinstance(setting, bool):
                replacement += ' ' + str(setting)
            value = re.sub(rf'^(?://)?#define {key}\b[^\n]*$', replacement, value, flags=re.M)
        return value

    def program(parts):
        handles = []
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
                handle, warning = driver.compile(value, kind, '1.8 optimization parity')
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

    def fragment_pair(name, options=None):
        return [program([(GRID_VERTEX, '.vsh'), (source(name, old, options), '.fsh')]) for old in [True, False]]

    def kernel_pair(expression, cache_comparison=False):
        result = []
        for old in [True, False]:
            old_source = old and not cache_comparison
            text = '#version 330 compatibility\n' + source('lib/settings.glsl', old_source)
            text += '\nuniform vec3 cameraPosition;uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n'
            library = source('lib/emissive_light.glsl', old_source)
            if cache_comparison and old:
                start = library.index('            for (int v = -1;', library.index('uint occupancy ='))
                end = library.index('        }\n        for (int layer', start)
                library = library[:start] + library[end:]
            text += library
            text += '\nin vec3 xonPlayerPosition;uniform vec3 testNormal;out vec4 result;\n'
            text += 'void main(){result=vec4(' + expression + ',1);}\n'
            result.append(program([(GRID_VERTEX, '.vsh'), (text, '.fsh')]))
        return result

    def setup(selected, normal=(0, 1, 0), position=(0, 0, 0), sky=0, material=0, vision=0):
        renderer.setup(selected)
        renderer.uniform1i(renderer.location('frameCounter'), renderer.frame - 1)
        renderer.uniform1i(renderer.location('normals'), 10)
        renderer.uniform1i(renderer.location('specular'), 0)
        for name, value in [('testBlock', .85), ('testSky', sky), ('testAO', .9), ('testMaterial', material),
                            ('testTangent', 1), ('alphaTestRef', .1), ('far', 1024), ('fogStart', 800), ('fogEnd', 1024),
                            ('nightVision', vision)]:
            renderer.uniform1f(renderer.location(name), value)
        for name, value in [('testPosition', position), ('testNormal', normal), ('sunPosition', (30, 90, 20)),
                            ('testView', (.45, .2, -1))]:
            renderer.uniform3f(renderer.location(name), *value)
        identity = np.eye(4, dtype=np.float32)
        renderer.uniform_matrix(renderer.location('gbufferModelView'), 1, 0, identity.ctypes.data)

    def compare(pair, label, **options):
        images = []
        for selected in pair:
            setup(selected, **options)
            images.append(renderer.draw(raw=True))
        difference = np.abs(images[1] - images[0])
        maximum = float(np.max(difference))
        assert maximum <= 2e-5, (label, options, maximum, np.unravel_index(difference.argmax(), difference.shape))
        checks.append({'case': label, 'options': options, 'max_linear_pixel_error': maximum,
                       'bit_identical_pixels': bool(np.array_equal(images[0], images[1]))})

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
        delete(48, queries)
        return {'before_ms': float(np.median(times[0])), 'after_ms': float(np.median(times[1])),
                'median_paired_ratio': float(np.median(np.array(times[1]) / times[0])),
                'p95_before_after_ms': [float(np.percentile(t, 95)) for t in times]}

    try:
        compute_pair = [program([(source('shadowcomp.csh', old), '.csh')]) for old in [True, False]]
        scene = np.zeros_like(renderer.voxels)
        scene[:, :HALF[1], :] = 255
        scene[:, :, :HALF[0] - 5] = 255
        scene[HALF[2], HALF[1]:HALF[1] + 8, HALF[0] + 2] = 136
        for x, y, z, code in [(-3, 3, -3, 131), (3, 4, 3, 139), (4, 2, -4, 132),
                               (-2, 2, 4, 130), (-4, 0, 3, 2), (4, 0, 4, 5)]:
            scene[z + HALF[2], y + HALF[1], x + HALF[0]] = code
        fields = []
        for selected in compute_pair:
            renderer.reset()
            renderer.voxels[:] = scene
            renderer.upload(0, renderer.voxels)
            for _ in range(16):
                renderer.step(selected)
            fields.append((renderer.current(), renderer.lamp_field()))
        for field, name in enumerate(['ore', 'lamp']):
            assert np.array_equal(fields[0][field], fields[1][field]), name
            checks.append({'case': 'bit-identical mixed-scene compute transport', 'field': name})

        for family in range(1, 76):
            pair_fields = []
            for selected in compute_pair:
                renderer.reset()
                renderer.voxels[48, 24, 48] = 128 + family
                renderer.upload(0, renderer.voxels)
                for _ in range(16):
                    renderer.step(selected)
                pair_fields.append(renderer.lamp_field())
            assert np.array_equal(pair_fields[0], pair_fields[1]), family
            checks.append({'case': 'bit-identical lamp transport and metadata', 'family': family})

        def check_contact_mask(occupancy, label):
            renderer.reset()
            renderer.voxels[:] = occupancy
            renderer.upload(0, renderer.voxels)
            renderer.step(compute_pair[1])
            renderer.active_texture(0x84CF)
            renderer.bind_texture(0x806F, renderer.contact[0])
            actual = np.empty(occupancy.shape, dtype=np.uint32)
            renderer.get_texture(0x806F, 0, 0x8D94, 0x1405, actual.ctypes.data)
            expected = np.zeros(occupancy.shape, dtype=np.uint32)
            blocked = occupancy == 255
            for axis in range(3):
                tangents = [a for a in range(3) if a != axis]
                for u in [-1, 0, 1]:
                    for v in [-1, 0, 1]:
                        offset = np.zeros(3, dtype=int)
                        offset[tangents] = [u, v]
                        origin, target = [], []
                        for step, length in zip(offset[::-1], occupancy.shape):
                            origin.append(slice(max(step, 0), length + min(step, 0)))
                            target.append(slice(max(-step, 0), length - max(step, 0)))
                        bit = axis * 9 + (v + 1) * 3 + u + 1
                        expected[tuple(target)] |= blocked[tuple(origin)].astype(np.uint32) << bit
            assert np.array_equal(actual, expected), label
            checks.append({'case': 'exhaustive contact-cache oracle', 'layout': label,
                           'voxels': int(occupancy.size)})

        rng = np.random.default_rng(20261104)
        for density in [0.0, .005, .05, .5, 1.0]:
            occupancy = np.where(rng.random(renderer.voxels.shape) < density, 255, 1).astype(np.uint8)
            check_contact_mask(occupancy, 'verified density ' + str(density))
        check_contact_mask(np.zeros_like(scene), 'all blockers removed on next frame')
        renderer.reset()
        renderer.voxels[:] = scene
        renderer.upload(0, renderer.voxels)
        for _ in range(16):
            renderer.step(compute_pair[1])

        kernels = {'contact': kernel_pair('vec3(xonIndoorOcclusion(xonPlayerPosition,testNormal))'),
                   'lamp': kernel_pair('xonLampLight(xonPlayerPosition,testNormal).rgb'),
                   'ore': kernel_pair('xonEmissiveLight(xonPlayerPosition,testNormal)')}
        normals = [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1), (.6, .8, 0),
                   (1e-7, 1, -1e-7), (1, 1e-7, -1e-7), (1e-7, -1e-7, 1), (.001, .9999995, 0)]
        for name, pair in kernels.items():
            for normal in normals:
                for height in [0, 1 / 16, .5]:
                    compare(pair, name + ' kernel', normal=normal, position=(.125, height, .25))

        for unit, value in [(8, [.55, .52, .46, 1]), (10, [.52, .48, 1, .8]), (0, [.3, .04, 0, 1])]:
            renderer.texture(unit, np.full((32, 32, 4), value, dtype=np.float32))
        terrain_pairs = {}
        for pbr in [False, True]:
            for dimension in ['', 'world-1/', 'world1/']:
                pair = fragment_pair(dimension + 'gbuffers_terrain.fsh',
                                     {'XON_ADVANCED_MATERIALS': pbr, 'XON_SHADOWS': False, 'XON_CLOUD_STYLE': 0,
                                      'XON_PARALLAX_DEPTH': '0.50'})
                if not dimension:
                    terrain_pairs['terrain_pbr' if pbr else 'terrain'] = pair
                for options in [{}, {'sky': 1}, {'vision': 1}, {'position': (.1, 1 / 16, .1)},
                                {'normal': (1, 0, 0), 'position': (3, 2, 0)}, {'material': 10023},
                                {'material': 10025}, {'material': 10032}, {'material': 10021}, {'material': 10046}]:
                    compare(pair, 'production terrain ' + dimension + ('PBR' if pbr else 'vanilla'), **options)

        def resize(width, height):
            renderer.width, renderer.height = width, height
            renderer.active_texture(0x84CB)
            renderer.bind_texture(0x0DE1, renderer.textures[11])
            renderer.tex_image(0x0DE1, 0, 0x8814, width, height, 0, 0x1908, 0x1406, None)
            renderer.viewport(0, 0, width, height)

        resize(96, 64)
        pack = Path.home() / 'AppData/Roaming/ModrinthApp/profiles/Ziz/resourcepacks/Primes HD Textures [256x].zip'
        pom_pairs = {}
        for depth in ['0.20', '0.50']:
            pair = []
            for old in [True, False]:
                prefix = '#version 330 compatibility\n#define XON_DIMENSION 0\n'
                prefix += source('lib/settings.glsl', old, {'XON_SHADOWS': False, 'XON_PARALLAX_DEPTH': depth})
                for library in ['uniforms', 'math', 'atmosphere', 'lighting', 'pbr']:
                    prefix += source('lib/' + library + '.glsl', old)
                prefix += '''
in vec2 xonUV;uniform vec3 testView;out vec4 result;
void main(){vec2 hit=xonGetParallaxCoord(xonUV,xonUV,vec4(0,0,1,1),testView,0);result=vec4(hit,0,1);}
'''
                pair.append(program([(source('final.vsh', old), '.vsh'), (prefix, '.fsh')]))
            pom_pairs[depth] = pair
        with zipfile.ZipFile(pack) as textures:
            for material in ['oak_log', 'stone_bricks', 'cobblestone']:
                normal_map = np.asarray(Image.open(io.BytesIO(textures.read(
                    'assets/minecraft/textures/block/' + material + '_n.png'))).convert('RGBA'), dtype=np.float32) / 255
                renderer.texture(10, normal_map)
                for depth, pair in pom_pairs.items():
                    for view in [(0, -.4, -1), (0, -2.5, -1), (.8, -4, -1), (5, .1, -1), (0, 0, -1), (.99, 0, -.05)]:
                        hits = []
                        for selected in pair:
                            setup(selected)
                            renderer.uniform3f(renderer.location('testView'), *view)
                            hits.append(renderer.draw(raw=True))
                        assert np.array_equal(hits[0], hits[1]), (material, depth, view, np.max(np.abs(hits[0] - hits[1])))
                        checks.append({'case': 'bit-identical real Primes POM intersections', 'material': material,
                                       'depth': depth, 'view': view})

        resize(1920, 1080)
        timings = {name: timing([(lambda p=p: setup(p), quad) for p in pair])
                   for name, pair in dict(kernels, **terrain_pairs).items()}
        timings['compute'] = timing([(lambda p=p: renderer.setup(p),
                                      lambda: (renderer.dispatch(12, 6, 12), renderer.barrier(0xFFFFFFFF)))
                                     for p in compute_pair])
        cache_pair = kernel_pair('vec3(xonIndoorOcclusion(xonPlayerPosition,testNormal))', cache_comparison=True)
        compare(cache_pair, 'bitmap cache vs presence-only kernel')
        timings['bitmap_vs_presence_cache'] = timing([(lambda p=p: setup(p, position=(-5.5, 0, 0)), quad) for p in cache_pair])
        report = {'passed': True, 'baseline': str(BASELINE), 'checks': checks, 'timings_1080p': timings,
                  'max_linear_pixel_error': max(c.get('max_linear_pixel_error', 0) for c in checks),
                  'scope': 'Controlled driver pixels and paired GPU timings; not full-game FPS or cross-vendor certification.'}
        (ROOT / 'validation-lighting-optimization.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': True, 'checks': len(checks), 'max_pixel_error': report['max_linear_pixel_error'],
                          'timings': timings}, indent=2))
    finally:
        archive.close()
        for selected in programs:
            driver.delete_program(selected)
        for stage in stages:
            driver.delete_shader(stage)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    run()
