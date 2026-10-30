"""Render the lighting libraries and real shadow/final programs on the GPU."""

from pathlib import Path
import ctypes as ct
import json
import re
import numpy as np
from PIL import Image

from validate import Driver, SHADERS, expand, variant_source
from render_checks import Renderer, expected_color

ROOT = Path(__file__).resolve().parents[1]


def run():
    driver = Driver()
    renderer = Renderer(driver)
    stages, programs, checks = [], [], []

    def compile_pair(vertex, fragment, label):
        pair = []
        for source, stage in [(vertex, '.vsh'), (fragment, '.fsh')]:
            shader, warning = driver.compile(source, stage, label)
            if warning:
                raise AssertionError(f'{label}: {warning}')
            stages.append(shader)
            pair.append(shader)
        program, warning = driver.link(*pair, label)
        if warning:
            raise AssertionError(f'{label}: {warning}')
        programs.append(program)
        return program

    def fragment(body, libraries, options=None):
        source = '#version 330 compatibility\n#define XON_DIMENSION 0\n'
        source += '\n'.join(expand(SHADERS / 'lib' / f'{name}.glsl') for name in libraries)
        source += '\nin vec2 xonUV;\nlayout(location=0) out vec4 result;\n' + body
        for name, value in (options or {}).items():
            pattern = rf'^([ \t]*)(?://[ \t]*)?#define[ \t]+{name}(?:[ \t]+[^\n]*)?$'
            replacement = f'#undef {name}' if value is False else f'#define {name} {value}'
            source = re.sub(pattern, replacement, source, flags=re.M)
        return compile_pair(variant_source(SHADERS / 'final.vsh', {}), source, body[:65])

    def actual(name, options=None):
        return compile_pair(*(variant_source(SHADERS / f'{name}.{stage}', options or {})
                              for stage in ['vsh', 'fsh']), name)

    def matrix(name, value):
        data = np.ascontiguousarray(value.T, dtype=np.float32)
        renderer.uniform_matrix(renderer.location(name), 1, 0, data.ctypes.data)

    def shadow_texture(data):
        data = np.ascontiguousarray(data, dtype=np.float32)
        renderer.active_texture(0x84C7)
        renderer.bind_texture(0x0DE1, renderer.textures[7])
        renderer.tex_image(0x0DE1, 0, 0x8CAC, data.shape[1], data.shape[0], 0,
                           0x1902, 0x1406, data.ctypes.data)
        renderer.tex_parameter(0x0DE1, 0x884C, 0x884E)
        renderer.tex_parameter(0x0DE1, 0x884D, 0x0203)

    try:
        width, height = renderer.width, renderer.height
        blank = np.zeros((height, width), dtype=np.float32)
        renderer.texture(1, blank)
        renderer.texture(2, np.full_like(blank, 0.99))
        renderer.texture(3, np.zeros((height, width, 4), dtype=np.float32))
        for unit, name in [(4, 'xon-grade.png'), (5, 'xon-noise.png')]:
            renderer.texture(unit, np.asarray(Image.open(SHADERS / 'textures' / name).convert('RGBA')) / 255.0)
        renderer.active_texture(0x84C5)
        for axis in [0x2802, 0x2803]:
            renderer.tex_parameter(0x0DE1, axis, 0x2901)

        ore = fragment('''void main() {
            int index = min(int(xonUV.x * 18.0), 17);
            vec3 veins[9] = vec3[9](vec3(.2,.85,.9),vec3(.1,.8,.25),vec3(.8,.1,.08),
                vec3(.1,.25,.8),vec3(.9,.7,.15),vec3(.75,.6,.49),vec3(.8,.5,.25),
                vec3(.95,.72,.15),vec3(.9,.85,.8));
            vec3 color = index % 2 == 0 ? vec3(.45) : veins[index / 2];
            float emission = xonOreEmission(10010.0 + float(index / 2), color);
            result = vec4(vec3(emission), 1.0);
        }''', ['settings', 'materials'])
        renderer.setup(ore)
        ore_pixels = renderer.draw(raw=True)
        values = [float(ore_pixels[height // 2, int((index + .5) / 18 * width), 0]) for index in range(18)]
        if max(values[::2]) > 0.0001 or min(values[1::2]) < 0.2:
            raise AssertionError(f'Ore mask lit host rock or missed a colored vein: {values}')
        checks.append({'case': 'nine ore families: colored veins glow, gray host rock stays dark', 'emission': values})

        shadow_program = actual('shadow')
        shadow_texture(np.ones((1024, 1024), dtype=np.float32))
        shadow_fbo = ct.c_uint()
        renderer.gen_framebuffers(1, ct.byref(shadow_fbo))
        enable = driver.function('glEnable', None, ct.c_uint)
        clear = driver.function('glClear', None, ct.c_uint)
        clear_depth = driver.function('glClearDepth', None, ct.c_double)
        draw_buffer = driver.function('glDrawBuffer', None, ct.c_uint)
        read_buffer = driver.function('glReadBuffer', None, ct.c_uint)
        matrix_mode = driver.function('glMatrixMode', None, ct.c_uint)
        identity = driver.function('glLoadIdentity', None)
        vertex3 = driver.function('glVertex3f', None, ct.c_float, ct.c_float, ct.c_float)

        def draw_shadow(alpha):
            renderer.texture(8, np.full((2, 2, 4), [1, 1, 1, alpha], dtype=np.float32))
            renderer.bind_framebuffer(0x8D40, shadow_fbo)
            renderer.attach_texture(0x8D40, 0x8D00, 0x0DE1, renderer.textures[7], 0)
            draw_buffer(0)
            read_buffer(0)
            if renderer.check_framebuffer(0x8D40) != 0x8CD5:
                raise AssertionError('Depth-only shadow framebuffer incomplete')
            renderer.setup(shadow_program)
            renderer.uniform1f(renderer.location('alphaTestRef'), .1)
            renderer.active_texture(0x84C0)
            for mode in [0x1700, 0x1701, 0x1702]:
                matrix_mode(mode)
                identity()
            renderer.viewport(0, 0, 1024, 1024)
            enable(0x0B71)
            clear_depth(1)
            clear(0x00000100)
            renderer.begin(0x0007)
            for x, y in [(-.9, -.9), (0, -.9), (0, .9), (-.9, .9)]:
                renderer.tex_coord(.5, .5)
                vertex3(x, y, -.5)
            renderer.end()
            renderer.disable(0x0B71)
            renderer.bind_framebuffer(0x8D40, renderer.framebuffer)
            draw_buffer(0x8CE0)
            read_buffer(0x8CE0)
            error = renderer.get_error()
            if error:
                raise AssertionError(f'Shadow render OpenGL error {error:#x}')

        lighting = fragment('''void main() {
            float visibility;
            vec3 pos = vec3((xonUV.x-.5)*1.2,0,0);
            vec3 color = xonLighting(vec3(.4), vec3(0,1,0),
                pos, pos, vec2(0,1), 0.0, 0.0, visibility);
            result = vec4(color, visibility);
        }''', ['settings', 'uniforms', 'math', 'atmosphere', 'shadows', 'lighting'])
        draw_shadow(1)
        renderer.setup(lighting)
        for name in ['shadowModelView', 'shadowProjection']:
            matrix(name, np.eye(4))
        renderer.uniform3f(renderer.location('sunPosition'), 0, 100, 0)
        cast = renderer.draw(raw=True)
        shade = cast[height // 2, width // 4]
        sunlight = cast[height // 2, width * 3 // 4]
        if shade[3] > .01 or sunlight[3] < .99 or np.mean(sunlight[:3]) < np.mean(shade[:3]) * 3:
            raise AssertionError(f'Shadow map/receiver disagreement: shade {shade}, sun {sunlight}')
        checks.append({'case': 'actual shadow vertex/depth pass aligns with hardware-PCF receiver',
                       'shade': shade.tolist(), 'sun': sunlight.tolist()})
        draw_shadow(0)
        renderer.setup(lighting)
        cutout = renderer.draw(raw=True)
        if float(np.min(cutout[..., 3])) < .99:
            raise AssertionError('Transparent shadow caster did not discard')
        checks.append({'case': 'cutout alpha leaves no opaque shadow', 'passed': True})
        renderer.delete_framebuffers(1, ct.byref(shadow_fbo))

        fog = fragment('''void main() {
            result = vec4(xonFog(vec3(.2,.4,.8),vec3(0,0,-1.0-xonUV.x*300.0),1.0),1);
        }''', ['settings', 'uniforms', 'math', 'atmosphere'])
        renderer.setup(fog)
        clear_air = renderer.draw(raw=True)
        error = float(np.max(np.abs(clear_air[..., :3] - [.2, .4, .8])))
        if error > .00001:
            raise AssertionError(f'Default air still has distance haze: {error}')
        matrix('gbufferModelViewInverse', np.eye(4))
        renderer.uniform1f(renderer.location('far'), 192.0)
        renderer.uniform3f(renderer.location('sunPosition'), 0.0, 90.0, 0.0)
        renderer.uniform3f(renderer.location('skyColor'), 0.45, 0.68, 0.98)
        border_fog = renderer.draw(raw=True)
        near_chunk_err = float(np.max(np.abs(border_fog[:, :width // 4, :3] - [.2, .4, .8])))
        far_chunk_diff = float(np.mean(np.abs(border_fog[:, -8:, :3] - [.2, .4, .8])))
        if near_chunk_err > 0.0001 or far_chunk_diff < 0.12:
            raise AssertionError(f'12-chunk border fog failed near clarity or far sky blend: near_err={near_chunk_err}, far_diff={far_chunk_diff}')
        renderer.uniform1f(renderer.location('far'), 0.0)
        renderer.uniform1i(renderer.location('isEyeInWater'), 1)
        renderer.uniform3f(renderer.location('fogColor'), .1, .2, .3)
        underwater = renderer.draw(raw=True)
        if np.mean(underwater[:, -4:, :3]) >= np.mean(underwater[:, :4, :3]):
            raise AssertionError('Underwater absorption lost its distance response')
        checks.append({'case': 'default air stays clear near player, smoothly fogs 12-chunk border into horizon sky, and preserves underwater absorption',
                       'maximum_near_air_error': near_chunk_err, 'chunk_border_sky_blend': far_chunk_diff})

        water_vertex = '''#version 330 compatibility
            out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels; out vec4 xonVertexColor;
            out vec3 xonViewPosition; out vec3 xonPlayerPosition; out vec3 xonWorldNormal; flat out float xonMaterial;
            void main(){
                vec2 uv=gl_MultiTexCoord0.xy;
                xonTexCoord=uv; xonAtlasBounds=vec4(0); xonLightLevels=vec2(0,1); xonVertexColor=vec4(.2,.5,.8,1);
                xonViewPosition=vec3((uv.x-.5)*4.0,-5,-5); xonPlayerPosition=xonViewPosition; xonWorldNormal=vec3(0,1,0);
                xonMaterial=10001.0; gl_Position=vec4(gl_Vertex.xy*2.0-1.0,0,1);
            }'''
        water_options = {'XON_SHADOWS': False, 'XON_CLOUD_STYLE': 0, 'XON_WATER_DETAIL': 0}
        water = compile_pair(water_vertex, variant_source(SHADERS / 'gbuffers_water.fsh', water_options), 'real water fragment')
        water_without_copy = compile_pair(water_vertex, variant_source(SHADERS / 'gbuffers_water.fsh',
                                          dict(water_options, XON_REFRACTION=False)), 'water refraction disabled')
        background = np.full((height, width, 4), [.65, .60, .55, 1], dtype=np.float32)
        renderer.texture(6, background[::2, ::2])
        renderer.texture(8, np.ones((2, 2, 4), dtype=np.float32))

        def background_depth(distance):
            near, far = .05, 1024.0
            ndc = (far + near) / (far - near) - (2 * far * near) / ((far - near) * distance)
            return np.full_like(blank, ndc * .5 + .5)

        renderer.setup(water)
        renderer.uniform1f(renderer.location('alphaTestRef'), .1)
        renderer.uniform3f(renderer.location('sunPosition'), 20, 90, 10)
        renderer.texture(9, background_depth(5.1))
        shallow_water = renderer.draw(raw=True)
        renderer.texture(9, background_depth(30))
        deep_water = renderer.draw(raw=True)
        if np.mean(shallow_water[..., 0]) < np.mean(deep_water[..., 0]) * 1.5:
            raise AssertionError('Water has no depth-dependent red absorption')
        if np.min(shallow_water[..., 3]) < .9999:
            raise AssertionError('Water copy was blended twice with the opaque background')
        renderer.setup(water_without_copy)
        renderer.uniform1f(renderer.location('alphaTestRef'), .1)
        renderer.uniform3f(renderer.location('sunPosition'), 20, 90, 10)
        fallback_water = renderer.draw(raw=True)
        if np.max(fallback_water[..., 3]) >= 1:
            raise AssertionError('Non-refractive water lost its transparency')
        checks.append({'case': 'real water fragment uses depth absorption, single background composition, and transparent fallback',
                       'shallow_red': float(np.mean(shallow_water[..., 0])), 'deep_red': float(np.mean(deep_water[..., 0]))})

        aa_options = {'XON_BLOOM': False, 'XON_LIGHT_SHAFTS': False, 'XON_COLOR_GRADE': False,
                      'XON_MOTION_BLUR': False}
        aa_on = actual('final', aa_options)
        aa_off = actual('final', dict(aa_options, XON_EDGE_AA=False))
        yy, xx = np.indices((height, width), dtype=np.float32)
        edge = xx + .5 < .61 * (yy + .5) + 62.37
        dark, light = np.array([.025, .03, .045]), np.array([.9, .8, .65])
        scene = np.ones((height, width, 4), dtype=np.float32)
        scene[..., :3] = np.where(edge[..., None], light, dark)
        renderer.texture(0, scene)
        renderer.texture(2, np.where(edge, .90, .99))
        renderer.setup(aa_off)
        jagged = renderer.draw()
        renderer.setup(aa_on)
        smoothed = renderer.draw()
        coverage = np.zeros((height, width), dtype=np.float32)
        for sy in (np.arange(16) + .5) / 16:
            for sx in (np.arange(16) + .5) / 16:
                coverage += (xx + sx < .61 * (yy + sy) + 62.37) / 256
        ideal = expected_color(dark + coverage[..., None] * (light - dark))
        edge_region = np.abs(xx + .5 - .61 * (yy + .5) - 62.37) < 2.0
        old_error = float(np.mean((jagged[..., :3][edge_region] - ideal[edge_region]) ** 2))
        new_error = float(np.mean((smoothed[..., :3][edge_region] - ideal[edge_region]) ** 2))
        if new_error >= old_error * .95:
            raise AssertionError(f'Edge AA failed to improve supersampled reference error: {old_error} -> {new_error}')
        renderer.texture(2, np.full_like(blank, .95))
        renderer.setup(aa_on)
        texture_edge = renderer.draw()
        renderer.setup(aa_off)
        texture_reference = renderer.draw()
        preserved_error = float(np.max(np.abs(texture_edge - texture_reference)))
        if preserved_error > .0001:
            raise AssertionError(f'AA blurred a texture edge on a flat surface: {preserved_error}')
        checks.append({'case': 'AA improves diagonal silhouette coverage and preserves flat-surface texture detail',
                       'jagged_mse': old_error, 'aa_mse': new_error, 'texture_detail_error': preserved_error})

        grading = fragment('void main(){result=vec4(xonApplyGrade(vec3(xonUV.x)),1);}', ['settings', 'grading'])
        renderer.setup(grading)
        graded = renderer.draw()
        neutral_spread = float(np.max(np.ptp(graded[..., :3], axis=-1)))
        if neutral_spread > .025 or np.min(np.diff(graded[height // 2, :, :3], axis=0)) < -.0001:
            raise AssertionError('Color LUT breaks neutral tones or monotonic brightness')
        checks.append({'case': 'actual LUT has restrained neutral tint and monotonic brightness', 'maximum_neutral_channel_spread': neutral_spread})

        scene[:] = [0, 0, 0, 1]
        scene[60:84, 116:140] = [.1, 4, 3, 1]
        renderer.texture(0, scene)
        bloom = actual('composite', {'XON_LIGHT_SHAFTS': False})
        renderer.setup(bloom)
        prefilter = renderer.draw(raw=True)
        renderer.texture(3, prefilter)
        soften = actual('composite1')
        renderer.setup(soften)
        glow = renderer.draw(raw=True)
        if float(np.max(glow[55:60, 112:144, 1])) < .005 or float(np.max(glow[:40, :, :3])) > .00001:
            raise AssertionError('Bloom failed to form a local halo or introduced a global veil')
        checks.append({'case': 'bloom forms a bounded colored halo with a black distant background', 'passed': True})

        shafts = actual('composite', {'XON_BLOOM': False})
        renderer.setup(shafts)
        renderer.uniform3f(renderer.location('sunPosition'), 0, 14, -99)
        uniform2i = driver.function('glUniform2i', None, ct.c_int, ct.c_int, ct.c_int)
        uniform2i(renderer.location('eyeBrightnessSmooth'), 240, 240)
        matrix('shadowModelView', np.eye(4))
        matrix('shadowProjection', np.diag([.02, .02, .02, 1.0]))
        renderer.texture(2, np.full_like(blank, .99999))
        shadow_texture(np.ones((256, 256), dtype=np.float32))
        rays = renderer.draw(raw=True)
        shadow_texture(np.zeros((256, 256), dtype=np.float32))
        blocked_rays = renderer.draw(raw=True)
        if float(np.max(rays[..., 3])) < .03 or float(np.max(blocked_rays[..., 3])) > .0001:
            raise AssertionError('Light shafts do not respond to shadow-map occlusion')
        far_from_sun = (xx / width - .5) ** 2 + (yy / height - .62) ** 2 > .25
        veil = float(np.mean(rays[..., 3][far_from_sun]))
        if veil > .003:
            raise AssertionError(f'Sun shafts created a broad veil: {veil}')
        checks.append({'case': 'rays respond to shadow occlusion and remain localized around the sun',
                       'peak': float(np.max(rays[..., 3])), 'mean_outside_sun_region': veil})

        cloud_body = '''void main(){
            vec3 direction = normalize(vec3((xonUV.x-.5)*2.8,xonUV.y*.9+.035,1));
            result=vec4(xonCloudSky(direction,true),1);
        }'''
        clouds = fragment(cloud_body, ['settings', 'uniforms', 'math', 'atmosphere', 'clouds'])
        no_clouds = fragment(cloud_body, ['settings', 'uniforms', 'math', 'atmosphere', 'clouds'], {'XON_CLOUD_STYLE': 0})
        sky_images = []
        for program in [clouds, no_clouds]:
            renderer.setup(program)
            renderer.uniform3f(renderer.location('cameraPosition'), -2020, 80, 2300)
            renderer.uniform3f(renderer.location('sunPosition'), 30, 70, 20)
            renderer.uniform3f(renderer.location('skyColor'), .5, .7, 1)
            renderer.uniform1f(renderer.location('frameTimeCounter'), 20)
            sky_images.append(renderer.draw(raw=True))
        cloud_difference = float(np.mean(np.abs(sky_images[0] - sky_images[1])))
        if cloud_difference < .005:
            raise AssertionError(f'Layered clouds are not visible: {cloud_difference}')
        renderer.setup(clouds)
        renderer.uniform1f(renderer.location('rainStrength'), 1)
        renderer.uniform1f(renderer.location('thunderStrength'), 1)
        storm = renderer.draw(raw=True)
        if np.mean(storm[..., :3]) >= np.mean(sky_images[0][..., :3]):
            raise AssertionError('Storm sky did not darken relative to daylight')
        checks.append({'case': 'layered clouds differ from clear sky and storms darken the sky', 'mean_cloud_difference': cloud_difference})
        previews = np.concatenate([expected_color(sky_images[0][..., :3]), expected_color(storm[..., :3])], axis=1)
        Image.fromarray(np.uint8(np.clip(previews[::-1], 0, 1) * 255)).resize((1024, 288)).save(ROOT / 'validation-sky-preview.png')

        sat_low = fragment('void main(){result=vec4(xonApplyGrade(vec3(0.8, 0.3, 0.2)),1);}',
                           ['settings', 'grading'], {'XON_SATURATION': 0.00})
        sat_def = fragment('void main(){result=vec4(xonApplyGrade(vec3(0.8, 0.3, 0.2)),1);}',
                           ['settings', 'grading'], {'XON_SATURATION': 0.70})
        sat_high = fragment('void main(){result=vec4(xonApplyGrade(vec3(0.8, 0.3, 0.2)),1);}',
                            ['settings', 'grading'], {'XON_SATURATION': 1.40})
        sat_chromas = []
        for p in [sat_low, sat_def, sat_high]:
            renderer.setup(p)
            px = renderer.draw()[height // 2, width // 2, :3]
            sat_chromas.append(float(np.max(px) - np.min(px)))
        if not (sat_chromas[0] < 0.01 and sat_chromas[0] < sat_chromas[1] < sat_chromas[2]):
            raise AssertionError(f'Saturation slider failed monotonic chroma test: {sat_chromas}')
        checks.append({'case': 'saturation slider scales from grayscale (0%) through 70% default to boosted (140%)',
                       'chromas': sat_chromas})

        line_black = actual('gbuffers_line', {'XON_BLOCK_OUTLINE': 0})
        line_rainbow = actual('gbuffers_line', {'XON_BLOCK_OUTLINE': 1})
        color4f = driver.function('glColor4f', None, ct.c_float, ct.c_float, ct.c_float, ct.c_float)
        normal3f = driver.function('glNormal3f', None, ct.c_float, ct.c_float, ct.c_float)
        outline_colors = []
        for p in [line_black, line_rainbow]:
            renderer.setup(p)
            renderer.uniform1f(renderer.location('frameTimeCounter'), 1.25)
            for mode in [0x1700, 0x1701]:
                matrix_mode(mode)
                identity()
            renderer.viewport(0, 0, width, height)
            clear_color = driver.function('glClearColor', None, ct.c_float, ct.c_float, ct.c_float, ct.c_float)
            clear_color(0.5, 0.5, 0.5, 1.0)
            clear(0x00004000)
            color4f(0.0, 0.0, 0.0, 0.4)
            normal3f(1.0, 0.0, 0.0)
            renderer.begin(0x0007)
            for x, y in [(-0.5, -0.1), (0.5, -0.1), (0.5, 0.1), (-0.5, 0.1)]:
                vertex3(x, y, 0.0)
            renderer.end()
            out_px = renderer.draw(raw=True) if False else None
            buf = np.empty((height, width, 4), dtype=np.float32)
            renderer.read_pixels(0, 0, width, height, 0x1908, 0x1406, buf.ctypes.data)
            outline_colors.append(buf[height // 2, width // 2, :3].tolist())
        if max(outline_colors[0]) > 0.01 or max(outline_colors[1]) < 0.5:
            raise AssertionError(f'Block outline modes failed: {outline_colors}')
        checks.append({'case': 'block selection outline supports Black and animated Rainbow modes',
                       'black_rgb': outline_colors[0], 'rainbow_rgb': outline_colors[1]})

        end_sky_src = '#version 330 compatibility\n#define XON_DIMENSION 1\n'
        end_sky_src += '\n'.join(expand(SHADERS / 'lib' / f'{name}.glsl') for name in ['settings', 'uniforms', 'math', 'atmosphere'])
        end_sky_src += '\nin vec2 xonUV;\nlayout(location=0) out vec4 result;\nvoid main(){vec3 dir=normalize(vec3((xonUV.x-.5)*2.5,xonUV.y*1.2-.2,1.0));result=vec4(xonSky(dir),1.0);}'
        end_sky_prog = compile_pair(variant_source(SHADERS / 'final.vsh', {}), end_sky_src, 'end sky aura check')
        renderer.setup(end_sky_prog)
        renderer.uniform1f(renderer.location('frameTimeCounter'), 5.0)
        end_pixels = renderer.draw(raw=True)
        end_b_mean = float(np.mean(end_pixels[..., 2]))
        end_g_mean = float(np.mean(end_pixels[..., 1]))
        end_variance = float(np.std(end_pixels[..., 2]))
        if not (end_b_mean > end_g_mean * 1.5 and end_variance > 0.01):
            raise AssertionError(f'End sky lacks purple aura variation: B={end_b_mean}, G={end_g_mean}, std={end_variance}')
        checks.append({'case': 'End sky renders dark purple/black void with spatial aura ribbons',
                       'mean_blue': end_b_mean, 'aura_std': end_variance})

        end_skytex = actual('world1/gbuffers_skytextured')
        renderer.setup(end_skytex)
        renderer.uniform1f(renderer.location('frameTimeCounter'), 5.0)
        for mode in [0x1700, 0x1701]:
            matrix_mode(mode)
            identity()
        renderer.viewport(0, 0, width, height)
        renderer.begin(0x0007)
        for x, y in [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]:
            renderer.tex_coord(x * 0.5 + 0.5, y * 0.5 + 0.5)
            vertex3(x, y, -0.5)
        renderer.end()
        end_skytex_buf = np.empty((height, width, 4), dtype=np.float32)
        renderer.read_pixels(0, 0, width, height, 0x1908, 0x1406, end_skytex_buf.ctypes.data)
        if float(np.std(end_skytex_buf[..., 2])) < 0.005:
            raise AssertionError('world1/gbuffers_skytextured did not render procedural End aura sky')
        checks.append({'case': 'End gbuffers_skytextured overrides vanilla tile sky with procedural aura sky',
                       'std_blue': float(np.std(end_skytex_buf[..., 2]))})

        lava_vsh = '''#version 330 compatibility
            out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels; out vec4 xonVertexColor;
            out vec3 xonViewPosition; out vec3 xonPlayerPosition; out vec3 xonWorldNormal; flat out float xonMaterial;
            void main(){
                vec2 uv=gl_MultiTexCoord0.xy;
                xonTexCoord=uv; xonAtlasBounds=vec4(0); xonLightLevels=vec2(1,1); xonVertexColor=vec4(1);
                xonViewPosition=vec3((uv.x-.5)*8.0,-2,-5); xonPlayerPosition=vec3((uv.x-.5)*16.0,-2,(uv.y-.5)*16.0);
                xonWorldNormal=vec3(0,1,0); xonMaterial=10005.0; gl_Position=vec4(gl_Vertex.xy*2.0-1.0,0,1);
            }'''
        lava_prog = compile_pair(lava_vsh, variant_source(SHADERS / 'gbuffers_terrain.fsh', {'XON_SHADOWS': False}), 'lava voronoi check')
        renderer.setup(lava_prog)
        renderer.uniform1f(renderer.location('alphaTestRef'), 0.1)
        renderer.uniform1f(renderer.location('frameTimeCounter'), 3.0)
        lava_pixels = renderer.draw(raw=True)
        lava_min = float(np.min(lava_pixels[..., 0]))
        lava_max = float(np.max(lava_pixels[..., 0]))
        if lava_max - lava_min < 1.0:
            raise AssertionError(f'Lava Voronoi shader lacks dark crust and bright core contrast: min={lava_min}, max={lava_max}')
        checks.append({'case': 'Voronoi cellular lava renders dark cooling crust and bright molten fissures',
                       'red_min': lava_min, 'red_max': lava_max})

        amethyst_vsh = '''#version 330 compatibility
            out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels; out vec4 xonVertexColor;
            out vec3 xonViewPosition; out vec3 xonPlayerPosition; out vec3 xonWorldNormal; flat out float xonMaterial;
            void main(){
                vec2 uv=gl_MultiTexCoord0.xy;
                xonTexCoord=uv; xonAtlasBounds=vec4(0); xonLightLevels=vec2(1,1); xonVertexColor=vec4(1);
                xonViewPosition=vec3(0,0,-3); xonPlayerPosition=vec3(0,0,-3);
                xonWorldNormal=vec3(0.707,0,0.707); xonMaterial=10019.0; gl_Position=vec4(gl_Vertex.xy*2.0-1.0,0,1);
            }'''
        amethyst_prog = compile_pair(amethyst_vsh, variant_source(SHADERS / 'gbuffers_terrain.fsh', {'XON_SHADOWS': False}), 'amethyst crystal check')
        renderer.texture(8, np.full((2, 2, 4), [0.94, 0.88, 0.98, 1.0], dtype=np.float32))
        renderer.setup(amethyst_prog)
        renderer.uniform1f(renderer.location('alphaTestRef'), 0.1)
        amethyst_px = renderer.draw(raw=True)[height // 2, width // 2, :3]
        if not (amethyst_px[2] > amethyst_px[1] and amethyst_px[1] > 0.55):
            raise AssertionError(f'Amethyst cluster tips turned solid dark purple instead of natural pale lilac-white: {amethyst_px}')
        checks.append({'case': 'amethyst shards preserve natural pale lilac-white crystal tips and lavender facets',
                       'amethyst_rgb': [float(v) for v in amethyst_px]})

        cloud_ground = fragment('''void main() {
            float visibility;
            vec3 pos = vec3((xonUV.x - 0.5) * 64.0, 0.0, (xonUV.y - 0.5) * 64.0);
            vec3 color = xonLighting(vec3(0.5), vec3(0.0, 1.0, 0.0),
                vec3(0.0, -2.0, -5.0), pos, vec2(0.0, 1.0), 0.0, 0.0, visibility);
            result = vec4(color, 1.0);
        }''', ['settings', 'uniforms', 'math', 'atmosphere', 'clouds', 'shadows', 'lighting'], {'XON_SHADOWS': False})
        renderer.setup(cloud_ground)
        renderer.uniform3f(renderer.location('sunPosition'), 100.0, 4.0, 0.0)
        renderer.uniform1f(renderer.location('frameTimeCounter'), 0.0)
        ground_t0 = renderer.draw(raw=True)[..., :3]
        renderer.uniform1f(renderer.location('frameTimeCounter'), 8.0)
        ground_t1 = renderer.draw(raw=True)[..., :3]
        luma_t0 = ground_t0 @ np.array([0.2126, 0.7152, 0.0722])
        min_ground = float(np.min(luma_t0))
        max_ground = float(np.max(luma_t0))
        motion_diff = float(np.mean(np.abs(ground_t1 - ground_t0)))
        if max_ground < min_ground * 2.0 or motion_diff < 0.02:
            raise AssertionError(f'Voronoi ground shadows/highlights too weak or static over 64-block view: min={min_ground}, max={max_ground}, motion={motion_diff}')
        checks.append({'case': '20-block-radius Voronoi ground shadow and highlight field moves across local 64-block terrain',
                       'min_luma': min_ground, 'max_luma': max_ground, 'motion_delta': motion_diff})

        dark_canopy = fragment('''void main() {
            float visibility;
            // Left half: stone under zero-skylight canopy (lightLevels = 0,0); Right half: dark tree bark in zero-skylight shade.
            vec3 albedo = xonUV.x < 0.5 ? vec3(0.20, 0.20, 0.21) : vec3(0.025, 0.016, 0.008);
            vec3 color = xonLighting(albedo, vec3(1.0, 0.0, 0.0),
                vec3(0.0, 0.0, -5.0), vec3(0.0, 0.0, -5.0), vec2(0.0, 0.0), 0.0, 0.0, visibility);
            result = vec4(color, 1.0);
        }''', ['settings', 'uniforms', 'math', 'atmosphere', 'clouds', 'shadows', 'lighting'], {'XON_SHADOWS': False})
        renderer.setup(dark_canopy)
        renderer.uniform3f(renderer.location('sunPosition'), 30.0, 80.0, 20.0)
        canopy_raw = renderer.draw(raw=True)[height // 2, :, :3]
        stone_display = expected_color(canopy_raw[width // 4])
        bark_display = expected_color(canopy_raw[width * 3 // 4])
        if float(np.mean(stone_display)) < 0.16 or float(np.mean(bark_display)) < 0.07:
            raise AssertionError(f'Zero-skylight canopy/bark areas crushed to pitch black: stone={stone_display}, bark={bark_display}')
        checks.append({'case': 'zero-skylight canopy undersides and dark tree bark stay readable with atmospheric shadow fill',
                       'stone_srgb': [float(v) for v in stone_display], 'bark_srgb': [float(v) for v in bark_display]})

        mood_sky = fragment('''void main() {
            vec3 dir = normalize(vec3((xonUV.x - 0.5) * 2.0, (xonUV.y - 0.35) * 1.2, 1.0));
            result = vec4(xonSky(dir), 1.0);
        }''', ['settings', 'uniforms', 'math', 'atmosphere'])
        renderer.setup(mood_sky)
        renderer.uniform3f(renderer.location('skyColor'), 0.48, 0.70, 0.98)
        renderer.uniform3f(renderer.location('sunPosition'), 92.0, 12.0, 20.0)
        morning_sky = renderer.draw(raw=True)[..., :3]
        renderer.uniform3f(renderer.location('sunPosition'), 0.0, 95.0, 20.0)
        noon_sky = renderer.draw(raw=True)[..., :3]
        renderer.uniform3f(renderer.location('sunPosition'), -92.0, 12.0, 20.0)
        evening_sky = renderer.draw(raw=True)[..., :3]
        morning_vs_evening = float(np.mean(np.abs(morning_sky - evening_sky)))
        noon_vs_evening = float(np.mean(np.abs(noon_sky - evening_sky)))
        if morning_vs_evening < 0.025 or noon_vs_evening < 0.08:
            raise AssertionError(f'Time-of-day moods failed to differentiate Morning, Noon, and Evening: m_e={morning_vs_evening}, n_e={noon_vs_evening}')
        checks.append({'case': '5-stage time-of-day mood differentiates Early Morning, High Noon, and Evening Sunset sky and void palettes',
                       'morning_vs_evening_diff': morning_vs_evening, 'noon_vs_evening_diff': noon_vs_evening})

        bright_blocks = fragment('''void main() {
            float visibility;
            // Monotonicity & ~70% sunlit white/sand damper test across quartz/snow ramp (0.72 -> 0.86 -> 0.98 sRGB) plus yellow shulker preservation.
            vec3 srgb = xonUV.x < 0.25 ? vec3(0.72)
                      : (xonUV.x < 0.50 ? vec3(0.86)
                      : (xonUV.x < 0.75 ? vec3(0.98) : vec3(0.95, 0.82, 0.05)));
            vec3 color = xonLighting(xonToLinear(srgb), vec3(0.0, 1.0, 0.0),
                vec3(0.0, -2.0, -5.0), vec3(0.0, -2.0, -5.0), vec2(0.0, 1.0), 0.0, 0.0, visibility);
            result = vec4(color, 1.0);
        }''', ['settings', 'uniforms', 'math', 'atmosphere', 'clouds', 'shadows', 'lighting'], {'XON_SHADOWS': False})
        renderer.setup(bright_blocks)
        renderer.uniform3f(renderer.location('sunPosition'), 20.0, 90.0, 10.0)
        bright_row = renderer.draw(raw=True)[height // 2, :, :3]
        q_groove = float(np.mean(bright_row[width // 8]))
        q_mid = float(np.mean(bright_row[width * 3 // 8]))
        q_peak = float(np.mean(bright_row[width * 5 // 8]))
        yellow_shulker = bright_row[width * 7 // 8]
        if not (q_groove < q_mid < q_peak < 1.38) or float(yellow_shulker[0]) < 1.2:
            raise AssertionError(f'White curve broke monotonicity or dimmed yellow blocks: groove={q_groove}, mid={q_mid}, peak={q_peak}, yellow={yellow_shulker}')
        checks.append({'case': 'sunlit sand/snow/white damper scales peak glare to ~68% while preserving quartz contrast and yellow blocks',
                       'quartz_ramp_hdr': [q_groove, q_mid, q_peak], 'yellow_r_hdr': float(yellow_shulker[0])})

        portal_vsh = '''#version 330 compatibility
            out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels; out vec4 xonVertexColor;
            out vec3 xonViewPosition; out vec3 xonPlayerPosition; out vec3 xonWorldNormal; flat out float xonMaterial;
            void main(){
                vec2 uv=gl_MultiTexCoord0.xy;
                xonTexCoord=uv; xonAtlasBounds=vec4(0); xonLightLevels=vec2(1,1); xonVertexColor=vec4(1);
                xonViewPosition=vec3((uv.x-.5)*4.0,(uv.y-.5)*4.0,-3.0);
                xonPlayerPosition=vec3((uv.x-.5)*4.0,(uv.y-.5)*4.0,-3.0);
                xonWorldNormal=vec3(0,0,1); xonMaterial=10021.0; gl_Position=vec4(gl_Vertex.xy*2.0-1.0,0,1);
            }'''
        portal_prog = compile_pair(portal_vsh, variant_source(SHADERS / 'gbuffers_water.fsh', {'XON_SHADOWS': False}), 'nether portal 3d voronoi check')
        renderer.texture(8, np.full((2, 2, 4), [0.55, 0.18, 0.85, 0.85], dtype=np.float32))
        renderer.setup(portal_prog)
        renderer.uniform1f(renderer.location('alphaTestRef'), 0.1)
        renderer.uniform1f(renderer.location('frameTimeCounter'), 2.5)
        portal_px = renderer.draw(raw=True)[..., :3]
        p_b_min = float(np.min(portal_px[..., 2]))
        p_b_max = float(np.max(portal_px[..., 2]))
        p_r_mean = float(np.mean(portal_px[..., 0]))
        p_g_mean = float(np.mean(portal_px[..., 1]))
        p_b_mean = float(np.mean(portal_px[..., 2]))
        if not (p_b_max > p_b_min * 2.2 and p_b_mean > p_r_mean > p_g_mean * 1.8):
            raise AssertionError(f'Nether portal Voronoi lacks dark-to-bright purple 3D depth contrast: minB={p_b_min}, maxB={p_b_max}, meanRGB={[p_r_mean, p_g_mean, p_b_mean]}')
        checks.append({'case': 'Nether portal renders 3D parallax non-repetitive Voronoi across dark abyss purple and bright magical purple',
                       'blue_min': p_b_min, 'blue_max': p_b_max, 'mean_rgb': [p_r_mean, p_g_mean, p_b_mean]})

        frog_vsh = '''#version 330 compatibility
            out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels; out vec4 xonVertexColor;
            out vec3 xonViewPosition; out vec3 xonPlayerPosition; out vec3 xonWorldNormal; flat out float xonMaterial;
            void main(){
                vec2 uv=gl_MultiTexCoord0.xy;
                xonTexCoord=uv; xonAtlasBounds=vec4(0); xonLightLevels=vec2(1,1); xonVertexColor=vec4(1);
                xonViewPosition=vec3(0,-2,-4); xonPlayerPosition=vec3(0,-2,-4);
                xonWorldNormal=vec3(0,1,0); xonMaterial=10022.0; gl_Position=vec4(gl_Vertex.xy*2.0-1.0,0,1);
            }'''
        frog_prog = compile_pair(frog_vsh, variant_source(SHADERS / 'gbuffers_terrain.fsh', {'XON_SHADOWS': False}), 'froglight border check')
        frog_tex = np.array([[[0.88, 0.71, 0.42, 1.0], [0.98, 0.95, 0.82, 1.0]],
                             [[0.55, 0.82, 0.52, 1.0], [0.82, 0.58, 0.78, 1.0]]], dtype=np.float32)
        renderer.texture(8, frog_tex)
        renderer.setup(frog_prog)
        renderer.uniform1f(renderer.location('alphaTestRef'), 0.1)
        frog_px = renderer.draw(raw=True)[..., :3]
        ochre_border = expected_color(frog_px[height // 4, width // 4])
        ochre_center = expected_color(frog_px[height // 4, width * 3 // 4])
        if float(np.max(frog_px)) > 0.95 or float(np.mean(ochre_center) - np.mean(ochre_border)) < 0.14 or ochre_border[0] < ochre_border[2] * 1.6:
            raise AssertionError(f'Froglight blew out to pure white or lost aged border contrast: border={ochre_border}, center={ochre_center}')
        checks.append({'case': 'Froglights (Ochre, Verdant, Pearlescent) stay below bloom threshold and preserve rich aged borders',
                       'ochre_border_srgb': [float(v) for v in ochre_border], 'ochre_center_srgb': [float(v) for v in ochre_center]})

    finally:
        for program in programs:
            driver.delete_program(program)
        for shader in stages:
            driver.delete_shader(shader)
        renderer.close()
        driver.close()
    report = {'kind': 'offscreen GPU feature checks; synthetic inputs, not Minecraft FPS', 'passed': True, 'checks': checks}
    (ROOT / 'validation-lighting.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    run()
