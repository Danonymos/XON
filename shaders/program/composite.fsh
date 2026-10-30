#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"
#include "/lib/shadows.glsl"

uniform sampler2D colortex0;
uniform sampler2D depthtex0;
#if XON_DIMENSION == 0 && defined XON_SHADOWS && defined XON_LIGHT_SHAFTS && defined XON_UNDERWATER_RAYS
uniform sampler2D noisetex;
#endif
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
        vec3 sun = xonSunDirection();
        vec3 shaftDirection = sun;
        if (underwater) {
            // Flat-interface refraction bends the visible sunlight toward the water normal.
            shaftDirection.xz *= 0.75019;
            shaftDirection.y = sqrt(max(1.0 - dot(shaftDirection.xz, shaftDirection.xz), 0.0));
            daylight *= smoothstep(0.0, 0.16, sun.y);
        }
        float sunDot = dot(playerRay, shaftDirection);
        if (underwater || sunDot > 0.55) {
            sunDot = max(sunDot, 0.0);
            float s2 = sunDot * sunDot;
            float s4 = s2 * s2;
            float s8 = s4 * s4;
            float phase = underwater ? (0.35 + 0.65 * s4)
                                     : (s8 * 0.08 + s8 * s8 * s8 * 0.92) * smoothstep(0.55, 0.75, sunDot);
            float depth = texture(depthtex0, xonSourceUV(xonUV)).r;
            vec4 depthView = gbufferProjectionInverse * vec4(xonUV * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
            depthView.xyz /= max(abs(depthView.w), 0.000001);
            float rayLength = min(length(depthView.xyz), shadowDistance * 0.76);
            if (underwater) rayLength = min(rayLength, 40.0);
            float jitter = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
            int sampleCount = underwater ? 6 : 4;
            float stepLength = rayLength / float(sampleCount);
            for (int stepIndex = 0; stepIndex < 6; ++stepIndex) {
                if (stepIndex >= sampleCount) break;
                float sampleOffset = underwater ? 0.5 + (jitter - 0.5) * 0.18 : 0.35 + jitter * 0.65;
                float distanceAlongRay = (float(stepIndex) + sampleOffset) * stepLength;
                vec3 samplePosition = gbufferModelViewInverse[3].xyz + playerRay * distanceAlongRay;
                float mediumLight = 1.0;
#ifdef XON_UNDERWATER_RAYS
                if (underwater) {
                    vec3 worldSample = samplePosition + cameraPosition;
                    // Project a moving surface-transmission field along the refracted sunlight.
                    // One existing noise lookup per step gives coherent shafts in open water too.
                    vec2 surfaceUV = (worldSample.xz - shaftDirection.xz * worldSample.y / shaftDirection.y) * 0.018;
                    vec2 noise = texture(noisetex, surfaceUV + vec2(0.008, -0.005) * frameTimeCounter).rg;
                    float beam = 1.0 - smoothstep(0.025, 0.14, abs(noise.r - noise.g));
                    mediumLight = 0.015 + beam * beam * beam * 2.4;
                }
#endif
                shafts += xonRayVisibility(samplePosition) * mediumLight * exp(-distanceAlongRay * (underwater ? 0.055 : 0.018));
            }
            shafts *= stepLength * (underwater ? 0.040 : 0.007) * phase * exposure * daylight * XON_RAY_STRENGTH;
            shafts = min(shafts, underwater ? 0.28 : 0.20);
        }
    }
#endif
#endif
#endif
    xonEffects = vec4(glow, shafts);
}
