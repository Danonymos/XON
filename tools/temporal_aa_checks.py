"""Exercise the production temporal resolve over real half-float GPU frame history."""
import ctypes as ct
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from validate import Driver, SHADERS, variant_source
from render_checks import Renderer, expected_color
from aa_gpu_checks import coverage

ROOT = Path(__file__).resolve().parents[1]
OPTIONS = {'XON_MOTION_BLUR': False, 'XON_BLOOM': False,
           'XON_LIGHT_SHAFTS': False, 'XON_COLOR_GRADE': False}
JITTER = np.array([[0, -1/6], [-.25, 1/6], [.25, -7/18], [-.375, -1/18],
                   [.125, 5/18], [-.125, -5/18], [.375, 1/18], [-.4375, 7/18]])
JITTER[:, 0] += .0546875


class TemporalRenderer(Renderer):
    def __init__(self, driver, width=256, height=192):
        super().__init__(driver, width, height)
        self.draw_buffers = driver.function('glDrawBuffers', None, ct.c_int, ct.POINTER(ct.c_uint))
        self.read_buffer = driver.function('glReadBuffer', None, ct.c_uint)
        self.texture(10, np.zeros((height, width, 4), dtype=np.float32))
        self.tex_image(0x0DE1, 0, 0x881A, width, height, 0, 0x1908, 0x1406, None)
        self.attach_texture(0x8D40, 0x8CE1, 0x0DE1, self.textures[10], 0)
        self.history = np.zeros((height, width, 4), dtype=np.float32)

    def setup(self, program):
        super().setup(program)
        identity = np.eye(4, dtype=np.float32)
        self.uniform_matrix(self.location('gbufferModelView'), 1, 0, identity.ctypes.data)
        self.uniform1i(self.location('colortex6'), 6)

    def resolve(self, program, scene, depth, frame, mask=None, camera=0, previous_camera=0,
                frame_time=1/120, history=None, matrix_scale=1):
        self.texture(0, scene)
        self.texture(1, np.zeros_like(depth) if mask is None else mask)
        self.texture(2, depth)
        self.tex_parameter(0x0DE1, 0x2801, 0x2600)
        self.tex_parameter(0x0DE1, 0x2800, 0x2600)
        self.texture(6, self.history if history is None else history)
        self.setup(program)
        self.uniform1i(self.location('frameCounter'), frame)
        self.uniform1f(self.location('frameTime'), frame_time)
        self.uniform3f(self.location('cameraPosition'), camera, 0, 0)
        self.uniform3f(self.location('previousCameraPosition'), previous_camera, 0, 0)
        if matrix_scale != 1:
            matrix = np.diag([matrix_scale, matrix_scale, 1, 1]).astype(np.float32)
            self.uniform_matrix(self.location('gbufferPreviousProjection'), 1, 0, matrix.ctypes.data)
        buffers = (ct.c_uint * 2)(0x8CE0, 0x8CE1)
        self.draw_buffers(2, buffers)
        self.read_buffer(0x8CE0)
        output = self.draw(raw=True)
        self.read_buffer(0x8CE1)
        self.read_pixels(0, 0, self.width, self.height, 0x1908, 0x1406, self.history.ctypes.data)
        assert np.isfinite(self.history).all(), 'Nonfinite history'
        self.read_buffer(0x8CE0)
        return output

    def present(self, program, scene, depth, mask=None):
        self.texture(0, scene)
        self.texture(1, np.zeros_like(depth) if mask is None else mask)
        self.texture(2, depth)
        self.setup(program)
        buffers = (ct.c_uint * 1)(0x8CE0)
        self.draw_buffers(1, buffers)
        return self.draw(raw=True)[..., :3]


def run():
    driver = Driver()
    renderer = TemporalRenderer(driver)
    stages, programs, checks, pictures = [], [], [], []
    archive = zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.5.zip')

    def saved(name):
        text = archive.read('shaders/' + name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                      lambda m: saved(m[1].lstrip('/')), text, flags=re.M)

    def compile_program(name, options=None, baseline=False):
        pair = []
        for suffix in ['vsh', 'fsh']:
            if baseline:
                source = saved(name + '.' + suffix)
                for option, value in OPTIONS.items():
                    source = re.sub(rf'^(?://)?#define {option}(?:[^\n]*)$',
                                    f'#undef {option}' if value is False else f'#define {option} {value}', source, flags=re.M)
            else:
                source = variant_source(SHADERS / (name + '.' + suffix), dict(OPTIONS, **(options or {})))
            shader, warning = driver.compile(source, '.' + suffix, name)
            assert not warning, warning
            stages.append(shader)
            pair.append(shader)
        program, warning = driver.link(*pair, name)
        assert not warning, warning
        programs.append(program)
        return program

    try:
        temporal = compile_program('composite2')
        final = compile_program('final')
        baseline = compile_program('final', baseline=True)
        h, w = renderer.height, renderer.width
        yy, xx = np.indices((h, w), dtype=float)
        dark, light = np.array([.025, .03, .045]), np.array([.9, .8, .65])
        scene = np.ones((h, w, 4), dtype=np.float32)
        errors = []
        foreground_depth, background_depth = .98, .997
        foreground_z = .05 * 1024 / (1024 - foreground_depth * (1024 - .05))
        for speed, phase in [(0, .17), (0, .63), (.125, 0), (.35, 0), (1.3, 0)]:
            moving = speed > 0
            for slope in [.15, .35, .61, 1, 1.9, -.4]:
                renderer.history[:] = 0
                values, output_frames = [], []
                for i in range(40):
                    frame = 120 + i
                    shift = i * speed + phase
                    position = w*.5 - slope*h*.5 - shift
                    jitter = JITTER[frame % 8]
                    edge = xx + .5 < slope*(yy+.5) + position + jitter[0] - slope*jitter[1]
                    scene[..., :3] = np.where(edge[..., None], light, dark)
                    depth = np.where(edge, foreground_depth, background_depth).astype(np.float32)
                    camera = shift * 2 * foreground_z / w
                    previous = (shift - speed) * 2 * foreground_z / w
                    resolved = renderer.resolve(temporal, scene, depth, frame, camera=camera, previous_camera=previous)
                    output = renderer.present(final, resolved, depth)
                    bare_edge = xx+.5 < slope*(yy+.5) + position
                    scene[..., :3] = np.where(bare_edge[..., None], light, dark)
                    bare_depth = np.where(bare_edge, foreground_depth, background_depth).astype(np.float32)
                    old = renderer.present(baseline, scene, bare_depth)
                    ideal = expected_color(dark + coverage(xx, yy, slope, position)[..., None]*(light-dark), base_exposure=.83)
                    region = (np.abs(xx+.5-slope*(yy+.5)-position) < 2) & (xx>4) & (xx<w-4) & (yy>4) & (yy<h-4)
                    if i >= 16:
                        values.append([float(np.mean((old[region]-ideal[region])**2)),
                                       float(np.mean((output[region]-ideal[region])**2))])
                        output_frames.append(output)
                    if speed == 0 and phase == .17 and slope == .61 and i == 39:
                        pictures.extend([old, output, ideal])
                mean = np.mean(values, axis=0)
                errors.append(mean)
                checks.append({'case': 'moving silhouette' if moving else 'stationary silhouette',
                               'pixels_per_frame':speed,'phase':phase,
                               'slope': slope, 'v1_5_mse': mean[0], 'temporal_mse': mean[1]})
                if not moving:
                    checks[-1]['mean_frame_standard_deviation'] = float(np.mean(np.std(output_frames, axis=0)))
        aggregate = np.mean(errors, axis=0)
        assert aggregate[1] < aggregate[0] * .80, ('Temporal edge coverage did not improve enough', aggregate.tolist())

        scene[..., :3] = np.where(((xx//8+yy//8)%2==0)[...,None],[.18,.5,1.2],[.8,.2,.1])
        depth = np.full((h, w), .98, dtype=np.float32)
        mask = np.ones((h, w), dtype=np.float32)
        poisoned = np.roll(scene,1,axis=1)
        poisoned[...,3] = foreground_z
        def stamp(history, frame=119, width=w, height=h):
            history[0,0] = [width%1024, height%1024, width//1024+height//1024*32, -(frame%1024+1)]
        stamp(poisoned)
        result = renderer.resolve(temporal, scene, depth, 120, mask=mask, history=poisoned)
        assert np.max(np.abs(result[...,:3]-scene[...,:3])) < .00001
        assert np.all(renderer.history[1:,:,3] < 0), 'Hand must not enter reusable history'
        checks.append({'case': 'first-person hand rejects poisoned history and remains unjittered', 'passed': True})
        mask[:] = .25
        reactive = renderer.resolve(temporal, scene, depth, 120, mask=mask, history=poisoned)
        static = renderer.resolve(temporal, scene, depth, 120, history=poisoned)
        reactive_error = float(np.mean(np.abs(reactive[3:-3,3:-3,:3]-scene[3:-3,3:-3,:3])))
        static_error = float(np.mean(np.abs(static[3:-3,3:-3,:3]-scene[3:-3,3:-3,:3])))
        assert static_error > .001 and reactive_error < static_error*.5
        checks.append({'case':'animated-surface mask reduces stale-history influence',
                       'static_error':static_error,'reactive_error':reactive_error})
        scene[..., :3] = [.18,.5,1.2]
        poisoned[:] = [30,0,15,100]
        stamp(poisoned)
        for name, kwargs in [
            ('first frame', {'frame':0}), ('teleport', {'camera':100}),
            ('long frame', {'frame_time':.25}), ('invalid frame', {'frame_time':0}),
            ('FOV cut', {'matrix_scale':1.5}), ('missed frame', {'frame':122})]:
            result = renderer.resolve(temporal, scene, depth, history=poisoned, **dict({'frame':120}, **kwargs))
            error = float(np.max(np.abs(result[...,:3]-scene[...,:3])))
            assert error < .00001, (name,error)
            checks.append({'case': name+' resets history', 'maximum_hdr_error':error})
        for name, width, height in [('resize',w+1,h), ('height resize',w,h+1), ('large resize',w+1024,h)]:
            invalid = poisoned.copy()
            stamp(invalid, width=width, height=height)
            result = renderer.resolve(temporal, scene, depth, 120, history=invalid)
            assert np.max(np.abs(result[...,:3]-scene[...,:3])) < .00001
            checks.append({'case':name+' resets history','passed':True})
        result = renderer.resolve(temporal, scene, depth, 120, history=poisoned)
        assert np.max(np.abs(result[...,:3]-scene[...,:3])) < .00001
        checks.append({'case':'newly revealed depth rejects poisoned history','passed':True})
        # Valid-depth, stale colored history must collapse to the current constant neighborhood.
        poisoned[...,3] = foreground_z
        stamp(poisoned)
        result = renderer.resolve(temporal, scene, depth, 120, history=poisoned)
        assert np.max(np.abs(result[...,:3]-scene[...,:3])) < .00001
        checks.append({'case':'neighborhood clamp rejects stale color at matching depth','passed':True})

        for mode, scale in [(0,1), (1,.85), (2,.75)]:
            program = temporal if mode == 0 else compile_program('composite2', {'XON_RENDER_MODE':mode})
            present = final if mode == 0 else compile_program('final', {'XON_RENDER_MODE':mode})
            scene[:] = [20,0,20,1]
            scene[:int(np.ceil(h*scale)),:int(np.ceil(w*scale))] = [.18,.5,1.2,1]
            renderer.history[:] = 0
            for frame in range(120,136):
                resolved = renderer.resolve(program, scene, depth, frame)
            output = renderer.present(present, resolved, depth)
            error = float(np.max(np.abs(output[3:-3,3:-3]-expected_color([.18,.5,1.2],base_exposure=.83))))
            assert error < .003, (mode,error)
            checks.append({'case':'native/Boost constant HDR, palette and inactive-region isolation',
                           'mode':mode,'maximum_display_error':error})

        report = {'passed':True,'scope':'Synthetic repeated-frame production GLSL, not live Minecraft or cross-vendor validation',
                  'driver':driver.get_string(0x1F01).decode(),'checks':checks,
                  'mean_edge_mse':{'v1_5':aggregate[0],'temporal':aggregate[1]},
                  'mean_edge_error_reduction_percent':float((1-aggregate[1]/aggregate[0])*100)}
        (ROOT/'validation-temporal-aa.json').write_text(json.dumps(report,indent=2)+'\n')
        canvas=Image.new('RGB',(w*3,h+24))
        draw=ImageDraw.Draw(canvas)
        for i,(picture,label) in enumerate(zip(pictures,['v1.5 spatial','v1.6 temporal','Area coverage reference'])):
            canvas.paste(Image.fromarray(np.uint8(np.clip(picture,0,1)*255)),(i*w,24))
            draw.text((i*w+5,5),label,fill='white')
        canvas.save(ROOT/'validation-temporal-aa.png')
        print(json.dumps(report,indent=2))
    finally:
        archive.close()
        for program in programs:driver.delete_program(program)
        for shader in stages:driver.delete_shader(shader)
        renderer.close()
        driver.close()


if __name__ == '__main__':
    run()
