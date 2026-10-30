"""Compare built-in spatial/moving AA and terrain mip sampling against the saved 1.0.7."""
import ctypes as ct
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from validate import Driver, SHADERS, variant_source
from render_checks import Renderer, expected_color

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT.parent / 'XON-Shader-v1.0.7-before-aa.zip'
OPTIONS = {'XON_BLOOM': False, 'XON_LIGHT_SHAFTS': False, 'XON_COLOR_GRADE': False}


def coverage(xx, yy, slope, position):
    distance = position - (xx + .5 - slope * (yy + .5))
    width = abs(slope)
    if width < 1e-6:
        return np.clip(distance + .5, 0, 1)
    s = distance + .5 * (1 + width)
    positive = lambda x: np.maximum(x, 0) ** 2
    return np.clip((positive(s) - positive(s - 1) - positive(s - width)
                    + positive(s - 1 - width)) / (2 * width), 0, 1)


def run():
    driver = Driver()
    renderer = Renderer(driver, 256, 192)
    archive = zipfile.ZipFile(BASELINE)
    shaders, programs, checks, pictures = [], [], [], []

    def saved(name):
        source = archive.read('shaders/' + name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda m: saved(m[1].lstrip('/')), source, flags=re.M)

    def source(name, old=False, options=None):
        if not old:
            return variant_source(SHADERS / name, options or {})
        result = saved(name)
        for name, value in (options or {}).items():
            result = re.sub(rf'^(?://)?#define {name}(?:[^\n]*)$',
                            f'#undef {name}' if value is False else f'#define {name} {value}', result, flags=re.M)
        return result

    def compile_pair(vertex, fragment):
        pair = []
        for text, stage in [(vertex, '.vsh'), (fragment, '.fsh')]:
            shader, warning = driver.compile(text, stage, 'AA quality comparison')
            assert not warning, warning
            shaders.append(shader)
            pair.append(shader)
        program, warning = driver.link(*pair, 'AA quality comparison')
        assert not warning, warning
        programs.append(program)
        return program

    def final(old=False, motion=True, bypass=False, mode=0, probe=False):
        options = dict(OPTIONS, XON_MOTION_BLUR=motion, XON_RENDER_MODE=mode)
        fragment = source('final.fsh', old, options)
        if bypass:
            fragment = fragment.replace('color = xonEdgeAA(color, depth, motionPixels, handMask);', '')
        if probe:
            fragment = fragment.replace('void main() {', 'uniform float testMotion;\nvoid main() {', 1)
            fragment = fragment.replace('color = xonEdgeAA(color, depth, motionPixels, handMask);',
                                        'color = xonEdgeAA(color, depth, testMotion, handMask);')
        return compile_pair(source('final.vsh', old, options), fragment)

    def draw(program, scene, depth, camera=0, mask=None):
        renderer.texture(0, scene)
        renderer.texture(1, np.zeros_like(depth) if mask is None else mask)
        renderer.texture(2, depth)
        renderer.setup(program)
        renderer.uniform3f(renderer.location('previousCameraPosition'), camera, 0, 0)
        return renderer.draw(raw=True)[..., :3]

    def timing(program, repeats=48, camera=-.01):
        renderer.setup(program)
        if program in moving:
            renderer.uniform3f(renderer.location('previousCameraPosition'), camera, 0, 0)
        renderer.draw(raw=True)
        f = driver.function
        gen = f('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin = f('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end = f('glEndQuery', None, ct.c_uint)
        get = f('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete = f('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        queries = (ct.c_uint * repeats)()
        gen(repeats, queries)
        for query in queries:
            begin(0x88BF, query)
            for _ in range(8):
                renderer.begin(0x0007)
                for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                    renderer.tex_coord(x, y)
                    renderer.vertex(x, y)
                renderer.end()
            end(0x88BF)
        times = []
        for query in queries:
            elapsed = ct.c_uint64()
            get(query, 0x8866, ct.byref(elapsed))
            times.append(elapsed.value / 8e6)
        delete(repeats, queries)
        return {'median_ms': float(np.median(times)), 'p95_ms': float(np.percentile(times, 95))}

    try:
        still = [final(True, False), final(False, False)]
        moving = [final(True), final(False)]
        raw = final(False, False, True)
        height, width = renderer.height, renderer.width
        yy, xx = np.indices((height, width), dtype=float)
        scene = np.ones((height, width, 4), dtype=np.float32)
        dark, light = np.array([.025, .03, .045]), np.array([.9, .8, .65])
        errors = []
        for slope in [.15, .35, .61, 1, 1.9, -.4]:
            values = []
            for phase in np.linspace(0, 1, 9, endpoint=False):
                position = width * .5 - slope * height * .5 + phase
                edge = xx + .5 < slope * (yy + .5) + position
                scene[..., :3] = np.where(edge[..., None], light, dark)
                depth = np.where(edge, .90, .99).astype(np.float32)
                ideal = expected_color(dark + coverage(xx, yy, slope, position)[..., None] * (light - dark))
                region = (np.abs(xx + .5 - slope * (yy + .5) - position) < 2) & (xx > 4) & (xx < width - 4) & (yy > 4) & (yy < height - 4)
                results = [draw(p, scene, depth) for p in [raw, *still]]
                mse = [float(np.mean((result[region] - ideal[region]) ** 2)) for result in results]
                values.append(mse)
                if slope == .61 and phase == 0:
                    pictures.append([results[1], results[2], ideal])
            means = np.mean(values, axis=0)
            assert means[2] < means[1] * 1.02, (slope, means.tolist())
            errors.append(means)
            checks.append({'case': 'static diagonal coverage across nine subpixel phases', 'slope': slope,
                           'unfiltered_mse': means[0], 'old_mse': means[1], 'current_mse': means[2]})
        aggregate = np.mean(errors, axis=0)
        assert aggregate[2] < aggregate[0] * .7, aggregate.tolist()
        assert aggregate[2] < aggregate[1] * .99, aggregate.tolist()

        depth = np.full((height, width), .95, dtype=np.float32)
        z = .1 * 1024 / (1024 + .05 - (.95 * 2 - 1) * (1024 - .05))
        camera = -.5 * 2 * z / width
        cap = 22 * (0.4 + .6 * 1.5) * height / 1080
        motion = cap * (1 - np.exp(-(.5 * .01875 * 120) / cap))
        residuals = [[], []]
        for frame in range(17):
            slope, position = .61, 70 + frame * .5
            edge = xx + .5 < slope * (yy + .5) + position
            scene[..., :3] = np.where(edge[..., None], light, dark)
            box = coverage(xx, yy, slope, position) * .42
            total = .42
            for t in np.linspace(-.85, .85, 97):
                weight = (.55 + .45 * np.cos(t * 1.65)) * 6 / 97
                box += coverage(xx, yy, slope, position - motion * t) * weight
                total += weight
            ideal = expected_color(dark + (box / total)[..., None] * (light - dark))
            for index, program in enumerate(moving):
                output = draw(program, scene, depth, camera)
                residuals[index].append(output - ideal)
                if frame == 8:
                    if index == 0:
                        pictures.append([output, None, ideal])
                    else:
                        pictures[-1][1] = output
        region = (np.abs(xx + .5 - .61 * (yy + .5) - 74) < 14) & (xx > 4) & (xx < width - 4)
        temporal = [float(np.mean(np.diff(np.array(values), axis=0)[:, region] ** 2)) for values in residuals]
        spatial = [float(np.mean(np.array(values)[:, region] ** 2)) for values in residuals]
        assert temporal[1] < temporal[0] and spatial[1] < spatial[0], (temporal, spatial)
        checks.append({'case': 'moving coverage against pixel-area/shutter reference', 'old_temporal_error': temporal[0],
                       'current_temporal_error': temporal[1], 'old_spatial_error': spatial[0], 'current_spatial_error': spatial[1]})

        scene[..., :3] = .025
        scene[:, width // 2, :3] = .9
        depth = np.full((height, width), .99, dtype=np.float32)
        depth[:, width // 2] = .9
        output = draw(still[1], scene, depth)
        contrast = float(np.mean(output[8:-8, width // 2] - output[8:-8, width // 2 + 4]))
        original = float(expected_color(.9) - expected_color(.025))
        assert contrast > original * .5, (contrast, original)
        checks.append({'case': 'one-pixel geometry retains visible contrast', 'retained_contrast_fraction': contrast / original})
        scene[..., :3] = np.where((xx < width // 2)[..., None], [.01, .02, .03], [4, 8, 2])
        depth = np.full((height, width), .95, dtype=np.float32)
        mask = np.ones_like(depth)
        protected = draw(moving[1], scene, depth, -.01, mask)
        reference = draw(raw, scene, depth, mask=mask)
        assert np.max(np.abs(protected - reference)) < .00001
        checks.append({'case': 'first-person hand is unchanged by moving/still smoothing'})
        edge = xx + .5 < .61 * (yy + .5) + 70
        scene[..., :3] = np.where(edge[..., None], light, dark)
        depth = np.where(edge, .9, .99).astype(np.float32)
        jumps = []
        for old in [True, False]:
            program = final(old, motion=False, probe=True)
            responses = []
            for value in [.4499, .4501]:
                renderer.setup(program)
                renderer.uniform1f(renderer.location('testMotion'), value)
                responses.append(draw(program, scene, depth))
            jumps.append(float(np.max(np.abs(responses[1] - responses[0]))))
        assert jumps[1] < .0001 and jumps[0] > .01, jumps
        checks.append({'case': 'continuous handoff at the former hard AA cutoff', 'old_maximum_jump': jumps[0], 'current_maximum_jump': jumps[1]})

        vertex = '''#version 330 compatibility
uniform float viewWidth, viewHeight, testFootprint, testPhase, testMaterial;
out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels; out vec4 xonVertexColor;
out vec3 xonViewPosition, xonPlayerPosition, xonWorldNormal; flat out float xonMaterial;
void main() {
    xonTexCoord=(gl_Vertex.xy*vec2(viewWidth,viewHeight)*testFootprint+testPhase)/1024.0;
    xonAtlasBounds=vec4(.5,.5,.5,.5); xonLightLevels=vec2(0,1); xonVertexColor=vec4(1);
    xonViewPosition=vec3(0,0,-64); xonPlayerPosition=xonViewPosition;
    xonWorldNormal=vec3(0,0,1); xonMaterial=testMaterial;
    gl_Position=vec4(gl_Vertex.xy*2-1,0,1);
}'''
        samplers = []
        for old in [True, False]:
            fragment = source('gbuffers_terrain.fsh', old, {'XON_COLORED_EMISSIVE_LIGHTING': False})
            prefix = fragment.split('void main() {')[0]
            samplers.append(compile_pair(vertex, prefix + '\nvoid main(){xonScene=xonSampleAnisotropic(xonTexCoord);}\n'))
        ay, ax = np.indices((1024, 1024))
        atlas = np.ones((1024, 1024, 4), dtype=np.float32)
        atlas[..., :3] = (((ax // 2 + ay // 2) % 2) * .8 + .1)[..., None]

        def upload_mips(data):
            renderer.active_texture(0x84C8)
            renderer.bind_texture(0x0DE1, renderer.textures[8])
            level = 0
            while True:
                data = np.ascontiguousarray(data, dtype=np.float32)
                h, w = data.shape[:2]
                renderer.tex_image(0x0DE1, level, 0x8814, w, h, 0, 0x1908, 0x1406, data.ctypes.data)
                if h == 1:
                    break
                data = data.reshape(h // 2, 2, w // 2, 2, 4).mean(axis=(1, 3))
                level += 1
            renderer.tex_parameter(0x0DE1, 0x2801, 0x2702)
            renderer.tex_parameter(0x0DE1, 0x2800, 0x2600)
            renderer.tex_parameter(0x0DE1, 0x2802, 0x2901)
            renderer.tex_parameter(0x0DE1, 0x2803, 0x2901)

        def sample(program, footprint, phase=0, material=0):
            renderer.setup(program)
            for name, value in [('testFootprint', footprint), ('testPhase', phase), ('testMaterial', material)]:
                renderer.uniform1f(renderer.location(name), value)
            return renderer.draw(raw=True)

        upload_mips(atlas)
        for footprint in [.5, 1, 2, 2.5, 3, 8]:
            output = [[sample(p, footprint, phase) for phase in [0, .25, .5, .75, 1]] for p in samplers]
            deviation = [float(np.mean((np.array(frames)[..., :3] - .5) ** 2)) for frames in output]
            if footprint <= 1:
                assert np.max(np.abs(np.array(output[0]) - output[1])) < .00001
            elif footprint < 4:
                assert deviation[1] < deviation[0] * .6, deviation
            checks.append({'case': 'real terrain mip sampler on distant wall beyond old 38-block filter', 'texels_per_pixel': footprint,
                           'old_alias_energy': deviation[0], 'current_alias_energy': deviation[1]})
        atlas[..., 3] = (ax // 4 % 2).astype(np.float32)
        upload_mips(atlas)
        for material in [0, 10003, 10004, 10006]:
            old, current = [sample(p, 2.5, .25, material) for p in samplers]
            error = float(np.max(np.abs(old[..., 3] - current[..., 3])))
            assert error < .00001, (material, error)
            checks.append({'case': 'cutout alpha coverage preserved at minified footprint', 'material': material, 'maximum_alpha_error': error})

        # Timings deliberately run after shader compilation and separately from other suites.
        renderer.close()
        renderer = Renderer(driver, 960, 540)
        yy, xx = np.indices((renderer.height, renderer.width))
        scene = np.ones((renderer.height, renderer.width, 4), dtype=np.float32)
        scene[..., :3] = np.where(((xx // 12 + yy // 12) % 2)[..., None], light, dark)
        depth = np.full((renderer.height, renderer.width), .95, dtype=np.float32)
        renderer.texture(0, scene)
        renderer.texture(1, np.zeros_like(depth))
        renderer.texture(2, np.where((xx // 12 + yy // 12) % 2, .90, .99))
        timings = {}
        for label, pair in [('stationary', still), ('moving', moving)]:
            if label == 'moving':
                renderer.texture(2, depth)
            timings[label] = [timing(program) for program in pair]
        raw_motion = -22 * 1.3 * renderer.height / 1080 * np.log(1 - .5 / (22 * 1.3 * renderer.height / 1080))
        slow_camera = -raw_motion * 2 * z / (renderer.width * .01875 * 120)
        timings['gentle_motion_half_pixel'] = [timing(program, camera=slow_camera) for program in moving]
        atlas[..., 3] = 1
        upload_mips(atlas)
        timings['terrain_mip_sampler'] = []
        for program in samplers:
            sample(program, 2.5)
            timings['terrain_mip_sampler'].append(timing(program))
        sheet = Image.new('RGB', (width * 3, (height + 24) * len(pictures)))
        painter = ImageDraw.Draw(sheet)
        for row, images in enumerate(pictures):
            for col, values in enumerate(images):
                sheet.paste(Image.fromarray(np.uint8(np.clip(values[::-1], 0, 1) * 255)), (col * width, row * (height + 24) + 24))
                painter.text((col * width + 8, row * (height + 24) + 5), ['Before', 'Built-in smoothing', 'Area reference'][col], fill='white')
        sheet.save(ROOT / 'validation-aa-comparison.png')
        report = {'passed': True, 'kind': 'real GPU production shader comparisons; synthetic inputs, not in-game FPS',
                  'checks': checks, 'static_aggregate_mse_unfiltered_old_current': aggregate.tolist(),
                  'isolated_gpu_ms_at_960x540': timings,
                  'limits': 'Spatial filtering reduces aliasing but cannot recover missing temporal samples. Mip stabilization needs the existing game mip chain.'}
        (ROOT / 'validation-aa.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        archive.close()
        for program in programs:
            driver.delete_program(program)
        for shader in shaders:
            driver.delete_shader(shader)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    run()
