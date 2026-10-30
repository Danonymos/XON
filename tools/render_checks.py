"""Exercise real final-pass pixels on a small offscreen OpenGL framebuffer."""

from pathlib import Path
import ctypes as ct
import json
import numpy as np

from validate import Driver, SHADERS, variant_source

ROOT = Path(__file__).resolve().parents[1]


class Renderer:
    def __init__(self, driver, width=256, height=144):
        self.driver = driver
        self.width = width
        self.height = height
        f = driver.function
        uint = ct.c_uint
        integer = ct.c_int
        pointer = ct.c_void_p
        self.gen_textures = f('glGenTextures', None, integer, ct.POINTER(uint))
        self.delete_textures = f('glDeleteTextures', None, integer, ct.POINTER(uint))
        self.bind_texture = f('glBindTexture', None, uint, uint)
        self.tex_parameter = f('glTexParameteri', None, uint, uint, integer)
        self.tex_image = f('glTexImage2D', None, uint, integer, integer, integer, integer,
                           integer, uint, uint, pointer)
        self.active_texture = f('glActiveTexture', None, uint)
        self.gen_framebuffers = f('glGenFramebuffers', None, integer, ct.POINTER(uint))
        self.bind_framebuffer = f('glBindFramebuffer', None, uint, uint)
        self.attach_texture = f('glFramebufferTexture2D', None, uint, uint, uint, uint, integer)
        self.check_framebuffer = f('glCheckFramebufferStatus', uint, uint)
        self.delete_framebuffers = f('glDeleteFramebuffers', None, integer, ct.POINTER(uint))
        self.use_program = f('glUseProgram', None, uint)
        self.uniform_location = f('glGetUniformLocation', integer, uint, ct.c_char_p)
        self.uniform1i = f('glUniform1i', None, integer, integer)
        self.uniform1f = f('glUniform1f', None, integer, ct.c_float)
        self.uniform3f = f('glUniform3f', None, integer, ct.c_float, ct.c_float, ct.c_float)
        self.uniform_matrix = f('glUniformMatrix4fv', None, integer, integer, ct.c_ubyte, pointer)
        self.viewport = f('glViewport', None, integer, integer, integer, integer)
        self.begin = f('glBegin', None, uint)
        self.end = f('glEnd', None)
        self.tex_coord = f('glTexCoord2f', None, ct.c_float, ct.c_float)
        self.vertex = f('glVertex2f', None, ct.c_float, ct.c_float)
        self.read_pixels = f('glReadPixels', None, integer, integer, integer, integer, uint, uint, pointer)
        self.disable = f('glDisable', None, uint)
        self.get_error = f('glGetError', uint)
        self.textures = (uint * 12)()
        self.gen_textures(12, self.textures)
        for texture in self.textures:
            self.bind_texture(0x0DE1, texture)
            self.tex_parameter(0x0DE1, 0x2801, 0x2601)
            self.tex_parameter(0x0DE1, 0x2800, 0x2601)
            self.tex_parameter(0x0DE1, 0x2802, 0x812F)
            self.tex_parameter(0x0DE1, 0x2803, 0x812F)
        self.framebuffer = uint()
        self.gen_framebuffers(1, ct.byref(self.framebuffer))
        self.bind_framebuffer(0x8D40, self.framebuffer)
        self.bind_texture(0x0DE1, self.textures[11])
        self.tex_image(0x0DE1, 0, 0x8814, width, height, 0, 0x1908, 0x1406, None)
        self.attach_texture(0x8D40, 0x8CE0, 0x0DE1, self.textures[11], 0)
        if self.check_framebuffer(0x8D40) != 0x8CD5:
            raise RuntimeError('Offscreen framebuffer incomplete')
        self.disable(0x0BE2)
        self.disable(0x0B71)

    def location(self, name):
        return self.uniform_location(self.program, name.encode())

    def texture(self, unit, data):
        data = np.ascontiguousarray(data, dtype=np.float32)
        self.active_texture(0x84C0 + unit)
        self.bind_texture(0x0DE1, self.textures[unit])
        channels = 4 if data.ndim == 3 else 1
        internal, external = (0x8814, 0x1908) if channels == 4 else (0x822E, 0x1903)
        height, width = data.shape[:2]
        self.tex_image(0x0DE1, 0, internal, width, height, 0,
                       external, 0x1406, data.ctypes.data)

    def setup(self, program):
        self.program = program
        self.use_program(program)
        for name, unit in [('colortex0', 0), ('colortex4', 1), ('depthtex0', 2),
                           ('colortex5', 3), ('xonGradeLUT', 4), ('noisetex', 5),
                           ('colortex7', 6), ('shadowtex0', 7), ('gtexture', 8), ('depthtex1', 9)]:
            self.uniform1i(self.location(name), unit)
        for name, value in [('viewWidth', self.width), ('viewHeight', self.height),
                             ('frameTime', 1 / 120)]:
            self.uniform1f(self.location(name), value)
        self.uniform1i(self.location('frameCounter'), 120)
        near, far = 0.05, 1024.0
        projection = np.array([[1.0, 0, 0, 0], [0, 1.7777778, 0, 0],
                               [0, 0, -(far + near) / (far - near), -2 * far * near / (far - near)],
                               [0, 0, -1, 0]], dtype=np.float32)
        for name, matrix in [('gbufferProjection', projection),
                              ('gbufferPreviousProjection', projection),
                              ('gbufferProjectionInverse', np.linalg.inv(projection)),
                              ('gbufferModelViewInverse', np.eye(4)),
                              ('gbufferPreviousModelView', np.eye(4))]:
            column_major = np.ascontiguousarray(matrix.T, dtype=np.float32)
            self.uniform_matrix(self.location(name), 1, 0, column_major.ctypes.data)
        self.uniform3f(self.location('cameraPosition'), 0, 0, 0)
        self.uniform3f(self.location('previousCameraPosition'), 0, 0, 0)

    def draw(self, raw=False):
        self.viewport(0, 0, self.width, self.height)
        self.begin(0x0007)
        for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
            self.tex_coord(x, y)
            self.vertex(x, y)
        self.end()
        output = np.empty((self.height, self.width, 4), dtype=np.float32)
        self.read_pixels(0, 0, self.width, self.height, 0x1908, 0x1406, output.ctypes.data)
        error = self.get_error()
        if error:
            raise RuntimeError(f'OpenGL error {error:#x}')
        if not np.isfinite(output).all() or (not raw and (np.min(output) < 0 or np.max(output) > 1)):
            raise AssertionError('Nonfinite or out-of-range final pixels')
        return output

    def close(self):
        self.delete_framebuffers(1, ct.byref(self.framebuffer))
        self.delete_textures(12, self.textures)


def expected_color(rgb):
    color = np.asarray(rgb, dtype=np.float32) * 1.05
    color = color * (2.51 * color + 0.03) / (color * (2.43 * color + 0.59) + 0.14)
    return np.clip(color ** (1 / 2.2), 0, 1)


def check():
    driver = Driver()
    renderer = Renderer(driver)
    stages = []
    programs = []
    results = []
    try:
        for mode, scale in [(0, 1.0), (1, 0.85), (2, 0.75)]:
            compiled = []
            for stage in ['vsh', 'fsh']:
                source = variant_source(SHADERS / f'final.{stage}',
                                        {'XON_RENDER_MODE': mode, 'XON_BLOOM': False,
                                         'XON_LIGHT_SHAFTS': False, 'XON_COLOR_GRADE': False})
                shader, warning = driver.compile(source, '.' + stage, f'pixel test mode {mode}')
                stages.append(shader)
                compiled.append(shader)
            program, warning = driver.link(*compiled, f'pixel test mode {mode}')
            programs.append(program)
            renderer.setup(program)
            width, height = renderer.width, renderer.height
            scene = np.zeros((height, width, 4), dtype=np.float32)
            scene[:] = [8, 0, 8, 1]
            active_width = int(np.ceil(width * scale))
            active_height = int(np.ceil(height * scale))
            color = [0.18, 0.50, 1.20]
            scene[:active_height, :active_width] = color + [1]
            mask = np.zeros((height, width), dtype=np.float32)
            depth = np.full((height, width), 0.95, dtype=np.float32)
            for unit, array in enumerate([scene, mask, depth]):
                renderer.texture(unit, array)
            output = renderer.draw()
            error = float(np.max(np.abs(output[3:-3, 3:-3, :3] - expected_color(color))))
            if error > 0.006:
                raise AssertionError(f'Boost mapping/color continuity failed in mode {mode}: {error}')
            results.append({'mode': mode, 'case': 'constant HDR and inactive-region rejection',
                            'maximum_display_error': error})

            pattern = np.indices((height, width)).sum(axis=0) % 2
            scene[..., :3] = np.where(pattern[..., None] == 0, 0.04, 0.85)
            renderer.texture(0, scene)
            stationary = renderer.draw()
            renderer.uniform3f(renderer.location('previousCameraPosition'), -0.12, 0, 0)
            moving = renderer.draw()
            motion_change = float(np.mean(np.abs(moving[8:-8, 8:-8, :3] - stationary[8:-8, 8:-8, :3])))
            if motion_change < 0.001:
                raise AssertionError(f'Camera blur did not affect moving checkerboard: {motion_change}')
            results.append({'mode': mode, 'case': 'camera blur changes moving fine detail',
                            'mean_display_change': motion_change})
            x0, x1 = int(width * scale * 0.35), int(width * scale * 0.65)
            y0, y1 = int(height * scale * 0.35), int(height * scale * 0.65)
            mask[y0:y1, x0:x1] = 1
            renderer.texture(1, mask)
            protected = renderer.draw()
            region = (slice(int(height * 0.40), int(height * 0.60)),
                      slice(int(width * 0.40), int(width * 0.60)), slice(0, 3))
            protected_error = float(np.max(np.abs(protected[region] - stationary[region])))
            if protected_error > 0.0001:
                raise AssertionError(f'Hand mask did not preserve fine detail: {protected_error}')
            results.append({'mode': mode, 'case': 'hand mask preserves fine detail during camera motion',
                            'maximum_display_error': protected_error})
            mask[:] = 0
            renderer.texture(1, mask)
            for frame_time in [0.0, 0.25, -0.01]:
                renderer.uniform1f(renderer.location('frameTime'), frame_time)
                guarded = renderer.draw()
                if float(np.max(np.abs(guarded - stationary))) > 0.0001:
                    raise AssertionError('Invalid-frame guard did not suppress blur')
            renderer.uniform1f(renderer.location('frameTime'), 1 / 120)
            renderer.uniform3f(renderer.location('previousCameraPosition'), 1000, 0, 0)
            guarded = renderer.draw()
            if float(np.max(np.abs(guarded - stationary))) > 0.0001:
                raise AssertionError('Teleport guard did not suppress blur')
            results.append({'mode': mode, 'case': 'invalid frame and teleport guards', 'passed': True})
    finally:
        for program in programs:
            driver.delete_program(program)
        for shader in stages:
            driver.delete_shader(shader)
        renderer.close()
        driver.close()
    report = {'kind': 'offscreen synthetic final-pass pixel checks; not Minecraft FPS',
              'passed': True, 'checks': results}
    (ROOT / 'validation-pixels.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    check()
