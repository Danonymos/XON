#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"

uniform sampler2D colortex0;
uniform sampler2D colortex4;
uniform sampler2D colortex6;
uniform sampler2D depthtex0;
in vec2 xonUV;
layout(location = 0) out vec4 xonResolvedScene;
layout(location = 1) out vec4 xonHistory;

vec4 xonCubicWeights(float t) {
    float t2 = t * t, t3 = t2 * t;
    return vec4(-0.75 * t + 1.5 * t2 - 0.75 * t3,
                1.0 - 2.25 * t2 + 1.25 * t3,
                0.75 * t + 1.5 * t2 - 1.25 * t3,
                -0.75 * t2 + 0.75 * t3);
}

vec4 xonHistoryStamp(int frame) {
    vec2 size = vec2(viewWidth, viewHeight);
    return vec4(mod(size, 1024.0), floor(size.x / 1024.0) + floor(size.y / 1024.0) * 32.0,
                -float(frame % 1024 + 1));
}

bool xonHistoryValid() {
    if (frameCounter < 2 || frameTime <= 0.0 || frameTime > 0.10) return false;
    vec3 delta = cameraPosition - previousCameraPosition;
    if (dot(delta, delta) > 16.0) return false;
    if (dot(gbufferModelView[2].xyz, gbufferPreviousModelView[2].xyz) < 0.85) return false;
    vec2 projectionDelta = vec2(gbufferProjection[0][0] - gbufferPreviousProjection[0][0],
                                gbufferProjection[1][1] - gbufferPreviousProjection[1][1]);
    if (dot(projectionDelta, projectionDelta) > 0.0004) return false;
    int previousFrame = (frameCounter + 720719) % 720720;
    return all(lessThan(abs(texelFetch(colortex6, ivec2(0), 0) - xonHistoryStamp(previousFrame)), vec4(0.25)));
}

vec3 xonResolveTemporal(vec3 current, vec2 currentUV, float depth, vec2 depthOffset, float surfaceMask) {
    if (surfaceMask > 0.75 || !xonHistoryValid()) return current;
    vec2 jitter = xonJitter(frameCounter) / (vec2(viewWidth, viewHeight) * XON_RENDER_SCALE);
    vec4 view = gbufferProjectionInverse * vec4((xonUV + depthOffset - jitter) * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    if (abs(view.w) < 0.000001) return current;
    view /= view.w;
    vec4 player = gbufferModelViewInverse * view;
    bool sky = depth >= 0.999999;
    if (sky) player = vec4(mat3(gbufferModelViewInverse) * view.xyz, 0.0);
    else player.xyz += cameraPosition - previousCameraPosition;
    vec4 previousView = gbufferPreviousModelView * player;
    vec4 previous = gbufferPreviousProjection * previousView;
    if (previous.w <= 0.000001) return current;
    vec2 previousUV = previous.xy / previous.w * 0.5 + 0.5 - depthOffset + jitter;
    vec2 size = vec2(viewWidth, viewHeight);
    vec2 historyPixel = previousUV * size - 0.5;
    if (any(lessThan(historyPixel, vec2(0.0))) || any(greaterThan(historyPixel, size - 2.0))) return current;
    // One history-only texel stores exact half-float-safe size/frame metadata; display color is unaffected.
    if (all(lessThan(historyPixel, vec2(1.0)))) return current;

    vec2 fraction = fract(historyPixel);
    ivec2 origin = ivec2(floor(historyPixel));
    ivec2 maxPixel = ivec2(size) - 1;
    float expectedDepth = sky ? 65000.0 : abs(previousView.z);
    float tolerance = max(0.04, expectedDepth * 0.02);
    vec3 history = vec3(0.0);
    float coverage = 0.0;
    float depthError = 1e20;
    vec4 weightsX = xonCubicWeights(fraction.x);
    vec4 weightsY = xonCubicWeights(fraction.y);
    // Evaluate inner 2x2 depth agreement first so disoccluded pixels during camera movement skip the 12 outer taps + 8 variance taps.
    for (int y = 1; y <= 2; ++y) {
        for (int x = 1; x <= 2; ++x) {
            float weight = weightsX[x] * weightsY[y];
            if (abs(weight) < 0.00001) continue;
            ivec2 tapPixel = clamp(origin + ivec2(x - 1, y - 1), ivec2(0), maxPixel);
            vec4 tap = texelFetch(colortex6, tapPixel, 0);
            if (tap.a <= 0.0) continue;
            depthError = min(depthError, abs(tap.a - expectedDepth));
            history += tap.rgb * weight;
            coverage += weight;
        }
    }
    if (depthError > tolerance) return current;
    for (int y = 0; y < 4; ++y) {
        for (int x = 0; x < 4; ++x) {
            if (x >= 1 && x <= 2 && y >= 1 && y <= 2) continue;
            float weight = weightsX[x] * weightsY[y];
            if (abs(weight) < 0.00001) continue;
            ivec2 tapPixel = clamp(origin + ivec2(x - 1, y - 1), ivec2(0), maxPixel);
            vec4 tap = texelFetch(colortex6, tapPixel, 0);
            if (tap.a <= 0.0) continue;
            history += tap.rgb * weight;
            coverage += weight;
        }
    }
    if (coverage < 0.80) return current;
    history /= coverage;

    vec3 low = current, high = current;
    vec3 sum = current, squares = current * current;
    vec2 pixel = 1.0 / (size * XON_RENDER_SCALE);
    for (int y = -1; y <= 1; ++y) {
        for (int x = -1; x <= 1; ++x) {
            if (x == 0 && y == 0) continue;
            vec3 tap = texture(colortex0, xonSourceUV(currentUV + vec2(x, y) * pixel)).rgb;
            low = min(low, tap);
            high = max(high, tap);
            sum += tap;
            squares += tap * tap;
        }
    }
    vec3 mean = sum / 9.0;
    vec3 sigma = sqrt(max(squares / 9.0 - mean * mean, vec3(0.0)));
    history = clamp(history, max(low, mean - sigma * 1.25), min(high, mean + sigma * 1.25));
    float motion = length((previousUV - xonUV) * size);
    float weight = mix(0.88, 0.72, smoothstep(0.0, 12.0, motion));
    // Entities, animated surfaces and translucent geometry lack per-object motion vectors.
    weight *= 1.0 - smoothstep(0.01, 0.20, surfaceMask) * 0.65;
    return mix(current, history, weight * clamp(coverage, 0.0, 1.0));
}

void main() {
    vec2 currentUV = xonUV;
    float hand = texture(colortex4, xonSourceUV(xonUV)).r;
    bool nearHand = hand > 0.75 || fwidth(hand) > 0.50;
    vec2 sourceUV = xonSourceUV(currentUV);
    vec3 current = texture(colortex0, sourceUV).rgb;
    float depth = texture(depthtex0, sourceUV).r;
    float surfaceMask = nearHand ? 1.0 : hand;
    vec2 depthOffset = vec2(0.0);
    if (!nearHand) {
        // Edge pixels share the nearest surface's camera motion, avoiding background trails around silhouettes.
        vec2 pixel = 1.0 / (vec2(viewWidth, viewHeight) * XON_RENDER_SCALE);
        for (int y = -1; y <= 1; ++y) {
            for (int x = -1; x <= 1; ++x) {
                if (x == 0 && y == 0) continue;
                vec2 offset = vec2(x, y) * pixel;
                float neighbor = texture(depthtex0, xonSourceUV(currentUV + offset)).r;
                if (neighbor < depth) {
                    depth = neighbor;
                    depthOffset = offset;
                }
            }
        }
    }
    vec3 resolved = xonResolveTemporal(current, currentUV, depth, depthOffset, surfaceMask);
    float historyDepth = nearHand ? -1.0 : (depth >= 0.999999 ? 65000.0 : min(xonViewDepth(depth), 64000.0));
    xonResolvedScene = vec4(resolved, 1.0);
    xonHistory = vec4(resolved, historyDepth);
    if (all(lessThan(gl_FragCoord.xy, vec2(1.0)))) xonHistory = xonHistoryStamp(frameCounter);
}
