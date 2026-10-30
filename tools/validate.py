"""Compile XON on the installed Windows OpenGL driver without third-party modules."""

from pathlib import Path
import ctypes as ct
from ctypes import wintypes as wt
import hashlib
import json
import re
import time

ROOT = Path(__file__).resolve().parents[1]
SHADERS = ROOT / 'shaders'


class PixelFormat(ct.Structure):
    _fields_ = [('size', wt.WORD), ('version', wt.WORD), ('flags', wt.DWORD),
                ('pixel_type', ct.c_ubyte), ('color_bits', ct.c_ubyte),
                ('red_bits', ct.c_ubyte), ('red_shift', ct.c_ubyte),
                ('green_bits', ct.c_ubyte), ('green_shift', ct.c_ubyte),
                ('blue_bits', ct.c_ubyte), ('blue_shift', ct.c_ubyte),
                ('alpha_bits', ct.c_ubyte), ('alpha_shift', ct.c_ubyte),
                ('accum_bits', ct.c_ubyte), ('accum_red', ct.c_ubyte),
                ('accum_green', ct.c_ubyte), ('accum_blue', ct.c_ubyte),
                ('accum_alpha', ct.c_ubyte), ('depth_bits', ct.c_ubyte),
                ('stencil_bits', ct.c_ubyte), ('aux_buffers', ct.c_ubyte),
                ('layer_type', ct.c_ubyte), ('reserved', ct.c_ubyte),
                ('layer_mask', wt.DWORD), ('visible_mask', wt.DWORD), ('damage_mask', wt.DWORD)]


class Driver:
    def __init__(self):
        self.user = ct.WinDLL('user32', use_last_error=True)
        self.gdi = ct.WinDLL('gdi32', use_last_error=True)
        self.gl = ct.WinDLL('opengl32', use_last_error=True)
        self.user.CreateWindowExW.restype = wt.HWND
        self.user.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                            ct.c_int, ct.c_int, ct.c_int, ct.c_int,
                                            wt.HWND, wt.HMENU, wt.HINSTANCE, ct.c_void_p]
        self.user.GetDC.argtypes = [wt.HWND]
        self.user.GetDC.restype = wt.HDC
        self.user.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
        self.user.DestroyWindow.argtypes = [wt.HWND]
        self.gdi.ChoosePixelFormat.argtypes = [wt.HDC, ct.POINTER(PixelFormat)]
        self.gdi.SetPixelFormat.argtypes = [wt.HDC, ct.c_int, ct.POINTER(PixelFormat)]
        self.gl.wglCreateContext.argtypes = [wt.HDC]
        self.gl.wglCreateContext.restype = ct.c_void_p
        self.gl.wglMakeCurrent.argtypes = [wt.HDC, ct.c_void_p]
        self.gl.wglDeleteContext.argtypes = [ct.c_void_p]
        self.gl.wglGetProcAddress.argtypes = [ct.c_char_p]
        self.gl.wglGetProcAddress.restype = ct.c_void_p
        self.window = self.user.CreateWindowExW(0, 'STATIC', 'XON OpenGL validation',
                                                0, 0, 0, 64, 64, None, None, None, None)
        if not self.window:
            raise ct.WinError(ct.get_last_error())
        self.dc = self.user.GetDC(self.window)
        fmt = PixelFormat()
        fmt.size = ct.sizeof(PixelFormat)
        fmt.version = 1
        fmt.flags = 0x00000004 | 0x00000020
        fmt.color_bits = 32
        fmt.alpha_bits = 8
        fmt.depth_bits = 24
        chosen = self.gdi.ChoosePixelFormat(self.dc, ct.byref(fmt))
        if not chosen or not self.gdi.SetPixelFormat(self.dc, chosen, ct.byref(fmt)):
            raise ct.WinError(ct.get_last_error())
        self.context = self.gl.wglCreateContext(self.dc)
        if not self.context or not self.gl.wglMakeCurrent(self.dc, self.context):
            raise ct.WinError(ct.get_last_error())
        self.get_string = self.function('glGetString', ct.c_char_p, ct.c_uint)
        self.create_shader = self.function('glCreateShader', ct.c_uint, ct.c_uint)
        self.shader_source = self.function('glShaderSource', None, ct.c_uint, ct.c_int,
                                           ct.POINTER(ct.c_char_p), ct.POINTER(ct.c_int))
        self.compile_shader = self.function('glCompileShader', None, ct.c_uint)
        self.get_shader = self.function('glGetShaderiv', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_int))
        self.shader_log = self.function('glGetShaderInfoLog', None, ct.c_uint, ct.c_int,
                                        ct.POINTER(ct.c_int), ct.c_char_p)
        self.delete_shader = self.function('glDeleteShader', None, ct.c_uint)
        self.create_program = self.function('glCreateProgram', ct.c_uint)
        self.attach_shader = self.function('glAttachShader', None, ct.c_uint, ct.c_uint)
        self.link_program = self.function('glLinkProgram', None, ct.c_uint)
        self.get_program = self.function('glGetProgramiv', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_int))
        self.program_log = self.function('glGetProgramInfoLog', None, ct.c_uint, ct.c_int,
                                         ct.POINTER(ct.c_int), ct.c_char_p)
        self.delete_program = self.function('glDeleteProgram', None, ct.c_uint)

    def function(self, name, result, *args):
        pointer = self.gl.wglGetProcAddress(name.encode())
        if pointer not in [None, 1, 2, 3, ct.c_void_p(-1).value]:
            return ct.WINFUNCTYPE(result, *args)(pointer)
        function = getattr(self.gl, name)
        function.restype = result
        function.argtypes = args
        return function

    def compile(self, source, stage, label):
        shader = self.create_shader(0x8B31 if stage == '.vsh' else 0x8B30)
        encoded = source.encode()
        pointer = ct.c_char_p(encoded)
        length = ct.c_int(len(encoded))
        self.shader_source(shader, 1, ct.byref(pointer), ct.byref(length))
        self.compile_shader(shader)
        status = ct.c_int()
        self.get_shader(shader, 0x8B81, ct.byref(status))
        log = ct.create_string_buffer(65536)
        self.shader_log(shader, len(log), None, log)
        message = log.value.decode(errors='replace').strip()
        if not status.value:
            self.delete_shader(shader)
            raise RuntimeError(f'{label}\n{message}')
        return shader, message

    def link(self, vertex, fragment, label):
        program = self.create_program()
        self.attach_shader(program, vertex)
        self.attach_shader(program, fragment)
        self.link_program(program)
        status = ct.c_int()
        self.get_program(program, 0x8B82, ct.byref(status))
        log = ct.create_string_buffer(65536)
        self.program_log(program, len(log), None, log)
        message = log.value.decode(errors='replace').strip()
        if not status.value:
            self.delete_program(program)
            raise RuntimeError(f'{label}\n{message}')
        return program, message

    def close(self):
        self.gl.wglMakeCurrent(None, None)
        self.gl.wglDeleteContext(self.context)
        self.user.ReleaseDC(self.window, self.dc)
        self.user.DestroyWindow(self.window)


def expand(path, active=()):
    if path in active:
        raise ValueError(f'Include cycle at {path}')
    source = path.read_text(encoding='utf-8')
    pattern = re.compile(r'^\s*#include\s+"([^"]+)"\s*$', re.M)

    def include(match):
        name = match[1]
        dependency = SHADERS / name.lstrip('/') if name.startswith('/') else path.parent / name
        if not dependency.is_file() or not dependency.resolve().is_relative_to(SHADERS.resolve()):
            raise ValueError(f'Invalid include {name} in {path}')
        return expand(dependency, active + (path,))

    return pattern.sub(include, source)


def variant_source(path, options):
    source = expand(path)
    for option, value in options.items():
        pattern = rf'^([ \t]*)(?://[ \t]*)?#define[ \t]+{re.escape(option)}(?:[ \t]+[^\n]*)?$'
        replacement = rf'\1#undef {option}' if value is False else rf'\1#define {option} {value}'
        source, count = re.subn(pattern, replacement, source, flags=re.M)
        if count == 0 and value is not False:
            source, count = re.subn(
                rf'^(const\s+\w+\s+{re.escape(option)}\s*=\s*)[^;]+;',
                lambda match: match[1] + str(value) + ';', source, flags=re.M)
        if count > 1:
            raise ValueError(f'Duplicate option {option}: {count}')
    definitions = '\n#define MC_RENDER_STAGE_SUNSET 2\n#define MC_RENDER_STAGE_STARS 6\n'
    return source.replace('#version 330 compatibility', '#version 330 compatibility' + definitions, 1)


def validate():
    started = time.perf_counter()
    report = {'kind': 'native OpenGL driver compile/link; not an Iris runtime test',
              'driver': {}, 'variants': {}, 'warnings': [], 'failures': []}
    driver = Driver()
    shaders = {}
    try:
        report['driver'] = {name: driver.get_string(enum).decode() for name, enum in
                            [('vendor', 0x1F00), ('renderer', 0x1F01), ('version', 0x1F02),
                             ('glsl', 0x8B8C)]}
        variants = {'native': {}, 'boost85': {'XON_RENDER_MODE': 1},
                    'boost75': {'XON_RENDER_MODE': 2},
                    'effects_off': {'XON_MOTION_BLUR': False, 'XON_HAND_LIGHT': False,
                                    'XON_CLOUD_LIGHTING': False, 'XON_WATER_DETAIL': 0,
                                    'XON_SHADOWS': False, 'XON_LIGHT_SHAFTS': False,
                                    'XON_EMISSIVE_ORES': False, 'XON_BLOOM': False,
                                    'XON_REFRACTION': False, 'XON_COLOR_GRADE': False,
                                    'XON_EDGE_AA': False, 'XON_CLOUD_STYLE': 0},
                    'speed': {'XON_SHADOWS': False, 'XON_LIGHT_SHAFTS': False,
                              'XON_BLOOM': False, 'XON_REFRACTION': False, 'XON_CLOUD_STYLE': 0},
                    'shadow1536_fog': {'shadowMapResolution': 1536, 'XON_AIR_FOG': 1},
                    'cinematic': {'shadowMapResolution': 1536, 'shadowDistance': '128.0',
                                  'XON_AA_MODE': 2, 'XON_ANISOTROPIC': 6, 'XON_AIR_FOG': 1,
                                  'XON_SMOOTH_SHADOW_LOD': 1},
                    'minimum_shadows': {'shadowMapResolution': 512, 'shadowDistance': '64.0',
                                        'XON_AA_MODE': 0, 'XON_ANISOTROPIC': 0},
                    'water_no_refraction': {'XON_REFRACTION': False},
                    'water_no_shadows': {'XON_SHADOWS': False}}
        for label, options in variants.items():
            count = 0
            entrypoints = sorted(path for path in SHADERS.rglob('*.vsh')
                                 if path.parent in [SHADERS, SHADERS / 'world-1', SHADERS / 'world1'])
            if len(entrypoints) != 82:
                raise ValueError(f'Expected 82 runtime entrypoints, found {len(entrypoints)}')
            for vertex_path in entrypoints:
                fragment_path = vertex_path.with_suffix('.fsh')
                if not fragment_path.is_file():
                    raise ValueError(f'Missing fragment pair for {vertex_path}')
                pair = []
                source_label = f'{label}/{vertex_path.relative_to(SHADERS).with_suffix("")}'
                try:
                    for path in [vertex_path, fragment_path]:
                        source = variant_source(path, options)
                        key = (path.suffix, hashlib.sha256(source.encode()).hexdigest())
                        if key not in shaders:
                            shader, warning = driver.compile(source, path.suffix, source_label)
                            shaders[key] = shader
                            if warning:
                                report['warnings'].append({'program': source_label, 'log': warning})
                        pair.append(shaders[key])
                    program, warning = driver.link(*pair, source_label)
                    driver.delete_program(program)
                    if warning:
                        report['warnings'].append({'program': source_label, 'log': warning})
                    count += 1
                except (RuntimeError, ValueError) as error:
                    report['failures'].append(str(error))
            report['variants'][label] = {'program_pairs_linked': count}
            print(label, count, 'pairs linked', flush=True)
        report['unique_stages_compiled'] = len(shaders)
    finally:
        for shader in shaders.values():
            driver.delete_shader(shader)
        driver.close()
    report['duration_seconds'] = round(time.perf_counter() - started, 3)
    report['passed'] = not report['failures']
    output = ROOT / 'validation-driver.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'warnings'}, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    validate()
