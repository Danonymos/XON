"""Compare exposure against 1.3 while verifying that 1.4 lighting and colors are retained."""
import argparse
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from PIL import Image

from render_checks import Renderer
from validate import Driver, SHADERS, expand

ROOT = Path(__file__).resolve().parents[1]
BODY = '''
in vec2 xonUV; out vec4 result;
uniform float testBlock,testSky; uniform vec3 testNormal;
void main(){
 int row=min(int(xonUV.y*8),7);
 vec3 colors[8]=vec3[8](vec3(.2),vec3(.08,.045,.02),vec3(.75,.74,.70),
  vec3(.025,.016,.008),vec3(.18,.055,.035),vec3(.4,.08,.06),vec3(.05,.1,.2),vec3(.5,.4,.2));
 float visibility;
 result=vec4(xonLighting(colors[row],testNormal,vec3(0,0,-8),vec3(0,0,-8),
                         vec2(testBlock,testSky),0,0,visibility),1);
}'''


def display_luma(raw, lut, exposure, golden):
    color = raw * (1.05 * exposure)
    color = color * (2.51 * color + .03) / (color * (2.43 * color + .59) + .14)
    color = np.clip(color, 0, 1) ** (1 / 2.2)
    coordinate = color * 15
    low = np.floor(coordinate).astype(int)
    high = np.minimum(low + 1, 15)
    blend = coordinate - low
    graded = np.zeros_like(color)
    for red in range(2):
        for green in range(2):
            for blue in range(2):
                corner = [red, green, blue]
                weight = np.prod(np.where(corner, blend, 1 - blend), axis=-1)
                pos = np.where(corner, high, low)
                graded += lut[pos[..., 1], pos[..., 2] * 16 + pos[..., 0]] * weight[..., None]
    color = color * .15 + graded * .85
    luma = color @ np.array([.2126, .7152, .0722])
    color = np.clip(luma[..., None] + (color - luma[..., None]) * .88, 0, 1)
    if golden:
        color = np.clip(color + np.array([.024, .015, -.014])
                        * (luma * (1 - luma * .4))[..., None] * .85, 0, 1)
    return color @ np.array([.2126, .7152, .0722])


def run(calibrate=False):
    driver = Driver()
    renderer = Renderer(driver, 32, 8)
    stages, programs, raw, luts = [], [], [], []
    libraries = ['settings', 'uniforms', 'math', 'atmosphere', 'lighting']
    try:
        for version in ['1.3', '1.4', 'current']:
            if version == 'current':
                source = '\n'.join(expand(SHADERS / f'lib/{name}.glsl') for name in libraries)
                lut = Image.open(SHADERS / 'textures/xon-grade.png')
            else:
                with zipfile.ZipFile(ROOT.parent / f'XON-Shader-v{version}.zip') as archive:
                    source = '\n'.join(archive.read(f'shaders/lib/{name}.glsl').decode() for name in libraries)
                    lut = Image.open(io.BytesIO(archive.read('shaders/textures/xon-grade.png')))
                    lut.load()
            source = source.replace('\r\n', '\n')
            source = re.sub(r'^#define XON_SHADOWS$', '#undef XON_SHADOWS', source, flags=re.M)
            source = '#version 330 compatibility\n#define XON_DIMENSION 0\n' + source + BODY
            pair = []
            for text, stage in [(expand(SHADERS / 'final.vsh'), '.vsh'), (source, '.fsh')]:
                handle, warning = driver.compile(text, stage, 'brightness ' + version)
                assert not warning, warning
                stages.append(handle)
                pair.append(handle)
            program, warning = driver.link(*pair, 'brightness ' + version)
            assert not warning, warning
            programs.append(program)
            samples = []
            for sun in [(30, 90, 20), (80, 20, 10), (-80, 20, 10), (30, -90, 20)]:
                for sky, block in [(0, 0), (0, .6), (0, .85), (.4, .4), (1, 0), (1, .4)]:
                    for normal in [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]:
                        renderer.setup(program)
                        renderer.uniform1f(renderer.location('testBlock'), block)
                        renderer.uniform1f(renderer.location('testSky'), sky)
                        renderer.uniform3f(renderer.location('testNormal'), *normal)
                        renderer.uniform3f(renderer.location('sunPosition'), *sun)
                        samples.append(renderer.draw(raw=True)[..., :3].mean(axis=1))
            raw.append(np.array(samples))
            luts.append(np.asarray(lut, dtype=float) / 255)
        assert np.max(np.abs(raw[1] - raw[2])) < 2e-6, '1.4 lighting changed'
        assert np.array_equal(luts[1], luts[2]), '1.4 grading texture changed'
        target = display_luma(raw[0], luts[0], .90, False)
        original = display_luma(raw[1], luts[1], .90, True)
        grading = (SHADERS / 'lib/grading.glsl').read_text()
        exposure = float(re.search(r'XON_BASE_EXPOSURE = ([\d.]+)', grading)[1])
        current = display_luma(raw[2], luts[2], exposure, True)
        rmse = lambda values: float(np.sqrt(np.mean((values - target) ** 2)))
        candidates = [(rmse(display_luma(raw[1], luts[1], float(value), True)), round(float(value), 3))
                      for value in np.arange(.60, .901, .005)]
        report = {'passed': True, 'samples': int(target.size), 'exposure': exposure,
                  'best_fit_exposure': min(candidates)[1],
                  'v14_display_luma_rmse_to_v13': rmse(original),
                  'current_display_luma_rmse_to_v13': rmse(current),
                  'current_to_v13_mean_luma_ratio': float(current.mean() / target.mean()),
                  'v14_lighting_and_lut_preserved': True,
                  'scope': 'GPU diffuse lighting with CPU reproduction of tone mapping/LUT; 144 light/time/face cases, eight albedos. Excludes bloom, rays and full-game captures.'}
        if not calibrate:
            assert exposure < .90
            assert rmse(current) < rmse(original)
            assert abs(report['current_to_v13_mean_luma_ratio'] - 1) < .015
            (ROOT / 'validation-brightness.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        for handle in programs:
            driver.delete_program(handle)
        for handle in stages:
            driver.delete_shader(handle)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibrate', action='store_true', help='Report an exposure fit without changing source')
    run(parser.parse_args().calibrate)
