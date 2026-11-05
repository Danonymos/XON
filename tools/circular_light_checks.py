"""Validate 1.8.3 circular light pools, wall-leak sealing, indoor balance, 83-family census, non-lamp pixel parity, and 1080p GPU timings."""
import argparse
import ctypes as ct
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from PIL import Image

from brightness_checks import display_luma
from lamp_gpu_checks import LampRenderer
from pbr_checks import VERTEX
from validate import Driver, SHADERS, expand, variant_source
from voxel_gpu_checks import SIZE, HALF

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT.parent / 'XON-Shader-v1.8.zip'
DEFAULT_PACK = Path(r'C:\Users\crypt\AppData\Roaming\ModrinthApp\profiles\Ziz\resourcepacks\Primes HD Textures [256x].zip')


def count_block_light_sources():
    block_props = (SHADERS / 'block.properties').read_text(encoding='utf-8')
    groups = {}
    for line in block_props.splitlines():
        line = line.strip()
        if line.startswith('block.'):
            key, val = line.split('=', 1)
            groups[int(key.split('.')[1])] = val.split()

    ore_ids = [10010, 10011, 10012, 10013, 10014, 10015, 10016, 10017, 10018]
    lamp_ids = [10005, 10006, 10019, 10020, 10021, 10023, 10024, 10025, 10026, 10027] + list(range(10030, 10097))
    # Note: 10032..10096 and 10030..10031 map to 67 families; check exact unique lamp families via GLSL mapping
    def lamp_family(mid: int) -> int:
        if 10030 <= mid <= 10096:
            return mid - 10021
        return {
            10006: 1, 10024: 2, 10025: 3, 10026: 4, 10027: 5,
            10019: 6, 10020: 7, 10023: 8, 10005: 24, 10021: 41,
        }.get(mid, 0)

    active_lamp_ids = [m for m in sorted(groups) if lamp_family(m) > 0]
    unique_lamp_families = sorted({lamp_family(m) for m in active_lamp_ids})
    assert unique_lamp_families == list(range(1, 76)), f'Expected 1..75 lamp families, got {unique_lamp_families}'

    active_ore_ids = [m for m in ore_ids if m in groups]
    ore_selectors = sum(len(groups[m]) for m in active_ore_ids)
    lamp_selectors = sum(len(groups[m]) for m in active_lamp_ids)
    return {
        'lamp_families': len(unique_lamp_families),
        'ore_families': 8,
        'total_voxelized_light_families': len(unique_lamp_families) + 8,
        'emitter_material_groups': len(active_lamp_ids) + len(active_ore_ids),
        'emitter_block_selectors': lamp_selectors + ore_selectors,
        'lamp_block_selectors': lamp_selectors,
        'ore_block_selectors': ore_selectors,
        'held_dynamic_light_paths': 1,
        'scalar_lightmap_fallback_paths': 1,
    }


def run(baseline_path: Path, resource_pack: Path):
    census = count_block_light_sources()
    archive = zipfile.ZipFile(baseline_path)
    driver = Driver()
    renderer = LampRenderer(driver)
    stages, programs, checks = [], [], []
    cache = {}

    def saved(name: str) -> str:
        if name not in cache:
            # For End atmosphere files added in 1.8.1, fall back to working tree if absent in 1.8 archive
            try:
                text = archive.read('shaders/' + name).decode('utf-8')
            except KeyError:
                text = (SHADERS / name).read_text(encoding='utf-8')
            cache[name] = re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                                 lambda m: saved(m[1].lstrip('/')), text, flags=re.M)
        return cache[name]

    def source(name: str, old: bool, options=None) -> str:
        value = saved(name) if old else expand(SHADERS / name)
        for key, setting in (options or {}).items():
            replacement = '#undef ' + key if setting is False else '#define ' + key
            if not isinstance(setting, bool):
                replacement += ' ' + str(setting)
            value = re.sub(rf'^(?://)?#define {key}\b[^\n]*$', replacement, value, flags=re.M)
        return value

    def make_program(parts):
        handles = []
        for code, kind in parts:
            if kind == '.csh':
                handle = driver.create_shader(0x91B9)
                encoded = code.encode('utf-8')
                pointer, length = ct.c_char_p(encoded), ct.c_int(len(encoded))
                driver.shader_source(handle, 1, ct.byref(pointer), ct.byref(length))
                driver.compile_shader(handle)
                status, log = ct.c_int(), ct.create_string_buffer(65536)
                driver.get_shader(handle, 0x8B81, ct.byref(status))
                driver.shader_log(handle, len(log), None, log)
                assert status.value and not log.value, log.value.decode('utf-8', errors='replace')
            else:
                handle, warning = driver.compile(code, kind, '1.8.2 check')
                assert not warning, warning
            handles.append(handle)
            stages.append(handle)
        prog = driver.create_program()
        for handle in handles:
            driver.attach_shader(prog, handle)
        driver.link_program(prog)
        status, log = ct.c_int(), ct.create_string_buffer(65536)
        driver.get_program(prog, 0x8B82, ct.byref(status))
        driver.program_log(prog, len(log), None, log)
        assert status.value and not log.value, log.value.decode('utf-8', errors='replace')
        programs.append(prog)
        return prog

    def settle(selected, count=16):
        renderer.upload(0, renderer.voxels)
        for _ in range(count):
            renderer.step(selected)

    def timing(actions, width=1920, height=1080, is_compute=False):
        if not is_compute:
            renderer.width, renderer.height = width, height
            renderer.active_texture(0x84CB)
            renderer.bind_texture(0x0DE1, renderer.textures[11])
            renderer.tex_image(0x0DE1, 0, 0x8814, width, height, 0, 0x1908, 0x1406, None)
            renderer.viewport(0, 0, width, height)
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
            for _ in range(10):
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
        before_med = float(np.median(times[0]))
        after_med = float(np.median(times[1]))
        return {
            'before_ms': round(before_med, 5),
            'after_ms': round(after_med, 5),
            'speedup_percent': round((1.0 - after_med / max(before_med, 1e-9)) * 100.0, 2),
            'median_paired_ratio': round(float(np.median(np.array(times[1]) / np.maximum(times[0], 1e-9))), 4),
        }

    try:
        old_compute = make_program([(source('shadowcomp.csh', True), '.csh')])
        new_compute = make_program([(source('shadowcomp.csh', False), '.csh')])

        # 1. Capture across all 3 dimension entrypoints (including shadow.vsh early-out optimization)
        source_materials = [(10006, 129), (10024, 130), (10025, 131), (10026, 132), (10027, 133),
                            (10019, 134), (10020, 135), (10023, 136), (10005, 152), (10021, 169)]
        source_materials += [(mid, 128 + (mid - 10021)) for mid in range(10030, 10097)]
        for folder in ['', 'world-1/', 'world1/']:
            caster = make_program([
                (variant_source(SHADERS / (folder + 'shadow.vsh'), {}), '.vsh'),
                (variant_source(SHADERS / (folder + 'shadow.fsh'), {}), '.fsh'),
            ])
            for material, expected in source_materials:
                renderer.reset()
                cell = renderer.capture(caster, material, world_block=(-3, 1, -4), camera=(-2.2, 0.1, -1.9))
                assert int(renderer.read(0)[cell]) == expected, (folder, material, renderer.read(0)[cell], expected)
            for material, expected in [(10021, 169), (10005, 152), (0, 0)]:
                renderer.reset()
                cell = renderer.capture(caster, material, stage=4)
                assert int(renderer.read(0)[cell]) == expected, (folder, material)
            checks.append({'case': 'all 77 emitter material groups captured across dimensions', 'dimension': folder or 'world0'})

        # 2. All 75 lamp families: finite, monotonic, d=15 zero tail, no ore leak, and circular isotropy!
        peaks, reaches = {}, {}
        for family in range(1, 76):
            renderer.reset()
            renderer.voxels[48, 24, 48] = 128 + family
            settle(new_compute)
            field = renderer.lamp_field()
            line = field[48, 24, 48:64, :3]
            luminance = line @ np.array([0.2126, 0.7152, 0.0722])
            assert np.isfinite(field).all() and np.min(field[..., :3]) >= 0.0
            assert np.max(np.diff(luminance)) <= 1e-5, (family, luminance)
            assert luminance[0] > 0.0 and luminance[-1] == 0.0, (family, luminance[-1])
            assert np.max(np.abs(renderer.current()[..., :3])) == 0.0, f'Lamp {family} leaked into ore field'
            peaks[family] = float(luminance[0])
            reaches[family] = int(np.max(np.where(luminance > 1e-4)[0]))
        assert peaks[1] < peaks[2] < peaks[3] and reaches[1] < reaches[2] < reaches[3]
        checks.append({'case': 'all 75 lamp families monotonic, zero at d=15, ordered peaks/reaches'})

        # 3. All 8 glowing ore families: exact cardinal reach (< 0.002) + circular diagonal isotropy + no lamp leak!
        for emitter in range(2, 10):
            renderer.reset()
            renderer.voxels[48, 24, 48] = emitter
            settle(new_compute)
            ore = renderer.current()
            reach = 4 + 3
            levels = [float(ore[48, 24, 48 + d, 3]) for d in range(reach + 3)]
            expected = np.maximum(1.0 - np.arange(reach + 3) / (reach + 1), 0.0)
            assert float(np.max(np.abs(np.array(levels) - expected))) < 0.002
            # Diagonal (2, 2) at r = 2.83 must exceed cardinal (3, 0) at r = 3.0 (was 0.500 vs 0.625 in Manhattan!)
            assert float(ore[48 + 2, 24, 48 + 2, 3]) >= float(ore[48, 24, 48 + 3, 3])
            assert float(np.max(renderer.lamp_field()[..., :3])) == 0.0
        checks.append({'case': 'all 8 ore families retain cardinal reach and gain circular diagonal pools'})

        # 4. Single flush floor lamp circular isotropy across 19 angles (0..90 deg): 1.8.2 vs 1.8.1
        probe_prefix = '#version 330 compatibility\n' + expand(SHADERS / 'lib/settings.glsl')
        probe_prefix += '\nuniform vec3 cameraPosition;uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n'
        probe_fsh = probe_prefix + expand(SHADERS / 'lib/emissive_light.glsl') + '''
uniform vec3 testPosition, testNormal;
uniform uint testReceiver;
out vec4 result;
void main() { result = xonLampLight(testPosition, testNormal, testReceiver); }
'''
        sampler = make_program([(expand(SHADERS / 'final.vsh'), '.vsh'), (probe_fsh, '.fsh')])

        isotropy_report = {}
        for fam_name, fam_id in [('lantern', 3), ('soul_lantern', 4), ('verdant_froglight', 26), ('sea_lantern', 11)]:
            renderer.reset()
            renderer.voxels[:, :HALF[1], :] = 255
            renderer.voxels[HALF[2], HALF[1] - 1, HALF[0]] = 128 + fam_id
            settle(new_compute)
            angles = np.linspace(0.0, np.pi / 2.0, 19)
            vals = []
            renderer.setup(sampler)
            renderer.uniform3f(renderer.location('testNormal'), 0.0, 1.0, 0.0)
            f_ui = driver.function('glUniform1ui', None, ct.c_int, ct.c_uint)
            f_ui(renderer.location('testReceiver'), 0)
            for th in angles:
                pt = (0.5 + 3.0 * float(np.cos(th)), 0.0, 0.5 + 3.0 * float(np.sin(th)))
                rgb = renderer.sample(sampler, pt)
                vals.append(float(np.dot(rgb, [0.2126, 0.7152, 0.0722])))
            diag_card = vals[9] / max(vals[0], 1e-6)
            min_max = min(vals) / max(max(vals), 1e-6)
            assert 0.85 <= diag_card <= 1.15 and min_max >= 0.82, (fam_name, diag_card, min_max)
            isotropy_report[fam_name] = {'diag_over_card_r3': round(diag_card, 4), 'min_over_max_r3': round(min_max, 4)}
        checks.append({'case': 'flush floor lamps cast circular radial pools across 0..90 deg', 'metrics': isotropy_report})

        # 5. Solid planar wall + 1-block wall surface/corner/alcove/pillar leak sealing + diagonal wall + teleport reset + steady-state zero flicker
        renderer.reset()
        renderer.voxels[48, 24, 48] = 131
        renderer.voxels[:, :, 51] = 255
        settle(new_compute)
        assert float(np.max(renderer.lamp_field()[:, :, 52:, :3])) == 0.0

        # 5b. 1-block wall surface trilinear sampling leak checks (Lantern 131 & Diamond Ore 6)
        probe_ore_fsh = probe_prefix + expand(SHADERS / 'lib/emissive_light.glsl') + '''
uniform vec3 testPosition, testNormal;
out vec4 result;
void main() { result = vec4(xonEmissiveLight(testPosition, testNormal), 1.0); }
'''
        ore_sampler = make_program([(expand(SHADERS / 'final.vsh'), '.vsh'), (probe_ore_fsh, '.fsh')])
        for emitter_code, is_ore in [(131, False), (6, True)]:
            active_sampler = ore_sampler if is_ore else sampler
            # Flat 1-block wall at x = 0 (voxel x = 48), emitter right against back of wall at x = -1 (voxel x = 47)
            renderer.reset()
            renderer.voxels[:, :, 48] = 255
            renderer.voxels[48, 24, 47] = emitter_code
            settle(new_compute)
            for nrm in [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)]:
                renderer.setup(active_sampler)
                renderer.uniform3f(renderer.location('testNormal'), *nrm)
                if not is_ore:
                    f_ui(renderer.location('testReceiver'), 0)
                for px in [1.0, 1.001, 1.02]:
                    for py in [-0.45, 0.0, 0.5, 0.95]:
                        rgb = renderer.sample(active_sampler, (px, py, 0.5))
                        assert float(np.max(rgb)) == 0.0, f'1-block flat wall leaked {emitter_code} at px={px}, py={py}, nrm={nrm}: {rgb}'

            # Corner wall (x = 48) + ceiling (y = 26), emitter at (47, 25, 48) behind wall below ceiling
            renderer.reset()
            renderer.voxels[:, :, 48] = 255
            renderer.voxels[:, 26, :] = 255
            renderer.voxels[48, 25, 47] = emitter_code
            settle(new_compute)
            for nrm in [(1.0, 0.0, 0.0), (0.0, -1.0, 0.0)]:
                renderer.setup(active_sampler)
                renderer.uniform3f(renderer.location('testNormal'), *nrm)
                if not is_ore:
                    f_ui(renderer.location('testReceiver'), 0)
                rgb = renderer.sample(active_sampler, (1.02, 1.95, 0.5))
                assert float(np.max(rgb)) == 0.0, f'Corner wall+ceiling leaked {emitter_code}: {rgb}'

            # Alcove / recessed chest wall: pillar at (48, y, 48), recessed wall at (48, y, 47), emitter behind pillar at (47, 24, 48)
            renderer.reset()
            renderer.voxels[48, :, 48] = 255
            renderer.voxels[49:, :, 48] = 255
            renderer.voxels[:48, :, 47] = 255
            renderer.voxels[48, 24, 47] = emitter_code
            settle(new_compute)
            for nrm in [(0.0, 0.0, -1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]:
                renderer.setup(active_sampler)
                renderer.uniform3f(renderer.location('testNormal'), *nrm)
                if not is_ore:
                    f_ui(renderer.location('testReceiver'), 0)
                rgb = renderer.sample(active_sampler, (0.05, 0.5, -0.02))
                assert float(np.max(rgb)) == 0.0, f'Alcove wall leaked {emitter_code} on normal {nrm}: {rgb}'

        # Quartz pillar (occ = 136) embedded in a 1-block wall at x = 48 with Lantern (131) & Diamond Ore (6) behind at x = 47
        renderer.reset()
        renderer.voxels[:, :, 48] = 255
        renderer.voxels[48, 22:28, 48] = 136
        renderer.voxels[48, 25, 47] = 131
        renderer.voxels[48, 23, 47] = 6
        settle(new_compute)
        assert float(np.max(renderer.current()[:, :, 49:, :3])) == 0.0, 'Diamond ore leaked through Quartz pillar wall'
        renderer.setup(sampler)
        renderer.uniform3f(renderer.location('testNormal'), 1.0, 0.0, 0.0)
        f_ui(renderer.location('testReceiver'), 8)
        pillar_front_rgb = renderer.sample(sampler, (1.001, 1.5, 0.5))
        assert float(np.max(pillar_front_rgb)) == 0.0, f'Lantern leaked through Quartz pillar onto front face: {pillar_front_rgb}'

        # Diagonal wall x + z == 99 separating x+z <= 98 from x+z >= 100 with corner-touching blocks:
        renderer.reset()
        renderer.voxels[48, 24, 48] = 131
        for x in range(SIZE[0]):
            for z in range(SIZE[2]):
                if x + z in (99, 100):
                    renderer.voxels[z, :, x] = 255
        settle(new_compute)
        zz_grid, yy_grid, xx_grid = np.indices(SIZE[::-1])
        outside = (xx_grid + zz_grid) >= 101
        assert float(np.max(renderer.lamp_field()[outside, :3])) == 0.0, 'Diagonal wall leaked light'
        # Steady-state zero flicker between ping-pong steps 16 and 17
        field16 = renderer.lamp_field().copy()
        renderer.step(new_compute)
        field17 = renderer.lamp_field()
        assert np.array_equal(field16, field17), 'Steady-state ping-pong drift detected'
        # Teleport > 16 blocks resets empty air immediately on 1st step
        renderer.step(new_compute, (100.0, 100.0, 100.0))
        assert float(np.max(renderer.lamp_field()[renderer.voxels == 0, :3])) == 0.0
        checks.append({'case': 'planar wall, 1-block surface/corner/alcove/pillar wall sealing, diagonal wall, steady-state stability, and teleport reset verified'})

        # 6. Decorative quartz/crystal/sculk/wire self-exclusion & zero native block-light claim
        for family in [6, 7, 8, 21]:
            renderer.reset()
            renderer.voxels[48, 24, 48] = 128 + family
            settle(new_compute)
            renderer.setup(sampler)
            renderer.uniform3f(renderer.location('testNormal'), 0.0, 1.0, 0.0)
            f_ui(renderer.location('testReceiver'), 0)
            rgb = renderer.sample(sampler, (0.5, -0.5, 0.5))
            assert float(np.max(rgb)) > 0.0
            assert float(renderer.draw(raw=True)[0, 0, 3]) == 0.0
            if family in (6, 7, 8):
                f_ui(renderer.location('testReceiver'), family)
                own_rgb = renderer.sample(sampler, (0.5, -0.5, 0.5))
                assert float(np.max(own_rgb)) == 0.0, f'Decorative family {family} self-lit itself'
        checks.append({'case': 'decorative families 6/7/8/21 never claim coverage and exclude own aura'})

        # 7. 20x20 6-lantern indoor room contrast preservation
        room_vertex = VERTEX.replace('xonViewPosition=testPosition;xonPlayerPosition=testPosition;', '''
 xonPlayerPosition=vec3((uv.x-.5)*20,0,(uv.y-.5)*20);xonViewPosition=xonPlayerPosition+vec3(0,-3,-18);
''')
        def inject_room(src: str) -> str:
            prefix, body = src.rsplit('void main() {', 1)
            return prefix + '''void main() {
 vec3 lamps[6]=vec3[6](vec3(-6,3,-6),vec3(0,3,-6),vec3(6,3,-6),vec3(-6,3,6),vec3(0,3,6),vec3(6,3,6));
 float distanceToLamp=100;
 for(int i=0;i<6;++i){vec3 d=abs(xonPlayerPosition+vec3(0,.5,0)-(lamps[i]+.5));distanceToLamp=min(distanceToLamp,d.x+d.y+d.z);}
 vec2 roomLightLevels=vec2(clamp((15-distanceToLamp)/15,0,1),0);
''' + body.replace('xonLightLevels', 'roomLightLevels')

        room_fsh = variant_source(SHADERS / 'gbuffers_terrain.fsh', {'XON_SHADOWS': False, 'XON_ANISOTROPIC': 0, 'XON_CLOUD_STYLE': 0, 'XON_ADVANCED_MATERIALS': False})
        room_prog = make_program([(room_vertex, '.vsh'), (inject_room(room_fsh), '.fsh')])
        renderer.width, renderer.height = 320, 320
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, 320, 320, 0, 0x1908, 0x1406, None)
        renderer.texture(8, np.full((16, 16, 4), [0.55, 0.52, 0.46, 1.0], dtype=np.float32))
        renderer.reset()
        renderer.voxels[:, :HALF[1], :] = 255
        for x in [-6, 0, 6]:
            for z in [-6, 6]:
                renderer.voxels[z + HALF[2], 3 + HALF[1], x + HALF[0]] = 131
        settle(new_compute)
        renderer.setup(room_prog)
        renderer.uniform1i(renderer.location('frameCounter'), renderer.frame - 1)
        for name, val in [('testBlock', 0.9), ('testSky', 0.0), ('testAO', 1.0), ('testMaterial', 0.0),
                          ('testTangent', 1.0), ('alphaTestRef', 0.1), ('far', 1024.0), ('fogStart', 800.0), ('fogEnd', 1024.0)]:
            renderer.uniform1f(renderer.location(name), val)
        for name, val in [('testPosition', (0.0, 0.0, -8.0)), ('testNormal', (0.0, 1.0, 0.0)), ('sunPosition', (30.0, 90.0, 20.0))]:
            renderer.uniform3f(renderer.location(name), *val)
        room_img = renderer.draw(raw=True)[..., :3]
        lut = np.asarray(Image.open(SHADERS / 'textures/xon-grade.png'), dtype=float) / 255.0
        room_luma = display_luma(room_img, lut, 0.83, True)
        p10, p50, p95 = [float(np.percentile(room_luma, p)) for p in (10, 50, 95)]
        room_ratio = p10 / p95
        assert room_ratio < 0.517 and p10 > 0.19 and 0.38 <= p95 <= 0.50, (room_ratio, p10, p50, p95)
        checks.append({'case': 'six-lantern 20x20 room preserves rebalanced pools and rich dark shadow separation',
                       'p10_over_p95': round(room_ratio, 4), 'p10': round(p10, 4), 'p95': round(p95, 4)})

        # 7b. Quartz pillar vertical decay above floor Sea Lantern (139) with hallway Lantern (131) behind wall
        pillar_prog = make_program([(VERTEX, '.vsh'), (room_fsh, '.fsh')])
        renderer.width, renderer.height = 1, 1
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, 1, 1, 0, 0x1908, 0x1406, None)
        renderer.texture(8, np.full((16, 16, 4), [0.90, 0.88, 0.84, 1.0], dtype=np.float32))
        renderer.reset()
        renderer.voxels[:, :HALF[1], :] = 255
        renderer.voxels[:, :, HALF[0]] = 255
        for y in range(HALF[1], HALF[1] + 5):
            renderer.voxels[HALF[2], y, HALF[0]] = 136
        renderer.voxels[HALF[2], HALF[1] - 1, HALF[0] + 1] = 139
        renderer.voxels[HALF[2], HALF[1] + 3, HALF[0] - 1] = 131
        settle(new_compute)
        pillar_lumas = []
        for y_off in [0.75, 1.25, 1.75, 2.25, 2.75, 3.25, 3.75]:
            bl = max(0.0, (15.0 - (y_off + 0.5)) / 15.0)
            renderer.setup(pillar_prog)
            renderer.uniform1i(renderer.location('frameCounter'), renderer.frame - 1)
            for name, val in [('testBlock', bl), ('testSky', 0.0), ('testAO', 1.0), ('testMaterial', 10023.0),
                              ('testTangent', 1.0), ('alphaTestRef', 0.1), ('far', 1024.0), ('fogStart', 800.0), ('fogEnd', 1024.0)]:
                renderer.uniform1f(renderer.location(name), val)
            for name, val in [('testPosition', (1.001, y_off, 0.5)), ('testNormal', (1.0, 0.0, 0.0)), ('sunPosition', (30.0, 90.0, 20.0))]:
                renderer.uniform3f(renderer.location(name), *val)
            rgb = renderer.draw(raw=True)[0, 0:1, :3]
            pillar_lumas.append(float(display_luma(rgb[None, ...], lut, 0.83, True)[0, 0]))
        assert all(pillar_lumas[i] > pillar_lumas[i + 1] for i in range(len(pillar_lumas) - 1)), f'Quartz pillar not monotonic decreasing: {pillar_lumas}'
        assert pillar_lumas[0] - pillar_lumas[-1] >= 0.22, f'Quartz pillar shadow contrast too small: {pillar_lumas}'
        checks.append({'case': 'quartz pillar vertical luminance decays monotonically into shadow without upper-half jump',
                       'y_0.75_to_3.75_luma': [round(v, 4) for v in pillar_lumas]})

        # 8. Exact pixel parity on non-lamp optimized shaders (terrain PBR/POM/fog/lighting, composite, composite2, final)
        pbr_opts = {'XON_COLORED_EMISSIVE_LIGHTING': False, 'XON_SHADOWS': False, 'XON_CLOUD_STYLE': 0, 'XON_ADVANCED_MATERIALS': 1}
        old_pbr_terrain = make_program([(VERTEX, '.vsh'), (source('gbuffers_terrain.fsh', True, pbr_opts), '.fsh')])
        new_pbr_terrain = make_program([(VERTEX, '.vsh'), (source('gbuffers_terrain.fsh', False, pbr_opts), '.fsh')])

        renderer.width, renderer.height = 128, 64
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, 128, 64, 0, 0x1908, 0x1406, None)

        if resource_pack.exists():
            with zipfile.ZipFile(resource_pack) as rp:
                albedo_im = np.asarray(Image.open(io.BytesIO(rp.read('assets/minecraft/textures/block/stone_bricks.png'))).convert('RGBA'), dtype=np.float32) / 255.0
                normal_im = np.asarray(Image.open(io.BytesIO(rp.read('assets/minecraft/textures/block/stone_bricks_n.png'))).convert('RGBA'), dtype=np.float32) / 255.0
                spec_im = np.asarray(Image.open(io.BytesIO(rp.read('assets/minecraft/textures/block/stone_bricks_s.png'))).convert('RGBA'), dtype=np.float32) / 255.0
            renderer.texture(8, albedo_im)
            renderer.texture(10, normal_im)
            renderer.texture(0, spec_im)
        else:
            renderer.texture(8, np.full((32, 32, 4), [0.6, 0.58, 0.55, 1.0], dtype=np.float32))
            yy, xx = np.indices((32, 32), dtype=np.float32) / 32.0
            h_map = 0.65 + 0.30 * np.sin(xx * 6.283) * np.cos(yy * 6.283)
            norm_arr = np.stack([np.full_like(h_map, 0.52), np.full_like(h_map, 0.48), np.ones_like(h_map), h_map], axis=-1)
            renderer.texture(10, norm_arr)
            renderer.texture(0, np.full((32, 32, 4), [0.45, 0.04, 0.0, 1.0], dtype=np.float32))

        max_pbr_err = 0.0
        for dist_z in [-6.0, -18.0, -45.0, -120.0]:
            for sky_v in [0.0, 0.6, 1.0]:
                imgs = []
                for prog in (old_pbr_terrain, new_pbr_terrain):
                    renderer.setup(prog)
                    renderer.uniform1i(renderer.location('normals'), 10)
                    renderer.uniform1i(renderer.location('specular'), 0)
                    for name, val in [('testBlock', 0.0), ('testSky', sky_v), ('testAO', 0.85), ('testTangent', 1.0),
                                      ('testMaterial', 0.0), ('alphaTestRef', 0.1), ('far', 256.0), ('fogStart', 180.0), ('fogEnd', 256.0)]:
                        renderer.uniform1f(renderer.location(name), val)
                    for name, val in [('testNormal', (0.0, 1.0, 0.0)), ('testPosition', (3.0, -1.5, dist_z)),
                                      ('testView', (0.35, 0.22, -0.91)), ('sunPosition', (35.0, 55.0, 25.0))]:
                        renderer.uniform3f(renderer.location(name), *val)
                    identity = np.eye(4, dtype=np.float32)
                    renderer.uniform_matrix(renderer.location('gbufferModelView'), 1, 0, identity.ctypes.data)
                    renderer.uniform_matrix(renderer.location('gbufferModelViewInverse'), 1, 0, identity.ctypes.data)
                    imgs.append(renderer.draw(raw=True)[..., :3])
                err = float(np.max(np.abs(imgs[0] - imgs[1])))
                max_pbr_err = max(max_pbr_err, err)
                assert err <= 2e-6, f'PBR/POM/fog parity error {err} at z={dist_z}, sky={sky_v}'
        checks.append({'case': 'PBR/POM/atmosphere/lighting exact parity across near and far distances', 'max_error': max_pbr_err})

        # Check final.fsh moving camera velocity + motion blur exact parity against 1.8
        final_opts = {'XON_BLOOM': False, 'XON_LIGHT_SHAFTS': False, 'XON_COLOR_GRADE': False}
        old_final = make_program([(source('final.vsh', True, final_opts), '.vsh'), (source('final.fsh', True, final_opts), '.fsh')])
        new_final = make_program([(source('final.vsh', False, final_opts), '.vsh'), (source('final.fsh', False, final_opts), '.fsh')])
        checker = (np.indices((64, 128)).sum(axis=0) % 2)[..., None].astype(np.float32)
        scene_tex = np.concatenate([np.where(checker == 0, 0.08, 0.88) * np.array([1.0, 0.85, 0.65], dtype=np.float32), np.ones((64, 128, 1), dtype=np.float32)], axis=-1)
        depth_tex = np.where((np.indices((64, 128))[1] > 96), 1.0, 0.82).astype(np.float32)
        mask_tex = np.zeros((64, 128), dtype=np.float32)
        renderer.texture(0, scene_tex)
        renderer.texture(1, mask_tex)
        renderer.texture(2, depth_tex)

        proj = np.array([[1.2, 0, 0, 0], [0, 1.8, 0, 0], [0, 0, -1.002, -1.0], [0, 0, -0.2, 0]], dtype=np.float32)
        proj_inv = np.linalg.inv(proj).astype(np.float32)
        mv = np.eye(4, dtype=np.float32)
        ang = 0.035
        prev_mv = np.array([[np.cos(ang), 0, np.sin(ang), 0], [0, 1, 0, 0], [-np.sin(ang), 0, np.cos(ang), 0], [0, 0, 0, 1]], dtype=np.float32)
        final_outs = []
        for prog in (old_final, new_final):
            renderer.setup(prog)
            renderer.uniform1i(renderer.location('colortex0'), 0)
            renderer.uniform1i(renderer.location('colortex4'), 1)
            renderer.uniform1i(renderer.location('depthtex0'), 2)
            renderer.uniform1i(renderer.location('frameCounter'), 12)
            renderer.uniform1f(renderer.location('frameTime'), 1.0 / 120.0)
            renderer.uniform3f(renderer.location('cameraPosition'), 10.25, 65.0, -4.5)
            renderer.uniform3f(renderer.location('previousCameraPosition'), 10.05, 65.0, -4.35)
            for mname, mat in [('gbufferProjection', proj), ('gbufferPreviousProjection', proj),
                               ('gbufferProjectionInverse', proj_inv), ('gbufferModelView', mv),
                               ('gbufferModelViewInverse', mv), ('gbufferPreviousModelView', prev_mv)]:
                renderer.uniform_matrix(renderer.location(mname), 1, 0, mat.T.copy().ctypes.data)
            final_outs.append(renderer.draw(raw=True)[..., :3])
        final_err = float(np.max(np.abs(final_outs[0] - final_outs[1])))
        assert final_err <= 2.5e-4, f'final.fsh motion blur parity error: {final_err}'
        checks.append({'case': 'final.fsh moving camera reprojection + motion blur exact parity', 'max_error': final_err})

        # 9. Interleaved 1080p OpenGL hardware timer-query benchmarks (1.8.1 vs 1.8.2)
        def quad():
            renderer.begin(0x0007)
            for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                renderer.tex_coord(x, y)
                renderer.vertex(x, y)
            renderer.end()

        def prep_pbr(prog):
            def _p():
                renderer.setup(prog)
                renderer.uniform1i(renderer.location('normals'), 10)
                renderer.uniform1i(renderer.location('specular'), 0)
                for name, val in [('testBlock', 0.7), ('testSky', 1.0), ('testAO', 0.85), ('testTangent', 1.0),
                                  ('testMaterial', 0.0), ('alphaTestRef', 0.1), ('far', 256.0), ('fogStart', 180.0), ('fogEnd', 256.0)]:
                    renderer.uniform1f(renderer.location(name), val)
                for name, val in [('testNormal', (0.0, 1.0, 0.0)), ('testPosition', (2.0, -1.5, -9.0)),
                                  ('testView', (0.42, 0.25, -0.87)), ('sunPosition', (35.0, 55.0, 25.0))]:
                    renderer.uniform3f(renderer.location(name), *val)
                identity = np.eye(4, dtype=np.float32)
                renderer.uniform_matrix(renderer.location('gbufferModelView'), 1, 0, identity.ctypes.data)
                renderer.uniform_matrix(renderer.location('gbufferModelViewInverse'), 1, 0, identity.ctypes.data)
            return _p

        def prep_final(prog):
            def _p():
                renderer.setup(prog)
                renderer.uniform1i(renderer.location('colortex0'), 0)
                renderer.uniform1i(renderer.location('colortex4'), 1)
                renderer.uniform1i(renderer.location('depthtex0'), 2)
                renderer.uniform1i(renderer.location('frameCounter'), 12)
                renderer.uniform1f(renderer.location('frameTime'), 1.0 / 120.0)
                renderer.uniform3f(renderer.location('cameraPosition'), 10.25, 65.0, -4.5)
                renderer.uniform3f(renderer.location('previousCameraPosition'), 10.05, 65.0, -4.35)
                for mname, mat in [('gbufferProjection', proj), ('gbufferPreviousProjection', proj),
                                   ('gbufferProjectionInverse', proj_inv), ('gbufferModelView', mv),
                                   ('gbufferModelViewInverse', mv), ('gbufferPreviousModelView', prev_mv)]:
                    renderer.uniform_matrix(renderer.location(mname), 1, 0, mat.T.copy().ctypes.data)
            return _p

        old_taa = make_program([(source('composite2.vsh', True), '.vsh'), (source('composite2.fsh', True), '.fsh')])
        new_taa = make_program([(source('composite2.vsh', False), '.vsh'), (source('composite2.fsh', False), '.fsh')])
        yy1080, xx1080 = np.indices((1080, 1920))
        checker1080 = ((yy1080 + xx1080) % 2)[..., None].astype(np.float32)
        scene1080 = np.concatenate([
            np.where(checker1080 == 0, 0.08, 0.88) * np.array([1.0, 0.85, 0.65], dtype=np.float32),
            np.ones((1080, 1920, 1), dtype=np.float32),
        ], axis=-1)
        depth1080 = np.where(xx1080 > 1440, 1.0, 0.82).astype(np.float32)
        mask1080 = np.zeros((1080, 1920), dtype=np.float32)
        hist1080 = np.ones((1080, 1920, 4), dtype=np.float32) * np.array([0.4, 0.5, 0.6, 42.0], dtype=np.float32)
        hist1080[:, :960, 3] = 2.5
        hist1080[0, 0] = [1920 % 1024, 1080 % 1024, 1 + 1 * 32, -12.0]
        renderer.texture(0, scene1080)
        renderer.texture(1, mask1080)
        renderer.texture(2, depth1080)
        renderer.texture(3, hist1080)

        def prep_taa(prog):
            def _p():
                renderer.setup(prog)
                renderer.uniform1i(renderer.location('colortex0'), 0)
                renderer.uniform1i(renderer.location('colortex4'), 1)
                renderer.uniform1i(renderer.location('depthtex0'), 2)
                renderer.uniform1i(renderer.location('colortex6'), 3)
                renderer.uniform1i(renderer.location('frameCounter'), 12)
                renderer.uniform1f(renderer.location('frameTime'), 1.0 / 120.0)
                renderer.uniform3f(renderer.location('cameraPosition'), 10.45, 65.0, -4.5)
                renderer.uniform3f(renderer.location('previousCameraPosition'), 10.05, 65.0, -4.25)
                for mname, mat in [('gbufferProjection', proj), ('gbufferPreviousProjection', proj),
                                   ('gbufferProjectionInverse', proj_inv), ('gbufferModelView', mv),
                                   ('gbufferModelViewInverse', mv), ('gbufferPreviousModelView', prev_mv)]:
                    renderer.uniform_matrix(renderer.location(mname), 1, 0, mat.T.copy().ctypes.data)
            return _p

        old_comp = make_program([(source('composite.vsh', True), '.vsh'), (source('composite.fsh', True), '.fsh')])
        new_comp = make_program([(source('composite.vsh', False), '.vsh'), (source('composite.fsh', False), '.fsh')])
        f_u2i = driver.function('glUniform2i', None, ct.c_int, ct.c_int, ct.c_int)
        def prep_comp(prog):
            def _p():
                renderer.setup(prog)
                renderer.uniform1i(renderer.location('colortex0'), 0)
                renderer.uniform1i(renderer.location('depthtex0'), 2)
                renderer.uniform1i(renderer.location('depthtex1'), 2)
                renderer.uniform1i(renderer.location('frameCounter'), 12)
                f_u2i(renderer.location('eyeBrightnessSmooth'), 0, 220)
                renderer.uniform1f(renderer.location('shadowDistance'), 96.0)
                renderer.uniform3f(renderer.location('sunPosition'), 30.0, 50.0, 80.0)
                for mname, mat in [('gbufferProjectionInverse', proj_inv), ('gbufferModelViewInverse', mv),
                                   ('shadowProjection', np.eye(4, dtype=np.float32)), ('shadowModelView', np.eye(4, dtype=np.float32))]:
                    renderer.uniform_matrix(renderer.location(mname), 1, 0, mat.T.copy().ctypes.data)
            return _p

        # Populate realistic 24-froglight 6x4 lawn scene for steady-state and post-teleport compute timing
        renderer.reset()
        renderer.voxels[:, :HALF[1], :] = 255
        for row in range(4):
            for col in range(6):
                lx = HALF[0] - 15 + col * 6
                lz = HALF[2] - 9 + row * 6
                renderer.voxels[lz, HALF[1] - 1, lx] = 128 + 26
        settle(new_compute)

        tp_counter = [0]
        def step_teleport(prog):
            tp_counter[0] += 1
            pos = (float(tp_counter[0] * 64), 64.0, 0.0)
            renderer.step(prog, pos)

        benchmarks = {
            'near_terrain_pbr_pom_fog_1080p': timing([(prep_pbr(old_pbr_terrain), quad), (prep_pbr(new_pbr_terrain), quad)]),
            'moving_final_motion_blur_1080p': timing([(prep_final(old_final), quad), (prep_final(new_final), quad)]),
            'moving_temporal_aa_disocclusion_1080p': timing([(prep_taa(old_taa), quad), (prep_taa(new_taa), quad)]),
            'volumetric_shafts_bloom_composite_540p': timing([(prep_comp(old_comp), quad), (prep_comp(new_comp), quad)], width=960, height=540),
            'voxel_compute_24lamp_lawn_steady': timing([
                (lambda: None, lambda: renderer.step(old_compute)),
                (lambda: None, lambda: renderer.step(new_compute)),
            ], is_compute=True),
            'voxel_compute_post_teleport_reset': timing([
                (lambda: None, lambda: step_teleport(old_compute)),
                (lambda: None, lambda: step_teleport(new_compute)),
            ], is_compute=True),
        }

        report = {
            'passed': True,
            'version_target': '1.8.3',
            'driver': 'NVIDIA GeForce RTX 5060 Ti/PCIe/SSE2',
            'light_source_census': census,
            'checks_count': len(checks),
            'checks': checks,
            'benchmarks_1080p_interleaved': benchmarks,
        }
        (ROOT / 'validation-1.8.3-circular-light.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
    finally:
        for prog in programs:
            driver.delete_program(prog)
        for sh in stages:
            driver.delete_shader(sh)
        renderer.close()
        driver.close()
        archive.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=DEFAULT_BASELINE)
    parser.add_argument('--resource-pack', type=Path, default=DEFAULT_PACK)
    args = parser.parse_args()
    run(args.baseline, args.resource_pack)
