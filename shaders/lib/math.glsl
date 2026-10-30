#ifndef XON_MATH
#define XON_MATH

float xonSaturate(float value) { return clamp(value, 0.0, 1.0); }
float xonSquare(float value) { return value * value; }
float xonLuminance(vec3 value) { return dot(value, vec3(0.2126, 0.7152, 0.0722)); }

vec3 xonToLinear(vec3 value) {
    return pow(max(value, vec3(0.0)), vec3(2.2));
}

vec3 xonToDisplay(vec3 value) {
    return pow(max(value, vec3(0.0)), vec3(1.0 / 2.2));
}

vec3 xonSafeNormalize(vec3 value) {
    return value * inversesqrt(max(dot(value, value), 0.000001));
}

vec3 xonSunDirection() {
    return xonSafeNormalize(mat3(gbufferModelViewInverse) * sunPosition);
}

vec3 xonKeyDirection() {
    if (dot(shadowLightPosition, shadowLightPosition) > 1.0) {
        return xonSafeNormalize(mat3(gbufferModelViewInverse) * shadowLightPosition);
    }
    vec3 sun = xonSunDirection();
    return sun * (sun.y >= 0.0 ? 1.0 : -1.0);
}

float xonDaylight(float sunY) {
    return smoothstep(-0.12, 0.10, sunY);
}

float xonDaylight() {
    return xonDaylight(xonSunDirection().y);
}

vec2 xonSourceUV(vec2 uv) {
    vec2 halfPixel = 0.5 / vec2(viewWidth, viewHeight);
    return clamp(uv * XON_RENDER_SCALE, halfPixel,
                 vec2(XON_RENDER_SCALE) - halfPixel);
}

vec4 xonScaleClip(vec4 clipPosition) {
#if XON_RENDER_MODE > 0
    clipPosition.xy = clipPosition.xy * XON_RENDER_SCALE
                    + clipPosition.w * (XON_RENDER_SCALE - 1.0);
#endif
    return clipPosition;
}

float xonViewDepth(float depth) {
    float ndcDepth = depth * 2.0 - 1.0;
    float numerator = gbufferProjectionInverse[2][2] * ndcDepth
                    + gbufferProjectionInverse[3][2];
    float denominator = gbufferProjectionInverse[2][3] * ndcDepth
                      + gbufferProjectionInverse[3][3];
    return abs(numerator) / max(abs(denominator), 0.000001);
}

#endif
