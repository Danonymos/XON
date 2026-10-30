#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"
#include "/lib/shadows.glsl"

uniform sampler2D colortex0;
uniform sampler2D depthtex0;
uniform sampler2D depthtex1;
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
    float exposure = smoothstep(0.02, 0.55, float(eyeBrightnessSmooth.y) / 240.0);
    float daylight = xonDaylight() * (1.0 - rainStrength * 0.85);
    bool underwater = false;
#ifdef XON_UNDERWATER_RAYS
    underwater = isEyeInWater == 1;
#endif
    // Underwater skylight can reach zero only a few blocks below an open surface.
    // The shadow map, rather than the eye lightmap, decides whether sunlight reaches each sample.
    if (underwater) exposure = 1.0;
    if (exposure > 0.001 && daylight > 0.001 && XON_RAY_STRENGTH > 0.0 && (isEyeInWater == 0 || underwater)) {
        vec4 view = gbufferProjectionInverse * vec4(xonUV * 2.0 - 1.0, 1.0, 1.0);
        vec3 playerRay = mat3(gbufferModelViewInverse) * xonSafeNormalize(view.xyz);
        vec3 sun = underwater ? xonKeyDirection() : xonSunDirection();
        if (underwater) {
            // Use the same key light direction as the occluder shadow map.
            daylight *= smoothstep(0.0, 0.14, sun.y);
        }
        float sunDot = dot(playerRay, sun);
        if (underwater || sunDot > 0.55) {
            float posDot = max(sunDot, 0.0);
            float s2 = posDot * posDot;
            float s4 = s2 * s2;
            float s8 = s4 * s4;
            float sunAlign = xonSaturate(sunDot * 0.5 + 0.5);
            // Linear forward-isotropic phase without radial powers, ensuring diagonal beams follow shadow occluders rather than forming circular halos.
            float phase = underwater ? (0.65 + 0.35 * sunAlign)
                                     : (s8 * 0.08 + s8 * s8 * s8 * 0.92) * smoothstep(0.55, 0.75, posDot);
            vec2 srcUV = xonSourceUV(xonUV);
            float depth = texture(depthtex0, srcUV).r;
            if (underwater) {
                float solidDepth = texture(depthtex1, srcUV).r;
                if (solidDepth > depth) depth = solidDepth;
            }
            vec4 depthView = gbufferProjectionInverse * vec4(xonUV * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
            depthView.xyz /= max(abs(depthView.w), 0.000001);
            float maxRayDist = underwater ? min(shadowDistance * 0.75, 72.0) : shadowDistance * 0.76;
            float rayLength = min(length(depthView.xyz), maxRayDist);
            float jitter = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
            int sampleCount = underwater ? 12 : 4;
            float stepLength = underwater ? (maxRayDist / 12.0) : rayLength * 0.25;
            vec3 rayOrigin = gbufferModelViewInverse[3].xyz;
            mat4 shadowMVP = shadowProjection * shadowModelView;
            vec3 shadowOrigin = (shadowMVP * vec4(rayOrigin, 1.0)).xyz;
            vec3 shadowStep = mat3(shadowMVP) * playerRay;
            for (int stepIndex = 0; stepIndex < 12; ++stepIndex) {
                if (stepIndex >= sampleCount) break;
                float distanceAlongRay = (float(stepIndex) + 0.35 + jitter * 0.65) * stepLength;
                float weight = 1.0;
                if (underwater) {
                    float start = float(stepIndex) * stepLength;
                    float end = min(start + stepLength, rayLength);
                    if (end <= start) break;
                    distanceAlongRay = start + (end - start) * (0.5 + (jitter - 0.5) * 0.35);
                    float nearRamp = smoothstep(0.0, 4.5, distanceAlongRay);
                    weight = (end - start) * nearRamp * exp(-distanceAlongRay * 0.020);
                } else {
                    weight = exp(-distanceAlongRay * 0.018);
                }
                vec3 shadowClip = shadowOrigin + shadowStep * distanceAlongRay;
                float visibility = underwater ? xonWaterRayVisibilityClip(shadowClip) : xonRayVisibilityClip(shadowClip);
                shafts += visibility * weight;
            }
            shafts *= (underwater ? 0.0052 : stepLength * 0.007) * phase * exposure * daylight * XON_RAY_STRENGTH;
            shafts = min(shafts, 0.20);
        }
    }
#endif
#endif
#endif
    xonEffects = vec4(glow, shafts);
}
