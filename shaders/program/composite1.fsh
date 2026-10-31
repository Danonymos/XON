#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
uniform sampler2D colortex5;
in vec2 xonUV;
layout(location = 0) out vec4 xonSoftEffects;

void main() {
    vec2 radius = 3.0 / vec2(viewWidth, viewHeight);
    vec4 center = texture(colortex5, xonUV);
    vec4 result = center;
    result += texture(colortex5, xonUV + vec2(-radius.x, -radius.y));
    result += texture(colortex5, xonUV + vec2(radius.x, -radius.y));
    result += texture(colortex5, xonUV + vec2(-radius.x, radius.y));
    result += texture(colortex5, xonUV + vec2(radius.x, radius.y));
    xonSoftEffects = vec4(result.rgb * 0.16 + center.rgb * 0.20, result.a * 0.20);
}
