#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"
#include "/lib/atmosphere.glsl"
#include "/lib/grading.glsl"

#ifdef XON_COLORED_EMISSIVE_LIGHTING
// Keep nearby emitters in the shadow draw list even behind the camera or underground.
const float voxelDistance = 48.0;
#endif

/*
const int colortex0Format = RGBA16F;
const int colortex4Format = R8;
const int colortex5Format = RGBA16F;
const bool colortex5Clear = false;
const int colortex7Format = RGBA16F;
const bool colortex7Clear = false;
const bool colortex4Clear = true;
const vec4 colortex4ClearColor = vec4(0.0, 0.0, 0.0, 0.0);
const float wetnessHalflife = 80.0;
const float drynessHalflife = 60.0;
const float eyeBrightnessHalflife = 6.0;
const int noiseTextureResolution = 256;
*/

uniform sampler2D colortex0;
uniform sampler2D colortex4;
uniform sampler2D depthtex0;
#if defined XON_BLOOM || (defined XON_LIGHT_SHAFTS && defined XON_SHADOWS && XON_DIMENSION == 0)
uniform sampler2D colortex5;
#endif
in vec2 xonUV;
layout(location = 0) out vec4 xonOutput;

#include "/lib/antialiasing.glsl"

vec2 xonCameraVelocity(float depth) {
    if (frameCounter < 4 || frameTime <= 0.0 || frameTime > 0.10) return vec2(0.0);
    vec3 cameraDelta = cameraPosition - previousCameraPosition;
    float camMoveSq = dot(cameraDelta, cameraDelta);
    if (camMoveSq > 16.0) return vec2(0.0);
    vec3 viewRotDelta = gbufferModelView[2].xyz - gbufferPreviousModelView[2].xyz;
    if (camMoveSq < 0.000001 && dot(viewRotDelta, viewRotDelta) < 0.00000005) return vec2(0.0);
    vec2 projectionDelta = vec2(gbufferProjection[0][0] - gbufferPreviousProjection[0][0],
                                gbufferProjection[1][1] - gbufferPreviousProjection[1][1]);
    if (dot(projectionDelta, projectionDelta) > 0.0004) return vec2(0.0);
    vec4 current = vec4(xonUV * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 viewPosition = gbufferProjectionInverse * current;
    if (abs(viewPosition.w) < 0.000001) return vec2(0.0);
    viewPosition /= viewPosition.w;
    vec4 playerPosition = gbufferModelViewInverse * viewPosition;
    if (depth >= 0.999999) {
        playerPosition = vec4(mat3(gbufferModelViewInverse) * viewPosition.xyz, 0.0);
    } else {
        playerPosition.xyz += cameraDelta;
    }
    vec4 previous = gbufferPreviousProjection * gbufferPreviousModelView * playerPosition;
    if (previous.w <= 0.000001) return vec2(0.0);
    vec2 previousUV = previous.xy / previous.w * 0.5 + 0.5;
    vec2 velocity = (xonUV - previousUV) * XON_BLUR_EXPOSURE / clamp(frameTime, 0.002, 0.05);
    vec2 pixels = velocity * vec2(viewWidth, viewHeight);
    float radius = length(pixels);
    float radiusCap = XON_BLUR_RADIUS * viewHeight / 1080.0;
    float softRadius = radiusCap * (1.0 - exp(-radius / max(radiusCap, 0.0001)));
    return velocity * (softRadius / max(radius, 0.0001));
}

vec3 xonMotionBlur(vec3 center, float depth, float handMask, out float motionPixels) {
    motionPixels = 0.0;
#ifdef XON_MOTION_BLUR
    float handBoundary = fwidth(handMask);
    if (handMask > 0.01 || handBoundary > 0.01) return center;
    vec2 velocity = xonCameraVelocity(depth);
    motionPixels = length(velocity * vec2(viewWidth, viewHeight));
    if (motionPixels < 0.35) return center;
    float stability = smoothstep(0.35, 0.45, motionPixels);
    vec2 pixel = 1.0 / (vec2(viewWidth, viewHeight) * XON_RENDER_SCALE);
    // Symmetric subpixel coverage shares the six shutter reads instead of adding an AA pass.
    const vec2 coverage[6] = vec2[6](vec2(-0.30, 0.0), vec2(-0.15, -0.2598),
        vec2(0.15, -0.2598), vec2(-0.15, 0.2598), vec2(0.15, 0.2598), vec2(0.30, 0.0));
    const float shutter[6] = float[6](0.7260, 0.8939, 0.9878, 0.9878, 0.8939, 0.7260);
    // Pre-check whether the motion vector endpoints touch the first-person hand so 98% of screen pixels skip per-tap colortex4 fetches.
    vec2 endPosUV = xonSourceUV(clamp(xonUV + velocity * 0.85, 0.0, 1.0));
    vec2 endNegUV = xonSourceUV(clamp(xonUV - velocity * 0.85, 0.0, 1.0));
    bool nearHand = (texture(colortex4, endPosUV).r + texture(colortex4, endNegUV).r) > 0.01;
    vec3 result = center * 0.42;
    float totalWeight = 0.42;
    for (int tap = 0; tap < 6; ++tap) {
        float offset = (float(tap) - 2.5) * (1.70 / 6.0);
        vec2 tapUV = xonUV + velocity * offset + coverage[tap] * pixel * stability;
        if (any(lessThan(tapUV, vec2(0.0))) || any(greaterThan(tapUV, vec2(1.0)))) continue;
        vec2 sourceUV = xonSourceUV(tapUV);
        if (nearHand && texture(colortex4, sourceUV).r > 0.01) continue;
        float weight = shutter[tap];
        result += texture(colortex0, sourceUV).rgb * weight;
        totalWeight += weight;
    }
    return mix(center, result / totalWeight, stability);
#else
    return center;
#endif
}

void main() {
    vec2 sourceUV = xonSourceUV(xonUV);
    vec3 color = texture(colortex0, sourceUV).rgb;
    float depth = texture(depthtex0, sourceUV).r;
    float handMask = texture(colortex4, sourceUV).r;
    float motionPixels;
    color = xonMotionBlur(color, depth, handMask, motionPixels);
    color = xonEdgeAA(color, depth, motionPixels, handMask);
#if defined XON_BLOOM || (defined XON_LIGHT_SHAFTS && defined XON_SHADOWS && XON_DIMENSION == 0)
    if (handMask < 0.01) {
        vec4 effects = texture(colortex5, xonUV);
#ifdef XON_BLOOM
        color += effects.rgb * (0.16 * XON_BLOOM_STRENGTH);
#endif
#if defined XON_LIGHT_SHAFTS && defined XON_SHADOWS && XON_DIMENSION == 0
        vec3 rayColor = isEyeInWater == 1 ? vec3(0.20, 0.40, 0.65) : xonSunlightColor();
        color += effects.a * rayColor;
#endif
    }
#endif
    color = max(color * XON_BRIGHTNESS, vec3(0.0));
    color = color * (2.51 * color + 0.03) / (color * (2.43 * color + 0.59) + 0.14);
    color = clamp(color, 0.0, 1.0);
    color = xonToDisplay(color);
    color = xonApplyGrade(color);
    float dither = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
    color += (dither - 0.5) / 255.0;
    xonOutput = vec4(clamp(color, 0.0, 1.0), 1.0);
}
