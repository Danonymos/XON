#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"

uniform sampler2D colortex5;
uniform sampler2D depthtex0;
in vec2 xonUV;
layout(location = 0) out vec4 xonSoftEffects;

void main() {
    vec2 radius = 2.5 / vec2(viewWidth, viewHeight);
    vec4 center = texture(colortex5, xonUV);
    float centerDepth = texture(depthtex0, xonSourceUV(xonUV)).r;

    const vec2 offsets[8] = vec2[8](
        vec2(-1.5, -1.5), vec2( 0.0, -2.0), vec2( 1.5, -1.5),
        vec2(-2.0,  0.0),                   vec2( 2.0,  0.0),
        vec2(-1.5,  1.5), vec2( 0.0,  2.0), vec2( 1.5,  1.5)
    );

    vec3 bloomSum = center.rgb * 0.28;
    float bloomWeight = 0.28;
    float shaftSum = center.a * 0.25;
    float shaftWeight = 0.25;

    for (int i = 0; i < 8; ++i) {
        vec2 tapUV = xonUV + offsets[i] * radius;
        vec4 tapColor = texture(colortex5, tapUV);
        float tapDepth = texture(depthtex0, xonSourceUV(tapUV)).r;

        float depthDiff = abs(centerDepth - tapDepth);
        float dWeight = exp(-depthDiff * 450.0);

        bloomSum += tapColor.rgb * 0.09;
        bloomWeight += 0.09;

        shaftSum += tapColor.a * (0.09375 * dWeight);
        shaftWeight += 0.09375 * dWeight;
    }

    xonSoftEffects = vec4(bloomSum / bloomWeight, shaftSum / max(shaftWeight, 0.001));
}
