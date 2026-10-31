"""GPU checks for 1.1 emitters, lantern cores, occluder edges and the existing bloom passes."""
import argparse
import ctypes as ct
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from validate import Driver, SHADERS, expand, variant_source
from voxel_gpu_checks import VoxelRenderer

ROOT = Path(__file__).resolve().parents[1]
VERTEX = '''#version 330 compatibility
out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels; out vec4 xonVertexColor;
out vec3 xonViewPosition,xonPlayerPosition,xonWorldNormal; flat out float xonMaterial;
uniform float testMaterial;
void main(){
 xonTexCoord=gl_MultiTexCoord0.xy;xonAtlasBounds=vec4(0);xonLightLevels=vec2(.8,0);xonVertexColor=vec4(1);
 xonViewPosition=vec3(0,0,-5);xonPlayerPosition=xonViewPosition;xonWorldNormal=vec3(0,1,0);
 xonMaterial=testMaterial;gl_Position=vec4(gl_Vertex.xy*2-1,0,1);
}'''


def run(client):
    baseline = zipfile.ZipFile(ROOT.parent / 'XON-Shader-v1.0.9.zip')
    assets = zipfile.ZipFile(client)
    driver = Driver()
    renderer = VoxelRenderer(driver)
    stages, programs, checks = [], [], []
    clear_color = driver.function('glClearColor', None, ct.c_float, ct.c_float, ct.c_float, ct.c_float)
    clear = driver.function('glClear', None, ct.c_uint)

    def saved(name):
        value = baseline.read('shaders/' + name).decode().replace('\r\n', '\n')
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$', lambda m: saved(m[1].lstrip('/')), value, flags=re.M)

    def options(text, flags):
        for name, value in flags.items():
            text = re.sub(rf'^(?://)?#define {name}(?:[^\n]*)?$',
                          '#undef ' + name if value is False else '#define ' + name + ' ' + str(value), text, flags=re.M)
        return text

    def program(parts):
        handles = []
        for text, kind in parts:
            if kind == '.csh':
                handle = driver.create_shader(0x91B9)
                data = text.encode(); pointer = ct.c_char_p(data); length = ct.c_int(len(data))
                driver.shader_source(handle, 1, ct.byref(pointer), ct.byref(length)); driver.compile_shader(handle)
                status = ct.c_int(); log = ct.create_string_buffer(65536)
                driver.get_shader(handle, 0x8B81, ct.byref(status)); driver.shader_log(handle, len(log), None, log)
                assert status.value and not log.value, log.value.decode()
            else:
                handle, warning = driver.compile(text, kind, 'emissive materials')
                assert not warning, warning
            stages.append(handle); handles.append(handle)
        selected = driver.create_program()
        for handle in handles: driver.attach_shader(selected, handle)
        driver.link_program(selected)
        status = ct.c_int(); log = ct.create_string_buffer(65536)
        driver.get_program(selected, 0x8B82, ct.byref(status)); driver.program_log(selected, len(log), None, log)
        assert status.value and not log.value, log.value.decode()
        programs.append(selected)
        return selected

    def fragment(body, libraries, old=False):
        prefix = '#version 330 compatibility\n#define XON_DIMENSION 0\n'
        prefix += '\n'.join(saved('lib/' + n + '.glsl') if old else expand(SHADERS / f'lib/{n}.glsl') for n in libraries)
        return program([(expand(SHADERS / 'final.vsh'), '.vsh'), (prefix + '\n' + body, '.fsh')])

    def resize(width, height):
        renderer.width, renderer.height = width, height
        renderer.active_texture(0x84C0); renderer.bind_texture(0x0DE1, renderer.textures[11])
        renderer.tex_image(0x0DE1, 0, 0x8814, width, height, 0, 0x1908, 0x1406, None)

    def draw(selected, material=0):
        renderer.setup(selected)
        renderer.uniform1f(renderer.location('testMaterial'), material)
        renderer.uniform1f(renderer.location('alphaTestRef'), .1)
        clear_color(0, 0, 0, 0); clear(0x4000)
        return renderer.draw(raw=True)

    def texture(name):
        data = assets.read('assets/minecraft/textures/block/' + name + '.png')
        return np.asarray(Image.open(io.BytesIO(data)).convert('RGBA'))[:16].astype(np.float32) / 255

    def sample_program(old=False, body=None):
        library = saved('lib/emissive_light.glsl') if old else expand(SHADERS / 'lib/emissive_light.glsl')
        prefix = '#version 330 compatibility\n' + expand(SHADERS / 'lib/settings.glsl')
        prefix += '\nuniform vec3 cameraPosition;uniform int frameCounter;\n#define XON_EMISSIVE_SAMPLING\n' + library
        body = body or 'uniform vec3 testPosition,testNormal;out vec4 result;void main(){result=vec4(xonEmissiveLight(testPosition,testNormal),1);}'
        return program([(expand(SHADERS / 'final.vsh'), '.vsh'), (prefix + '\n' + body, '.fsh')])

    try:
        resize(16, 16)
        selectors = []
        for line in (SHADERS / 'block.properties').read_text().splitlines():
            if line.startswith('block.'):
                key, value = line.split('=', 1)
                for token in value.split():
                    parts = token.split(':'); selectors.append((int(key.split('.')[1]), ':'.join(parts[:2]), parts[2:]))

        def material(name, state=None):
            result = [value for value, block, predicates in selectors if block == 'minecraft:' + name
                      and all((state or {}).get(k) in v.split(',') for k, v in (p.split('=') for p in predicates))]
            assert len(result) == 1, (name, state, result)
            return result[0]

        for name in ['amethyst_block', 'glow_lichen', 'sculk_vein', 'quartz_block', 'quartz_stairs',
                     'quartz_slab', 'smooth_quartz_stairs', 'smooth_quartz_slab', 'lantern', 'soul_lantern']:
            assets.read('assets/minecraft/blockstates/' + name + '.json')
            material(name)
        for name in ['cave_vines', 'cave_vines_plant']:
            states = json.loads(assets.read('assets/minecraft/blockstates/' + name + '.json'))['variants']
            for state in states:
                values = dict(p.split('=') for p in state.split(','))
                assert material(name, values) == (10024 if values['berries'] == 'true' else 10004)
        checks.append({'case': 'new selectors exist in client assets; berry states are disjoint; quartz and lantern mappings are unique'})

        captures = [program([(variant_source(SHADERS / directory / 'shadow.vsh', {}), '.vsh'),
                             (variant_source(SHADERS / directory / 'shadow.fsh', {}), '.fsh')])
                    for directory in ['', 'world-1', 'world1']]
        compute = program([(variant_source(SHADERS / 'shadowcomp.csh', {}), '.csh')])
        samples = [sample_program(True), sample_program()]
        for dimension, caster in zip([0, -1, 1], captures):
            for name, identifier, dominant in [('amethyst_block', 10, 2), ('glow_lichen', 13, 1),
                                                ('cave_vines', 14, 0), ('sculk_vein', 11, 2), ('quartz_stairs', 12, 2)]:
                value = material(name, {'berries': 'true'} if name == 'cave_vines' else None)
                renderer.reset(); voxel = renderer.capture(caster, value, stage=3 if value in [10006,10024,10020] else 1)
                assert renderer.read(0)[voxel] == identifier
                for _ in range(12): renderer.step(compute)
                color = renderer.sample(samples[1], (2.5,-.5,.5))
                assert int(np.argmax(color)) == dominant and float(np.min(color)) > .001, (name, color)
                checks.append({'case': 'real capture and propagated colored spill', 'block': name, 'dimension': dimension, 'rgb': color.tolist()})

        masks = fragment('''in vec2 xonUV;out vec4 result;uniform float testMaterial;
uniform sampler2D gtexture;void main(){vec4 c=texture(gtexture,xonUV);result=vec4(vec3(xonOreEmission(testMaterial,c.rgb)),c.a);}''', ['settings','materials'])
        for name, value in [('glow_lichen',10006),('cave_vines_lit',10024),('cave_vines_plant_lit',10024),('amethyst_block',10019),('sculk_vein',10020)]:
            tex = texture(name);renderer.texture(8,tex); emission=draw(masks,value)[...,0]
            assert np.max(emission[tex[...,3]>.5]) > .05
            if value == 10024:
                leaves=(tex[...,1]>tex[...,0]) & (tex[...,3]>.5)
                assert np.max(emission[leaves]) < .000001
            checks.append({'case':'actual texture luminous accents, with berry leaves protected','texture':name})

        flags={'XON_COLORED_EMISSIVE_LIGHTING':False,'XON_SHADOWS':False,'XON_CLOUD_STYLE':0,'XON_ANISOTROPIC':0}
        terrain = [program([(VERTEX,'.vsh'),(options(saved('gbuffers_terrain.fsh'),flags),'.fsh')]),
                   program([(VERTEX,'.vsh'),(variant_source(SHADERS/'gbuffers_terrain.fsh',flags),'.fsh')])]
        core = fragment('''in vec2 xonUV;out vec4 result;uniform float testMaterial;uniform sampler2D gtexture;
void main(){vec4 c=texture(gtexture,xonUV);result=vec4(vec3(xonLanternCoreMask(testMaterial,c.rgb)),c.a);}''',['settings','materials'])
        for name, value in [('lantern',10025),('soul_lantern',10026)]:
            tex=texture(name);renderer.texture(8,tex);mask=draw(core,value)[...,0]
            frame=(tex[...,2]>tex[...,0]) & (tex[...,1]<.4) & (tex[...,3]>.5)
            luminous=(mask>.8) & (tex[...,3]>.5)
            assert np.max(mask[frame]) == 0 and np.any(luminous)
            before=draw(terrain[0],10002)[...,:3];current=draw(terrain[1],value)[...,:3]
            ratio=float(current[luminous].mean()/before[luminous].mean())
            assert ratio>1.20 and current[frame].mean()<before[frame].mean()*.75,(name,ratio)
            checks.append({'case':'bright lantern core with normally shaded metal','lantern':name,'core_hdr_ratio':ratio})

        for name in ['torch', 'end_rod', 'sea_lantern']:
            tex=texture(name);renderer.texture(8,tex);light=draw(terrain[1],10002)[...,:3]
            assert np.max(light[tex[...,3]>.5])>1.1,name
            checks.append({'case':'ordinary indoor light retains an HDR core for the shared bloom','texture':name})

        renderer.reset();field=np.zeros_like(renderer.empty_light);field[...,3]=-1
        field[50,26,50]=[.64,.32,1,1]
        renderer.upload(1,field);renderer.upload(2,field);renderer.frame=1
        values=[]
        for selected in samples:
            line=[renderer.sample(selected,(1.5+x,1.5,2))[2] for x in np.linspace(-.02,.02,257)]
            values.append(np.array(line))
        jumps=[float(np.max(np.abs(np.diff(v)))) for v in values]
        assert jumps[0]>.5 and jumps[1]<.0001,jumps
        checks.append({'case':'partly occluded interpolation no longer amplifies tiny weights into a flash','maximum_step_before_current':jumps})

        moving = sample_program(body='''in vec2 xonUV;out vec4 result;void main(){vec3 p=vec3(2+xonUV.x,2,xonUV.y);
result=vec4(xonEmissiveLight(p-cameraPosition,vec3(0,1,0)),1);}''')
        renderer.reset();previous=np.array([0,1.62,4.]);reference=None;error=0.
        for index in range(120):
            camera=np.array([0 if index<20 else (index-20)*.031,1.62+(.04*np.sin(index*.2) if index>=20 else 0),4])
            renderer.voxels.fill(0);renderer.upload(0,renderer.voxels)
            for block,value in [((0,1,0),10023),((1,1,0),0),((2,1,0),0)]:renderer.capture(captures[0],value,block,camera)
            renderer.step(compute,camera,previous);renderer.setup(moving)
            renderer.uniform1i(renderer.location('frameCounter'),renderer.frame-1);renderer.uniform3f(renderer.location('cameraPosition'),*camera)
            image=renderer.draw(raw=True)
            if index==19:reference=image
            if index>=20:error=max(error,float(np.max(np.abs(image-reference))))
            previous=camera
        assert error<.00001,error
        checks.append({'case':'quartz/wood/receiving-block motion across voxel boundaries','frames':120,'maximum_error':error,
                       'limit':'controlled top-surface probe; not a reproduction of the exact live scene'})

        resize(128,128)
        old_extract=program([(expand(SHADERS/'final.vsh'),'.vsh'),(options(saved('composite.fsh'),{'XON_LIGHT_SHAFTS':False}),'.fsh')])
        extraction=program([(expand(SHADERS/'final.vsh'),'.vsh'),(variant_source(SHADERS/'composite.fsh',{'XON_LIGHT_SHAFTS':False}),'.fsh')])
        blurs=[program([(expand(SHADERS/'final.vsh'),'.vsh'),(saved('composite1.fsh') if old else expand(SHADERS/'composite1.fsh'),'.fsh')]) for old in [True,False]]
        scene=np.zeros((128,128,4),np.float32);scene[...,3]=1;scene[62:66,62:66,:3]=[5,3,1]
        renderer.texture(0,scene);energies=[]
        for extract,blur,gain in [(old_extract,blurs[0],.16),(extraction,blurs[1],.208)]:
            extracted=draw(extract);renderer.texture(3,extracted);soft=draw(blur)
            energies.append(float(np.sum(soft[...,:3]))*gain)
            assert np.min(soft)>=0 and np.max(soft[...,:3])<5
            assert np.sum(soft[58:62,58:62,:3])>0
        ratio=energies[1]/energies[0]
        assert 1.27<ratio<1.34,ratio
        checks.append({'case':'compact soft bloom in existing passes, about 30 percent more integrated energy','ratio':ratio})
        for level in [.5,.85,.9,1.,1.1,1.2,1.3]:
            renderer.texture(0,np.full((128,128,4),[level,level,level,1],np.float32));out=draw(extraction)[0,0,0]
            if level<=.9:assert out<.000001
            if level==1.1:assert abs(float(out)-.05)<.00001
        checks.append({'case':'soft-knee bloom avoids glowing dark frames and eases through the highlight threshold'})
        rng=np.random.default_rng(49);effects=rng.random((128,128,4),dtype=np.float32);renderer.texture(3,effects)
        alpha=[draw(selected)[...,3] for selected in blurs]
        assert np.max(np.abs(alpha[0]-alpha[1]))<.000001
        checks.append({'case':'shaft alpha retains its original filter while bloom gets softer weighting'})

        resize(960,540)
        gen=driver.function('glGenQueries',None,ct.c_int,ct.POINTER(ct.c_uint))
        begin=driver.function('glBeginQuery',None,ct.c_uint,ct.c_uint)
        end=driver.function('glEndQuery',None,ct.c_uint)
        elapsed=driver.function('glGetQueryObjectui64v',None,ct.c_uint,ct.c_uint,ct.POINTER(ct.c_uint64))
        delete=driver.function('glDeleteQueries',None,ct.c_int,ct.POINTER(ct.c_uint))
        timings={}
        for label,pair in [('colored surface sampler',samples),('bloom extraction',[old_extract,extraction]),('effect softening',blurs)]:
            handles=(ct.c_uint*64)();gen(64,handles)
            for selected in pair:
                renderer.setup(selected);renderer.uniform3f(renderer.location('testPosition'),-1.5,-.5,.5)
                renderer.uniform3f(renderer.location('testNormal'),0,1,0)
                warm=renderer.draw(raw=True)
                if label=='colored surface sampler':assert np.mean(warm[...,:3])>.005
            for index in range(32):
                for version in ([0,1] if index%2==0 else [1,0]):
                    renderer.setup(pair[version]);begin(0x88BF,handles[index*2+version])
                    for _ in range(4):
                        renderer.begin(0x0007)
                        for x,y in [(0,0),(1,0),(1,1),(0,1)]:renderer.tex_coord(x,y);renderer.vertex(x,y)
                        renderer.end()
                    end(0x88BF)
            values=[[],[]]
            for index in range(32):
                for version in [0,1]:
                    value=ct.c_uint64();elapsed(handles[index*2+version],0x8866,ct.byref(value))
                    values[version].append(value.value/4e6)
            delete(64,handles)
            timings[label]=[{'median_ms':float(np.median(v)),'p95_ms':float(np.percentile(v,95))} for v in values]
        report={'passed':True,'checks':checks,'gpu':driver.get_string(0x1F01).decode(),
                'microbenchmarks_960x540_before_current':timings,
                'scope':'actual source capture/compute/sampling, real local client texture inputs and production bloom shaders; not live Iris/FPS certification'}
        (ROOT/'validation-emissive-materials.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    finally:
        assets.close();baseline.close()
        for selected in programs:driver.delete_program(selected)
        for selected in stages:driver.delete_shader(selected)
        renderer.close();driver.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minecraft-jar',type=Path,default=Path.home()/'AppData/Roaming/ModrinthApp/meta/versions/26.3-0.20.1/26.3-0.20.1.jar')
    run(parser.parse_args().minecraft_jar)
