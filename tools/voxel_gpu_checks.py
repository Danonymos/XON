"""Execute XON's voxel capture, compute propagation and surface sampling on OpenGL."""
import ctypes as ct
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from validate import Driver, SHADERS, expand, variant_source
from render_checks import Renderer

ROOT = Path(__file__).resolve().parents[1]
SIZE = (96, 48, 96)
HALF = np.array(SIZE) // 2


class VoxelRenderer(Renderer):
    def __init__(self, driver):
        super().__init__(driver, 640, 360)
        f = driver.function
        u, i, p = ct.c_uint, ct.c_int, ct.c_void_p
        self.image3d = f('glTexImage3D', None, u, i, i, i, i, i, i, u, u, p)
        self.sub3d = f('glTexSubImage3D', None, u, i, i, i, i, i, i, i, u, u, p)
        self.get_texture = f('glGetTexImage', None, u, i, u, u, p)
        self.bind_image = f('glBindImageTexture', None, u, u, i, ct.c_ubyte, i, u, u)
        self.dispatch = f('glDispatchCompute', None, u, u, u)
        self.barrier = f('glMemoryBarrier', None, u)
        self.enable = f('glEnable', None, u)
        self.matrix_mode = f('glMatrixMode', None, u)
        self.load_matrix = f('glLoadMatrixf', None, p)
        self.enable_client = f('glEnableClientState', None, u)
        self.disable_client = f('glDisableClientState', None, u)
        self.vertex_pointer = f('glVertexPointer', None, i, u, i, p)
        self.attribute = f('glGetAttribLocation', i, u, ct.c_char_p)
        self.attribute4 = f('glVertexAttrib4f', None, u, ct.c_float, ct.c_float, ct.c_float, ct.c_float)
        self.attribute_pointer = f('glVertexAttribPointer', None, u, i, u, ct.c_ubyte, i, p)
        self.enable_attribute = f('glEnableVertexAttribArray', None, u)
        self.disable_attribute = f('glDisableVertexAttribArray', None, u)
        self.draw_arrays = f('glDrawArrays', None, u, i, i)
        self.volumes = (u * 3)()
        self.gen_textures(3, self.volumes)
        self.voxels = np.zeros((SIZE[2], SIZE[1], SIZE[0]), dtype=np.uint8)
        self.empty_light = np.zeros((*self.voxels.shape, 4), dtype=np.float32)
        for index in range(3):
            self.active_texture(0x84C0 + 10 + index)
            self.bind_texture(0x806F, self.volumes[index])
            for axis in (0x2801, 0x2800):
                self.tex_parameter(0x806F, axis, 0x2600)
            for axis in (0x2802, 0x2803, 0x8072):
                self.tex_parameter(0x806F, axis, 0x812F)
            internal, external, kind = (0x8232, 0x8D94, 0x1401) if index == 0 else (0x881A, 0x1908, 0x1406)
            data = self.voxels if index == 0 else self.empty_light
            self.image3d(0x806F, 0, internal, *SIZE, 0, external, kind, data.ctypes.data)
            self.bind_image(index, self.volumes[index], 0, 1, 0, 0x88BA, internal)
        self.frame = 0

    def setup(self, program):
        super().setup(program)
        for name, unit in [('xonVoxelTex', 10), ('xonLightTex0', 11), ('xonLightTex1', 12),
                           ('xonVoxelImg', 0), ('xonLightImg0', 1), ('xonLightImg1', 2)]:
            self.uniform1i(self.location(name), unit)
        self.uniform1i(self.location('frameCounter'), self.frame)

    def upload(self, index, data):
        self.active_texture(0x84C0 + 10 + index)
        self.bind_texture(0x806F, self.volumes[index])
        external, kind = (0x8D94, 0x1401) if index == 0 else (0x1908, 0x1406)
        self.sub3d(0x806F, 0, 0, 0, 0, *SIZE, external, kind, data.ctypes.data)
        self.barrier(0xFFFFFFFF)

    def reset(self):
        self.voxels.fill(0)
        self.upload(0, self.voxels)
        for index in (1, 2):
            self.upload(index, self.empty_light)
        self.frame = 0

    def read(self, index):
        self.barrier(0xFFFFFFFF)
        self.active_texture(0x84C0 + 10 + index)
        self.bind_texture(0x806F, self.volumes[index])
        data = np.empty_like(self.voxels if index == 0 else self.empty_light)
        self.get_texture(0x806F, 0, 0x8D94 if index == 0 else 0x1908,
                         0x1401 if index == 0 else 0x1406, data.ctypes.data)
        return data

    def step(self, program, camera=(0, 0, 0), previous=(0, 0, 0)):
        self.setup(program)
        self.uniform3f(self.location('cameraPosition'), *camera)
        self.uniform3f(self.location('previousCameraPosition'), *previous)
        self.dispatch(12, 6, 12)
        self.barrier(0xFFFFFFFF)
        self.frame += 1

    def current(self):
        return self.read(1 + ((self.frame - 1) & 1))

    def capture(self, program, material, world_block=(0, 0, 0), camera=(0, 0, 0), rotation=None, stage=1):
        self.setup(program)
        self.uniform1i(self.location('renderStage'), stage)
        self.uniform3f(self.location('cameraPosition'), *camera)
        rotation = np.eye(4) if rotation is None else rotation
        inverse = np.ascontiguousarray(np.linalg.inv(rotation).T, dtype=np.float32)
        self.uniform_matrix(self.location('shadowModelViewInverse'), 1, 0, inverse.ctypes.data)
        model = np.ascontiguousarray(rotation.T, dtype=np.float32)
        projection = np.ascontiguousarray(np.diag([1 / 64, 1 / 64, 1 / 64, 1]), dtype=np.float32)
        for mode, matrix in [(0x1700, model), (0x1701, projection)]:
            self.matrix_mode(mode)
            self.load_matrix(matrix.ctypes.data)
        block = np.asarray(world_block, dtype=np.float32)
        center = block + 0.5 - camera
        vertices = np.ascontiguousarray(block + np.array([[0, 1, 0], [0, 1, 1], [1, 1, 1], [1, 1, 0]]) - camera, dtype=np.float32)
        offsets = np.ascontiguousarray((center - vertices) * 64, dtype=np.float32)
        entity = self.attribute(program, b'mc_Entity')
        midpoint = self.attribute(program, b'at_midBlock')
        assert entity >= 0 and midpoint >= 0, 'Voxel capture attributes were optimized out'
        self.attribute4(entity, material, 0, 0, 0)
        self.enable_attribute(midpoint)
        self.attribute_pointer(midpoint, 3, 0x1406, 0, 0, offsets.ctypes.data)
        self.enable_client(0x8074)
        self.vertex_pointer(3, 0x1406, 0, vertices.ctypes.data)
        self.enable(0x8C89)
        self.draw_arrays(0x0007, 0, 4)
        self.disable(0x8C89)
        self.disable_client(0x8074)
        self.disable_attribute(midpoint)
        self.barrier(0xFFFFFFFF)
        return tuple((np.floor(block + 0.5) - np.floor(camera) + HALF).astype(int)[::-1])

    def sample(self, program, position, normal=(0, 1, 0), camera=(0, 0, 0)):
        self.setup(program)
        self.uniform1i(self.location('frameCounter'), self.frame - 1)
        self.uniform3f(self.location('cameraPosition'), *camera)
        self.uniform3f(self.location('testPosition'), *position)
        self.uniform3f(self.location('testNormal'), *normal)
        return self.draw(raw=True)[0, 0, :3].copy()

    def close(self):
        self.delete_textures(3, self.volumes)
        super().close()


def run():
    driver = Driver()
    renderer = VoxelRenderer(driver)
    stages, programs, checks = [], [], []
    warnings = []

    def compile_stage(source, kind, label):
        if kind != '.csh':
            stage, warning = driver.compile(source, kind, label)
        else:
            stage = driver.create_shader(0x91B9)
            encoded = source.encode()
            pointer, length = ct.c_char_p(encoded), ct.c_int(len(encoded))
            driver.shader_source(stage, 1, ct.byref(pointer), ct.byref(length))
            driver.compile_shader(stage)
            status, log = ct.c_int(), ct.create_string_buffer(65536)
            driver.get_shader(stage, 0x8B81, ct.byref(status))
            driver.shader_log(stage, len(log), None, log)
            warning = log.value.decode()
            assert status.value, f'{label}: {warning}'
        stages.append(stage)
        if warning:
            warnings.append({'stage': label, 'warning': warning})
        return stage

    def program(parts, label):
        compiled = [compile_stage(source, kind, label) for source, kind in parts]
        handle = driver.create_program()
        for stage in compiled:
            driver.attach_shader(handle, stage)
        driver.link_program(handle)
        status, log = ct.c_int(), ct.create_string_buffer(65536)
        driver.get_program(handle, 0x8B82, ct.byref(status))
        driver.program_log(handle, len(log), None, log)
        assert status.value, f'{label}: {log.value.decode()}'
        if log.value:
            warnings.append({'program': label, 'warning': log.value.decode()})
        programs.append(handle)
        return handle

    def compute(radius=4):
        return program([(variant_source(SHADERS / 'shadowcomp.csh', {'XON_EMISSIVE_RADIUS': f'{radius}.0'}), '.csh')], f'compute radius {radius}')

    def sampler_program(radius=4, body=None):
        prefix = '#version 330 compatibility\n'
        prefix += expand(SHADERS / 'lib/settings.glsl')
        prefix = re.sub(r'#define XON_EMISSIVE_RADIUS [^\n]+', f'#define XON_EMISSIVE_RADIUS {radius}.0', prefix)
        prefix += '\nuniform vec3 cameraPosition; uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n'
        prefix += expand(SHADERS / 'lib/emissive_light.glsl')
        fragment = prefix + (body or '''
uniform vec3 testPosition, testNormal;
out vec4 result;
void main() { result = vec4(xonEmissiveLight(testPosition, testNormal), 1); }
''')
        return program([(expand(SHADERS / 'final.vsh'), '.vsh'), (fragment, '.fsh')], 'surface sampling')

    try:
        shadow_programs = []
        for directory in ['', 'world-1', 'world1']:
            path = SHADERS / directory
            shadow_programs.append(program([(variant_source(path / 'shadow.vsh', {}), '.vsh'),
                                            (variant_source(path / 'shadow.fsh', {}), '.fsh')], f'capture {directory}'))
        rotation = np.eye(4)
        angle = 0.71
        rotation[:3, :3] = [[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]]
        for dimension, caster in zip([0, -1, 1], shadow_programs):
            renderer.reset()
            camera = (100.2, -34.7, -999.8)
            block = (102, -35, -1002)
            voxel = renderer.capture(caster, 10018, block, camera, rotation)
            occupancy = renderer.read(0)
            assert occupancy[voxel] == 9 and np.count_nonzero(occupancy) == 1, 'Emitter capture/transform failed'
            checks.append({'case': 'real shadow vertex capture at negative coordinates and rotated shadow view', 'dimension': dimension})
        for material, expected in [(0, 1), (10010, 2), (10019, 10), (10023, 12), (10003, 0), (10004, 0), (10006, 0)]:
            renderer.reset()
            voxel = renderer.capture(shadow_programs[0], material)
            assert renderer.read(0)[voxel] == expected, f'Wrong voxel for material {material}'
        renderer.reset()
        renderer.capture(shadow_programs[0], 10010, stage=12)
        assert np.count_nonzero(renderer.read(0)) == 0, 'Entity entered terrain volume'
        checks.append({'case': 'ore/quartz IDs, solid occluders, plant/lichen and entity exclusion'})

        sample = sampler_program()
        default_compute = None
        center = (48, 24, 48)
        for radius in [3, 4, 5]:
            selected = compute(radius)
            if radius == 4:
                default_compute = selected
            renderer.reset()
            # This test starts with the real shadow vertex write, not a fabricated emitter grid.
            renderer.capture(shadow_programs[0], 10010)
            for _ in range(16):
                renderer.step(selected)
            light = renderer.current()
            reach = radius + 3
            levels = [float(light[48, 24, 48 + distance, 3]) for distance in range(reach + 3)]
            expected = np.maximum(1 - np.arange(reach + 3) / (reach + 1), 0)
            assert np.max(np.abs(np.array(levels) - expected)) < 0.002, (radius, levels)
            assert np.isfinite(light).all(), 'Non-finite flood fill'
            sampler = sample if radius == 4 else sampler_program(radius)
            pools = [renderer.sample(sampler, (x + 0.5, -0.5, 0.5)).tolist() for x in range(reach + 2)]
            assert pools[1][2] > pools[2][2] > pools[3][2] > 0, pools
            tail = [pools[x][2] for x in range(radius, reach + 2)]
            assert all(a > b for a, b in zip(tail, tail[1:])) and tail[-1] == 0, tail
            assert pools[reach][2] > 0, 'Three-block aura tail was cut off'
            checks.append({'case': 'GPU capture -> compute -> receiving floor with three-block eased aura tail',
                           'radius': radius, 'reach': reach, 'axis_levels': levels, 'surface_rgb': pools})
            distances = np.linspace(radius, reach + 1, 65)
            eased = np.array([renderer.sample(sampler, (x + .5, -.5, .5))[2] for x in distances])
            assert np.all(np.diff(eased) <= .000001) and eased[-1] == 0, eased.tolist()
            edge_slope = float(abs(eased[-1] - eased[-2]) / (distances[-1] - distances[-2]))
            assert edge_slope < .001 and np.max(-np.diff(eased)) < .025, (edge_slope, eased.tolist())
            checks.append({'case': 'sub-block GPU aura fade has no hard steps and eases flat at darkness',
                           'radius': radius, 'maximum_sample_drop': float(np.max(-np.diff(eased))),
                           'outer_edge_slope': edge_slope})

        renderer.reset()
        voxel = renderer.capture(shadow_programs[0], 10023)
        for _ in range(12):
            renderer.step(default_compute)
        purple = renderer.sample(sample, (2.5, -0.5, 0.5))
        assert purple[2] > purple[0] > purple[1] > 0.01, purple
        checks.append({'case': 'quartz produces violet illumination on receiving stone', 'rgb': purple.tolist()})
        reference = renderer.sample(sample, (1.73, -0.5, 0.51))
        for camera in [(0.99, -0.99, 0.49), (1.01, -1.01, 0.51), (-1.01, 1.01, -0.51)]:
            shift = np.floor(camera).astype(int)
            renderer.voxels.fill(0)
            pos = np.array([0, 0, 0]) - shift + HALF
            renderer.voxels[tuple(pos[::-1])] = 12
            renderer.upload(0, renderer.voxels)
            previous = (0, 0, 0)
            for _ in range(16):
                renderer.step(default_compute, camera, previous)
                previous = camera
            actual = renderer.sample(sample, np.array([1.73, -0.5, 0.51]) - camera, camera=camera)
            assert np.max(np.abs(actual - reference)) < 0.001, (camera, actual, reference)
            # Return the history to the same world position before the next independent camera test.
            renderer.reset()
            renderer.capture(shadow_programs[0], 10023)
            for _ in range(12):
                renderer.step(default_compute)
        checks.append({'case': 'world-anchored surface sampling across positive and negative block boundaries'})

        renderer.reset()
        renderer.voxels[:, :, 50] = 1
        renderer.voxels[center] = 2
        renderer.upload(0, renderer.voxels)
        for _ in range(16):
            renderer.step(default_compute)
        light = renderer.current()
        assert np.max(light[:, :, 51:, :3]) == 0, 'Light propagated through wall'
        front = renderer.sample(sample, (2, 0.5, 0.5), normal=(-1, 0, 0))
        back = renderer.sample(sample, (3, 0.5, 0.5), normal=(1, 0, 0))
        assert front[2] > 0.1 and np.max(back) == 0, (front, back)
        checks.append({'case': 'GPU solid-wall propagation and front/back surface occlusion', 'front': front.tolist(), 'back': back.tolist()})
        renderer.voxels.fill(0)
        renderer.upload(0, renderer.voxels)
        for _ in range(8):
            renderer.step(default_compute)
        assert np.max(renderer.current()[..., :3]) == 0, 'Removed light left a ghost'
        checks.append({'case': 'removing ore clears light history'})

        renderer.reset()
        renderer.voxels[48, 24, 46] = 4
        renderer.voxels[48, 24, 50] = 5
        renderer.upload(0, renderer.voxels)
        for _ in range(16):
            renderer.step(default_compute)
        mixed = renderer.current()[center][:3]
        assert mixed[0] > mixed[1] and mixed[2] > mixed[1], mixed
        renderer.step(default_compute, (100, 100, 100))
        teleported = renderer.current()
        empty = renderer.voxels == 0
        assert np.max(teleported[empty, :3]) == 0, 'Old illumination survived teleport'
        checks.append({'case': 'redstone/lapis color blending and teleport history rejection', 'blend_rgb': mixed.tolist()})

        # Render the real terrain fragment with controlled varyings to verify receiving surfaces and self-tint exclusion.
        vertex = '''#version 330 compatibility
out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels;
out vec4 xonVertexColor; out vec3 xonViewPosition, xonPlayerPosition, xonWorldNormal;
flat out float xonMaterial;
uniform vec3 testPosition; uniform float testMaterial;
void main() {
 gl_Position=vec4(gl_Vertex.xy*2-1,0,1); xonTexCoord=vec2(.5); xonAtlasBounds=vec4(0);
 xonLightLevels=vec2(0); xonVertexColor=vec4(1); xonViewPosition=vec3(0,0,-5);
 xonPlayerPosition=testPosition; xonWorldNormal=vec3(0,1,0); xonMaterial=testMaterial;
}
'''
        terrain = []
        for enabled in [False, True]:
            fragment = variant_source(SHADERS / 'gbuffers_terrain.fsh',
                                      {'XON_COLORED_EMISSIVE_LIGHTING': enabled, 'XON_SHADOWS': False,
                                       'XON_CAUSTICS': False, 'XON_ANISOTROPIC': 0})
            terrain.append(program([(vertex, '.vsh'), (fragment, '.fsh')], f'terrain colored light {enabled}'))
        renderer.texture(8, np.full((2, 2, 4), [0.55, 0.55, 0.55, 1], dtype=np.float32))
        renderer.reset()
        renderer.capture(shadow_programs[0], 10023)
        for _ in range(12):
            renderer.step(default_compute)
        for material in [0, 10010, 10018, 10023]:
            values = []
            for selected in terrain:
                renderer.setup(selected)
                renderer.uniform1i(renderer.location('frameCounter'), renderer.frame - 1)
                renderer.uniform1f(renderer.location('testMaterial'), material)
                renderer.uniform3f(renderer.location('testPosition'), 1.5, -0.5, 0.5)
                values.append(renderer.draw(raw=True)[0, 0, :3])
            difference = values[1] - values[0]
            if material == 0:
                assert difference[2] > difference[0] > difference[1] > 0.01, difference
            else:
                assert np.max(np.abs(difference)) < 1e-6, (material, difference)
            checks.append({'case': 'real terrain shading: wall receives light, source materials keep their surface color',
                           'material': material, 'added_rgb': difference.tolist()})

        preview = sampler_program(body='''
in vec2 xonUV; out vec4 result; uniform int testEnabled;
void main() {
 vec3 p=vec3((xonUV.x-.5)*12.0,-.5,(xonUV.y-.5)*7.0);
 vec3 c=vec3(.24)*.12;
 if(testEnabled==1) c+=vec3(.24)*xonEmissiveLight(p,vec3(0,1,0))*1.45;
 c*=1.05; c=c*(2.51*c+.03)/(c*(2.43*c+.59)+.14);
 result=vec4(pow(clamp(c,0,1),vec3(1.0/2.2)),1);
}
''')
        sheet = Image.new('RGB', (1280, 390))
        painter = ImageDraw.Draw(sheet)
        for index in [0, 1]:
            renderer.setup(preview)
            renderer.uniform1i(renderer.location('frameCounter'), renderer.frame - 1)
            renderer.uniform1i(renderer.location('testEnabled'), index)
            pixels = renderer.draw(raw=True)
            sheet.paste(Image.fromarray((np.flipud(pixels[..., :3]) * 255).astype(np.uint8)), (index * 640, 30))
            painter.text((index * 640 + 12, 8), ['Spill OFF / synthetic stone floor', 'Spill ON / quartz violet illumination'][index], fill='white')
        sheet.save(ROOT / 'validation-emissive-preview.png')

        # Timer queries measure the real dispatch at its full 96x48x96 resolution.
        gen = driver.function('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin = driver.function('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end = driver.function('glEndQuery', None, ct.c_uint)
        get = driver.function('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete = driver.function('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        queries = (ct.c_uint * 32)()
        gen(32, queries)
        renderer.setup(default_compute)
        for query in queries:
            begin(0x88BF, query)
            renderer.dispatch(12, 6, 12)
            renderer.barrier(0xFFFFFFFF)
            end(0x88BF)
        times = []
        for query in queries:
            elapsed = ct.c_uint64()
            get(query, 0x8866, ct.byref(elapsed))
            times.append(elapsed.value / 1e6)
        delete(32, queries)
        error = renderer.get_error()
        assert error == 0, f'OpenGL error {error:#x}'
        report = {'passed': True, 'kind': 'actual GPU voxel capture, compute and receiving-surface tests; not a live Iris test',
                  'driver': driver.get_string(0x1F01).decode(), 'checks': checks, 'warnings': warnings,
                  'voxel_size': SIZE, 'volume_storage_mib': int(np.prod(SIZE)) * 17 / 1048576,
                  'compute_gpu_ms': {'median': float(np.median(times)), 'p95': float(np.percentile(times, 95))},
                  'limits': 'Synthetic scene. Timings exclude additional shadow terrain submissions, occupancy clear and terrain sampling. No in-game FPS claim.'}
        (ROOT / 'validation-emissive-gpu.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        for handle in programs:
            driver.delete_program(handle)
        for stage in stages:
            driver.delete_shader(stage)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    run()
