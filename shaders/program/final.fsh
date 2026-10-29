#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"
#include "/lib/atmosphere.glsl"
#include "/lib/grading.glsl"

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
    if (camMoveSq > 4096.0) return vec2(0.0);
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
    return velocity * min(1.0, radiusCap / max(radius, 0.0001));
}

vec3 xonMotionBlur(vec3 center, float depth, float handMask, out float motionPixels) {
    motionPixels = 0.0;
#ifdef XON_MOTION_BLUR
    if (handMask > 0.01) return center;
    vec2 velocity = xonCameraVelocity(depth);
    motionPixels = length(velocity * vec2(viewWidth, viewHeight));
    if (motionPixels < 0.45) return center;
    float centerDistance = xonViewDepth(depth);
    float jitter = (fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) - 0.5) * 0.22;
    vec3 result = center * 1.15;
    float totalWeight = 1.15;
    for (int tap = 0; tap < 4; ++tap) {
        float offset = (float(tap) - 1.5 + jitter) * (1.0 / 3.0);
        vec2 tapUV = xonUV + velocity * offset;
        if (any(lessThan(tapUV, vec2(0.0))) || any(greaterThan(tapUV, vec2(1.0)))) continue;
        vec2 sourceUV = xonSourceUV(tapUV);
        if (texture(colortex4, sourceUV).r > 0.01) continue;
        float sampleDepth = texture(depthtex0, sourceUV).r;
        float sampleDistance = xonViewDepth(sampleDepth);
        float tolerance = max(0.35, min(centerDistance, sampleDistance) * 0.06);
        float depthWeight = 1.0 - smoothstep(tolerance, tolerance * 2.0,
                                             abs(sampleDistance - centerDistance));
        float tentWeight = 1.0 - abs(offset) * 0.35;
        float weight = depthWeight * tentWeight;
        result += texture(colortex0, sourceUV).rgb * weight;
        totalWeight += weight;
    }
    return result / totalWeight;
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
        color += effects.rgb * 0.16;
#endif
#if defined XON_LIGHT_SHAFTS && defined XON_SHADOWS && XON_DIMENSION == 0
        color += effects.a * xonSunlightColor();
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
