"""Check End atmosphere math, production pixels, isolation and paired GPU cost."""
import argparse
import ctypes as ct
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from PIL import Image, ImageDraw

from render_checks import Renderer
from validate import Driver, SHADERS, expand

ROOT = Path(__file__).resolve().parents[1]
BODY = '''
in vec2 xonUV;out vec4 result;
uniform int testKind,testRaw;
uniform float testDistance,testSky,testBlock,testEmission;
uniform vec3 testNormal,testOffset;
uniform sampler2D testInputs;
void main(){
 vec3 ray=normalize(vec3((xonUV.x-.5)*3.0,(xonUV.y-.5)*1.8,1));
 vec3 pos=ray*testDistance;
 vec3 c=vec3(.28,.25,.20);float visibility;
 if(testKind==0)c=xonLighting(c,testNormal,pos,pos,vec2(testBlock,testSky),testEmission,0,visibility);
 else if(testKind==1)c=xonFog(c,pos,testSky);
 else if(testKind==2){
#if XON_DIMENSION == 1
  c=xonEndSky(ray);
#else
  c=xonSky(ray);
#endif
 }
#if XON_DIMENSION == 1 && defined TEST_NEW
 else if(testKind==3){result=xonEndHaze(testOffset,length(testOffset));return;}
 else if(testKind==4){vec2 h=texture(testInputs,xonUV).rg;result=vec4(xonEndLayerMean(h.x,h.y));return;}
#endif
 else if(testKind==5){
  c=xonLighting(c,testNormal,pos,pos,vec2(testBlock,testSky),0,0,visibility);
  c=xonFog(c,pos,testSky);
 }else{
  vec3 origin=vec3(0,78,-32);
  ray=normalize(vec3((xonUV.x-.5)*2.8,(xonUV.y-.58)*1.6,1));
#if XON_DIMENSION == 1
  c=xonEndSky(ray);
#else
  c=xonSky(ray);
#endif
  float nearest=10000;vec3 normal=vec3(0,1,0);vec3 point=vec3(0);
  for(int i=0;i<8;i++){
   float fi=float(i);float z=fi*57.0;float y=62.0-fi*2.5;
   vec3 center=vec3(sin(fi*2.1)*68.0,y-10.0,z);
   vec3 size=vec3(26.0+fi*2.0,10,19.0+fi*1.5);
   vec3 a=(center-size-origin)/ray;vec3 b=(center+size-origin)/ray;
   vec3 near3=min(a,b);vec3 far3=max(a,b);
   float entry=max(max(near3.x,near3.y),near3.z);float leave=min(min(far3.x,far3.y),far3.z);
   if(entry>0 && entry<leave && entry<nearest){
    nearest=entry;point=origin+ray*entry;
    normal=near3.x>=near3.y && near3.x>=near3.z ? vec3(-sign(ray.x),0,0) :
           near3.y>=near3.z ? vec3(0,-sign(ray.y),0):vec3(0,0,-sign(ray.z));
   }
  }
  if(nearest<10000){
   float grain=.94+.06*sin(point.x*6.2+point.y*5.7)*cos(point.z*5.1-point.y*4.2);
   vec3 albedo=vec3(.53,.49,.34)*grain;
   c=xonLighting(albedo,normal,ray*nearest,ray*nearest,vec2(0,1),0,0,visibility);
   c=xonFog(c,ray*nearest,1);
  }
 }
 if(testRaw==0){
  c=max(c*(XON_BRIGHTNESS*XON_BASE_EXPOSURE),vec3(0));
  c=c*(2.51*c+.03)/(c*(2.43*c+.59)+.14);
  c=xonApplyGrade(xonToDisplay(clamp(c,0,1)));
 }
 result=vec4(c,1);
}'''


def run(baseline):
    driver = Driver()
    renderer = Renderer(driver, 480, 270)
    archive = zipfile.ZipFile(baseline)
    stages, programs, checks = [], [], []

    def saved(name):
        source = archive.read('shaders/' + name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda match: saved(match[1].lstrip('/')), source, flags=re.M)

    def program(old, dimension, density=1, fixed_kind=None):
        source = f'#version 330 compatibility\n#define XON_DIMENSION {dimension}\n'
        if not old:
            source += '#define TEST_NEW\n'
        for name in ['settings', 'uniforms', 'math', 'atmosphere', 'clouds', 'lighting', 'end_sky', 'grading']:
            path = f'lib/{name}.glsl'
            source += '\n' + (saved(path) if old else expand(SHADERS / path))
        source = re.sub(r'^#define XON_SHADOWS\b', '#undef XON_SHADOWS', source, flags=re.M)
        source = re.sub(r'^#define XON_ATMOSPHERE_DENSITY .*$',
                        f'#define XON_ATMOSPHERE_DENSITY {float(density)}', source, flags=re.M)
        body = BODY if fixed_kind is None else BODY.replace('uniform int testKind,testRaw;', f'const int testKind={fixed_kind};uniform int testRaw;')
        pair = []
        for text, stage in [(expand(SHADERS / 'final.vsh'), '.vsh'), (source + body, '.fsh')]:
            handle, warning = driver.compile(text, stage, 'End atmosphere')
            assert not warning, warning
            stages.append(handle)
            pair.append(handle)
        selected, warning = driver.link(*pair, 'End atmosphere')
        assert not warning, warning
        programs.append(selected)
        return selected

    def setup(selected, kind=0, distance=100, normal=(0, 1, 0), block=0, emission=0,
              camera=(0, 78, -32), offset=(0, 0, 0), time=240, medium=0, blind=0,
              darkness=0, vision=0, flash=0, far=1024, raw=True):
        renderer.setup(selected)
        for name, value in [('testKind', kind), ('testRaw', int(raw)), ('isEyeInWater', medium), ('testInputs', 0)]:
            renderer.uniform1i(renderer.location(name), value)
        for name, value in [('testDistance', distance), ('testSky', 1), ('testBlock', block),
                            ('testEmission', emission), ('frameTimeCounter', time), ('far', far),
                            ('fogStart', far * .8), ('fogEnd', far), ('blindness', blind),
                            ('darknessFactor', darkness), ('nightVision', vision), ('endFlashIntensity', flash)]:
            renderer.uniform1f(renderer.location(name), value)
        for name, value in [('testNormal', normal), ('testOffset', offset), ('cameraPosition', camera),
                            ('sunPosition', (30, 90, 20)), ('fogColor', (.3, .25, .2)), ('skyColor', (.5, .7, 1))]:
            renderer.uniform3f(renderer.location(name), *value)

    def draw(selected, **options):
        setup(selected, **options)
        return renderer.draw(raw=True)

    def parity(pair, label, **options):
        before, after = [draw(p, **options) for p in pair]
        error = float(np.max(np.abs(before - after)))
        assert error < 2e-6, (label, options, error)
        checks.append({'case': label, 'options': options, 'maximum_raw_error': error})

    def timing(pair):
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

        queries = (ct.c_uint * 48)()
        gen(48, queries)
        try:
            for p in pair:
                setup(p, kind=5, distance=160)
                for _ in range(12):
                    quad()
            for batch in range(24):
                for version in ([0, 1] if batch % 2 == 0 else [1, 0]):
                    setup(pair[version], kind=5, distance=160)
                    begin(0x88BF, queries[batch * 2 + version])
                    for _ in range(4):
                        quad()
                    end(0x88BF)
            times = [[], []]
            for batch in range(24):
                for version in [0, 1]:
                    value = ct.c_uint64()
                    read(queries[batch * 2 + version], 0x8866, ct.byref(value))
                    times[version].append(value.value / 4e6)
            return {'before_ms': float(np.median(times[0])), 'after_ms': float(np.median(times[1])),
                    'median_paired_ratio': float(np.median(np.array(times[1]) / times[0]))}
        finally:
            delete(48, queries)

    try:
        for unit, name in [(4, 'xon-grade.png'), (5, 'xon-noise.png'), (10, 'xon-black-hole.png')]:
            renderer.texture(unit, np.asarray(Image.open(SHADERS / 'textures' / name).convert('RGBA')) / 255)
        renderer.active_texture(0x84C5)
        for axis in [0x2802, 0x2803]:
            renderer.tex_parameter(0x0DE1, axis, 0x2901)
        pairs = {dim: [program(old, dim) for old in [True, False]] for dim in [0, -1, 1]}
        for selected in programs:
            renderer.use_program(selected)
            renderer.uniform1i(renderer.uniform_location(selected, b'xonBlackHoleLUT'), 10)
        for dim in [0, -1]:
            for kind in [0, 1, 2, 5]:
                for medium in range(4):
                    parity(pairs[dim], 'other dimension unchanged', kind=kind, medium=medium, block=.7)
        pair = pairs[1]
        for time in [0, 71, 3599.99, 3600]:
            for flash in [0, .6]:
                parity(pair, 'End sky preserved', kind=2, time=time, flash=flash)
        for medium in [1, 2, 3]:
            parity(pair, 'End medium fog preserved', kind=1, medium=medium)
        for normal in [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]:
            parity(pair, 'emissive cores retained', emission=1, normal=normal, block=.8)
            values = [draw(p, normal=normal)[..., :3].mean(axis=(0, 1)) for p in pair]
            before, after = values
            luma_ratio = float((after @ [.2126, .7152, .0722]) / (before @ [.2126, .7152, .0722]))
            assert .65 < luma_ratio < 1.12, (normal, luma_ratio)
            assert after[2] / after[1] > before[2] / before[1] * 1.25
            checks.append({'case': 'violet surface light with readable form', 'normal': normal, 'linear_luma_ratio': luma_ratio})
        new = pair[1]
        rng = np.random.default_rng(181)
        h = np.zeros((270, 480, 4), np.float32)
        h[..., 0] = rng.uniform(-250, 400, h.shape[:2])
        h[..., 1] = h[..., 0] + rng.uniform(-600, 600, h.shape[:2])
        h[:30, :, 1] = h[:30, :, 0] + rng.uniform(-.1, .1, h[:30].shape[:2])
        renderer.texture(0, h)
        values = draw(new, kind=4)[..., 0]
        nodes, weights = np.polynomial.legendre.leggauss(4)
        a, b = np.minimum(h[..., 0], h[..., 1]).astype(float), np.maximum(h[..., 0], h[..., 1]).astype(float)
        area = np.zeros_like(a)
        for low, high in [(-32, 56), (56, 144)]:
            lo, hi = np.maximum(a, low), np.minimum(b, high)
            span = np.maximum(hi - lo, 0)
            y = lo[..., None] + (nodes + 1) * span[..., None] * .5
            q = np.clip(np.abs((y - 56) / 88), 0, 1)
            density = 1 - q * q * (3 - 2 * q)
            area += (density @ weights) * span * .5
        reference = np.divide(area, b - a, out=np.zeros_like(a), where=b > a)
        same = b == a
        q = np.clip(np.abs((a - 56) / 88), 0, 1)
        reference[same] = (1 - q * q * (3 - 2 * q))[same]
        error = float(np.max(np.abs(values - reference)))
        assert error < .0003, error
        assert values.min() >= 0 and values.max() <= 1
        checks.append({'case': '129600 height paths versus independent piecewise Gaussian quadrature', 'maximum_density_error': error})
        for height in [-100, 0, 56, 78, 144, 220]:
            for direction in [(0, 0, 1), (.6, .7, .2), (-.3, -.6, .4)]:
                direction = np.array(direction) / np.linalg.norm(direction)
                opacity = []
                for distance in [0, 4, 8, 8.01, 10, 20, 40, 80, 160, 320, 640, 1280]:
                    value = draw(new, kind=3, camera=(12, height, -35), offset=direction * distance)[0, 0]
                    opacity.append(float(value[3]))
                assert np.min(np.diff(opacity)) > -1e-4, (height, direction, opacity)
                assert max(opacity[:3]) == 0 and 0 <= min(opacity) <= max(opacity) < 1
                checks.append({'case': 'clear near zone and monotonic depth haze', 'height': height, 'direction': direction.tolist(), 'opacity': opacity})
        for offset in [(100, 0, 100), (0, 180, 0), (0, -140, 300), (.001, 0, .001)]:
            for time in [0, 93, 3599.99]:
                a = draw(new, kind=3, offset=offset, time=time)
                b = draw(new, kind=3, offset=offset, time=time + 1 / 60)
                delta = float(np.max(np.abs(a - b)))
                assert delta < .0002, (offset, time, delta)
            a, b = [draw(new, kind=3, offset=offset, time=t) for t in [0, 3600]]
            assert np.max(np.abs(a - b)) < 2e-6
            checks.append({'case': 'smooth animation and hourly timer seam', 'offset': offset})
        off = program(False, 1, density=0)
        for distance in [10, 160, 1000]:
            assert np.max(np.abs(draw(off, kind=3, offset=(0, 0, distance)))) == 0
        checks.append({'case': 'atmosphere density zero removes added haze'})
        for blind, darkness, vision, flash in [(1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)]:
            value = draw(new, kind=5, blind=blind, darkness=darkness, vision=vision, flash=flash)
            assert np.isfinite(value).all() and value.min() >= 0
            checks.append({'case': 'vision and flash boundaries finite', 'blindness': blind, 'darkness': darkness, 'night_vision': vision, 'flash': flash})
        rows = []
        for label, options in [('synthetic island scene', {'kind': 6}), ('near surface / 12 blocks', {'kind': 5, 'distance': 12}),
                               ('mid-distance / 96 blocks', {'kind': 5, 'distance': 96}), ('distant surface / 240 blocks', {'kind': 5, 'distance': 240})]:
            rows.append((label, [draw(p, raw=False, **options) for p in pair]))
        sheet = Image.new('RGB', (960, 294 * len(rows)))
        painter = ImageDraw.Draw(sheet)
        for row, (label, values) in enumerate(rows):
            for version, value in enumerate(values):
                sheet.paste(Image.fromarray(np.uint8(np.clip(value[::-1, :, :3], 0, 1) * 255)), (version * 480, row * 294 + 24))
                painter.text((version * 480 + 8, row * 294 + 6), ('1.8 / ' if version == 0 else '1.8.1 / ') + label, fill='white')
        sheet.save(ROOT / 'validation-end-atmosphere.png')
        unchanged = ['lib/end_sky.glsl', 'program/sky.fsh', 'program/sky.vsh', 'lib/settings.glsl',
                     'lib/emissive_light.glsl', 'lib/lamp_light.glsl', 'program/geometry.fsh', 'shaders.properties',
                     'textures/xon-grade.png', 'textures/xon-black-hole.png', 'textures/xon-noise.png']
        for name in unchanged:
            assert archive.read('shaders/' + name).replace(b'\r\n', b'\n') == (SHADERS / name).read_bytes().replace(b'\r\n', b'\n'), name
        checks.append({'case': 'sky, lamps, quality settings, geometry and render passes unchanged', 'files': unchanged})
        timing_pair = [program(old, 1, fixed_kind=5) for old in [True, False]]
        renderer.width, renderer.height = 1920, 1080
        renderer.active_texture(0x84CB)
        renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, renderer.width, renderer.height, 0, 0x1908, 0x1406, None)
        renderer.viewport(0, 0, renderer.width, renderer.height)
        timings = timing(timing_pair)
        report = {'passed': True, 'baseline': str(baseline), 'checks': checks,
                  'height_oracle_paths': int(h.shape[0] * h.shape[1]), 'lighting_fog_gpu_ms_1080p': timings,
                  'scope': 'Native OpenGL production-function pixels, numerical integration oracle and synthetic scene; not live Minecraft approval or full-frame FPS.'}
        (ROOT / 'validation-end-atmosphere.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': True, 'checks': len(checks), 'height_oracle_paths': report['height_oracle_paths'], 'timings': timings,
                          'report': str(ROOT / 'validation-end-atmosphere.json')}, indent=2))
    finally:
        archive.close()
        for selected in programs:
            driver.delete_program(selected)
        for handle in stages:
            driver.delete_shader(handle)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=ROOT.parent / 'XON-Shader-v1.8.zip')
    run(parser.parse_args().baseline)
