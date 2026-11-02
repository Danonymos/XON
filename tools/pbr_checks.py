"""Render production terrain/PBR code against controlled textures and the 1.4 lighting."""
import argparse
import io
import json
from pathlib import Path
import re
import zipfile

import numpy as np
from PIL import Image

from render_checks import Renderer
from validate import Driver, SHADERS, expand, variant_source

ROOT = Path(__file__).resolve().parents[1]
VERTEX = '''#version 330 compatibility
out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels;
out vec4 xonVertexColor; out vec3 xonViewPosition,xonPlayerPosition,xonWorldNormal;
flat out float xonMaterial;
out vec3 xonTangent,xonBinormal,xonViewVector; out vec4 xonAtlasAM;
out vec2 xonLocalUV; out float xonDist;
uniform float testBlock,testSky,testAO,testMaterial,testTangent;
uniform vec3 testNormal,testPosition,testView;
void main(){
 vec2 uv=gl_MultiTexCoord0.xy*.98+.01;
 xonTexCoord=uv;xonAtlasBounds=vec4(.5,.5,.5,.5);
 xonLightLevels=vec2(testBlock,testSky);xonVertexColor=vec4(1,1,1,testAO);
 xonViewPosition=testPosition;xonPlayerPosition=testPosition;xonWorldNormal=testNormal;
 xonMaterial=testMaterial;xonTangent=vec3(testTangent,0,0);xonBinormal=vec3(0,0,testTangent);
 xonViewVector=testView;xonAtlasAM=vec4(0,0,1,1);xonLocalUV=uv;xonDist=length(testPosition);
 gl_Position=vec4(gl_Vertex.xy*2-1,0,1);
}'''


def run(resource_pack=None):
    driver = Driver()
    renderer = Renderer(driver, 128, 64)
    stages, programs, checks = [], [], []
    baseline = zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.4.zip')
    options = {'XON_COLORED_EMISSIVE_LIGHTING': False, 'XON_SHADOWS': False,
               'XON_CLOUD_STYLE': 0, 'XON_PARALLAX': 0}

    def saved(name):
        value = baseline.read('shaders/' + name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda m: saved(m[1].lstrip('/')), value, flags=re.M)

    def compile_pair(fragment, vertex=VERTEX):
        pair = []
        for source, kind in [(vertex, '.vsh'), (fragment, '.fsh')]:
            handle, warning = driver.compile(source, kind, 'PBR pixel regression')
            assert not warning, warning
            stages.append(handle)
            pair.append(handle)
        handle, warning = driver.link(*pair, 'PBR pixel regression')
        assert not warning, warning
        programs.append(handle)
        return handle

    def terrain(dimension=0, pbr=True, old=False, **overrides):
        path = ('' if dimension == 0 else f'world{dimension}/') + 'gbuffers_terrain.fsh'
        flags = dict(options, XON_ADVANCED_MATERIALS=1 if pbr else False, **overrides)
        if not old:
            return compile_pair(variant_source(SHADERS / path, flags))
        source = saved(path)
        for key, value in flags.items():
            source = re.sub(rf'^(?://)?#define {key}(?:[^\n]*)?$',
                            '#undef ' + key if value is False else f'#define {key} {value}',
                            source, flags=re.M)
        return compile_pair(source)

    def texture(unit, values):
        data = np.asarray(values, dtype=np.float32)
        if data.ndim == 1:
            data = np.tile(data, (16, 16, 1))
        if data.shape[-1] == 4:
            renderer.texture(unit, data)
        else:
            data = np.ascontiguousarray(np.rint(data * 255), dtype=np.uint8)
            renderer.active_texture(0x84C0 + unit)
            renderer.bind_texture(0x0DE1, renderer.textures[unit])
            renderer.tex_image(0x0DE1, 0, 0x8051, data.shape[1], data.shape[0], 0,
                               0x1907, 0x1401, data.ctypes.data)

    def draw(program, block=.65, sky=0, ao=1, normal=(0, 1, 0), position=(0, 0, -8),
             tangent=1, material=0):
        renderer.setup(program)
        renderer.uniform1i(renderer.location('normals'), 10)
        renderer.uniform1i(renderer.location('specular'), 0)
        for name, value in [('testBlock', block), ('testSky', sky), ('testAO', ao),
                            ('testTangent', tangent), ('testMaterial', material), ('alphaTestRef', .1),
                            ('far', 1024), ('fogStart', 800), ('fogEnd', 1024)]:
            renderer.uniform1f(renderer.location(name), value)
        for name, value in [('testNormal', normal), ('testPosition', position),
                            ('testView', (.3, .15, -1)), ('sunPosition', (30, 90, 20))]:
            renderer.uniform3f(renderer.location(name), *value)
        return renderer.draw(raw=True)[..., :3]

    def equal(name, before, after, tolerance=2e-6):
        error = float(np.max(np.abs(before - after)))
        assert error <= tolerance, (name, error)
        checks.append({'case': name, 'max_error': error})

    try:
        texture(8, [.75, .71, .65, 1])
        texture(10, [128 / 255, 128 / 255, 1, 1])
        texture(0, [0, 0, 0, 1])
        for dimension in [0, -1, 1]:
            off, on, old = terrain(dimension, False), terrain(dimension), terrain(dimension, old=True)
            for sky in [0, .4, 1]:
                for normal in [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]:
                    reference = draw(off, sky=sky, normal=normal, ao=.6)
                    equal(f'1.4 diffuse lighting retained / dimension {dimension} / sky {sky} / {normal}',
                          draw(old, sky=sky, normal=normal, ao=.6), reference)
                    equal(f'flat PBR on/off / dimension {dimension} / sky {sky} / {normal}',
                          reference, draw(on, sky=sky, normal=normal, ao=.6))

        off, on = terrain(pbr=False), terrain()
        for sentinel in [[0, 0, 0, 0], [128 / 255, 128 / 255, 1, 1]]:
            texture(10, sentinel)
            equal('missing/flat normal retains geometry lighting', draw(off), draw(on))
        texture(10, [128 / 255, 128 / 255, 1, 1])
        for alpha in [0, 1]:
            texture(0, [200 / 255, 0, 100 / 255, alpha])
            equal(f'quartz non-emissive alpha {alpha}', draw(off, ao=.55), draw(on, ao=.55))
        texture(0, [200 / 255, 0, 100 / 255])
        equal('native RGB specular has no emission', draw(off, ao=.55), draw(on, ao=.55))
        for sky in [0, .4, 1]:
            light = np.array([30, 90, 20], dtype=float)
            light /= np.linalg.norm(light)
            view = np.array([0, 0, 1])
            half = light + view
            half /= np.linalg.norm(half)
            neutral = [0.0, .04, 0, 1]
            texture(0, neutral)
            no_spec = draw(on, sky=sky, normal=half)
            texture(0, [.8, .04, 0, 1])
            glossy = draw(on, sky=sky, normal=half)
            if sky < .55:
                equal(f'no celestial specular under roof / sky {sky}', no_spec, glossy)
            else:
                delta = float(np.mean(glossy - no_spec))
                assert .001 < delta < 1.0, delta
                checks.append({'case': 'sunlit GGX is visible and bounded', 'mean_delta': delta})

        texture(0, [0, 0, 100 / 255, 0])
        lit = draw(on)
        texture(0, [0, 0, 100 / 255, 254 / 255])
        emissive = draw(on)
        assert np.mean(emissive) > np.mean(lit) + .25
        checks.append({'case': 'LabPBR alpha 254 still emits; blue is not emission'})
        texture(0, [0, 0, 0, 1])
        texture(10, [128 / 255, 128 / 255, 0, 1])
        assert np.max(draw(on)) < 1e-6
        checks.append({'case': 'LabPBR AO zero remains fully occluded'})

        texture(10, [.7, .4, 1, 1])
        equal('invalid tangent does not perturb geometric normal', draw(off), draw(on, tangent=0))
        texture(10, [128 / 255, 128 / 255, 1, 1])
        cavity, flat = draw(on, ao=.5), draw(on)
        assert np.mean(cavity) < np.mean(flat) * .75
        checks.append({'case': 'architectural cavity AO retained'})

        pom_source = '#version 330 compatibility\n#define XON_DIMENSION 0\n'
        pom_source += '\n'.join(expand(SHADERS / f'lib/{n}.glsl') for n in
                                 ['settings', 'uniforms', 'math', 'atmosphere', 'lighting', 'pbr'])
        pom_source = re.sub(r'^#define XON_SHADOWS$', '#undef XON_SHADOWS', pom_source, flags=re.M)
        pom_source += '''
in vec2 xonTexCoord; out vec4 result;
void main(){
 vec2 uv=xonTexCoord*.25+vec2(.25);
 vec2 hit=xonGetParallaxCoord(uv,xonTexCoord,vec4(.25,.25,.25,.25),vec3(.5,0,-1),0);
 result=vec4(hit,0,1);
}'''
        pom = compile_pair(pom_source)
        texture(10, [128 / 255, 128 / 255, 1, .5])
        hit = draw(pom)
        u = (np.arange(renderer.width) + .5) / renderer.width * .98 + .01
        expected_u = np.clip(((u + .05) % 1) * .25 + .25, .28125, .46875)
        assert np.max(np.abs(hit[0, :, 0] - expected_u)) < 2e-6
        assert hit[..., :2].min() >= .25 and hit[..., :2].max() <= .5
        checks.append({'case': 'POM constant-depth intersection and atlas containment'})

        ramp = np.tile([.5, .5, 1, 1], (64, 64, 1))
        axis = (np.arange(64) + .5) / 64
        ramp[..., 3] = np.clip(.25 + .5 * (axis - .25) / .25, 0, 1)
        texture(10, ramp)
        expected_u = (u + .1 * (.75 - .5 * u) / 1.05) * .25 + .25
        interior = (u > .1) & (u < .85)
        for quality in [16, 32, 64, 128, 256]:
            source = re.sub(r'#define XON_PARALLAX_QUALITY 64\b',
                            f'#define XON_PARALLAX_QUALITY {quality}', pom_source)
            output = draw(compile_pair(source))
            error = float(np.max(np.abs(output[0, interior, 0] - expected_u[interior])))
            assert error < 2e-6, (quality, error)
            checks.append({'case': f'POM sloped-height analytic intersection / {quality} steps', 'max_error': error})
        no_offset = np.stack(np.meshgrid(u * .25 + .25,
                             ((np.arange(renderer.height) + .5) / renderer.height * .98 + .01) * .25 + .25), axis=-1)
        for label, source, normal in [
            ('distance fade', pom_source.replace('vec3(.5,0,-1),0)', 'vec3(.5,0,-1),1)'), [.5, .5, 1, .5]),
            ('missing tangents', pom_source.replace('vec3(.5,0,-1)', 'vec3(0)'), [.5, .5, 1, .5]),
            ('missing normal texture', pom_source, [0, 0, 0, 0]),
            ('flat height', pom_source, [.5, .5, 1, 1]),
        ]:
            texture(10, normal)
            output = draw(compile_pair(source))
            equal('POM bypass / ' + label, no_offset, output[..., :2])
        texture(10, [.5, .5, 1, .5])
        grazing = draw(compile_pair(pom_source.replace('vec3(.5,0,-1)', 'vec3(5,0,-1)')))
        assert grazing[..., :2].min() >= .25 and grazing[..., :2].max() <= .5
        checks.append({'case': 'POM grazing-angle ray stays inside atlas tile'})

        if resource_pack:
            with_pom = terrain(XON_PARALLAX=1)
            with zipfile.ZipFile(resource_pack) as archive:
                for name in ['quartz_block_side', 'oak_planks', 'stone']:
                    prefix = f'assets/minecraft/textures/block/{name}'
                    for unit, suffix in [(8, ''), (10, '_n'), (0, '_s')]:
                        im = Image.open(io.BytesIO(archive.read(prefix + suffix + '.png')))
                        texture(unit, np.asarray(im.convert('RGB' if unit == 0 and im.mode == 'RGB' else 'RGBA')) / 255)
                    before, after = draw(off, ao=.6), draw(on, ao=.6)
                    ratio = float(np.mean(after) / np.mean(before))
                    assert .70 < ratio < 1.15, (name, ratio)
                    cavity, flat = draw(on, ao=.5), draw(on)
                    assert np.mean(cavity) < np.mean(flat) * .75
                    checks.append({'case': f'Primes HD {name}: no indoor blowout, AO retained',
                                   'pbr_on_off_mean_ratio': ratio})
                    displaced = draw(with_pom, ao=.6)
                    displacement = float(np.mean(np.abs(displaced - after)))
                    assert displacement > .0001, (name, displacement)
                    assert .7 < float(np.mean(displaced) / np.mean(after)) < 1.15
                    checks.append({'case': f'Primes HD {name}: height map changes rendered relief',
                                   'mean_pixel_change': displacement})

        report = {'passed': True, 'checks': checks, 'resource_pack': str(resource_pack) if resource_pack else None,
                  'scope': 'Synthetic native OpenGL terrain/material pixels; no Iris runtime or full-scene visual certification.'}
        (ROOT / 'validation-pbr.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': True, 'checks': len(checks), 'scope': report['scope']}, indent=2))
    finally:
        baseline.close()
        for handle in programs:
            driver.delete_program(handle)
        for handle in stages:
            driver.delete_shader(handle)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resource-pack', type=Path, help='Optional Primes HD 256x archive for real material checks')
    run(parser.parse_args().resource_pack)
