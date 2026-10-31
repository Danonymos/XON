"""Render a small building through XON's real shadow caster/receiver and grading."""
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
BODY = '''
in vec2 xonUV; out vec4 result;
void main() {
    vec4 v=gbufferProjectionInverse*vec4(xonUV*2.0-1.0,1,1);
    vec3 rd=normalize(mat3(gbufferModelViewInverse)*v.xyz);
    vec3 lo=vec3(1,-3,-15), hi=vec3(7,.2,-9);
    vec3 safe=mix(vec3(.00001),rd,greaterThan(abs(rd),vec3(.00001)));
    vec3 a=lo/safe,b=hi/safe;
    vec3 t0=min(a,b),t1=max(a,b);
    float enter=max(t0.x,max(t0.y,t0.z)),leave=min(t1.x,min(t1.y,t1.z));
    float ground=rd.y < -.00001 ? -3.0/rd.y : 10000.0;
    bool box=enter>0.0 && enter<leave && enter<ground;
    float t=box?enter:ground;
    if(t>150.0){result=vec4(.28,.43,.64,0);return;}
    vec3 p=rd*t,n=vec3(0,1,0),albedo=vec3(.24,.29,.19);
    if(box){
        vec3 q=(p-(lo+hi)*.5)/((hi-lo)*.5);
        vec3 w=abs(q);
        n=w.x>w.y && w.x>w.z?vec3(sign(q.x),0,0):
          (w.y>w.z?vec3(0,sign(q.y),0):vec3(0,0,sign(q.z)));
        albedo=vec3(.66,.64,.60);
    }
    float visibility;
    vec3 c=xonLighting(albedo,n,(gbufferModelView*vec4(p,1)).xyz,p,vec2(0,1),0,0,visibility);
    c=max(c*(XON_BRIGHTNESS*XON_BASE_EXPOSURE),vec3(0));
    c=c*(2.51*c+.03)/(c*(2.43*c+.59)+.14);
    c=xonApplyGrade(xonToDisplay(clamp(c,0,1)));
    result=vec4(c,box && n.z>.5 ? 1.0 : (box ? .75 : (visibility<.3 ? .5 : .25)));
}
'''


def look_at(eye,target):
    forward=np.asarray(target,dtype=float)-np.asarray(eye,dtype=float)
    forward/=np.linalg.norm(forward)
    side=np.cross(forward,[0,1,0]); side/=np.linalg.norm(side)
    up=np.cross(side,forward)
    matrix=np.eye(4); matrix[:3,:3]=[side,up,-forward]
    matrix[:3,3]=-matrix[:3,:3]@np.asarray(eye)
    return matrix


def run():
    driver=Driver(); renderer=Renderer(driver,640,360)
    stages=[]; programs=[]; checks=[]; images=[]
    archive=zipfile.ZipFile(ROOT.parent/'XON-Shader-v1.0.4-original.zip')

    def source(name,old):
        if not old:return expand(SHADERS/name)
        text=archive.read('shaders/'+name).decode('utf-8')
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',lambda m:source(m[1].lstrip('/'),True),text,flags=re.M)

    def program(vertex,fragment):
        pair=[]
        for text,stage in [(vertex,'.vsh'),(fragment,'.fsh')]:
            handle,warning=driver.compile(text,stage,'building scene')
            if warning:raise AssertionError(warning)
            stages.append(handle);pair.append(handle)
        handle,warning=driver.link(*pair,'building scene')
        if warning:raise AssertionError(warning)
        programs.append(handle);return handle

    def matrix(name,value):
        data=np.ascontiguousarray(value.T,dtype=np.float32)
        renderer.uniform_matrix(renderer.location(name),1,0,data.ctypes.data)

    f=driver.function
    matrix_mode=f('glMatrixMode',None,ct.c_uint)
    load_matrix=f('glLoadMatrixf',None,ct.c_void_p)
    enable=f('glEnable',None,ct.c_uint)
    clear=f('glClear',None,ct.c_uint)
    clear_depth=f('glClearDepth',None,ct.c_double)
    draw_buffer=f('glDrawBuffer',None,ct.c_uint)
    read_buffer=f('glReadBuffer',None,ct.c_uint)
    vertex3=f('glVertex3f',None,ct.c_float,ct.c_float,ct.c_float)
    gen=f('glGenQueries',None,ct.c_int,ct.POINTER(ct.c_uint))
    begin=f('glBeginQuery',None,ct.c_uint,ct.c_uint)
    end=f('glEndQuery',None,ct.c_uint)
    get=f('glGetQueryObjectui64v',None,ct.c_uint,ct.c_uint,ct.POINTER(ct.c_uint64))
    delete=f('glDeleteQueries',None,ct.c_int,ct.POINTER(ct.c_uint))
    def timing():
        def quad():
            renderer.begin(0x0007)
            for x,y in [(0,0),(1,0),(1,1),(0,1)]:
                renderer.tex_coord(x,y);renderer.vertex(x,y)
            renderer.end()
        for _ in range(12):quad()
        queries=(ct.c_uint*48)();gen(48,queries)
        for query in queries:
            begin(0x88BF,query)
            for _ in range(4):quad()
            end(0x88BF)
        samples=[]
        for query in queries:
            value=ct.c_uint64();get(query,0x8866,ct.byref(value));samples.append(value.value/4e6)
        delete(48,queries)
        return {'median_ms':float(np.median(samples)),'p95_ms':float(np.percentile(samples,95))}
    shadow_fbo=ct.c_uint()
    try:
        for unit,name in [(4,'xon-grade.png'),(5,'xon-noise.png')]:
            renderer.texture(unit,np.asarray(Image.open(SHADERS/'textures'/name).convert('RGBA'))/255)
        renderer.active_texture(0x84C5)
        for axis in [0x2802,0x2803]:renderer.tex_parameter(0x0DE1,axis,0x2901)
        renderer.active_texture(0x84C7)
        renderer.bind_texture(0x0DE1,renderer.textures[7])
        renderer.tex_image(0x0DE1,0,0x8CAC,1024,1024,0,0x1902,0x1406,None)
        renderer.tex_parameter(0x0DE1,0x884C,0x884E)
        renderer.tex_parameter(0x0DE1,0x884D,0x0203)
        renderer.gen_framebuffers(1,ct.byref(shadow_fbo))
        caster=program(variant_source(SHADERS/'shadow.vsh',{}),variant_source(SHADERS/'shadow.fsh',{}))
        view=look_at([0,0,0],[4,-1,-12])
        projection=np.eye(4);projection[0,0]=projection[1,1]=1/18
        projection[2,2]=-2/89.9;projection[2,3]=-90.1/89.9
        box=[(x,y,z) for x in [1,7] for y in [-3,.2] for z in [-15,-9]]
        faces=[(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
        scene_programs=[]
        for old in [True,False]:
            text='#version 330 compatibility\n#define XON_DIMENSION 0\n'
            text+='\n'.join(source('lib/'+name+'.glsl',old) for name in
                            ['settings','uniforms','math','atmosphere','clouds','shadows','lighting','grading'])
            if old:text+='\nconst float XON_BASE_EXPOSURE=1.0;\n'
            scene_programs.append(program(source('final.vsh',old),text+'\n'+BODY))
        metrics=[]
        for version,selected in zip(['original 1.0.4','revised 1.0.4'],scene_programs):
            row=[];values=[];night_vision_values=[]
            for label,sun in [('sun in front',[.5,.65,1]),('sun behind building',[-.5,.65,-1])]:
                sun=np.asarray(sun,dtype=float);sun/=np.linalg.norm(sun)
                target=np.array([4,-1,-12]);shadow_view=look_at(target+sun*30,target)
                renderer.bind_framebuffer(0x8D40,shadow_fbo)
                renderer.attach_texture(0x8D40,0x8D00,0x0DE1,renderer.textures[7],0)
                draw_buffer(0);read_buffer(0)
                if renderer.check_framebuffer(0x8D40)!=0x8CD5:raise AssertionError('Shadow FBO incomplete')
                renderer.setup(caster)
                for mode,value in [(0x1700,shadow_view),(0x1701,projection)]:
                    matrix_mode(mode);data=np.ascontiguousarray(value.T,dtype=np.float32);load_matrix(data.ctypes.data)
                renderer.viewport(0,0,1024,1024);enable(0x0B71);clear_depth(1);clear(0x00000100)
                renderer.begin(0x0007)
                for face in faces:
                    for index in face:vertex3(*box[index])
                renderer.end();renderer.disable(0x0B71)
                renderer.bind_framebuffer(0x8D40,renderer.framebuffer);draw_buffer(0x8CE0);read_buffer(0x8CE0)
                renderer.setup(selected)
                renderer.uniform1f(renderer.location('nightVision'),0.0)
                for name,value in [('gbufferModelView',view),('gbufferModelViewInverse',np.linalg.inv(view)),
                                   ('shadowModelView',shadow_view),('shadowModelViewInverse',np.linalg.inv(shadow_view)),
                                   ('shadowProjection',projection)]:matrix(name,value)
                light=view[:3,:3]@sun*100
                renderer.uniform3f(renderer.location('sunPosition'),*light)
                renderer.uniform3f(renderer.location('shadowLightPosition'),*light)
                px=renderer.draw(raw=True)
                front=px[...,3]>.99
                if front.sum()<100:raise AssertionError('Test building front not visible')
                mean=float((px[front,:3]@np.array([.2126,.7152,.0722])).mean())
                values.append(mean)
                gpu=timing()
                renderer.uniform1f(renderer.location('nightVision'),1.0)
                nv=renderer.draw(raw=True)
                night_vision_values.append(float((nv[front,:3]@np.array([.2126,.7152,.0722])).mean()))
                shadow_pixels=int(np.sum(np.abs(px[...,3]-.5)<.01))
                if shadow_pixels<100:raise AssertionError('Building did not cast a visible ground shadow')
                row.append(Image.fromarray((np.flipud(np.clip(px[...,:3],0,1))*255).astype(np.uint8)))
                metrics.append({'version':version,'sun':label,'front_display_luminance':mean,'cast_shadow_pixels':shadow_pixels,'synthetic_640x360_gpu':gpu})
            ratio=values[1]/values[0]
            if version=='revised 1.0.4' and not .35<ratio<.82:
                raise AssertionError(f'Building backlighting contrast/readability failed: {ratio}, {values}')
            nv_ratio=night_vision_values[1]/night_vision_values[0]
            if version=='revised 1.0.4' and not .45<nv_ratio<.85:
                raise AssertionError(f'Night vision flattened building contrast: {nv_ratio}')
            checks.append({'version':version,'night_vision_back_to_front_ratio':nv_ratio})
            if version=='revised 1.0.4':
                renderer.uniform1f(renderer.location('nightVision'),0.0)
                for time in [3.0,11.0,23.0]:
                    renderer.uniform1f(renderer.location('frameTimeCounter'),time)
                    cloud_frame=renderer.draw(raw=True)
                    mean=float((cloud_frame[front,:3]@np.array([.2126,.7152,.0722])).mean())
                    if not .35<mean<.60:raise AssertionError('Cloud highlights relit the back of the building')
                    checks.append({'case':'backlit building remains readable and shaded under moving cloud lighting',
                                   'time':time,'display_luminance':mean})
            images.append(row)
        checks+=metrics
        sheet=Image.new('RGB',(1280,760));draw=ImageDraw.Draw(sheet)
        for y,row in enumerate(images):
            for x,img in enumerate(row):
                sheet.paste(img,(x*640,y*380+20))
                draw.text((x*640+12,y*380+4),('Original' if y==0 else 'Revised')+' / '+('sun in front' if x==0 else 'sun behind'),fill='white')
        sheet.save(ROOT/'validation-building-comparison.png')
        # Binding check: world-space key direction is invariant to camera rotation.
        text='#version 330 compatibility\n'+source('lib/settings.glsl',False)+'\n'+source('lib/uniforms.glsl',False)+'\n'+source('lib/math.glsl',False)
        text+='\nout vec4 result;void main(){result=vec4(xonKeyDirection(),1);}'
        selected=program(source('final.vsh',False),text)
        expected=np.array([.4,.7,-.5]);expected/=np.linalg.norm(expected)
        for direction in [[0,0,-1],[1,.3,-1],[-1,-.2,.2]]:
            rotation=look_at([0,0,0],direction)
            renderer.setup(selected);matrix('gbufferModelViewInverse',np.linalg.inv(rotation))
            renderer.uniform3f(renderer.location('shadowLightPosition'),*(rotation[:3,:3]@expected*100))
            error=float(np.max(np.abs(renderer.draw(raw=True)[0,0,:3]-expected)))
            if error>.00001:raise AssertionError('Sunlight rotates with camera')
            checks.append({'case':'key follows Iris shadow light under camera rotation','maximum_error':error})
    finally:
        archive.close()
        if shadow_fbo.value:renderer.delete_framebuffers(1,ct.byref(shadow_fbo))
        for selected in programs:driver.delete_program(selected)
        for stage in stages:driver.delete_shader(stage)
        renderer.close();driver.close()
    report={'passed':True,'kind':'synthetic building, real shadow pass and XON grading; not Minecraft screenshots','checks':checks}
    (ROOT/'validation-scenes.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':run()
