"""Compare outdoor color and night visibility against the preserved 1.7 pack."""
import argparse
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
uniform int testKind,testRaw;uniform float testSky,testBlock;
uniform vec3 testNormal;
void main(){
 vec3 c;
 vec3 ray=normalize(vec3((xonUV.x-.5)*2.8,xonUV.y*.9+.025,1));
 if(testKind==1)c=xonSky(ray);
 else if(testKind==2)c=xonCloudSky(ray,true);
 else{
  int material=min(int(xonUV.x*6),5);
  vec3 albedo=material==0?vec3(.22):material==1?vec3(.08,.28,.045):
   material==2?vec3(.32,.19,.09):material==3?vec3(.78,.77,.74):
   material==4?vec3(.44,.18,.065):vec3(.025,.016,.008);
  float detail=.94+.06*cos(floor(xonUV.x*180)*1.7+floor(xonUV.y*90)*2.1);
  vec3 pos=vec3(0,0,-8);float visibility;
  c=xonLighting(albedo*detail,testNormal,pos,pos,vec2(testBlock,testSky),0,0,visibility);
  if(testKind==3)c=xonFog(c,vec3(35,5,-180),testSky);
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
    renderer = Renderer(driver, 480, 160)
    stages, programs, checks, rows = [], [], [], []
    archive = zipfile.ZipFile(baseline)

    def saved(name):
        text = archive.read('shaders/' + name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda m: saved(m[1].lstrip('/')), text, flags=re.M)

    def program(old, dimension):
        text = f'#version 330 compatibility\n#define XON_DIMENSION {dimension}\n'
        for name in ['settings', 'uniforms', 'math', 'atmosphere', 'clouds', 'lighting', 'grading']:
            path = f'lib/{name}.glsl'
            text += '\n' + (saved(path) if old else expand(SHADERS / path))
        text = re.sub(r'^#define XON_SHADOWS\b', '#undef XON_SHADOWS', text, flags=re.M)
        pair = []
        for value, kind in [(expand(SHADERS / 'final.vsh'), '.vsh'), (text + BODY, '.fsh')]:
            handle, warning = driver.compile(value, kind, 'outdoor warmth')
            assert not warning, warning
            pair.append(handle)
            stages.append(handle)
        selected, warning = driver.link(*pair, 'outdoor warmth')
        assert not warning, warning
        programs.append(selected)
        return selected

    def draw(selected, sun=(30, 90, 20), normal=(0, 1, 0), sky=1, block=0,
             kind=0, moon=0, rain=0, raw=False):
        renderer.setup(selected)
        for name, value in [('testSky', sky), ('testBlock', block), ('rainStrength', rain),
                            ('far', 1024), ('fogStart', 800), ('fogEnd', 1024), ('frameTimeCounter', 240)]:
            renderer.uniform1f(renderer.location(name), value)
        for name, value in [('testKind', kind), ('testRaw', int(raw)), ('moonPhase', moon)]:
            renderer.uniform1i(renderer.location(name), value)
        for name, value in [('sunPosition', sun), ('testNormal', normal), ('skyColor', (.5, .7, 1)),
                            ('fogColor', (.35, .25, .2)), ('cameraPosition', (0, 75, 0))]:
            renderer.uniform3f(renderer.location(name), *value)
        return renderer.draw(raw=True)[..., :3]

    def neutral(value):
        return value[8:-8, 8:72].mean(axis=(0, 1), dtype=np.float64)

    def luma(value):
        return value @ np.array([.2126, .7152, .0722])

    try:
        for unit, name in [(4, 'xon-grade.png'), (5, 'xon-noise.png')]:
            renderer.texture(unit, np.asarray(Image.open(SHADERS / 'textures' / name).convert('RGBA')) / 255)
        renderer.active_texture(0x84C5)
        for axis in [0x2802, 0x2803]:
            renderer.tex_parameter(0x0DE1, axis, 0x2901)
        pairs = {dim: [program(old, dim) for old in [True, False]] for dim in [0, -1, 1]}
        pair = pairs[0]
        day_cases = [('morning', (90, 22, 20)), ('noon', (30, 90, 20)),
                     ('afternoon', (-80, 35, 20)), ('sunset', (-90, 12, 20))]
        for label, sun in day_cases:
            for normal in [(0, 1, 0), (-1, 0, 0)]:
                images = [draw(p, sun=sun, normal=normal) for p in pair]
                before, after = [neutral(v) for v in images]
                warmth = float((after[0] / after[2]) / (before[0] / before[2]))
                ratio = float(luma(after) / luma(before))
                assert warmth > 1.02, (label, normal, warmth)
                assert .92 < ratio < 1.08, (label, normal, ratio)
                checks.append({'case': label + ' / ' + str(normal), 'display_warmth_ratio': warmth,
                               'display_luma_ratio': ratio, 'stone_rgb_before_after': [before.tolist(), after.tolist()]})
                if normal == (0, 1, 0):
                    grass = images[1][8:-8, 88:152].mean(axis=(0, 1))
                    assert grass[1] > grass[0] > grass[2], grass
                    rows.append((label + ' / outdoor materials', images))
        for moon in [0, 2, 4]:
            for kind in [0, 1, 2, 3]:
                images = [draw(p, sun=(-30, -90, -20), moon=moon, kind=kind) for p in pair]
                before, after = [neutral(v) for v in images]
                ratio = float(luma(after) / luma(before))
                assert .65 < ratio < .96, (moon, kind, ratio)
                assert after[2] > after[0], after
                assert (after[0] / after[2]) > (before[0] / before[2]), (before, after)
                checks.append({'case': 'darker, less icy outdoor night', 'moon_phase': moon, 'kind': kind,
                               'display_luma_ratio': ratio, 'stone_rgb_before_after': [before.tolist(), after.tolist()]})
                if moon == 0:
                    rows.append(('night / ' + ['materials', 'sky', 'clouds', 'distance atmosphere'][kind], images))
        for sun in [(30, 90, 20), (-30, -90, -20)]:
            for block in [0, .8]:
                values = [draw(p, sun=sun, sky=0, block=block, raw=True) for p in pair]
                assert np.max(np.abs(values[1] - values[0])) < 2e-6
                checks.append({'case': 'enclosed cave/lamp lighting unchanged', 'sun': sun, 'block': block})
        for dim in [-1, 1]:
            for kind in [0, 1, 3]:
                values = [draw(p, kind=kind, raw=True) for p in pairs[dim]]
                assert np.max(np.abs(values[1] - values[0])) < 2e-6
                checks.append({'case': 'other dimension retained', 'dimension': dim, 'kind': kind})
        for rain in [0, .5, 1]:
            values = [draw(p, rain=rain, kind=3) for p in pair]
            ratio = float(luma(values[1]).mean() / luma(values[0]).mean())
            assert .9 < ratio < 1.1, (rain, ratio)
            checks.append({'case': 'bounded weather/distance brightness', 'rain': rain, 'luma_ratio': ratio})
            for kind in [1, 2]:
                night = [draw(p, sun=(-30, -90, -20), rain=rain, kind=kind) for p in pair]
                night_ratio = float(luma(night[1]).mean() / luma(night[0]).mean())
                assert .65 < night_ratio < .96, (rain, kind, night_ratio)
                checks.append({'case': 'night weather also darkens', 'rain': rain, 'kind': kind, 'luma_ratio': night_ratio})
        for kind in [1, 2, 3]:
            values = [draw(p, kind=kind) for p in pair]
            rows.append((['', 'day / sky', 'day / clouds', 'day / distance atmosphere'][kind], values))
        transition = []
        for height in np.linspace(-.2, .9, 128):
            transition.append(neutral(draw(pair[1], sun=(90, float(height * 100), 20))))
        assert np.max(np.abs(np.diff(transition, axis=0))) < .08
        checks.append({'case': 'continuous dawn/day transition', 'maximum_display_step': float(np.max(np.abs(np.diff(transition, axis=0))))})
        for name in ['lib/grading.glsl', 'lib/settings.glsl', 'textures/xon-grade.png', 'lib/emissive_light.glsl']:
            assert archive.read('shaders/' + name).replace(b'\r\n', b'\n') == (SHADERS / name).read_bytes().replace(b'\r\n', b'\n')
        checks.append({'case': 'global grade, exposure, controls and local light volume unchanged'})
        sheet = Image.new('RGB', (960, 184 * len(rows)))
        painter = ImageDraw.Draw(sheet)
        for row, (label, values) in enumerate(rows):
            for index, value in enumerate(values):
                sheet.paste(Image.fromarray(np.uint8(np.clip(value[::-1], 0, 1) * 255)), (index * 480, row * 184 + 24))
                painter.text((index * 480 + 8, row * 184 + 6), ('1.7 / ' if index == 0 else 'Warmer outdoors / ') + label, fill='white')
        sheet.save(ROOT / 'validation-outdoor-warmth.png')
        report = {'passed': True, 'checks': checks, 'baseline': str(baseline),
                  'scope': 'Synthetic production lighting/sky/cloud/fog pixels and unchanged LUT; not a Minecraft visual match or live FPS measurement.'}
        (ROOT / 'validation-outdoor-warmth.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': True, 'checks': len(checks), 'report': str(ROOT / 'validation-outdoor-warmth.json')}, indent=2))
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
    parser.add_argument('--baseline', type=Path, default=ROOT.parent / 'XON-Shader-v1.7.zip')
    run(parser.parse_args().baseline)
