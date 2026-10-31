"""Render the production palette/LUT before and after the golden-hour rebalance."""
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from validate import Driver, SHADERS, expand
from render_checks import Renderer

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT.parent / 'XON-Shader-v1.0.7-before-golden.zip'
BODY = '''
in vec2 xonUV; out vec4 result;
uniform int testKind;
void main() {
    if (testKind == 5) { result=vec4(xonApplyGrade(vec3(xonUV.x)),1); return; }
    if (testKind == 6) { result=vec4(xonApplyGrade(vec3(.8,.3,.2)),1); return; }
    vec3 c;
    if (testKind == 4) {
        c=xonSky(normalize(vec3((xonUV.x-.5)*2.8,xonUV.y*.9+.03,1)));
    } else {
        int material=min(int(xonUV.x*5),4);
        vec3 albedo=material==0?vec3(.30):material==1?vec3(.08,.27,.045):
                    material==2?vec3(.32,.19,.09):material==3?vec3(.78,.77,.74):vec3(.44,.18,.065);
        vec3 n=xonKeyDirection();
        if(testKind==1)n=-n;
        float sky=testKind==2 || testKind==3?0.0:1.0;
        float block=testKind==3?.65:0.0;
        float textureDetail=.92+.08*cos(floor(xonUV.x*160)*1.7+floor(xonUV.y*96)*2.1);
        float visibility;
        c=xonLighting(albedo*textureDetail,n,vec3(0,0,-8),vec3(0,0,-8),vec2(block,sky),0,0,visibility);
    }
    c=max(c*(XON_BRIGHTNESS*XON_BASE_EXPOSURE),vec3(0));
    c=c*(2.51*c+.03)/(c*(2.43*c+.59)+.14);
    result=vec4(xonApplyGrade(xonToDisplay(clamp(c,0,1))),1);
}
'''


def run():
    driver=Driver(); renderer=Renderer(driver,480,160)
    archive=zipfile.ZipFile(BASELINE)
    shaders=[]; programs=[]; checks=[]; rows=[]

    def saved(name):
        text=archive.read('shaders/'+name).decode()
        return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',lambda m:saved(m[1].lstrip('/')),text,flags=re.M)

    def program(old):
        source='#version 330 compatibility\n#define XON_DIMENSION 0\n'
        for name in ['settings','uniforms','math','atmosphere','lighting','grading']:
            source+='\n'+(saved(f'lib/{name}.glsl') if old else expand(SHADERS/f'lib/{name}.glsl'))
        source=re.sub(r'^#define XON_SHADOWS\b', '#undef XON_SHADOWS', source,flags=re.M)
        if old:source+='\nconst float XON_BASE_EXPOSURE=1.0;\n'
        pair=[]
        for text,stage in [(expand(SHADERS/'final.vsh'),'.vsh'),(source+'\n'+BODY,'.fsh')]:
            handle,warning=driver.compile(text,stage,'golden palette')
            assert not warning,warning
            shaders.append(handle);pair.append(handle)
        handle,warning=driver.link(*pair,'golden palette')
        assert not warning,warning
        programs.append(handle);return handle

    def draw(index,kind,sun):
        renderer.texture(4,luts[index]);renderer.setup(selected[index])
        renderer.uniform1i(renderer.location('testKind'),kind)
        renderer.uniform3f(renderer.location('sunPosition'),*sun)
        renderer.uniform3f(renderer.location('skyColor'),.5,.7,1)
        renderer.uniform1f(renderer.location('far'),1024)
        return renderer.draw(raw=True)[...,:3]

    def sample(values):
        return np.mean(values[8:-8,8:88],axis=(0,1))

    def luma(c):return float(np.dot(c,[.2126,.7152,.0722]))

    try:
        selected=[program(True),program(False)]
        luts=[np.asarray(Image.open(io.BytesIO(archive.read('shaders/textures/xon-grade.png'))).convert('RGBA'))/255,
              np.asarray(Image.open(SHADERS/'textures/xon-grade.png').convert('RGBA'))/255]
        for label,sun in [('day',(30,90,20)),('golden hour',(-90,18,20)),('night',(-30,-90,-20))]:
            for kind,name in [(0,'lit surfaces'),(1,'shadow surfaces'),(2,'unlit caves'),(3,'torch caves'),(4,'sky')]:
                images=[draw(i,kind,sun) for i in range(2)]
                old,current=[sample(v) for v in images]
                ratio=luma(current)/luma(old)
                assert .72<ratio<1.05,(label,name,ratio)
                if label=='day' and kind==0:assert .90<ratio<.995,ratio
                if label=='day' and kind==1:assert current[1]/current[0]>old[1]/old[0],(old,current)
                if label=='golden hour' and kind==0:
                    assert current[0]>current[1]>current[2],current
                    assert current[1]/current[0]>old[1]/old[0],(old,current)
                if label=='night' and kind in [0,1]:
                    assert current[2]>current[1]>current[0] and ratio<.99,(current,ratio)
                    assert current[2]/current[1]>old[2]/old[1],(old,current)
                if kind==2:assert luma(current)>.14,current
                if kind==3:assert current[0]>current[1]>current[2],current
                checks.append({'case':label+' / '+name,'old_rgb':old.tolist(),'current_rgb':current.tolist(),'luminance_ratio':ratio})
                if kind in [0,1,4]:rows.append((label+' / '+name,images))
        ramp=draw(1,5,(30,90,20))
        assert np.min(np.diff(ramp[0],axis=0))>=-.00001
        spread=float(np.max(np.ptp(ramp,axis=-1)))
        assert spread<.025,spread
        assert np.max(np.abs(ramp[0,0]))<.005 and np.min(ramp[0,-1])>.99
        checks.append({'case':'neutral ramp stays monotonic with restrained split toning','maximum_channel_spread':spread})
        swatches=[sample(draw(i,6,(30,90,20))) for i in range(2)]
        chroma=[float(np.max(c)-np.min(c)) for c in swatches]
        assert chroma[1]>chroma[0]*1.02,(chroma,swatches)
        checks.append({'case':'modest saturation increase at unchanged saturation control','chroma_ratio':chroma[1]/chroma[0]})
        settings=(SHADERS/'lib/settings.glsl').read_text()
        assert '#define XON_BRIGHTNESS 1.05 ' in settings and '#define XON_SATURATION 0.70 ' in settings
        sheet=Image.new('RGB',(960,184*len(rows)));painter=ImageDraw.Draw(sheet)
        for row,(label,images) in enumerate(rows):
            for col,values in enumerate(images):
                sheet.paste(Image.fromarray(np.uint8(np.clip(values[::-1],0,1)*255)),(col*480,row*184+24))
                painter.text((col*480+8,row*184+6),('Before / ' if col==0 else 'Golden palette / ')+label,fill='white')
        sheet.save(ROOT/'validation-palette-comparison.png')
        report={'passed':True,'kind':'actual lighting/sky/LUT GPU renders; synthetic materials, not Minecraft screenshots',
                'base_linear_exposure':.90,'brightness_control_unchanged':1.05,'saturation_control_unchanged':.70,'checks':checks}
        (ROOT/'validation-palette.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
    finally:
        archive.close()
        for handle in programs:driver.delete_program(handle)
        for handle in shaders:driver.delete_shader(handle)
        renderer.close();driver.close()


if __name__=='__main__':run()
