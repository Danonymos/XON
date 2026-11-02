"""Check stepped resource-pack height maps against a dense, independently traced surface."""
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
in vec2 xonUV; out vec4 result; uniform vec3 testView; uniform float testScale;
void main(){
 vec2 uv=xonUV*testScale+(1-testScale)*.5;
 vec2 hit=xonGetParallaxCoord(uv,uv,vec4(0,0,1,1),testView,0);
 result=vec4(hit,0,1);
}'''


def reference(height, uv, view):
    facing = -view[2] / np.linalg.norm(view)
    fade = np.clip((facing - .04) / .12, 0, 1)
    fade = fade * fade * (3 - 2 * fade)
    direction = np.asarray(view[:2]) * (.20 / -view[2]) * fade
    size = np.array([height.shape[1], height.shape[0]])

    def read(depth):
        position = (uv + (1 - depth[..., None]) * direction) % 1
        position = np.clip(position, .5 / size, 1 - .5 / size) * size - .5
        base = np.floor(position).astype(int)
        next_pos = np.minimum(base + 1, size - 1)
        weight = position - base
        a, b = height[base[..., 1], base[..., 0]], height[base[..., 1], next_pos[..., 0]]
        c, d = height[next_pos[..., 1], base[..., 0]], height[next_pos[..., 1], next_pos[..., 0]]
        return (a * (1 - weight[..., 0]) + b * weight[..., 0]) * (1 - weight[..., 1]) \
            + (c * (1 - weight[..., 0]) + d * weight[..., 0]) * weight[..., 1]

    upper = np.ones(uv.shape[:2])
    lower = np.zeros_like(upper)
    flat = read(upper) >= .999
    lower[flat] = 1.0
    searching = ~flat
    for step in range(1, 2049):
        depth = np.full_like(upper, 1 - step / 2048)
        hit = searching & (depth <= read(depth))
        upper[hit] = depth[hit] + 1 / 2048
        lower[hit] = depth[hit]
        searching[hit] = False
        if not searching.any():
            break
    assert not searching.any()
    for _ in range(16):
        middle = (upper + lower) * .5
        above = middle > read(middle)
        upper = np.where(above, middle, upper)
        lower = np.where(above, lower, middle)
    hit = (uv + (1 - ((upper + lower) * .5)[..., None]) * direction) % 1
    return np.clip(hit, .5 / size, 1 - .5 / size)


def run(resource_pack, baseline):
    driver = Driver()
    renderer = Renderer(driver, 96, 64)
    stages, programs, results = [], [], []
    with zipfile.ZipFile(baseline) as archive:
        old_library = archive.read('shaders/lib/pbr.glsl').decode().replace('\r\n', '\n')
    current = expand(SHADERS / 'lib/pbr.glsl')
    prefix = '#version 330 compatibility\n#define XON_DIMENSION 0\n'
    prefix += '\n'.join(expand(SHADERS / f'lib/{name}.glsl') for name in
                        ['settings', 'uniforms', 'math', 'atmosphere', 'lighting'])
    prefix = re.sub(r'^#define XON_SHADOWS$', '#undef XON_SHADOWS', prefix, flags=re.M)
    axis_x = (np.arange(renderer.width) + .5) / renderer.width
    axis_y = (np.arange(renderer.height) + .5) / renderer.height
    try:
        for library in [old_library, current]:
            pair = []
            for source, stage in [(expand(SHADERS / 'final.vsh'), '.vsh'), (prefix + library + BODY, '.fsh')]:
                handle, warning = driver.compile(source, stage, 'stepped height POM')
                assert not warning, warning
                stages.append(handle)
                pair.append(handle)
            program, warning = driver.link(*pair, 'stepped height POM')
            assert not warning, warning
            programs.append(program)
        with zipfile.ZipFile(resource_pack) as archive:
            for material in ['oak_log', 'spruce_log', 'oak_planks', 'stone_bricks', 'bricks', 'cobblestone']:
                data = np.asarray(Image.open(io.BytesIO(archive.read(
                    f'assets/minecraft/textures/block/{material}_n.png'))).convert('RGBA'), dtype=np.float32) / 255
                renderer.texture(10, data)
                renderer.tex_parameter(0x0DE1, 0x2801, 0x2600)
                renderer.tex_parameter(0x0DE1, 0x2800, 0x2600)
                for view, scale in [(v, s) for v in [(0, -.4, -1), (0, -2.5, -1), (.8, -4, -1)] for s in [.24, .96]]:
                    uv = np.stack(np.meshgrid(axis_x * scale + (1 - scale) * .5,
                                              axis_y * scale + (1 - scale) * .5), axis=-1)
                    expected = reference(data[..., 3], uv, view)
                    errors = []
                    for program in programs:
                        renderer.setup(program)
                        renderer.uniform1i(renderer.location('normals'), 10)
                        renderer.uniform3f(renderer.location('testView'), *view)
                        renderer.uniform1f(renderer.location('testScale'), scale)
                        actual = renderer.draw(raw=True)[..., :2]
                        # Compare periodic coordinates; adjacent repetitions describe the same tile.
                        delta = np.abs(actual - expected)
                        delta = np.minimum(delta, 1 - delta) * data.shape[1]
                        errors.append(np.max(delta, axis=-1))
                    renderer.active_texture(0x84C0 + 10)
                    renderer.bind_texture(0x0DE1, renderer.textures[10])
                    renderer.tex_parameter(0x0DE1, 0x2801, 0x2601)
                    renderer.tex_parameter(0x0DE1, 0x2800, 0x2601)
                    linear = renderer.draw(raw=True)[..., :2]
                    assert np.max(np.abs(linear - actual)) < 1e-6, 'POM depends on atlas sampler filtering'
                    renderer.tex_parameter(0x0DE1, 0x2801, 0x2600)
                    renderer.tex_parameter(0x0DE1, 0x2800, 0x2600)
                    results.append({'material': material, 'view': view, 'uv_span': scale,
                                    'mean_texel_error_before_after': [float(e.mean()) for e in errors],
                                    'p95_texel_error_after': float(np.percentile(errors[1], 95)),
                                    'fraction_over_one_texel_after': float(np.mean(errors[1] > 1))})
        before = float(np.mean([r['mean_texel_error_before_after'][0] for r in results]))
        after = float(np.mean([r['mean_texel_error_before_after'][1] for r in results]))
        assert after < before * .25, (before, after)
        assert max(r['p95_texel_error_after'] for r in results) < .25
        assert max(r['fraction_over_one_texel_after'] for r in results) < .01
        report = {'passed': True, 'checks': results, 'mean_texel_error_before_after': [before, after],
                  'baseline': str(baseline),
                  'scope': 'Native GPU UV intersections, nearest-bound real Primes height maps, dense CPU bilinear reference. No full-game FPS claim.'}
        (ROOT / 'validation-pom-quality.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'passed': True, 'cases': len(results), 'mean_texel_error_before_after': [before, after]}, indent=2))
    finally:
        for program in programs:
            driver.delete_program(program)
        for stage in stages:
            driver.delete_shader(stage)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resource-pack', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True, help='Preserved pre-polish XON build')
    args = parser.parse_args()
    run(args.resource_pack, args.baseline)
