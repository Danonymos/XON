#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"
#include "/lib/shadows.glsl"
#include "/lib/materials.glsl"

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

#ifdef XON_EMISSIVE_ORES
#ifdef XON_COLORED_EMISSIVE_LIGHTING
    vec3 emissiveLight = vec3(0.0);
    vec2 srcUV = xonSourceUV(xonUV);
    float solidDepth = texture(depthtex1, srcUV).r;
    float sceneDepth = texture(depthtex0, srcUV).r;
    float currentDepth = max(solidDepth, sceneDepth);
    if (currentDepth < 0.99999) {
        vec4 currentClip = vec4(xonUV * 2.0 - 1.0, currentDepth * 2.0 - 1.0, 1.0);
        vec4 currentView = gbufferProjectionInverse * currentClip;
        currentView.xyz /= max(abs(currentView.w), 0.000001);
        float surfaceDist = length(currentView.xyz);
        if (surfaceDist < 36.0) {
            vec3 surfaceNormal = normalize(cross(dFdx(currentView.xyz), dFdy(currentView.xyz)));
            if (dot(surfaceNormal, surfaceNormal) > 0.5) {
                float uvRadius = clamp((3.0 * gbufferProjection[1][1] * 0.5) / max(abs(currentView.z), 0.5), 0.01, 0.45);
                vec2 aspect = vec2(viewHeight / viewWidth, 1.0) * uvRadius;
                float jitterAngle = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) * 6.2831853;
                mat2 rot = mat2(cos(jitterAngle), -sin(jitterAngle), sin(jitterAngle), cos(jitterAngle));
                
                const vec2 POISSON[12] = vec2[12](
                    vec2( 0.0259,  0.0000), vec2(-0.0675,  0.0618), vec2( 0.0144, -0.1640),
                    vec2( 0.1475,  0.1924), vec2(-0.3187, -0.0564), vec2( 0.3440, -0.2188),
                    vec2(-0.1283,  0.4771), vec2(-0.2685, -0.5169), vec2( 0.6318,  0.2307),
                    vec2(-0.7066,  0.2917), vec2( 0.3635, -0.7768), vec2( 0.2850,  0.9086)
                );
                
                vec3 accumLight = vec3(0.0);
                float accumWeight = 0.0;
                for (int i = 0; i < 12; ++i) {
                    vec2 tapUV = xonUV + (rot * POISSON[i]) * aspect;
                    if (any(lessThan(tapUV, vec2(0.001))) || any(greaterThan(tapUV, vec2(0.999)))) continue;
                    vec2 tapSrcUV = xonSourceUV(tapUV);
                    float emitterId = texture(colortex0, tapSrcUV).a;
                    if (emitterId < 0.05 || emitterId > 0.95) continue;
                    vec3 emitColor; float emitRadius; float emitIntensity;
                    if (!xonGetEmissiveProfile(emitterId, emitColor, emitRadius, emitIntensity)) continue;
                    
                    float tapDepth = texture(depthtex0, tapSrcUV).r;
                    vec4 tapClip = vec4(tapUV * 2.0 - 1.0, tapDepth * 2.0 - 1.0, 1.0);
                    vec4 tapView = gbufferProjectionInverse * tapClip;
                    tapView.xyz /= max(abs(tapView.w), 0.000001);
                    
                    vec3 emitterPos = tapView.xyz - normalize(tapView.xyz) * 0.20;
                    vec3 toLight = emitterPos - currentView.xyz;
                    float dist = length(toLight);
                    if (dist >= emitRadius || dist < 0.08) continue;
                    
                    vec3 lightDir = toLight / dist;
                    float nDotL = max(dot(surfaceNormal, lightDir), 0.0);
                    if (nDotL <= 0.001) continue;
                    
                    float falloff = 1.0 - smoothstep(0.0, emitRadius, dist);
                    
                    bool occluded = false;
                    for (float t = 0.25; t <= 0.75; t += 0.25) {
                        vec2 stepUV = mix(xonUV, tapUV, t);
                        float stepDepth = texture(depthtex0, xonSourceUV(stepUV)).r;
                        vec4 stepClip = vec4(stepUV * 2.0 - 1.0, stepDepth * 2.0 - 1.0, 1.0);
                        vec4 stepView = gbufferProjectionInverse * stepClip;
                        stepView.xyz /= max(abs(stepView.w), 0.000001);
                        float expectedZ = mix(currentView.z, tapView.z, t);
                        if (stepView.z > expectedZ + 0.35) {
                            occluded = true;
                            break;
                        }
                    }
                    if (occluded) continue;
                    
                    accumLight += emitColor * (falloff * nDotL * emitIntensity);
                    accumWeight += 1.0;
                }
                if (accumWeight > 0.001) {
                    emissiveLight = (accumLight / max(accumWeight, 1.0)) * 1.25;
                }
            }
        }
    }
    glow += emissiveLight * (6.25 / max(XON_BLOOM_STRENGTH, 0.10));
#endif
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
    if (underwater) exposure = 1.0;
    if (exposure > 0.001 && daylight > 0.001 && XON_RAY_STRENGTH > 0.0 && (isEyeInWater == 0 || underwater)) {
        vec4 view = gbufferProjectionInverse * vec4(xonUV * 2.0 - 1.0, 1.0, 1.0);
        vec3 playerRay = mat3(gbufferModelViewInverse) * xonSafeNormalize(view.xyz);
        vec3 sun = underwater ? xonKeyDirection() : xonSunDirection();
        if (underwater) {
            daylight *= smoothstep(0.0, 0.14, sun.y);
        }
        float sunDot = dot(playerRay, sun);
        if (underwater || sunDot > 0.55) {
            float posDot = max(sunDot, 0.0);
            float s2 = posDot * posDot;
            float s4 = s2 * s2;
            float s8 = s4 * s4;
            float sunAlign = xonSaturate(sunDot * 0.5 + 0.5);
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
