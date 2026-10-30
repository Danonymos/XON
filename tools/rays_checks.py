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

    def draw(program, medium=0, sunlight=True, exposure=240, depth=.99999, sun=None,
             camera=(0, 0, 0), rotation=None, time=0, map_origin=(0, 0, 0)):
        renderer.setup(program)
        renderer.uniform1i(renderer.location('isEyeInWater'), medium)
        rotation = np.eye(4) if rotation is None else rotation
        light = rotation[:3, :3] @ np.array(sun or (0, 14 if sunlight else -40, -99))
        renderer.uniform3f(renderer.location('sunPosition'), *light)
        renderer.uniform3f(renderer.location('cameraPosition'), *camera)
        renderer.uniform1f(renderer.location('frameTimeCounter'), time)
        uniform2i(renderer.location('eyeBrightnessSmooth'), 240, exposure)
        shadow_view = np.eye(4)
        shadow_view[:3, 3] = np.array(camera) - np.array(map_origin)
        for name, value in [('gbufferModelViewInverse', np.linalg.inv(rotation)),
                            ('shadowModelView', shadow_view),
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
            if lit.max() > .20001:
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
        shadow(pattern)
        for sun in [(0,95,-31),(0,95,31),(90,30,0)]:
            water=draw(shafts,1,exposure=0,sun=sun)
            center=water[renderer.height//3:renderer.height*2//3,renderer.width//3:renderer.width*2//3]
            if center.mean()<.0005 or water.std()<.001:
                raise AssertionError(f'Shadow-defined underwater scattering absent: {sun}')
            checks.append({'case':'horizontal swimming: actual occluder shapes restrained scattering at zero eye skylight',
                           'sun':sun,'center_mean':float(center.mean()),'spatial_std':float(water.std())})
        # Open water has no invented beams; compare its integrated energy to Beer-Lambert.
        shadow(1)
        reference_fragment = variant_source(SHADERS / 'composite.fsh', {'XON_BLOOM': False})
        reference_fragment = reference_fragment.replace('underwater ? 12 : 4', 'underwater ? 128 : 4')
        reference_fragment = reference_fragment.replace('stepIndex < 12', 'stepIndex < 128')
        reference_fragment = reference_fragment.replace('maxRayDist / 12.0', 'maxRayDist / 128.0')
        dense = compile_pair(variant_source(SHADERS / 'composite.vsh', {}), reference_fragment)
        base = draw(shafts, 1)
        animated = draw(shafts, 1, time=172.5)
        if np.max(np.abs(animated - base)) > 1e-7:
            raise AssertionError('Stationary shaft source animates without a sun/occluder change')
        checks.append({'case': 'stationary world has no time-animated underwater noise', 'passed': True})
        relocated = draw(shafts, 1, camera=(2695, 59, 15970), map_origin=(2695, 59, 15970))
        if np.max(np.abs(relocated - base)) > 1e-7:
            raise AssertionError('Large world coordinates change the local scattering field')
        checks.append({'case': 'scattering is invariant to world-origin relocation near player screenshot coordinates', 'passed': True})
        errors = []
        energies = []
        for distance in [1, 3, 6, 9, 12, 18, 24, 32]:
            # Renderer uses near=.05, far=1024; invert its perspective depth transform.
            depth = ((1024 + .05) / (1024 - .05) - 2 * 1024 * .05 / ((1024 - .05) * distance) + 1) * .5
            water = draw(shafts, 1, depth=depth)
            reference = draw(dense, 1, depth=depth)
            errors.append(float(np.max(np.abs(water - reference))))
            energies.append(float(water.mean()))
        if max(errors) > .005 or np.min(np.diff(energies)) < -1e-7:
            raise AssertionError(f'Depth changes stretch or reverse open-water scattering: {errors}, {energies}')
        checks.append({'case': 'foreground depth sweep matches dense integration and adds energy monotonically',
                       'maximum_absolute_error': max(errors), 'mean_energy_by_depth': energies})
        # Sweep a fixed world-space opening with camera translation and rotation.
        from scene_checks import look_at
        shadow(pattern)
        previous = previous_reference = None
        motion_errors = []
        integration_errors = []
        for index in range(25):
            offset = (index - 12) * .12
            camera = (offset, .03 * index, -offset * 2)
            rotation = look_at([0, 0, 0], [offset * .035, .04, -1])
            water = draw(shafts, 1, camera=camera, rotation=rotation)
            reference = draw(dense, 1, camera=camera, rotation=rotation)
            integration_errors.append(float(np.quantile(np.abs(water-reference), .99)))
            if previous is not None:
                motion_errors.append(float(np.quantile(np.abs((water-previous)-(reference-previous_reference)), .99)))
            previous, previous_reference = water, reference
        if max(integration_errors) > .018 or max(motion_errors) > .018:
            raise AssertionError(f'Camera movement exceeds the scattering error budget: {integration_errors}, {motion_errors}')
        checks.append({'case': '25 translating/rotating camera frames across fixed occluder vs 128-step integration',
                       'worst_frame_p99_error': max(integration_errors), 'worst_motion_p99_error': max(motion_errors)})
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
        with zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.0.4-revised.zip') as archive:
            smoky_shafts=compile_pair(baseline('composite.vsh'),baseline('composite.fsh').replace('#define XON_BLOOM\n','#undef XON_BLOOM\n'))
            fog_prefix = '#version 330 compatibility\n#define XON_DIMENSION 0\n'
            fog_body = '\nuniform float testDistance; out vec4 result; void main(){result=vec4(xonFog(vec3(.12),vec3(0,0,-testDistance),1),1);}'
            fog_programs = []
            for historical in [True, False]:
                libraries = ['lib/'+name+'.glsl' for name in ['settings','uniforms','math','atmosphere']]
                text = '\n'.join(baseline(name) if historical else expand(SHADERS/name) for name in libraries)
                fog_programs.append(compile_pair(variant_source(SHADERS/'final.vsh',{}),fog_prefix+text+fog_body))
        for medium, distance in [(1,3),(1,6),(1,24),(1,64),(0,24),(2,24),(3,24)]:
            values = []
            for selected in fog_programs:
                renderer.setup(selected)
                renderer.uniform1i(renderer.location('isEyeInWater'),medium)
                renderer.uniform1f(renderer.location('testDistance'),distance)
                renderer.uniform3f(renderer.location('sunPosition'),0,100,0)
                values.append(renderer.draw(raw=True)[0,0,:3])
            delta = float(np.max(np.abs(values[1]-values[0])))
            if medium != 1 or distance <= 6:
                if delta > 1e-6: raise AssertionError('Clear near zone or non-water atmosphere changed')
            elif not (.01 < values[1].mean() < values[0].mean() and values[1][2] > values[1][0]):
                raise AssertionError('Distant water lost blue color, readability or absorption')
            checks.append({'case':'water background absorption and other-medium parity',
                           'medium':medium,'distance':distance,'old_rgb':values[0].tolist(),'new_rgb':values[1].tolist()})
        # Synthetic constant underwater backdrop, composed through the same filmic curve.
        from PIL import ImageDraw
        sheet=Image.new('RGB',(1920,570))
        painter=ImageDraw.Draw(sheet)
        for index,program in enumerate([smoky_shafts,shafts]):
            shadow(pattern)
            alpha=draw(program,1,exposure=0,sun=(0,95,-31))
            tint = [.38,.78,.92] if index == 0 else [.20,.40,.65]
            rgb=np.array([.035,.075,.10])+alpha[...,None]*np.array(tint)
            rgb*=1.05;rgb=rgb*(2.51*rgb+.03)/(rgb*(2.43*rgb+.59)+.14)
            rgb=np.clip(rgb,0,1)**(1/2.2)
            sheet.paste(Image.fromarray((np.flipud(rgb)*255).astype(np.uint8)),(index*960,30))
            painter.text((index*960+12,8),('Previous smoke field' if index==0 else 'Occluder-defined scattering')+' / synthetic opening',fill='white')
        sheet.save(ROOT/'validation-underwater-comparison.png')
        gen = driver.function('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin = driver.function('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end = driver.function('glEndQuery', None, ct.c_uint)
        get = driver.function('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete = driver.function('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        for label, program, medium in [('1.0.3.3 outdoor',old_shafts,0),('original 1.0.4 underwater',original_shafts,1),('previous smoky underwater',smoky_shafts,1),('1.0.5 outdoor',shafts,0),('1.0.5 underwater',shafts,1)]:
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
