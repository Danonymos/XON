"""Build a separate component-view pack without changing production shader files."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

from PIL import Image, ImageDraw, ImageFont
import numpy as np

from render_checks import Renderer
from validate import Driver

ROOT = Path(__file__).resolve().parents[1]
LABELS = ['1  MINECRAFT LIGHT', '2  COLORED LIGHT', '3  REPLACEMENT WEIGHT',
          '4  MINECRAFT AO', '5  VOXEL CONTACT AO', '6  SHADED SCENE']

DIAGNOSTIC_MAIN = '''
uniform sampler2D colortex1;
uniform sampler2D colortex2;
uniform sampler2D xonDiagnosticLabels;
/*
const int colortex1Format = RGBA16F;
const int colortex2Format = RGBA16F;
const bool colortex1Clear = true;
const bool colortex2Clear = true;
const vec4 colortex1ClearColor = vec4(0.0, 0.0, 1.0, 1.0);
const vec4 colortex2ClearColor = vec4(0.0, 0.0, 0.0, 0.0);
*/
void main() {
    vec2 grid = xonUV * vec2(3.0, 2.0);
    ivec2 tile = ivec2(floor(grid));
    int pane = (1 - tile.y) * 3 + tile.x;
    vec2 local = fract(grid);
    vec3 color = vec3(0.025);
    // Letterbox each view so the six copies keep the original camera aspect.
    vec2 uv = vec2(local.x, (local.y - 0.5) * 1.5 + 0.5);
    if (uv.y >= 0.0 && uv.y <= 1.0) {
        vec2 sourceUV = xonSourceUV(uv);
        vec4 values = texture(colortex1, sourceUV);
        if (pane == 0) color = vec3(values.r);
        else if (pane == 1) {
            vec3 pool = max(texture(colortex2, sourceUV).rgb, vec3(0.0));
            color = xonToDisplay(pool / (1.0 + pool));
        } else if (pane == 2) color = vec3(values.g);
        else if (pane == 3) color = vec3(values.b);
        else if (pane == 4) color = vec3(values.a);
        else {
            color = texture(colortex0, xonFinalSourceUV(uv)).rgb;
#if defined XON_BLOOM || (defined XON_LIGHT_SHAFTS && defined XON_SHADOWS && XON_DIMENSION == 0)
            vec4 effects = texture(colortex5, uv);
#ifdef XON_BLOOM
            color += effects.rgb * (0.208 * XON_BLOOM_STRENGTH);
#endif
#if defined XON_LIGHT_SHAFTS && defined XON_SHADOWS && XON_DIMENSION == 0
            vec3 rayColor = isEyeInWater == 1 ? vec3(0.20, 0.40, 0.65)
                : mix(xonSunlightColor(), vec3(1.32, 1.08, 0.78), 0.20 * XON_WARMTH);
            color += effects.a * rayColor;
#endif
#endif
            color = max(color * (XON_BRIGHTNESS * XON_BASE_EXPOSURE), vec3(0.0));
            color = color * (2.51 * color + 0.03) / (color * (2.43 * color + 0.59) + 0.14);
            color = xonApplyGrade(xonToDisplay(clamp(color, 0.0, 1.0)));
        }
    }
    if (local.y > 0.90 && local.y < 0.98) {
        vec2 labelUV = vec2(local.x, (float(pane) + (0.98 - local.y) / 0.08) / 6.0);
        vec4 label = texture(xonDiagnosticLabels, labelUV);
        color = mix(color, label.rgb, label.a);
    }
    if (local.x < 0.004 || local.y < 0.004) color = vec3(0.18);
    xonOutput = vec4(clamp(color, 0.0, 1.0), 1.0);
}
'''


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected exactly one instrumentation site: {old[:70]}')
    return text.replace(old, new, 1)


def instrument(files):
    name = 'shaders/program/geometry.fsh'
    text = files[name].decode().replace('\r', '')
    text = replace_once(text, 'layout(location = 1) out float xonHandMask;',
                        'layout(location = 1) out float xonHandMask;\n'
                        'layout(location = 2) out vec4 xonDiagnosticValues;\n'
                        'layout(location = 3) out vec4 xonDiagnosticPool;')
    text = replace_once(text, '    xonHandMask = 0.0;',
                        '    xonHandMask = 0.0;\n'
                        '    xonDiagnosticValues = vec4(xonLightLevels.x, 0.0, 1.0, 1.0);\n'
                        '    xonDiagnosticPool = vec4(0.0);')
    site = '    if (emission < 0.5) {\n        float indoorContact'
    text = replace_once(text, site, '    xonDiagnosticValues.b = rawAO;\n' + site)
    site = '        float lampLuma = max(xonLuminance(lampLight.rgb), 0.0);'
    text = replace_once(text, site, site + '\n'
                        '        xonDiagnosticValues.g = lampCoverage;\n'
                        '        xonDiagnosticPool = vec4(lampLight.rgb, 1.0);')
    site = '            color *= mix(1.0, xonIndoorOcclusion(xonPlayerPosition, lightSamplingNormal), indoorOcclusion);'
    text = replace_once(text, site,
                        '            xonDiagnosticValues.a = mix(1.0, xonIndoorOcclusion(xonPlayerPosition, lightSamplingNormal), indoorOcclusion);\n'
                        '            color *= xonDiagnosticValues.a;')
    files[name] = text.encode()
    for name in list(files):
        if name.endswith('/gbuffers_terrain.fsh'):
            text = files[name].decode().replace('RENDERTARGETS: 0,4', 'RENDERTARGETS: 0,4,1,2')
            files[name] = text.encode()
    name = 'shaders/program/final.fsh'
    text = files[name].decode().replace('\r', '')
    text = replace_once(text, text[text.index('void main() {'):], DIAGNOSTIC_MAIN)
    files[name] = text.encode()
    name = 'shaders/shaders.properties'
    files[name] += b'\ncustomTexture.xonDiagnosticLabels=textures/xon-diagnostic-labels.png\n'
    image = Image.new('RGBA', (768, 6 * 48))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/consolab.ttf', 29)
    for row, label in enumerate(LABELS):
        draw.text((20, row * 48 + 4), label, fill='white', font=font)
    output = io.BytesIO()
    image.save(output, format='PNG')
    files['shaders/textures/xon-diagnostic-labels.png'] = output.getvalue()
    files['DIAGNOSTIC.md'] = ('# Lighting diagnostic — not a release\n\n'
        'Select this pack manually. Keep the camera in the pillar room and take the same view '
        'with the quartz bases present and removed. Wait two seconds after editing blocks.\n\n'
        + '\n'.join(LABELS) + '\n\n'
        'Views 1, 3, 4, 5 show raw scalar values: white = 1, black = 0. '
        'View 2 displays only sampled colored light, without textures or native lighting. '
        'View 6 retains normal surface shading. These buffers are diagnostic overhead, '
        'not a performance measurement. Switch back to the normal pack afterward.\n').encode()


def validate(files):
    clear_colors = 0
    for name, data in files.items():
        if not name.endswith(('.glsl', '.fsh', '.vsh', '.csh')):
            continue
        for directive, arguments in re.findall(r'const\s+vec4\s+(\w+ClearColor)\s*=\s*vec4\(([^)]*)\)', data.decode()):
            # Iris parses these settings itself, including declarations in comments.
            components = arguments.split(',')
            if len(components) != 4:
                raise ValueError(f'Iris requires four explicit components: {name}: {directive}')
            for component in components:
                float(component.strip())
            clear_colors += 1
    driver = Driver()
    compiled, programs, cache = [], [], {}

    def expand(name):
        if name not in cache:
            text = files[name].decode().replace('\r', '')
            cache[name] = re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                lambda match: expand('shaders/' + match[1].lstrip('/')), text, flags=re.M)
        return cache[name]

    try:
        pairs = 0
        panel_error = None
        for folder in ['', 'world-1/', 'world1/']:
            for pbr in [False, True]:
                for program in ['gbuffers_terrain', 'final']:
                    pair = []
                    for stage in ['vsh', 'fsh']:
                        text = expand('shaders/' + folder + program + '.' + stage)
                        if pbr:
                            text = text.replace('//#define XON_ADVANCED_MATERIALS', '#define XON_ADVANCED_MATERIALS')
                        handle, warning = driver.compile(text, '.' + stage, 'lighting diagnostic')
                        compiled.append(handle)
                        if warning:
                            raise RuntimeError(warning)
                        pair.append(handle)
                    handle, warning = driver.link(*pair, 'lighting diagnostic')
                    programs.append(handle)
                    if warning:
                        raise RuntimeError(warning)
                    if not folder and not pbr and program == 'final':
                        panel_error = check_panels(driver, handle, files)
                    pairs += 1
        return {'graphics_pairs': pairs, 'warnings': 0,
                'iris_clear_color_directives_checked': clear_colors,
                'component_panel_maximum_error': panel_error,
                'driver': driver.get_string(0x1F01).decode(), 'live_Iris_check': 'pending'}
    finally:
        for handle in programs:
            driver.delete_program(handle)
        for handle in compiled:
            driver.delete_shader(handle)
        driver.close()


def check_panels(driver, program, files):
    renderer = Renderer(driver, 768, 432)
    try:
        def texture(unit, value):
            renderer.texture(unit, np.full((8, 8, 4), value, dtype=np.float32))

        texture(0, [.12, .25, .30, 1])
        texture(1, [0, 0, 0, 0])
        texture(3, [0, 0, 0, 0])
        texture(6, [.20, .65, .45, .80])
        texture(8, [.04, .16, .36, 1])
        renderer.texture(4, np.asarray(Image.open(io.BytesIO(files['shaders/textures/xon-grade.png']))) / 255)
        renderer.texture(10, np.asarray(Image.open(io.BytesIO(files['shaders/textures/xon-diagnostic-labels.png']))) / 255)
        renderer.setup(program)
        for name, unit in [('colortex1', 6), ('colortex2', 8), ('xonDiagnosticLabels', 10)]:
            renderer.uniform1i(renderer.location(name), unit)
        pixels = renderer.draw()
        expected_pool = np.power(np.array([.04, .16, .36]) / np.array([1.04, 1.16, 1.36]), 1 / 2.2)
        expected = [np.full(3, .20), expected_pool, np.full(3, .65), np.full(3, .45), np.full(3, .80)]
        error = 0.0
        for pane, target in enumerate(expected):
            x = int((pane % 3 + .5) * renderer.width / 3)
            y = int((1 - pane // 3 + .5) * renderer.height / 2)
            error = max(error, float(np.max(np.abs(pixels[y, x, :3] - target))))
        if error > .00001:
            raise AssertionError(f'Diagnostic component routing error: {error}')
        return error
    finally:
        renderer.close()


def build(source, output):
    with zipfile.ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    original = files.copy()
    instrument(files)
    report = validate(files)
    report['modified_entries'] = [name for name, data in files.items() if original.get(name) != data]
    report['input_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    report['input'] = str(source)
    report['production_sources_modified'] = False
    files['DIAGNOSTIC-VALIDATION.json'] = json.dumps(report, indent=2).encode()
    temporary = output.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    temporary.replace(output)
    report['output'] = str(output)
    report['output_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT.parent / 'XON-Shader-v1.8.4.zip')
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'XON-Lighting-Diagnostic.zip')
    args = parser.parse_args()
    build(args.source, args.output)
