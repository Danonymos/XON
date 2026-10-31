"""Benchmark actual lighting against 1.0.8, including lamp gaps and doorway continuity."""
import argparse
import ctypes as ct
import hashlib
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from validate import Driver, SHADERS, expand, variant_source
from render_checks import Renderer

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT.parent / 'XON-Shader-v1.0.8.zip'
BODY = '''
in vec2 xonUV; out vec4 result;
uniform float testBlock, testSky, testEmission;
uniform int testRamp, testRaw;
uniform vec3 testNormal;
void main() {
    vec3 n=testNormal;
    float b=testBlock, s=testSky;
    int material=min(int(xonUV.y*5),4);
    vec3 albedo=material==0?vec3(.20,.20,.21):material==1?vec3(.08,.045,.02):
                material==2?vec3(.75,.74,.70):material==3?vec3(.025,.016,.008):vec3(.18,.055,.035);
    vec3 p=vec3((xonUV.x-.5)*24,0,-8);
    if(testRamp==1 || testRamp==2){
        albedo=vec3(.20);p=vec3(0,0,-8);
        if(testRamp==1)b=xonUV.x; else s=xonUV.x;
    }
    if(testRamp==3){
        // Controlled Minecraft-like Manhattan light levels, not source-direction tracing.
        float d=min(abs(p.x-5.0),abs(p.x+5.0))+1.0;
        b=clamp((14.0-d)/15.0,0.0,1.0);
    }
    float visibility;
    vec3 c=xonLighting(albedo,n,p,p,vec2(b,s),testEmission,0,visibility);
    if(testRaw==0){
        c=max(c*(XON_BRIGHTNESS*XON_BASE_EXPOSURE),vec3(0));
        c=c*(2.51*c+.03)/(c*(2.43*c+.59)+.14);
        c=xonApplyGrade(xonToDisplay(clamp(c,0,1)));
    }
    result=vec4(c,1);
}
'''
GEOMETRY_VERTEX = '''#version 330 compatibility
out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels; out vec4 xonVertexColor;
out vec3 xonViewPosition,xonPlayerPosition,xonWorldNormal; flat out float xonMaterial;
uniform float testBlock,testSky; uniform int testRamp; uniform vec3 testNormal;
void main(){
 vec2 uv=gl_MultiTexCoord0.xy;xonTexCoord=uv;xonAtlasBounds=vec4(0);
 xonLightLevels=vec2(testRamp==1?uv.x:testBlock,testSky);xonVertexColor=vec4(1);
 xonPlayerPosition=vec3((uv.x-.5)*32,-2,-4-uv.y*16);xonViewPosition=xonPlayerPosition;
 xonWorldNormal=testNormal;xonMaterial=0;gl_Position=vec4(gl_Vertex.xy*2-1,0,1);
}'''


def run(candidate=None):
    driver = Driver()
    renderer = Renderer(driver, 1024, 320)
    archive = zipfile.ZipFile(BASELINE)
    stages, programs, checks, rows = [], [], [], []
    baseline_hash = hashlib.sha256(BASELINE.read_bytes()).hexdigest()

    def source(name, old):
        if not old:
            if name == 'lib/lighting.glsl' and candidate:
                return candidate.read_text(encoding='utf-8')
            return expand(SHADERS / name)
        value = archive.read('shaders/' + name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda m: source(m[1].lstrip('/'), True), value, flags=re.M)

    def compile_program(old, dimension):
        text = f'#version 330 compatibility\n#define XON_DIMENSION {dimension}\n'
        text += '\n'.join(source(f'lib/{name}.glsl', old) for name in
                          ['settings', 'uniforms', 'math', 'atmosphere', 'lighting', 'grading'])
        text = re.sub(r'^#define XON_SHADOWS\b', '#undef XON_SHADOWS', text, flags=re.M)
        pair = []
        for value, stage in [(expand(SHADERS / 'final.vsh'), '.vsh'), (text + BODY, '.fsh')]:
            handle, warning = driver.compile(value, stage, 'lighting balance')
            assert not warning, warning
            stages.append(handle)
            pair.append(handle)
        handle, warning = driver.link(*pair, 'lighting balance')
        assert not warning, warning
        programs.append(handle)
        return handle

    def setup(selected, block=0, sky=0, night=False, held=0, ramp=0, raw=False,
              normal=(0, 1, 0), emission=0, vision=0):
        renderer.setup(selected)
        for name, value in [('testBlock', block), ('testSky', sky),
                            ('testEmission', emission), ('nightVision', vision)]:
            renderer.uniform1f(renderer.location(name), value)
        for name, value in [('testRamp', ramp), ('testRaw', int(raw)), ('heldBlockLightValue', held)]:
            renderer.uniform1i(renderer.location(name), value)
        renderer.uniform3f(renderer.location('testNormal'), *normal)
        renderer.uniform3f(renderer.location('sunPosition'), *((-30, -90, -20) if night else (30, 90, 20)))
        renderer.uniform3f(renderer.location('fogColor'), .35, .12, .08)
        renderer.uniform1f(renderer.location('alphaTestRef'), .1)
        for name, value in [('gbufferModelView', np.eye(4)), ('shadowModelView', np.eye(4)),
                            ('shadowModelViewInverse', np.eye(4)), ('shadowProjection', np.diag([.02,.02,.02,1]))]:
            data = np.ascontiguousarray(value.T, dtype=np.float32)
            renderer.uniform_matrix(renderer.location(name), 1, 0, data.ctypes.data)

    def geometry_pair(shadows):
        fragment = variant_source(SHADERS / 'gbuffers_terrain.fsh',
                                  {'XON_COLORED_EMISSIVE_LIGHTING': False, 'XON_SHADOWS': shadows, 'XON_CLOUD_STYLE': 0})
        current = expand(SHADERS / 'lib/lighting.glsl')
        assert fragment.count(current) == 1
        pair = []
        for old in [True, False]:
            handles = []
            for text, stage in [(GEOMETRY_VERTEX, '.vsh'),
                                (fragment.replace(current, source('lib/lighting.glsl', old)), '.fsh')]:
                handle, warning = driver.compile(text, stage, 'full terrain balance benchmark')
                assert not warning, warning
                stages.append(handle)
                handles.append(handle)
            handle, warning = driver.link(*handles, 'full terrain balance benchmark')
            assert not warning, warning
            programs.append(handle)
            pair.append(handle)
        return pair

    def images(pair, **options):
        values = []
        for selected in pair:
            setup(selected, **options)
            values.append(renderer.draw(raw=options.get('raw', False))[..., :3])
        return values

    def luma(rgb):
        return rgb @ np.array([.2126, .7152, .0722])

    def metrics(label, pair, **options):
        values = images(pair, **options)
        stone = [float(luma(v)[renderer.height // 10].mean()) for v in values]
        ratio = stone[1] / stone[0]
        assert .78 < ratio <= 1.001, (label, ratio)
        assert stone[1] > (.14 if options.get('night') else .16), (label, stone)
        dark = [float(luma(v)[renderer.height * 7 // 10].mean()) for v in values]
        readability_limit = .70 if options.get('block', 0) or options.get('held', 0) else .90
        assert dark[1] >= dark[0] * readability_limit, (label, dark)
        if label in ['moonlit outdoors', 'unlit night cave']:
            assert np.max(np.abs(values[0] - values[1])) < .000001
        else:
            assert ratio < .995, (label, ratio)
        checks.append({'case': label, 'stone_display_luma_before_current': stone,
                       'dark_material_display_luma_before_current': dark, 'ratio': ratio})
        rows.append((label, values))

    def benchmark(pair, **options):
        f = driver.function
        gen = f('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin = f('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end = f('glEndQuery', None, ct.c_uint)
        read = f('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete = f('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))

        def quad():
            renderer.begin(0x0007)
            for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                renderer.tex_coord(x, y)
                renderer.vertex(x, y)
            renderer.end()

        # Interleave both programs per query pair to limit clock/load ordering bias.
        handles = (ct.c_uint * 96)()
        gen(96, handles)
        for selected in pair:
            setup(selected, raw=True, **options)
            for _ in range(12):
                quad()
        samples = [[], []]
        for index in range(48):
            for version in ([0, 1] if index % 2 == 0 else [1, 0]):
                setup(pair[version], raw=True, **options)
                begin(0x88BF, handles[index * 2 + version])
                for _ in range(8):
                    quad()
                end(0x88BF)
        for index in range(48):
            for version in [0, 1]:
                value = ct.c_uint64()
                read(handles[index * 2 + version], 0x8866, ct.byref(value))
                samples[version].append(value.value / 8e6)
        delete(96, handles)
        return [{'median_ms': float(np.median(v)), 'p95_ms': float(np.percentile(v, 95))} for v in samples]

    try:
        renderer.texture(4, np.asarray(Image.open(SHADERS / 'textures/xon-grade.png').convert('RGBA')) / 255)
        pairs = {dimension: [compile_program(old, dimension) for old in [True, False]]
                 for dimension in [0, -1, 1]}
        for label, dimension, options in [
            ('daylit outdoors', 0, {'sky': 1}),
            ('outdoor shade', 0, {'sky': 1, 'normal': (-1, 0, 0)}),
            ('moonlit outdoors', 0, {'sky': 1, 'night': True}),
            ('indoor lamp', 0, {'block': .85}),
            ('cave lamp', 0, {'block': .55}),
            ('unlit cave', 0, {}),
            ('unlit night cave', 0, {'night': True}),
            ('held torch indoors', 0, {'held': 15}),
            ('Nether ambient', -1, {}),
            ('Nether lamp', -1, {'block': .75}),
            ('End ambient', 1, {}),
            ('End lamp', 1, {'block': .75}),
        ]:
            metrics(label, pairs[dimension], **options)

        for dimension in [0, -1, 1]:
            values = images(pairs[dimension], ramp=1)
            current = values[1][renderer.height // 2]
            assert np.min(np.diff(current, axis=0)) >= -.00001, dimension
            assert np.max(np.abs(np.diff(current, axis=0))) < .005
            checks.append({'case': 'smooth monotonic indoor light ramp', 'dimension': dimension})
        doorway = images(pairs[0], block=.65, ramp=2)
        line = doorway[1][renderer.height // 2]
        assert np.max(np.abs(np.diff(line, axis=0))) < .01
        curvature = float(np.max(np.abs(np.diff(line, n=2, axis=0))))
        previous_curvature = float(np.max(np.abs(np.diff(doorway[0][renderer.height // 2], n=2, axis=0))))
        assert curvature <= previous_curvature * 1.10
        checks.append({'case': 'continuous indoor/outdoor blend', 'max_step': float(np.max(np.abs(np.diff(line, axis=0))))})

        pools = images(pairs[0], ramp=3)
        lines = [luma(v)[renderer.height // 10] for v in pools]
        peak = int((5 / 24 + .5) * renderer.width)
        gap = renderer.width // 2
        ratios = [float(v[gap] / v[peak]) for v in lines]
        assert ratios[1] < ratios[0] - .025, ratios
        assert lines[1][gap] > .20, float(lines[1][gap])
        checks.append({'case': 'two lamps leave readable shade between pools',
                       'gap_to_peak_luma_before_current': ratios, 'gap_luma_current': float(lines[1][gap])})
        rows.append(('two lamps / smooth shade between pools', pools))

        for vision in [0, 1]:
            for dimension in [0, -1, 1]:
                emissive = images(pairs[dimension], emission=1, vision=vision, raw=True)
                assert np.max(np.abs(emissive[0] - emissive[1])) < .000001
                checks.append({'case': 'emissive floor retained', 'dimension': dimension, 'night_vision': vision})
        shade, night_vision = [images(pairs[0], vision=v)[1] for v in [0, 1]]
        assert np.mean(night_vision) > np.mean(shade) * 1.3
        checks.append({'case': 'night vision remains useful'})

        renderer.texture(8, np.full((16, 16, 4), [.5, .48, .44, 1], dtype=np.float32))
        renderer.active_texture(0x84C7)
        renderer.bind_texture(0x0DE1, renderer.textures[7])
        depth = np.ones((512,512), dtype=np.float32)
        renderer.tex_image(0x0DE1, 0, 0x8CAC, 512, 512, 0, 0x1902, 0x1406, depth.ctypes.data)
        renderer.tex_parameter(0x0DE1, 0x884C, 0x884E)
        renderer.tex_parameter(0x0DE1, 0x884D, 0x0203)
        renderer.width, renderer.height = 1920, 1080
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, 1920, 1080, 0, 0x1908, 0x1406, None)
        renderer.viewport(0, 0, 1920, 1080)
        timings = {name: benchmark(pairs[dimension], **options) for name, dimension, options in [
            ('indoor lamps', 0, {'ramp': 1}), ('daylight', 0, {'sky': 1}),
            ('Nether lamps', -1, {'ramp': 1}), ('held torch', 0, {'held': 15})]}
        for name, shadows, options in [('terrain indoor', False, {'ramp': 1}),
                                        ('terrain daylight with shadows', True, {'sky': 1})]:
            pair = geometry_pair(shadows)
            # Check that real fragments survive alpha testing before timing their work.
            for selected in pair:
                setup(selected, **options)
                assert float(np.mean(renderer.draw(raw=True)[...,:3])) > .005
            timings[name] = benchmark(pair, **options)
        report = {'passed': True, 'candidate': str(candidate) if candidate else None,
                  'baseline': str(BASELINE), 'baseline_sha256': baseline_hash, 'checks': checks,
                  'timings_before_current': timings, 'test_resolution': [1024, 320],
                  'benchmark_resolution': [renderer.width, renderer.height],
                  'timing_method': '48 interleaved timer queries per version, eight draws each; warmup; production lighting library',
                  'limitations': 'Synthetic material/lightmap inputs and RGBA32F target. Terrain timing disables voxel light/clouds; outdoor shadows remain enabled. No source-direction reconstruction or full-game FPS measurement.'}
        sheet = Image.new('RGB', (1024, len(rows) * 184))
        painter = ImageDraw.Draw(sheet)
        for row, (label, values) in enumerate(rows):
            for column, value in enumerate(values):
                tile = Image.fromarray(np.uint8(np.clip(value[::-1], 0, 1) * 255)).resize((512, 160))
                sheet.paste(tile, (column * 512, row * 184 + 24))
                painter.text((column * 512 + 8, row * 184 + 6), ('1.0.8 / ' if column == 0 else 'Balanced / ') + label, fill='white')
        sheet.save(ROOT / 'validation-lighting-balance.png')
        (ROOT / 'validation-lighting-balance.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        archive.close()
        for program in programs:
            driver.delete_program(program)
        for stage in stages:
            driver.delete_shader(stage)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, help='Benchmark an uninstalled lighting library before adopting it')
    run(parser.parse_args().candidate)
