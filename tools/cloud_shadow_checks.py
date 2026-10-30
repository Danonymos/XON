"""GPU coverage, scale, motion, receiving-light and cost checks for cloud shadows."""
import ctypes as ct
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from validate import Driver, SHADERS, expand
from render_checks import Renderer, expected_color

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT.parent / 'XON-Shader-v1.0.6-before-cloud-polish.zip'
FIELD = '''
uniform float testSpan;
uniform vec3 testOrigin;
void main() {
    vec2 p=(xonUV-.5)*vec2(testSpan,testSpan*viewHeight/viewWidth);
    float field=xonCloudGroundLight(p+testOrigin.xz+cameraPosition.xz);
    result=vec4(vec3(field),1);
}
'''
SURFACE = '''
uniform float testSpan, testSky, testBlock;
uniform vec3 testOrigin, testNormal;
void main() {
    vec2 p=(xonUV-.5)*vec2(testSpan,testSpan*viewHeight/viewWidth);
    vec3 pos=vec3(p.x,0,p.y)+testOrigin;
    float visibility;
    vec3 color=xonLighting(vec3(.24,.30,.18),testNormal,pos,pos,
                           vec2(testBlock,testSky),0,0,visibility);
    result=vec4(color,1);
}
'''


def run_widths(mask, block_per_pixel):
    widths = []
    for lines in [mask[::16], mask.T[::16]]:
        for row in lines:
            edges = np.flatnonzero(np.diff(row.astype(np.int8))) + 1
            for left, right in zip(edges[:-1], edges[1:]):
                if row[left]:
                    widths.append((right - left) * block_per_pixel)
    return np.asarray(widths)


def run():
    driver = Driver()
    renderer = Renderer(driver, 960, 540)
    archive = zipfile.ZipFile(BASELINE)
    stages, programs, checks = [], [], []

    def old_source(name):
        source = archive.read('shaders/' + name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda match: old_source(match[1].lstrip('/')), source, flags=re.M)

    def compile_program(body, old=False, options=None, dimension=0, moon_reference=False, motion_probe=False):
        source = f'#version 330 compatibility\n#define XON_DIMENSION {dimension}\n'
        for library in ['settings', 'uniforms', 'math', 'atmosphere', 'clouds', 'shadows', 'lighting']:
            name = f'lib/{library}.glsl'
            source += '\n' + (old_source(name) if old else expand(SHADERS / name))
        source += '\nin vec2 xonUV; out vec4 result;\n' + body
        if moon_reference:
            source = source.replace('illumination *= 1.0 + moonOpening * 0.28;', '')
        if motion_probe:
            source = source.replace('float xonCloudGroundLight(vec2 worldXZ) {',
                                    'vec2 xonWindProbe = vec2(0.0);\nfloat xonCloudGroundLight(vec2 worldXZ) {', 1)
            source = source.replace('vec2 advected = worldXZ + drift;',
                                    'xonWindProbe = drift;\nvec2 advected = worldXZ + drift;')
        for key, value in (options or {}).items():
            source = re.sub(rf'^(?://)?#define {key}(?:[^\n]*)$',
                            f'#undef {key}' if value is False else f'#define {key} {value}', source, flags=re.M)
        pair = []
        for text, kind in [(expand(SHADERS / 'final.vsh'), '.vsh'), (source, '.fsh')]:
            shader, warning = driver.compile(text, kind, 'cloud shadow GPU check')
            assert not warning, warning
            stages.append(shader)
            pair.append(shader)
        program, warning = driver.link(*pair, 'cloud shadow GPU check')
        assert not warning, warning
        programs.append(program)
        return program

    def draw(program, span=1024, origin=(0, 0, 0), camera=(0, 80, 0), time=0,
             rain=0, sun=(30, 90, 20), sky=1, block=0, normal=(0, 1, 0), water=0):
        renderer.setup(program)
        for name, value in [('testSpan', span), ('frameTimeCounter', time), ('rainStrength', rain),
                            ('testSky', sky), ('testBlock', block), ('far', 1024)]:
            renderer.uniform1f(renderer.location(name), value)
        for name, value in [('testOrigin', origin), ('cameraPosition', camera),
                            ('sunPosition', sun), ('testNormal', normal)]:
            renderer.uniform3f(renderer.location(name), *value)
        renderer.uniform1i(renderer.location('isEyeInWater'), water)
        return renderer.draw(raw=True)

    def timing(program, **kwargs):
        draw(program, **kwargs)
        f = driver.function
        gen = f('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin = f('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end = f('glEndQuery', None, ct.c_uint)
        get = f('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete = f('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        queries = (ct.c_uint * 32)()
        gen(32, queries)
        for query in queries:
            begin(0x88BF, query)
            for _ in range(4):
                renderer.begin(0x0007)
                for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                    renderer.tex_coord(x, y)
                    renderer.vertex(x, y)
                renderer.end()
            end(0x88BF)
        values = []
        for query in queries:
            value = ct.c_uint64()
            get(query, 0x8866, ct.byref(value))
            values.append(value.value / 4e6)
        delete(32, queries)
        return {'median_ms': float(np.median(values)), 'p95_ms': float(np.percentile(values, 95))}

    try:
        renderer.texture(5, np.asarray(Image.open(SHADERS / 'textures/xon-noise.png').convert('RGBA')) / 255)
        renderer.active_texture(0x84C5)
        for axis in [0x2802, 0x2803]:
            renderer.tex_parameter(0x0DE1, axis, 0x2901)
        field = compile_program(FIELD)
        motion = compile_program('''void main() {
            float field = xonCloudGroundLight(vec2(0.0));
            result = vec4(xonWindProbe, field, 1.0);
        }''', motion_probe=True)
        old_field = compile_program(FIELD, old=True)
        off_field = compile_program(FIELD, options={'XON_GROUND_SHADOW_STRENGTH': '0.00'})
        raw = draw(field)[..., 0]
        old_raw = draw(old_field)[..., 0]
        coverage = []
        for origin in [(0, 0, 0), (3200, 0, 15900), (-2100, 0, 2300), (17000, 0, -11000)]:
            values = draw(field, span=4096, origin=origin)[..., 0]
            coverage.append({'origin': origin, 'lit_fraction': float(np.mean(values > 0)),
                             'lit_core_fraction': float(np.mean(values > .4)),
                             'shadow_core_fraction': float(np.mean(values < -.4))})
            assert .30 < coverage[-1]['lit_fraction'] < .70, coverage[-1]
            assert min(coverage[-1]['lit_core_fraction'], coverage[-1]['shadow_core_fraction']) > .16, coverage[-1]
        aggregate = float(np.mean([entry['lit_fraction'] for entry in coverage]))
        assert .42 < aggregate < .58, aggregate
        checks.append({'case': 'broad light and shadow areas remain balanced across distant positive/negative world locations',
                       'coverage': coverage, 'aggregate_lit_fraction': aggregate})
        transition_fraction = float(np.mean([1 - entry['lit_core_fraction'] - entry['shadow_core_fraction'] for entry in coverage]))
        assert .22 < transition_fraction < .4, transition_fraction
        checks.append({'case': 'wide eased transition band separates the light and shadow cores',
                       'transition_area_fraction': transition_fraction})
        widths = {}
        for name, values in [('previous', old_raw), ('polished', raw)]:
            widths[name] = {}
            for sign, mask in [('light', values > 0), ('shadow', values < 0)]:
                runs = run_widths(mask, 1024 / renderer.width)
                widths[name][sign] = {'median_blocks': float(np.median(runs)), 'p90_blocks': float(np.percentile(runs, 90))}
        assert widths['polished']['light']['median_blocks'] > widths['previous']['light']['median_blocks'] * 2, widths
        assert all(25 < widths['polished'][sign]['median_blocks'] < 60 for sign in ['light', 'shadow']), widths
        checks.append({'case': 'player-scale varied patches replace narrow cellular bright channels', 'axis_run_widths': widths})

        before = draw(field, origin=(3200, 0, 15900), time=300)[..., 0]
        after = draw(field, origin=(3200, 0, 15900), time=300 + 1 / 60)[..., 0]
        delta = np.abs(after - before)
        assert float(np.quantile(delta, .999)) < .004, 'Cloud motion jumps at normal frame intervals'
        long_change = float(np.mean(np.abs(draw(field, time=120)[..., 0] - raw)))
        assert .05 < long_change < 1.1, long_change
        travel = []
        for time in [0, 900, 1800, 2700, 3598]:
            start = draw(motion, time=time)[0, 0, :2]
            stop = draw(motion, time=time + 2)[0, 0, :2]
            displacement = float(np.linalg.norm(stop - start))
            assert abs(displacement - 1) < .001, (time, displacement)
            travel.append({'time': time, 'two_second_travel_blocks': displacement})
        checks.append({'case': 'production wind travels one block every two seconds throughout the hour', 'samples': travel})
        # Follow the measured production wind to isolate shape evolution from translation.
        drift = draw(motion, time=180)[0, 0, :2]
        followed = draw(field, time=180, origin=(-drift[0], 0, -drift[1]))[..., 0]
        shear_change = float(np.mean(np.abs(followed - raw)))
        assert .02 < shear_change < .5, shear_change
        checks.append({'case': 'slow frame-continuous motion with evolving rather than rigid silhouettes',
                       'frame_p999_signal_change': float(np.quantile(delta, .999)),
                       'two_minute_mean_change': long_change, 'three_minute_shape_change_following_wind': shear_change})
        hour_end = draw(field, origin=(3200, 0, 15900), time=3600 - 1 / 60)
        hour_start = draw(field, origin=(3200, 0, 15900), time=0)
        seam = float(np.quantile(np.abs(hour_end - hour_start), .999))
        assert seam < .004, seam
        checks.append({'case': 'hourly Iris timer reset remains as smooth as an ordinary frame', 'signal_p999_change': seam})
        stationary = draw(field, origin=(3200, 0, 15900), time=37)
        shifted = draw(field, origin=(3198.75, 0, 15902.5), camera=(1.25, 80, -2.5), time=37)
        anchor_error = float(np.max(np.abs(stationary - shifted)))
        assert anchor_error < .0002, anchor_error
        checks.append({'case': 'camera translation does not move the world-anchored pattern', 'maximum_error': anchor_error})
        rainy = draw(field, rain=1)[..., 0]
        assert np.max(np.abs(rainy - raw * .22)) < .00001
        assert np.max(np.abs(draw(off_field)[..., 0])) == 0
        assert np.max(np.abs(draw(field, camera=(0, 330, 0))[..., 0])) == 0
        checks.append({'case': 'storm contrast reduction, disabled option and above-cloud cutoff'})

        surface = compile_program(SURFACE, options={'XON_SHADOWS': False})
        surface_off = compile_program(SURFACE, options={'XON_SHADOWS': False, 'XON_GROUND_SHADOW_STRENGTH': '0.00'})
        old_surface = compile_program(SURFACE, old=True, options={'XON_SHADOWS': False})
        moon_reference = compile_program(SURFACE, options={'XON_SHADOWS': False}, moon_reference=True)
        rows = []
        for label, sun in [('day', (30, 90, 20)), ('moon', (-30, -90, -20))]:
            baseline = draw(surface_off, sun=sun)
            result = draw(surface, sun=sun)
            luma = result[..., :3] @ np.array([.2126, .7152, .0722])
            reference = baseline[..., :3] @ np.array([.2126, .7152, .0722])
            ratio = luma / reference
            shade, opening = float(np.mean(ratio[raw < -.7])), float(np.mean(ratio[raw > .7]))
            assert .40 < shade < .94 and 1.01 < opening < (1.10 if label == 'day' else 1.40), (label, shade, opening)
            assert np.isfinite(result).all() and np.min(result[..., :3]) > 0
            checks.append({'case': f'{label}: cloud cover softens existing key light while gaps retain natural light color',
                           'shadow_to_baseline_ratio': shade, 'opening_to_baseline_ratio': opening})
            rows.append([draw(old_surface, sun=sun), result])
            prior = draw(moon_reference, sun=sun)
            prior_luma = prior[..., :3] @ np.array([.2126, .7152, .0722])
            if label == 'moon':
                increase = float(np.mean(luma[raw > .9] / prior_luma[raw > .9]))
                assert 1.20 < increase < 1.30, increase
                shadow_error = float(np.max(np.abs(result[raw < 0] - prior[raw < 0])))
                assert shadow_error < .00001, shadow_error
                checks.append({'case': '1.0.7 boosts exposed moonlit openings without lifting the dark patches',
                               'bright_core_ratio_to_1_0_6': increase, 'shadow_patch_error': shadow_error})
            else:
                assert np.max(np.abs(result - prior)) < .00001, 'Moon boost changed daylight'
        for label, kwargs in [('cave', {'sky': 0}), ('torch-lit cave', {'sky': 0, 'block': 1}),
                              ('underwater', {'water': 1}), ('backface in a clear opening', {'normal': (0, -1, 0)})]:
            baseline, result = draw(surface_off, **kwargs), draw(surface, **kwargs)
            values = np.abs(baseline - result)
            if label.startswith('backface'):
                values = values[raw > .7]
            error = float(np.max(values))
            assert error < .00001, (label, error)
            checks.append({'case': label + ' preserves existing lighting', 'maximum_error': error})

        # A very distant point still receives cloud modulation before the horizon fade.
        distant = draw(surface, span=0, origin=(300, 0, 0))
        distant_off = draw(surface_off, span=0, origin=(300, 0, 0))
        assert np.max(np.abs(distant - distant_off)) > .005
        checks.append({'case': 'cloud shading survives beyond the old 96-block cutoff'})

        sheet = Image.new('RGB', (1920, 1130))
        painter = ImageDraw.Draw(sheet)
        for index, values in enumerate([old_raw, raw]):
            grey = np.repeat(((values + 1) * .5)[..., None], 3, axis=-1)
            sheet.paste(Image.fromarray((np.flipud(np.clip(grey, 0, 1)) * 255).astype(np.uint8)), (index * 960, 30))
            painter.text((index * 960 + 12, 8), ['Previous / 1024-block field', 'Polished / same 1024-block field'][index], fill='white')
        # Save daylight and moonlight surface comparisons separately from the raw field.
        for index, values in enumerate(rows[0]):
            sheet.paste(Image.fromarray((np.flipud(expected_color(values[..., :3])) * 255).astype(np.uint8)), (index * 960, 590))
            painter.text((index * 960 + 12, 570), ['Previous / synthetic grass under daylight', 'Polished / synthetic grass under daylight'][index], fill='white')
        sheet.save(ROOT / 'validation-cloud-shadow-comparison.png')
        frames = []
        for time in range(0, 241, 8):
            values = draw(field, span=768, time=time)[..., 0]
            grey = np.repeat(((values + 1) * .5)[..., None], 3, axis=-1)
            frame = Image.fromarray((np.flipud(np.clip(grey, 0, 1)) * 255).astype(np.uint8)).resize((640, 360))
            ImageDraw.Draw(frame).text((12, 10), f'Synthetic cloud coverage / {time}s / 20x playback', fill=(225, 75, 45))
            frames.append(frame)
        frames[0].save(ROOT / 'validation-cloud-shadow-motion.gif', save_all=True, append_images=frames[1:], duration=400, loop=0)
        timings = {'previous_field': timing(old_field), 'polished_field': timing(field),
                   'previous_synthetic_ground': timing(old_surface), 'polished_synthetic_ground': timing(surface),
                   'polished_effect_off': timing(surface_off)}
        report = {'passed': True, 'kind': 'GPU cloud pattern and receiving-light checks; synthetic scene, not Minecraft FPS',
                  'driver': driver.get_string(0x1F01).decode(), 'checks': checks, 'gpu_960x540': timings,
                  'limits': 'Cloud coverage is an artistic local approximation, not a traced projection of visible sky clouds. Timing includes synthetic flat shading only; far terrain now participates.'}
        (ROOT / 'validation-cloud-shadows.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        archive.close()
        for program in programs:
            driver.delete_program(program)
        for shader in stages:
            driver.delete_shader(shader)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    run()
