"""Render and compare V1.3 sky/lava shaders on the GPU against the saved V1.2 pack."""
import ctypes as ct
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from validate import Driver, SHADERS, expand, variant_source
from render_checks import Renderer

ROOT = Path(__file__).resolve().parents[1]
SKY_VERTEX = '''#version 330 compatibility
out vec3 xonSkyRay;out vec4 xonSkyVertexColor;out vec2 xonSkyTexCoord;
uniform vec3 testCenter,testRight,testUp;uniform float testFov;
void main(){
 vec2 p=(gl_MultiTexCoord0.xy-.5)*testFov;
 xonSkyRay=testCenter+testRight*p.x+testUp*p.y;
 xonSkyVertexColor=vec4(1);xonSkyTexCoord=gl_MultiTexCoord0.xy;
 gl_Position=vec4(gl_Vertex.xy*2-1,0,1);
}'''
LAVA_VERTEX = '''#version 330 compatibility
out vec2 xonTexCoord;out vec4 xonAtlasBounds;out vec2 xonLightLevels;out vec4 xonVertexColor;
out vec3 xonViewPosition,xonPlayerPosition,xonWorldNormal;flat out float xonMaterial;
uniform vec3 testNormal;
void main(){
 vec2 p=(gl_MultiTexCoord0.xy-.5)*48;
 xonTexCoord=gl_MultiTexCoord0.xy;xonAtlasBounds=vec4(0);xonLightLevels=vec2(1,0);xonVertexColor=vec4(1);
 xonViewPosition=vec3(0,-2,-5);xonPlayerPosition=vec3(p.x,0,p.y);xonWorldNormal=testNormal;
 xonMaterial=10005;gl_Position=vec4(gl_Vertex.xy*2-1,0,1);
}'''


def run():
    driver = Driver()
    renderer = Renderer(driver, 960, 540)
    baseline = zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.2.zip')
    stages, programs, checks = [], [], []
    folder = ROOT / 'docs' / 'images' / 'v1.3-previews'
    folder.mkdir(exist_ok=True)

    def old(name):
        text = baseline.read('shaders/' + name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$', lambda m: old(m[1].lstrip('/')), text, flags=re.M)

    def program(vertex, fragment):
        pair = []
        for source, stage in [(vertex, '.vsh'), (fragment, '.fsh')]:
            handle, warning = driver.compile(source, stage, 'visual polish')
            assert not warning, warning
            stages.append(handle)
            pair.append(handle)
        selected, warning = driver.link(*pair, 'visual polish')
        assert not warning, warning
        programs.append(selected)
        return selected

    def options(source, values):
        for key, value in values.items():
            source = re.sub(rf'^(?://)?#define {key}(?:[^\n]*)?$',
                            '#undef ' + key if value is False else f'#define {key} {value}', source, flags=re.M)
        return source

    def sky(dimension, flags=None, previous=False):
        path = ('world1/' if dimension == 1 else '') + 'gbuffers_skybasic.fsh'
        source = old(path) if previous else variant_source(SHADERS / path, flags or {})
        if previous:
            source = source.replace('#version 330 compatibility', '#version 330 compatibility\n#define MC_RENDER_STAGE_SUNSET 2\n#define MC_RENDER_STAGE_STARS 6', 1)
        return program(SKY_VERTEX, source)

    def setup(selected, time=0, rain=0, center=(0, .35, 1), fov=1.6, camera=(0, 80, 0)):
        renderer.setup(selected)
        renderer.uniform1i(renderer.location('xonBlackHoleLUT'), 10)
        forward = np.asarray(center, dtype=float)
        forward /= np.linalg.norm(forward)
        right = np.cross([0, 1, 0], forward)
        right /= np.linalg.norm(right)
        up = np.cross(forward, right)
        for key, value in [('testCenter', forward), ('testRight', right * (16 / 9)), ('testUp', up),
                           ('cameraPosition', camera), ('sunPosition', (30, 70, 20)), ('skyColor', (.5, .7, 1)),
                           ('testNormal', (0, 1, 0))]:
            renderer.uniform3f(renderer.location(key), *value)
        for key, value in [('testFov', fov), ('frameTimeCounter', time), ('far', 1024),
                           ('rainStrength', rain), ('thunderStrength', rain * .4), ('alphaTestRef', .1)]:
            renderer.uniform1f(renderer.location(key), value)

    def draw(selected, **kwargs):
        setup(selected, **kwargs)
        return renderer.draw(raw=True)

    for unit, name in [(4, 'xon-grade.png'), (5, 'xon-noise.png')]:
        renderer.texture(unit, np.asarray(Image.open(SHADERS / 'textures' / name).convert('RGBA'), np.float32) / 255)
    renderer.active_texture(0x84C5)
    for axis in [0x2802, 0x2803]:
        renderer.tex_parameter(0x0DE1, axis, 0x2901)
    renderer.texture(1, np.zeros((540, 960), np.float32))
    renderer.texture(2, np.ones((540, 960), np.float32))
    renderer.texture(8, np.full((16, 16, 4), [.8, .3, .05, 1], np.float32))
    renderer.texture(10, np.asarray(Image.open(SHADERS / 'textures/xon-black-hole.png').convert('RGBA'), np.float32) / 255)

    extraction = program(expand(SHADERS / 'final.vsh'), variant_source(SHADERS / 'composite.fsh', {'XON_LIGHT_SHAFTS': False}))
    blur = program(expand(SHADERS / 'final.vsh'), expand(SHADERS / 'composite1.fsh'))
    resolve = program(expand(SHADERS / 'final.vsh'), variant_source(SHADERS / 'final.fsh', {'XON_MOTION_BLUR': False, 'XON_LIGHT_SHAFTS': False}))

    def display(image):
        renderer.texture(0, image)
        renderer.setup(extraction)
        effects = renderer.draw(raw=True)
        renderer.texture(3, effects)
        renderer.setup(blur)
        renderer.texture(3, renderer.draw(raw=True))
        renderer.setup(resolve)
        return renderer.draw()[..., :3]

    def save(name, images, labels):
        sheet = Image.new('RGB', (960 * len(images), 568), (13, 14, 20))
        painter = ImageDraw.Draw(sheet)
        for index, (data, label) in enumerate(zip(images, labels)):
            sheet.paste(Image.fromarray(np.uint8(np.clip(data[::-1], 0, 1) * 255)), (index * 960, 28))
            painter.text((index * 960 + 12, 9), label + ' | synthetic GPU view', fill=(225, 224, 230))
        sheet.save(folder / name)

    def timing(pair, **kwargs):
        gen = driver.function('glGenQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        begin = driver.function('glBeginQuery', None, ct.c_uint, ct.c_uint)
        end = driver.function('glEndQuery', None, ct.c_uint)
        get = driver.function('glGetQueryObjectui64v', None, ct.c_uint, ct.c_uint, ct.POINTER(ct.c_uint64))
        delete = driver.function('glDeleteQueries', None, ct.c_int, ct.POINTER(ct.c_uint))
        ids = (ct.c_uint * 48)()
        gen(48, ids)
        for selected in pair:
            draw(selected, **kwargs)
        for index in range(24):
            for version in ([0, 1] if index % 2 == 0 else [1, 0]):
                setup(pair[version], **kwargs)
                begin(0x88BF, ids[index * 2 + version])
                for _ in range(4):
                    renderer.begin(0x0007)
                    for x, y in [(0, 0), (1, 0), (1, 1), (0, 1)]:
                        renderer.tex_coord(x, y)
                        renderer.vertex(x, y)
                    renderer.end()
                end(0x88BF)
        times = [[], []]
        for index in range(24):
            for version in range(2):
                value = ct.c_uint64()
                get(ids[index * 2 + version], 0x8866, ct.byref(value))
                times[version].append(value.value / 4e6)
        delete(48, ids)
        return [{'median_ms': float(np.median(v)), 'p95_ms': float(np.percentile(v, 95))} for v in times]

    try:
        end_before, end_after = sky(1, previous=True), sky(1)
        no_hole = sky(1, {'XON_END_BLACK_HOLE': False})
        no_stars = sky(1, {'XON_END_STARS': '0.00'})
        center = (-.35046, .42055, .83609)
        end = draw(end_after, center=center, fov=1.1)
        blank = draw(no_hole, center=center, fov=1.1)
        assert np.max(end[..., :3]) > 3 and np.mean(end[295:305, 475:485, :3]) < .005
        assert np.mean(blank[295:305, 475:485, :3]) > .01
        save('end-galaxy.png', [display(draw(end_before, center=center, fov=1.1)), display(end)], ['V1.2', 'V1.3'])
        save('black-hole.png', [display(draw(end_after, center=center, fov=.65))], ['V1.3 black hole'])
        save('galactic-band.png', [display(draw(end_after, center=(.885, .460, .050), fov=1.4))], ['V1.3 galactic band'])
        checks.append({'case': 'production End sky has an occluding dark core and HDR disk/arcs; toggle restores background'})
        stars = draw(end_after, center=(0, .8, -1)) - draw(no_stars, center=(0, .8, -1))
        assert np.max(stars[..., :3]) > .02 and np.count_nonzero(stars[..., 0] > .01) > 25
        checks.append({'case': 'filtered End stars contribute localized highlights independently of galaxy/disk'})
        assert np.array_equal(draw(end_after, center=center, camera=(0, 80, 0)), draw(end_after, center=center, camera=(12000, 80, -9000)))
        checks.append({'case': 'celestial background is translation invariant'})
        transfer = np.asarray(Image.open(SHADERS / 'textures/xon-black-hole.png'))
        edges = np.concatenate([transfer[0], transfer[-1], transfer[:, 0], transfer[:, -1]])
        assert np.max(edges) == 0, 'Lookup boundary must blend into the surrounding sky'
        checks.append({'case': 'black-hole lookup has transparent dark borders, preventing a rectangular sky seam'})
        for medium in [1, 2, 3]:
            setup(end_after, center=center)
            renderer.uniform1i(renderer.location('isEyeInWater'), medium)
            assert np.isfinite(renderer.draw(raw=True)).all()
        renderer.uniform1i(renderer.location('isEyeInWater'), 0)
        checks.append({'case': 'End sky remains finite through water/lava/powder-snow medium handling'})

        previous_cloud = sky(0, previous=True)
        formations = [sky(0, {'XON_CLOUD_FORMATION': mode}) for mode in range(4)]
        images = [draw(p, time=30) for p in formations]
        for left, right in [(1, 2), (1, 3), (2, 3)]:
            difference = float(np.mean(np.abs(images[left] - images[right])))
            assert difference > .012, difference
            checks.append({'case': 'fixed formations have distinct silhouettes', 'pair': [left, right], 'difference': difference})
        save('cloud-formations.png', [display(images[i]) for i in [1, 2, 3]], ['Cumulus', 'Cloudlets', 'Veils'])
        save('cloud-comparison.png', [display(draw(previous_cloud, time=30)), display(images[0])], ['V1.2', 'V1.3 evolving'])
        a, b = draw(formations[0], time=0), draw(formations[0], time=3600)
        error = float(np.max(np.abs(a - b)))
        assert error < .001, error
        checks.append({'case': 'evolving formations/wind are seamless across the hourly timer reset', 'maximum_error': error})
        for boundary in [0, 300, 600, 900]:
            before = draw(formations[0], time=(boundary - .001) % 3600)
            after = draw(formations[0], time=(boundary + .001) % 3600)
            error = float(np.percentile(np.abs(before - after), 99))
            assert error < .003, (boundary, error)
            checks.append({'case': 'smooth formation boundary', 'time': boundary, 'p99_error': error})
        moved = draw(formations[0], time=60)
        assert np.mean(np.abs(moved - a)) > .01
        assert np.mean(draw(formations[0], time=30, rain=1)[..., :3]) < np.mean(images[0][..., :3])
        checks.append({'case': 'clouds move/evolve over one minute and storms retain darker lighting'})

        lava_before = program(LAVA_VERTEX, options(old('gbuffers_terrain.fsh'), {'XON_SHADOWS': False, 'XON_COLORED_EMISSIVE_LIGHTING': False}))
        lava_after = program(LAVA_VERTEX, variant_source(SHADERS / 'gbuffers_terrain.fsh', {'XON_SHADOWS': False, 'XON_COLORED_EMISSIVE_LIGHTING': False}))
        lava_off = program(LAVA_VERTEX, variant_source(SHADERS / 'gbuffers_terrain.fsh', {'XON_SHADOWS': False, 'XON_COLORED_EMISSIVE_LIGHTING': False, 'XON_LAVA_GLOW': '0.00'}))
        before, after = draw(lava_before, time=30), draw(lava_after, time=30)
        assert np.max(np.abs(draw(lava_off, time=30) - before)) < .000001
        assert np.min(after[..., 0]) < .8 and np.max(after[..., 0]) > np.max(before[..., 0]) * 1.25
        bloom_energy = []
        for image in [before, after]:
            renderer.texture(0, image)
            renderer.setup(extraction)
            bloom_energy.append(float(renderer.draw(raw=True)[..., :3].sum()))
        assert bloom_energy[1] > bloom_energy[0] * 1.15, bloom_energy
        save('lava-comparison.png', [display(before), display(after)], ['V1.2 lava', 'V1.3 lava'])
        checks.append({'case': 'production lava retains crust; new glow adds bloom energy; zero exactly restores V1.2', 'bloom_energy_ratio': bloom_energy[1] / bloom_energy[0]})
        timings = {'End sky': timing([end_before, end_after], center=center, fov=1.1),
                   'Overworld sky': timing([previous_cloud, formations[0]], time=30),
                   'Lava terrain': timing([lava_before, lava_after], time=30)}
        report = {'passed': True, 'checks': checks, 'gpu': driver.get_string(0x1F01).decode(),
                  'timings_960x540_before_after': timings,
                  'scope': 'Controlled production shader rendering and isolated GPU timers. Previews are synthetic, not Minecraft captures. No full-game FPS claim.'}
        (ROOT / 'validation-visual-polish.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    finally:
        baseline.close()
        for selected in programs:
            driver.delete_program(selected)
        for stage in stages:
            driver.delete_shader(stage)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    run()
