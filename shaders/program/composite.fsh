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
    float knee = clamp(peak - 0.90, 0.0, 0.40);
    float threshold = max(peak - 1.10, knee * knee * 1.25) / max(peak, 0.001);
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
        vec2 rayUV = xonUV - xonJitter(frameCounter) / (vec2(viewWidth, viewHeight) * XON_RENDER_SCALE);
        vec4 view = gbufferProjectionInverse * vec4(rayUV * 2.0 - 1.0, 1.0, 1.0);
        vec3 playerRay = mat3(gbufferModelViewInverse) * xonSafeNormalize(view.xyz);
        vec3 sun = underwater ? xonKeyDirection() : xonSunDirection();
        if (underwater) {
            // Use the same key light direction as the occluder shadow map.
            daylight *= smoothstep(0.0, 0.14, sun.y);
        }
        float sunDot = dot(playerRay, sun);
        // Wide-angle volumetric visibility: shafts remain active when viewing around building occluders
        if (underwater || sunDot > -0.20) {
            // Dual-lobe Henyey-Greenstein + Rayleigh scattering phase function
            float g = mix(0.82, 0.65, clamp((XON_RAY_WRAP - 0.5) * 0.75, 0.0, 1.0));
            float g2 = g * g;
            float hgDenom = max(1.0 + g2 - 2.0 * g * sunDot, 0.01);
            float hgPhase = (1.0 - g2) / (hgDenom * sqrt(hgDenom));
            float rayleighPhase = 1.0 + 0.35 * sunDot * sunDot;
            float sunAlign = xonSaturate(sunDot * 0.5 + 0.5);
            float phase = underwater ? (0.65 + 0.35 * sunAlign)
                                     : mix(rayleighPhase * 0.28, hgPhase * 0.09, 0.82) * smoothstep(-0.20, 0.12, sunDot);

            vec2 srcUV = xonSourceUV(xonUV);
            float depth = texture(depthtex0, srcUV).r;
            if (underwater) {
                float solidDepth = texture(depthtex1, srcUV).r;
                if (solidDepth > depth) depth = solidDepth;
            }
            vec4 depthView = gbufferProjectionInverse * vec4(rayUV * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
            depthView.xyz /= max(abs(depthView.w), 0.000001);
            float maxRayDist = underwater ? min(shadowDistance * 0.75, 72.0) : shadowDistance * 0.85;
            float rayLength = min(length(depthView.xyz), maxRayDist);
            float jitter = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
            int sampleCount = underwater ? 12 : 10;
            vec3 rayOrigin = gbufferModelViewInverse[3].xyz;
            mat4 shadowMVP = shadowProjection * shadowModelView;
            vec3 shadowOrigin = (shadowMVP * vec4(rayOrigin, 1.0)).xyz;
            vec3 shadowStep = mat3(shadowMVP) * playerRay;
            float totalWeight = 0.0;
            float camY = cameraPosition.y;

            for (int stepIndex = 0; stepIndex < 12; ++stepIndex) {
                if (stepIndex >= sampleCount) break;
                float distanceAlongRay;
                float weight = 1.0;
                if (underwater) {
                    float stepLength = maxRayDist / 12.0;
                    float start = float(stepIndex) * stepLength;
                    float end = min(start + stepLength, rayLength);
                    if (end <= start) break;
                    distanceAlongRay = start + (end - start) * (0.5 + (jitter - 0.5) * 0.35);
                    float nearRamp = smoothstep(0.0, 4.5, distanceAlongRay);
                    weight = (end - start) * nearRamp * exp(-distanceAlongRay * 0.020);
                } else {
                    float t0 = float(stepIndex) / float(sampleCount);
                    float t1 = float(stepIndex + 1) / float(sampleCount);
                    float sampleT = mix(t0, t1, 0.35 + jitter * 0.65);
                    distanceAlongRay = rayLength * pow(sampleT, 1.32);
                    float worldY = camY + playerRay.y * distanceAlongRay;
                    float heightDensity = exp(-max(worldY - 64.0, 0.0) * 0.016);
                    weight = (pow(t1, 1.32) - pow(t0, 1.32)) * exp(-distanceAlongRay * 0.014) * (0.45 + 0.55 * heightDensity);
                }
                vec3 shadowClip = shadowOrigin + shadowStep * distanceAlongRay;
                float visibility = underwater ? xonWaterRayVisibilityClip(shadowClip) : xonRayVisibilityClip(shadowClip);
                shafts += visibility * weight;
                totalWeight += weight;
            }
            if (underwater) {
                shafts *= 0.0052 * phase * exposure * daylight * XON_RAY_STRENGTH;
            } else {
                float normFactor = totalWeight > 0.0001 ? (shafts / totalWeight) : 0.0;
                float distanceEnvelope = min(rayLength * 0.045, 1.25);
                shafts = normFactor * distanceEnvelope * (0.17 * phase * exposure * daylight * XON_RAY_STRENGTH);
            }
            shafts = min(shafts, 0.28);
        }
    }
#endif
#endif
#endif
    xonEffects = vec4(glow, shafts);
}
