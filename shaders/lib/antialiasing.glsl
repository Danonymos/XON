#ifndef XON_ANTIALIASING
#define XON_ANTIALIASING

float xonEdgeLuma(vec3 color) {
    float value = dot(color, vec3(0.2126, 0.7152, 0.0722));
    return value / (1.0 + value);
}

vec3 xonEdgeAA(vec3 center, float centerDepth, float motionPixels, float handMask) {
    if (motionPixels > 0.45) return center;
#if XON_RENDER_MODE > 0 || defined XON_EDGE_AA
    vec2 pixel = 1.0 / (vec2(viewWidth, viewHeight) * XON_RENDER_SCALE);
    vec2 uvN = xonSourceUV(xonUV + vec2(0.0, pixel.y));
    vec2 uvS = xonSourceUV(xonUV - vec2(0.0, pixel.y));
    vec2 uvE = xonSourceUV(xonUV + vec2(pixel.x, 0.0));
    vec2 uvW = xonSourceUV(xonUV - vec2(pixel.x, 0.0));
    vec3 cN = texture(colortex0, uvN).rgb;
    vec3 cS = texture(colortex0, uvS).rgb;
    vec3 cE = texture(colortex0, uvE).rgb;
    vec3 cW = texture(colortex0, uvW).rgb;
#if XON_RENDER_MODE > 0
    vec3 lowRGB = min(center, min(min(cN, cS), min(cE, cW)));
    vec3 highRGB = max(center, max(max(cN, cS), max(cE, cW)));
    vec3 detail = center - (cN + cS + cE + cW) * 0.25;
    center = clamp(center + detail * 0.24, lowRGB, highRGB);
#endif
#ifdef XON_EDGE_AA
    if (handMask > 0.01 || centerDepth >= 0.999999) return center;
    float north = xonEdgeLuma(cN);
    float south = xonEdgeLuma(cS);
    float east = xonEdgeLuma(cE);
    float west = xonEdgeLuma(cW);
    float middle = xonEdgeLuma(center);
    float low = min(middle, min(min(north, south), min(east, west)));
    float high = max(middle, max(max(north, south), max(east, west)));
    if (high - low < max(0.032, high * 0.11)) return center;

    float eyeDepth = xonViewDepth(centerDepth);
    vec4 neighbors = vec4(xonViewDepth(texture(depthtex0, uvN).r),
                          xonViewDepth(texture(depthtex0, uvS).r),
                          xonViewDepth(texture(depthtex0, uvE).r),
                          xonViewDepth(texture(depthtex0, uvW).r));
    float curvature = max(abs(neighbors.x + neighbors.y - 2.0 * eyeDepth),
                          abs(neighbors.z + neighbors.w - 2.0 * eyeDepth)) / max(eyeDepth, 0.1);
    // Depth curvature rejects texture-only edges and smooth perspective slopes.
    if (curvature < 0.002) return center;
    vec2 direction = vec2(-(north - south), east - west);
    float extent = max(abs(direction.x), abs(direction.y));
    if (extent < 0.0001) return center;
    vec2 stepVec = direction / extent * pixel;
    vec3 innerA = texture(colortex0, xonSourceUV(xonUV + stepVec * 0.45)).rgb;
    vec3 innerB = texture(colortex0, xonSourceUV(xonUV - stepVec * 0.45)).rgb;
    vec3 outerA = texture(colortex0, xonSourceUV(xonUV + stepVec * 0.92)).rgb;
    vec3 outerB = texture(colortex0, xonSourceUV(xonUV - stepVec * 0.92)).rgb;
    vec3 filtered = (innerA + innerB) * 0.34 + (outerA + outerB) * 0.16;
    float edgeBlend = smoothstep(0.002, 0.020, curvature) * 0.88;
    return mix(center, filtered, edgeBlend);
#else
    return center;
#endif
#else
    return center;
#endif
}

#endif
