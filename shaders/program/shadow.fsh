#include "/lib/uniforms.glsl"
uniform sampler2D gtexture;
in vec2 xonShadowUV;
layout(location = 0) out vec4 xonShadowColor;

void main() {
    if (texture(gtexture, xonShadowUV).a < alphaTestRef) discard;
    xonShadowColor = vec4(1.0);
}
