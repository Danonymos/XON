"""Real GPU checks for celestial occlusion, relief direction and exact foliage-work skips."""
import ctypes as ct
import json
from pathlib import Path

import numpy as np

from validate import Driver, SHADERS, expand, variant_source
from render_checks import Renderer

ROOT=Path(__file__).resolve().parents[1]
VERTEX='''#version 330 compatibility
out vec2 xonTexCoord; out vec4 xonAtlasBounds; out vec2 xonLightLevels; out vec4 xonVertexColor;
out vec3 xonViewPosition,xonPlayerPosition,xonWorldNormal; flat out float xonMaterial;
uniform float testMaterial, testSky;
void main(){
 xonTexCoord=gl_MultiTexCoord0.xy; xonAtlasBounds=vec4(0);xonLightLevels=vec2(0,testSky);xonVertexColor=vec4(1);
 xonViewPosition=vec3(0,-2,-4);xonPlayerPosition=xonViewPosition;xonWorldNormal=vec3(0,1,0);xonMaterial=testMaterial;
 gl_Position=vec4(gl_Vertex.xy*2-1,0,1);
}'''


def run():
    driver=Driver();renderer=Renderer(driver,960,540)
    shaders=[];programs=[];checks=[]

    def program(vertex,fragment):
        pair=[]
        for source,stage in [(vertex,'.vsh'),(fragment,'.fsh')]:
            handle,warning=driver.compile(source,stage,'lighting audit')
            assert not warning,warning
            shaders.append(handle);pair.append(handle)
        handle,warning=driver.link(*pair,'lighting audit')
        assert not warning,warning
        programs.append(handle);return handle

    def depth(value):
        data=np.full((512,512),value,dtype=np.float32)
        renderer.active_texture(0x84C7);renderer.bind_texture(0x0DE1,renderer.textures[7])
        renderer.tex_image(0x0DE1,0,0x8CAC,512,512,0,0x1902,0x1406,data.ctypes.data)
        renderer.tex_parameter(0x0DE1,0x884C,0x884E);renderer.tex_parameter(0x0DE1,0x884D,0x0203)

    def matrix(name,m):
        data=np.ascontiguousarray(m.T,dtype=np.float32)
        renderer.uniform_matrix(renderer.location(name),1,0,data.ctypes.data)

    def setup(selected,night=False,material=10001,sky=1):
        renderer.setup(selected)
        light=np.array([0,1,-2],dtype=float);light/=np.linalg.norm(light)
        renderer.uniform3f(renderer.location('sunPosition'),*(light*(-100 if night else 100)))
        renderer.uniform3f(renderer.location('shadowLightPosition'),*(light*100))
        renderer.uniform1f(renderer.location('testMaterial'),material)
        renderer.uniform1f(renderer.location('testSky'),sky)
        renderer.uniform1f(renderer.location('alphaTestRef'),.1)
        for name,m in [('gbufferModelView',np.eye(4)),('shadowModelView',np.eye(4)),
                       ('shadowModelViewInverse',np.eye(4)),('shadowProjection',np.diag([.02,.02,.02,1]))]:matrix(name,m)

    def timing(selected):
        renderer.setup(selected);renderer.uniform1f(renderer.location('testFoliage'),1)
        renderer.uniform3f(renderer.location('sunPosition'),30,80,20)
        matrix('shadowModelView',np.eye(4));matrix('shadowModelViewInverse',np.eye(4));matrix('shadowProjection',np.diag([.01,.01,.01,1]))
        renderer.draw(raw=True)
        f=driver.function;gen=f('glGenQueries',None,ct.c_int,ct.POINTER(ct.c_uint))
        begin=f('glBeginQuery',None,ct.c_uint,ct.c_uint);end=f('glEndQuery',None,ct.c_uint)
        get=f('glGetQueryObjectui64v',None,ct.c_uint,ct.c_uint,ct.POINTER(ct.c_uint64));delete=f('glDeleteQueries',None,ct.c_int,ct.POINTER(ct.c_uint))
        queries=(ct.c_uint*48)();gen(48,queries)
        for q in queries:
            begin(0x88BF,q)
            for _ in range(4):
                renderer.begin(0x0007)
                for x,y in [(0,0),(1,0),(1,1),(0,1)]:renderer.tex_coord(x,y);renderer.vertex(x,y)
                renderer.end()
            end(0x88BF)
        values=[]
        for q in queries:
            t=ct.c_uint64();get(q,0x8866,ct.byref(t));values.append(t.value/4e6)
        delete(48,queries)
        return {'median_ms':float(np.median(values)),'p95_ms':float(np.percentile(values,95))}

    try:
        renderer.texture(8,np.ones((2,2,4),dtype=np.float32))
        renderer.texture(6,np.full((2,2,4),[.2,.3,.4,1],dtype=np.float32))
        renderer.texture(9,np.full((2,2),.99,dtype=np.float32))
        for refract in [True,False]:
            options={'XON_WATER_DETAIL':0,'XON_CLOUD_STYLE':0,'XON_REFRACTION':refract}
            source=variant_source(SHADERS/'gbuffers_water.fsh',options)
            original=source.replace('mix(xonNightColor() * 2.6, xonSunlightColor(sunDir), day) * sunVisibility',
                                    'mix(xonNightColor() * 2.6, xonSunlightColor(sunDir) * sunVisibility, day)')
            pairs=[program(VERTEX,text) for text in [original,source,source.replace('color += glintColor * sunGlint;','')]]
            for night in [False,True]:
                depth(0)
                images=[]
                for selected in pairs:
                    setup(selected,night);images.append(renderer.draw(raw=True))
                current_error=float(np.max(np.abs(images[1]-images[2])))
                old_error=float(np.max(np.abs(images[0]-images[2])))
                assert current_error<.00001,(refract,night,current_error)
                if night:assert old_error>.05,old_error
                depth(1)
                lit=[]
                for selected in pairs[:2]:setup(selected,night);lit.append(renderer.draw(raw=True))
                assert np.max(np.abs(lit[0]-lit[1]))<.00001
                checks.append({'case':'water celestial glints respect occlusion','night':night,'refraction':refract,
                               'old_occluded_glint_error':old_error,'current_error':current_error})

        source=variant_source(SHADERS/'gbuffers_terrain.fsh',{'XON_SHADOWS':False,'XON_COLORED_EMISSIVE_LIGHTING':False,'XON_CLOUD_STYLE':0})
        source=source.replace('void main() {','vec3 reliefProbe=vec3(0);\nvoid main() {',1)
        source=source.replace('vec2 lightScreen =','reliefProbe=keyWorld;\nvec2 lightScreen =')
        source=source.replace('xonScene = vec4(max(color, vec3(0.0)), surface.a);','xonScene=vec4(reliefProbe,1);')
        old=source.replace('vec3 reliefLight = xonKeyDirection();','vec3 reliefLight = xonSunDirection();').replace('max(reliefLight.y, 0.35)','max(abs(reliefLight.y), 0.35)')
        errors=[]
        for text in [old,source]:
            selected=program(VERTEX,text);values=[]
            for night in [False,True]:setup(selected,night,0);values.append(renderer.draw(raw=True))
            errors.append(float(np.max(np.abs(values[0]-values[1]))))
        assert errors[0]>.5 and errors[1]<.00001,errors
        checks.append({'case':'micro-relief follows active moon/sun rather than the below-horizon sun',
                       'old_day_night_direction_error':errors[0],'current_error':errors[1]})

        prefix='#version 330 compatibility\n#define XON_DIMENSION 0\n'
        prefix+='\n'.join(expand(SHADERS/f'lib/{name}.glsl') for name in ['settings','uniforms','math','atmosphere','shadows','lighting'])
        body='''in vec2 xonUV;out vec4 result;uniform float testFoliage;
        void main(){float visibility;vec3 p=vec3((xonUV.x-.5)*64,-2,-4-xonUV.y*64);
        result=vec4(xonLighting(vec3(.25),vec3(0,1,0),p,p,vec2(0,1),0,testFoliage,visibility),visibility);}'''
        old=prefix.replace('if (foliage < 1.0) depthGradient =','depthGradient =').replace('if (foliage > 0.0 && openSky > 0.0)','if (foliage > 0.0)')
        pairs=[program(expand(SHADERS/'final.vsh'),text+'\n'+body) for text in [old,prefix]]
        for visible in [0,1]:
            depth(visible)
            for foliage in [0,.5,1]:
                pixels=[]
                for selected in pairs:
                    setup(selected,False,0);renderer.uniform1f(renderer.location('testFoliage'),foliage)
                    pixels.append(renderer.draw(raw=True))
                error=float(np.max(np.abs(pixels[0]-pixels[1])))
                assert error<.000001,error
                checks.append({'case':'foliage work skips preserve exact lighting','foliage':foliage,'visible':visible,'maximum_error':error})
        depth(0);timings=[timing(p) for p in pairs]
        report={'passed':True,'kind':'production GPU lighting audit; synthetic inputs, no in-game FPS claim',
                'checks':checks,'occluded_foliage_960x540_gpu_ms_before_current':timings}
        (ROOT/'validation-lighting-audit.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    finally:
        for p in programs:driver.delete_program(p)
        for p in shaders:driver.delete_shader(p)
        renderer.close();driver.close()


if __name__=='__main__':run()
