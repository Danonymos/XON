#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"
#include "/lib/shadows.glsl"

uniform sampler2D colortex0;
uniform sampler2D depthtex0;
in vec2 xonUV;
layout(location = 0) out vec4 xonEffects;

vec3 xonBloomSample(vec2 uv) {
    vec3 color = texture(colortex0, xonSourceUV(uv)).rgb;
    float peak = max(color.r, max(color.g, color.b));
    float threshold = max(peak - 1.10, 0.0) / max(peak, 0.001);
    return min(color * threshold, vec3(4.0));
}

void main() {
    vec3 glow = vec3(0.0);
#ifdef XON_BLOOM
    vec2 pixel = 1.5 / vec2(viewWidth, viewHeight);
    glow += xonBloomSample(xonUV + vec2(-pixel.x, -pixel.y));
    glow += xonBloomSample(xonUV + vec2(pixel.x, -pixel.y));
    glow += xonBloomSample(xonUV + vec2(-pixel.x, pixel.y));
    glow += xonBloomSample(xonUV + vec2(pixel.x, pixel.y));
    glow *= 0.25;
#endif
    float shafts = 0.0;
#if XON_DIMENSION == 0
#ifdef XON_SHADOWS
#ifdef XON_LIGHT_SHAFTS
    float exposure = smoothstep(0.10, 0.65, float(eyeBrightnessSmooth.y) / 240.0);
    float daylight = xonDaylight() * (1.0 - rainStrength * 0.85);
    if (exposure > 0.001 && daylight > 0.001 && isEyeInWater == 0) {
        vec4 view = gbufferProjectionInverse * vec4(xonUV * 2.0 - 1.0, 1.0, 1.0);
        vec3 playerRay = mat3(gbufferModelViewInverse) * xonSafeNormalize(view.xyz);
        float sunDot = dot(playerRay, xonSunDirection());
        if (sunDot > 0.70) {
            float s2 = sunDot * sunDot;
            float s4 = s2 * s2;
            float s8 = s4 * s4;
            float phase = s8 * s8 * s8;
            float depth = texture(depthtex0, xonSourceUV(xonUV)).r;
            vec4 depthView = gbufferProjectionInverse * vec4(xonUV * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
            depthView.xyz /= max(abs(depthView.w), 0.000001);
            float rayLength = min(length(depthView.xyz), shadowDistance * 0.76);
            float jitter = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
            for (int stepIndex = 0; stepIndex < 4; ++stepIndex) {
                float distanceAlongRay = (float(stepIndex) + 0.35 + jitter * 0.65) * rayLength * 0.25;
                vec3 samplePosition = gbufferModelViewInverse[3].xyz + playerRay * distanceAlongRay;
                shafts += xonRayVisibility(samplePosition) * exp(-distanceAlongRay * 0.018);
            }
            shafts *= rayLength * 0.25 * 0.007 * phase * exposure * daylight;
            shafts = min(shafts, 0.22);
        }
    }
#endif
#endif
#endif
    xonEffects = vec4(glow, shafts);
}
