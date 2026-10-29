#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
uniform sampler2D colortex5;
in vec2 xonUV;
layout(location = 0) out vec4 xonSoftEffects;

void main() {
    vec2 radius = 3.0 / vec2(viewWidth, viewHeight);
    vec4 result = texture(colortex5, xonUV);
    result += texture(colortex5, xonUV + vec2(-radius.x, -radius.y));
    result += texture(colortex5, xonUV + vec2(radius.x, -radius.y));
    result += texture(colortex5, xonUV + vec2(-radius.x, radius.y));
    result += texture(colortex5, xonUV + vec2(radius.x, radius.y));
    xonSoftEffects = result * 0.20;
}
