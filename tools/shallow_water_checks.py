"""Real water-fragment regression tests against the preserved 1.0.3 pack."""
import json
import re
import zipfile
from pathlib import Path
import numpy as np
from validate import Driver, SHADERS, expand
from render_checks import Renderer
from optimization_checks import GEOMETRY_VERTEX

ROOT = Path(__file__).resolve().parents[1]


def run():
    driver = Driver()
    renderer = Renderer(driver)
    stages, programs, checks = [], [], []
    try:
        with zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.0.3.zip') as archive:
            def old_source(name):
                # Hold the intentional palette rebalance fixed while testing water composition.
                if name == 'lib/atmosphere.glsl':
                    return expand(SHADERS / name)
                text = archive.read('shaders/' + name).decode('utf-8')
                return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                              lambda m: old_source(m[1].lstrip('/')), text, flags=re.M)
            sources = [old_source('gbuffers_water.fsh'), expand(SHADERS / 'gbuffers_water.fsh')]
        vertex = GEOMETRY_VERTEX.replace('uniform float testMaterial;', 'uniform float testMaterial; uniform float testSky;')
        vertex = vertex.replace('xonLightLevels=vec2(0.2,1)', 'xonLightLevels=vec2(0.2,testSky)')
        vertex = vertex.replace('xonVertexColor=vec4(1)', 'xonVertexColor=vec4(.2,.5,.8,1)')
        vertex = vertex.replace('vec3((uv.x-0.5)*24.0,-2,-4.0-uv.y*56.0)', 'vec3((uv.x-0.5)*2.0,-5,-5)')
        for fragment in sources:
            for name, value in [('XON_SHADOWS', None), ('XON_CLOUD_STYLE', '0'), ('XON_WATER_DETAIL', '0')]:
                fragment = re.sub(r'^#define '+name+r'(?: [^\n]*)?$',
                                  '#undef '+name if value is None else '#define '+name+' '+value, fragment, flags=re.M)
            pair = []
            for text, suffix in [(vertex, '.vsh'), (fragment, '.fsh')]:
                stage, warning = driver.compile(text, suffix, 'shallow water')
                if warning:
                    raise AssertionError(warning)
                stages.append(stage)
                pair.append(stage)
            program, warning = driver.link(*pair, 'shallow water')
            if warning:
                raise AssertionError(warning)
            programs.append(program)
        renderer.texture(8, np.ones((2, 2, 4), dtype=np.float32))
        for background in [[.65, .65, .65], [.10, .06, .03], [.025, .025, .025]]:
            renderer.texture(6, np.full((8, 8, 4), background + [1], dtype=np.float32))
            for sky in [0, 1]:
                for medium in [0, 1]:
                    for thickness in [.02, .10, .50, 1.49, 1.51, 2, 16]:
                        near, far, distance = .05, 1024., 5 + thickness
                        depth = ((far+near)/(far-near) - 2*far*near/((far-near)*distance))*.5+.5
                        renderer.texture(9, np.full((8, 8), depth, dtype=np.float32))
                        images = []
                        for program in programs:
                            renderer.setup(program)
                            renderer.uniform1f(renderer.location('testMaterial'), 10001)
                            renderer.uniform1f(renderer.location('testSky'), sky)
                            renderer.uniform1i(renderer.location('isEyeInWater'), medium)
                            renderer.uniform3f(renderer.location('sunPosition'), 0, 100, 0)
                            images.append(renderer.draw(raw=True))
                        difference = float(np.max(np.abs(images[1] - images[0])))
                        if (medium == 1 or thickness >= 1.5) and difference > .000001:
                            raise AssertionError('Deep water or underwater appearance changed')
                        red_drop = float(np.mean(images[0][..., 0] - images[1][..., 0]))
                        if medium == 0 and sky == 0 and thickness <= .1 and red_drop < background[0]*.10:
                            raise AssertionError(f'Thin water visibility: background={background}, thickness={thickness}, red_drop={red_drop}, difference={difference}')
                        if np.min(images[1][..., 3]) < .9999:
                            raise AssertionError('Refractive water would be blended with the background twice')
                        checks.append({'background': background, 'sky': sky, 'medium': medium,
                                       'thickness': thickness, 'max_hdr_difference': difference,
                                       'red_absorption_increase': red_drop})
    finally:
        for program in programs:
            driver.delete_program(program)
        for stage in stages:
            driver.delete_shader(stage)
        renderer.close()
        driver.close()
    report = {'passed': True, 'kind': 'synthetic water-fragment checks at the same current atmospheric palette; not game FPS', 'checks': checks}
    (ROOT / 'validation-shallow-water.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print('Passed', len(checks), 'water cases; deep/underwater parity and thin indoor visibility')


if __name__ == '__main__':
    run()
