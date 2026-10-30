"""Offscreen 1.0.4 shaft gates, depth clipping, occlusion and light-strength checks."""
import ctypes as ct
import json
import re
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image
from validate import Driver, SHADERS, variant_source, expand
from render_checks import Renderer

ROOT = Path(__file__).resolve().parents[1]


def run():
    driver = Driver()
    renderer = Renderer(driver, 960, 540)
    stages, programs, checks = [], [], []
    timings = {}

    def compile_pair(vertex, fragment):
        pair = []
        for text, stage in [(vertex, '.vsh'), (fragment, '.fsh')]:
            shader, warning = driver.compile(text, stage, '1.0.4 rays')
            if warning:
                raise AssertionError(warning)
            stages.append(shader)
            pair.append(shader)
        program, warning = driver.link(*pair, '1.0.4 rays')
        if warning:
            raise AssertionError(warning)
        programs.append(program)
        return program

    def actual(options):
        return compile_pair(*(variant_source(SHADERS / ('composite.' + stage), options)
                              for stage in ['vsh', 'fsh']))

    def shadow(value):
        data = np.full((256, 256), value, dtype=np.float32)
        renderer.active_texture(0x84C7)
        renderer.bind_texture(0x0DE1, renderer.textures[7])
        renderer.tex_image(0x0DE1, 0, 0x8CAC, 256, 256, 0, 0x1902, 0x1406, data.ctypes.data)
        renderer.tex_parameter(0x0DE1, 0x884C, 0x884E)
        renderer.tex_parameter(0x0DE1, 0x884D, 0x0203)

    uniform2i = driver.function('glUniform2i', None, ct.c_int, ct.c_int, ct.c_int)

    def draw(program, medium=0, sunlight=True, exposure=240, depth=.99999, sun=None):
        renderer.setup(program)
        renderer.uniform1i(renderer.location('isEyeInWater'), medium)
        renderer.uniform3f(renderer.location('sunPosition'), *(sun or (0, 14 if sunlight else -40, -99)))
        uniform2i(renderer.location('eyeBrightnessSmooth'), 240, exposure)
        for name, value in [('shadowModelView', np.eye(4)),
                            ('shadowProjection', np.diag([.02, .02, .02, 1]))]:
            data = np.ascontiguousarray(value.T, dtype=np.float32)
            renderer.uniform_matrix(renderer.location(name), 1, 0, data.ctypes.data)
        renderer.texture(2, np.full((8, 8), depth, dtype=np.float32))
        return renderer.draw(raw=True)[..., 3]

    try:
        renderer.texture(5, np.asarray(Image.open(SHADERS / 'textures/xon-noise.png').convert('RGBA')) / 255)
        renderer.active_texture(0x84C5)
        for axis in [0x2802,0x2803]: renderer.tex_parameter(0x0DE1,axis,0x2901)
        shafts = actual({'XON_BLOOM': False})
        for medium in [0, 1]:
            shadow(1)
            lit = draw(shafts, medium)
            near = draw(shafts, medium, depth=.8)
            night = draw(shafts, medium, sunlight=False)
            dark = draw(shafts, medium, exposure=0)
            shadow(0)
            blocked = draw(shafts, medium)
            if lit.max() < .01 or blocked.max() > .00001 or night.max() > .00001 or (medium == 0 and dark.max() > .00001):
                raise AssertionError('Sunlight, darkness or shadow occlusion gate failed')
            if medium == 1 and np.max(np.abs(dark-lit)) > .000001:
                raise AssertionError('Open-water rays incorrectly depend on underwater eye skylight')
            if near.mean() >= lit.mean() * .1:
                raise AssertionError('Shafts ignore foreground depth')
            if lit.max() > (.28001 if medium == 1 else .20001):
                raise AssertionError('Shaft intensity cap exceeded')
            checks.append({'case': f'medium {medium}: bounded daylight shafts, depth clipping, night/darkness/occlusion suppression',
                           'peak': float(lit.max()), 'mean': float(lit.mean())})
            pattern = np.ones((256,256),dtype=np.float32)
            pattern[:, :128] = 0
            shadow(pattern)
            opening = draw(shafts,medium)
            if not .0001 < opening.mean() < lit.mean() or opening.std() < .005:
                raise AssertionError('An opaque edge did not shape the light shaft')
            checks.append({'case': f'medium {medium}: shadow-map opening shapes beam', 'standard_deviation':float(opening.std())})
        shadow(1)
        for sun in [(0,95,-31),(0,95,31),(90,30,0)]:
            water=draw(shafts,1,exposure=0,sun=sun)
            center=water[renderer.height//3:renderer.height*2//3,renderer.width//3:renderer.width*2//3]
            if center.mean()<.015 or water.std()<.015:
                raise AssertionError(f'Horizontal underwater view lost distinct beams: {sun}')
            checks.append({'case':'horizontal swimming view retains shaped beams at zero eye skylight',
                           'sun':sun,'center_mean':float(center.mean()),'spatial_std':float(water.std())})
        for options, medium in [({'XON_UNDERWATER_RAYS': False}, 1),
                                ({'XON_RAY_STRENGTH': '0.00'}, 0),
                                ({'XON_RAY_STRENGTH': '0.00'}, 1),
                                ({'XON_LIGHT_SHAFTS': False}, 1),
                                ({'XON_SHADOWS': False}, 1), ({}, 2), ({}, 3)]:
            program = actual(dict(options, XON_BLOOM=False))
            if draw(program, medium).max() > .00001:
                raise AssertionError(f'Option/medium gate failed: {options}, {medium}')
            checks.append({'case': f'gate {options}, medium {medium}', 'passed': True})

        # Compare new light defaults against legacy strength using the same current shader.
        body = '''in vec2 xonUV; out vec4 result;
        void main(){ float visibility; bool torch=xonUV.x>.5;
        vec3 p=vec3(0,0,-8);
        result=vec4(xonLighting(vec3(.2),vec3(0,1,0),p,p,
            torch ? vec2(1,0) : vec2(0,1),0,0,visibility),1); }'''
        source = '#version 330 compatibility\n#define XON_DIMENSION 0\n'
        source += '\n'.join(expand(SHADERS / 'lib' / (name+'.glsl')) for name in
                            ['settings', 'uniforms', 'math', 'atmosphere', 'shadows', 'lighting'])
        source = source.replace('#define XON_SHADOWS\n', '#undef XON_SHADOWS\n')
        old = source.replace('#define XON_SUN_STRENGTH 0.80', '#define XON_SUN_STRENGTH 1.00')
        old = old.replace('#define XON_LOCAL_LIGHT_STRENGTH 0.80', '#define XON_LOCAL_LIGHT_STRENGTH 1.00')
        images = []
        for text in [old, source]:
            program = compile_pair(variant_source(SHADERS / 'final.vsh', {}), text+'\n'+body)
            renderer.setup(program)
            renderer.uniform3f(renderer.location('sunPosition'), 0, 100, 0)
            images.append(renderer.draw(raw=True))
        ratio = images[1][..., :3].mean(axis=(0, 2)) / images[0][..., :3].mean(axis=(0, 2))
        if not .78 < ratio[:renderer.width//2].mean() < .90 or not .78 < ratio[renderer.width//2:].mean() < .90:
            raise AssertionError('Sun/torch reduction did not lower lit surfaces as intended')
        checks.append({'case': 'sun and torch surfaces are less intense with preserved ambient fill',
                       'sun_ratio': float(ratio[:renderer.width//2].mean()),
                       'torch_ratio': float(ratio[renderer.width//2:].mean())})
        shade_body = body.replace('torch ? vec2(1,0) : vec2(0,1)', 'vec2(0,0)')
        shade=[]
        for text in [old,source]:
            program=compile_pair(variant_source(SHADERS / 'final.vsh',{}),text+'\n'+shade_body)
            renderer.setup(program)
            renderer.uniform3f(renderer.location('sunPosition'),0,100,0)
            shade.append(renderer.draw(raw=True))
        if np.max(np.abs(shade[0]-shade[1])) > .000001:
            raise AssertionError('Light-strength adjustment darkened unlit shade')
        checks.append({'case':'unlit shadow fill is unchanged by lower sun/local light strengths','passed':True})
        with zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.0.3.3.zip') as archive:
            def baseline(name):
                text = archive.read('shaders/'+name).decode('utf-8')
                return re.sub(r'^\s*#include\s+"([^"]+)"\s*$', lambda m: baseline(m[1].lstrip('/')), text, flags=re.M)
            old_shafts = compile_pair(baseline('composite.vsh'), baseline('composite.fsh').replace('#define XON_BLOOM\n', '#undef XON_BLOOM\n'))
        with zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.0.4-original.zip') as archive:
            original_shafts=compile_pair(baseline('composite.vsh'),baseline('composite.fsh').replace('#define XON_BLOOM\n','#undef XON_BLOOM\n'))
        # Synthetic constant underwater backdrop, composed through the same filmic curve.
        from PIL import ImageDraw
        sheet=Image.new('RGB',(1920,570))
        painter=ImageDraw.Draw(sheet)
        for index,program in enumerate([original_shafts,shafts]):
            shadow(1)
            alpha=draw(program,1,exposure=0,sun=(0,95,-31))
            rgb=np.array([.035,.075,.10])+alpha[...,None]*np.array([.38,.78,.92])
            rgb*=1.05;rgb=rgb*(2.51*rgb+.03)/(rgb*(2.43*rgb+.59)+.14)
            rgb=np.clip(rgb,0,1)**(1/2.2)
            sheet.paste(Image.fromarray((np.flipud(rgb)*255).astype(np.uint8)),(index*960,30))
            painter.text((index*960+12,8),('Original' if index==0 else 'Revised')+' 1.0.4 / horizontal underwater view',fill='white')
        sheet.save(ROOT/'validation-underwater-comparison.png')
        gen = driver.function('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin = driver.function('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end = driver.function('glEndQuery', None, ct.c_uint)
        get = driver.function('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete = driver.function('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        for label, program, medium in [('1.0.3.3 outdoor',old_shafts,0),('original 1.0.4 underwater',original_shafts,1),('1.0.4 outdoor',shafts,0),('1.0.4 underwater',shafts,1)]:
            shadow(1)
            draw(program,medium)
            def quad():
                renderer.begin(0x0007)
                for x,y in [(0,0),(1,0),(1,1),(0,1)]:
                    renderer.tex_coord(x,y)
                    renderer.vertex(x,y)
                renderer.end()
            for _ in range(12): quad()
            queries=(ct.c_uint*48)()
            gen(48,queries)
            for query in queries:
                begin(0x88BF,query)
                for _ in range(4): quad()
                end(0x88BF)
            samples=[]
            for query in queries:
                elapsed=ct.c_uint64()
                get(query,0x8866,ct.byref(elapsed))
                samples.append(elapsed.value/4e6)
            delete(48,queries)
            timings[label]={'median_ms':float(np.median(samples)), 'p95_ms':float(np.percentile(samples,95))}
    finally:
        for program in programs:
            driver.delete_program(program)
        for shader in stages:
            driver.delete_shader(shader)
        renderer.close()
        driver.close()
    report = {'passed': True, 'kind': 'synthetic GPU rays and lighting checks; not Minecraft FPS', 'checks': checks,
              'shaft_only_gpu_timings': timings, 'pass_resolution':[960,540],
              'timing_limitations':'Synthetic inputs, concurrent desktop load, no game geometry/CPU or bloom. Sequential runs; clocks and ordering affect results.'}
    (ROOT / 'validation-rays.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    run()
