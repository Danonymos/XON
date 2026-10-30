"""Compare 1.0.2 with the immutable 1.0.1 pack on the installed OpenGL driver."""

from pathlib import Path
import ctypes as ct
import json
import re
import zipfile
import numpy as np
from PIL import Image
from validate import Driver, SHADERS, expand
from render_checks import Renderer

ROOT = Path(__file__).resolve().parents[1]
VERTEX = '''#version 330 compatibility
out vec2 xonUV;
void main() { xonUV=gl_MultiTexCoord0.xy; gl_Position=vec4(gl_Vertex.xy*2.0-1.0,0,1); }
'''
GEOMETRY_VERTEX = '''#version 330 compatibility
out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels;
out vec4 xonVertexColor; out vec3 xonViewPosition; out vec3 xonPlayerPosition;
out vec3 xonWorldNormal; flat out float xonMaterial;
uniform float testMaterial;
void main() {
    vec2 uv=gl_MultiTexCoord0.xy;
    xonTexCoord=uv; xonAtlasBounds=vec4(0); xonLightLevels=vec2(0.2,1);
    xonVertexColor=vec4(1); xonWorldNormal=vec3(0,1,0);
    xonPlayerPosition=vec3((uv.x-0.5)*24.0,-2,-4.0-uv.y*56.0);
    xonViewPosition=xonPlayerPosition; xonMaterial=testMaterial;
    gl_Position=vec4(gl_Vertex.xy*2.0-1.0,0,1);
}
'''


def run(baseline_version='1.0.1', visual_update=False):
    driver = Driver()
    renderer = Renderer(driver, 1920, 1080)
    shaders, programs = [], []
    checks = []
    labels = [baseline_version, '1.0.3' if visual_update else '1.0.2']
    report = {'kind': ' vs '.join(labels) + ' synthetic GPU comparison; not game FPS',
              'resolution': [1920, 1080], 'checks': checks}
    archive = zipfile.ZipFile(ROOT.parent / f'XON-Shader-v{baseline_version}.zip')

    def source(name, baseline):
        if not baseline:
            return expand(SHADERS / name)
        text = archive.read('shaders/' + name).decode('utf-8')
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda m: source(m[1].lstrip('/'), True), text, flags=re.M)

    def compile_program(vertex, fragment):
        pair = []
        for text, stage in [(vertex, '.vsh'), (fragment, '.fsh')]:
            shader, warning = driver.compile(text, stage, 'optimization comparison')
            if warning:
                raise AssertionError(warning)
            shaders.append(shader)
            pair.append(shader)
        program, warning = driver.link(*pair, 'optimization comparison')
        if warning:
            raise AssertionError(warning)
        programs.append(program)
        return program

    def library_program(body, libraries, baseline, dimension=0):
        text = '#version 330 compatibility\n#define XON_DIMENSION %d\n' % dimension
        text += '\n'.join(source('lib/' + name + '.glsl', baseline) for name in libraries)
        if 'testDistance' in body:
            text = text.replace('//#define XON_SMOOTH_SHADOW_LOD', '#define XON_SMOOTH_SHADOW_LOD')
        return compile_program(VERTEX, text + '\nin vec2 xonUV; out vec4 result;\n' + body)

    def matrix(name, value):
        data = np.ascontiguousarray(np.asarray(value).T, dtype=np.float32)
        renderer.uniform_matrix(renderer.location(name), 1, 0, data.ctypes.data)

    def setup(program, water=0, rain=0, sun=(30, 80, 10), material=0):
        renderer.setup(program)
        for name in ['gbufferModelView', 'shadowModelView', 'shadowModelViewInverse']:
            matrix(name, np.eye(4))
        matrix('shadowProjection', np.diag([.009, .009, .009, 1]))
        for name, value in [('far', 192), ('fogStart', 96), ('fogEnd', 192),
                            ('rainStrength', rain), ('frameTimeCounter', 23),
                            ('alphaTestRef', .1), ('testMaterial', material)]:
            renderer.uniform1f(renderer.location(name), value)
        renderer.uniform1i(renderer.location('isEyeInWater'), water)
        renderer.uniform3f(renderer.location('sunPosition'), *sun)
        renderer.uniform3f(renderer.location('skyColor'), .45, .68, .98)
        renderer.uniform3f(renderer.location('fogColor'), .1, .2, .3)

    def quad():
        renderer.begin(0x0007)
        for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
            renderer.tex_coord(x, y)
            renderer.vertex(x, y)
        renderer.end()

    f = driver.function
    gen = f('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
    begin = f('glBeginQuery', None, ct.c_uint, ct.c_uint)
    end = f('glEndQuery', None, ct.c_uint)
    get = f('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
    delete = f('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))

    def timings(pair, kwargs):
        samples = [[], []]
        # Reverse order on alternate rounds to reduce clock/load ordering bias.
        for order in [(0, 1), (1, 0), (0, 1), (1, 0)]:
            for index in order:
                setup(pair[index], **kwargs)
                for _ in range(8):
                    quad()
                queries = (ct.c_uint * 12)()
                gen(len(queries), queries)
                for query in queries:
                    begin(0x88BF, query)
                    for _ in range(4):
                        quad()
                    end(0x88BF)
                for query in queries:
                    elapsed = ct.c_uint64()
                    get(query, 0x8866, ct.byref(elapsed))
                    samples[index].append(elapsed.value / 4e6)
                delete(len(queries), queries)
        return {label: {'median_ms': float(np.median(values)),
                        'p95_ms': float(np.percentile(values, 95))}
                for label, values in zip(labels, samples)}

    def compare(label, pair, kwargs=None, tolerance=0.00005, timed=False):
        kwargs = kwargs or {}
        images = []
        for program in pair:
            setup(program, **kwargs)
            images.append(renderer.draw(raw=True))
        error = float(np.max(np.abs(images[0] - images[1])))
        changed_lighting = visual_update and (label.startswith('terrain lighting') or
                           label in ['actual terrain stone', 'actual terrain amethyst'] or
                           ('water parity' in label and 'refraction False' in label))
        if changed_lighting:
            old_mean = float(np.mean(images[0][..., :3]))
            new_mean = float(np.mean(images[1][..., :3]))
            if not .85 < new_mean / max(old_mean, .00001) < 1.35 or error > .5:
                raise AssertionError(f'{label}: lighting outside exposure envelope {old_mean}, {new_mean}, {error}')
            if label.startswith('terrain lighting') and error < .001:
                raise AssertionError(f'{label}: visual lighting update has no measurable effect')
        elif error > tolerance:
            raise AssertionError(f'{label}: maximum HDR difference {error} > {tolerance}')
        item = {'case': label, 'maximum_hdr_difference': error,
                'criterion': 'intentional lighting change; mean exposure within -15%/+35%, max HDR change <0.5' if changed_lighting else f'pixel parity within {tolerance}'}
        if timed:
            item['gpu'] = timings(pair, kwargs)
        checks.append(item)
        print(label, 'max difference', error, item.get('gpu', ''), flush=True)

    try:
        for unit, name in [(4, 'xon-grade.png'), (5, 'xon-noise.png')]:
            renderer.texture(unit, np.asarray(Image.open(SHADERS / 'textures' / name).convert('RGBA')) / 255)
        renderer.active_texture(0x84C5)
        for axis in [0x2802, 0x2803]:
            renderer.tex_parameter(0x0DE1, axis, 0x2901)
        yy, xx = np.indices((64, 64))
        tile = np.ones((64, 64, 4), dtype=np.float32)
        tile[..., :3] = np.where(((xx // 4 + yy // 4) % 2)[..., None], [.75, .45, .8], [.15, .08, .2])
        renderer.texture(8, tile)
        renderer.texture(9, np.full((8, 8), .999, dtype=np.float32))
        renderer.texture(6, np.full((8, 8, 4), [.3, .5, .7, 1], dtype=np.float32))
        renderer.active_texture(0x84C7)
        renderer.bind_texture(0x0DE1, renderer.textures[7])
        shadow = np.ones((1024, 1024), dtype=np.float32)
        renderer.tex_image(0x0DE1, 0, 0x8CAC, 1024, 1024, 0, 0x1902, 0x1406, shadow.ctypes.data)
        renderer.tex_parameter(0x0DE1, 0x884C, 0x884E)
        renderer.tex_parameter(0x0DE1, 0x884D, 0x0203)

        fog_body = '''void main() {
            vec3 p=vec3((xonUV.x-.5)*320.0,(xonUV.y-.5)*180.0,-1.0-xonUV.x*240.0);
            result=vec4(xonFog(vec3(.2,.4,.8),p,.7),1);
        }'''
        for dimension in [0, -1, 1]:
            pair = [library_program(fog_body, ['settings', 'uniforms', 'math', 'atmosphere'], old, dimension)
                    for old in [True, False]]
            for water in [0, 1, 2, 3]:
                compare(f'fog dimension {dimension}, medium {water}', pair, {'water': water}, timed=water in [0, 1])
            compare(f'storm fog dimension {dimension}', pair, {'rain': 1})

        lighting_body = '''void main() {
            vec3 p=vec3((xonUV.x-.5)*32.0,-2,-8.0-xonUV.y*64.0);
            float visibility;
            vec3 a=vec3(xonUV.x*xonUV.x*.9, xonUV.x*.4, xonUV.x*.2);
            result=vec4(xonLighting(a,vec3(0,1,0),p,p,vec2(.2,xonUV.y),0,0,visibility),visibility);
        }'''
        pair = [library_program(lighting_body, ['settings', 'uniforms', 'math', 'atmosphere', 'clouds', 'shadows', 'lighting'], old)
                for old in [True, False]]
        for label, sun in [('noon', (0, 100, 0)), ('dawn', (100, 12, 0)),
                           ('dusk', (-100, 12, 0)), ('night', (0, -100, 0))]:
            compare('terrain lighting ' + label, pair, {'sun': sun}, timed=True)

        pair = [compile_program(GEOMETRY_VERTEX, source('gbuffers_terrain.fsh', old)) for old in [True, False]]
        for label, material in [('stone', 0), ('lava', 10005), ('amethyst', 10019),
                                ('portal', 10021), ('froglight', 10022)]:
            compare('actual terrain ' + label, pair, {'material': material}, timed=True)
        pair = [compile_program(GEOMETRY_VERTEX, source('gbuffers_water.fsh', old)) for old in [True, False]]
        for water in [0, 1]:
            compare('actual water medium ' + str(water), pair, {'water': water, 'material': 10001}, timed=True)

        # Isolate the diffuse-work bypass from the deliberate shadow-filter refinement.
        shadow[:, :512] = .45
        renderer.active_texture(0x84C7)
        renderer.bind_texture(0x0DE1, renderer.textures[7])
        renderer.tex_image(0x0DE1, 0, 0x8CAC, 1024, 1024, 0, 0x1902, 0x1406, shadow.ctypes.data)
        for dimension, prefix in [(0, ''), (-1, 'world-1/'), (1, 'world1/')]:
            for refractive in [True, False]:
                pair = []
                for old in [True, False]:
                    fragment = source(prefix + 'gbuffers_water.fsh', old)
                    if not old:
                        fragment = fragment.replace(source('lib/shadows.glsl', False), source('lib/shadows.glsl', True))
                    if not refractive:
                        fragment = fragment.replace('#define XON_REFRACTION\n', '#undef XON_REFRACTION\n')
                    pair.append(compile_program(GEOMETRY_VERTEX, fragment))
                for sun in [(30, 80, 10), (0, -100, 0)]:
                    compare(f'water parity with shared shadow filter: dimension {dimension}, refraction {refractive}, sun {sun}',
                            pair, {'material': 10001, 'sun': sun})

        # Hold projected position fixed while crossing filtering LOD boundaries.
        shadow[:] = 1
        shadow[::2, :] = .45
        renderer.active_texture(0x84C7)
        renderer.bind_texture(0x0DE1, renderer.textures[7])
        renderer.tex_image(0x0DE1, 0, 0x8CAC, 1024, 1024, 0, 0x1902, 0x1406, shadow.ctypes.data)
        body = '''uniform float testDistance;
        void main() {
            vec3 p=vec3(testDistance,0,(xonUV.x-.5)*0.02);
            result=vec4(vec3(xonShadowVisibility(p,vec3(0,1,0),1,1,0)),1);
        }'''
        pair = [library_program(body, ['settings', 'uniforms', 'math', 'shadows'], old) for old in [True, False]]
        for boundary in [20, 42]:
            jumps = []
            for program in pair:
                images = []
                for distance in [boundary - .001, boundary + .001]:
                    setup(program)
                    transform = np.eye(4)
                    transform[0, 3] = -distance
                    matrix('shadowModelView', transform)
                    renderer.uniform1f(renderer.location('testDistance'), distance)
                    images.append(renderer.draw(raw=True))
                jumps.append(float(np.max(np.abs(images[0] - images[1]))))
            if jumps[1] > .002 or jumps[1] > jumps[0] + .0001:
                raise AssertionError(f'Shadow transition regression at {boundary}: {jumps}')
            checks.append({'case': f'shadow LOD continuity at {boundary} blocks',
                           labels[0] + '_maximum_jump': jumps[0], labels[1] + '_maximum_jump': jumps[1]})
        if visual_update:
            body = '''void main() {
                float visibility;
                vec3 p=vec3(0,-2,-8);
                vec3 c=xonLighting(vec3(.25),vec3(1,0,0),p,p,vec2(xonUV.x,0),0,0,visibility);
                result=vec4(c,1);
            }'''
            ramps=[]
            for old in [True,False]:
                program=library_program(body,['settings','uniforms','math','atmosphere','shadows','lighting'],old)
                setup(program,sun=(0,-100,0))
                ramps.append(renderer.draw(raw=True)[renderer.height//2,:,:3])
            luma=ramps[1] @ np.array([.2126,.7152,.0722])
            if np.min(np.diff(luma)) < -0.00001:
                raise AssertionError('Local light falloff must brighten monotonically toward the source')
            if np.mean(ramps[1][:8]) < np.mean(ramps[0][:8]):
                raise AssertionError('Unlit nighttime shade became darker')
            if not np.mean(ramps[1][800:1000]) > np.mean(ramps[0][800:1000]):
                raise AssertionError('Local light transition did not gain readable midtones')
            checks.append({'case':'night shade stays readable and local light falloff is monotonic', 'passed':True})
            body = '''void main() {
                vec2 q=(xonUV-0.5)*2.0;
                float r2=dot(q,q);
                vec3 n=vec3(q.x,sqrt(max(1.0-r2,0.0)),q.y);
                float visibility;
                vec3 p=vec3(q.x*4.0,-2,-8.0+q.y*4.0);
                vec3 a=vec3(.42,.34,.24);
                vec3 c=xonLighting(a,n,p,p,vec2(.35,.85),0,0,visibility);
                c=c*1.05; c=c*(2.51*c+.03)/(c*(2.43*c+.59)+.14);
                result=vec4(r2<1.0 ? xonToDisplay(clamp(c,0,1)) : vec3(.09),1);
            }'''
            previews=[]
            for old in [True, False]:
                program=library_program(body,['settings','uniforms','math','atmosphere','shadows','lighting'],old)
                row=[]
                for sun in [(40,80,20),(-100,15,0),(0,-100,0)]:
                    setup(program,sun=sun)
                    pixels=renderer.draw()
                    row.append(Image.fromarray((np.flipud(pixels[...,:3])*255).astype(np.uint8)).resize((480,270)))
                previews.append(row)
            sheet=Image.new('RGB',(1440,540))
            for y,row in enumerate(previews):
                for x,picture in enumerate(row): sheet.paste(picture,(x*480,y*270))
            sheet.save(ROOT/'validation-lighting-comparison.png')
        if renderer.get_error():
            raise AssertionError('OpenGL error during comparison')
        report['passed'] = True
        report['limitations'] = ['Synthetic fullscreen fragments, no world draw calls or CPU simulation.',
                                'Concurrent desktop load and GPU clock changes affect timings.',
                                'Pixel parity is checked on sampled inputs, not every possible Minecraft scene.']
    finally:
        archive.close()
        for program in programs:
            driver.delete_program(program)
        for shader in shaders:
            driver.delete_shader(shader)
        renderer.close()
        driver.close()
    output = 'validation-visual-update.json' if visual_update else 'validation-optimization.json'
    (ROOT / output).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--visual-update',action='store_true')
    args=parser.parse_args()
    run('1.0.2' if args.visual_update else '1.0.1',args.visual_update)
