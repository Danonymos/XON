#ifndef XON_ANTIALIASING
#define XON_ANTIALIASING

float xonEdgeLuma(vec3 color) {
    float value = dot(color, vec3(0.2126, 0.7152, 0.0722));
    return value / (1.0 + value);
}

vec3 xonEdgeAA(vec3 center, float centerDepth, float motionPixels, float handMask) {
    float handBoundary = fwidth(handMask);
    if (motionPixels >= 0.45 || handMask > 0.01 || handBoundary > 0.01) return center;
#if XON_RENDER_MODE == 0
    if (centerDepth >= 0.999999 && XON_SHARPNESS <= 0.001) return center;
#endif
    vec2 pixel = 1.0 / (vec2(viewWidth, viewHeight) * XON_RENDER_SCALE);
    vec2 uvN = xonSourceUV(xonUV + vec2(0.0, pixel.y));
    vec2 uvS = xonSourceUV(xonUV - vec2(0.0, pixel.y));
    vec2 uvE = xonSourceUV(xonUV + vec2(pixel.x, 0.0));
    vec2 uvW = xonSourceUV(xonUV - vec2(pixel.x, 0.0));
    vec3 cN = texture(colortex0, uvN).rgb;
    vec3 cS = texture(colortex0, uvS).rgb;
    vec3 cE = texture(colortex0, uvE).rgb;
    vec3 cW = texture(colortex0, uvW).rgb;
    float motionFade = 1.0 - smoothstep(0.35, 0.45, motionPixels);
    vec3 lowRGB = min(center, min(min(cN, cS), min(cE, cW)));
    vec3 highRGB = max(center, max(max(cN, cS), max(cE, cW)));
#if XON_RENDER_MODE > 0
    float sharpness = 0.24 + XON_SHARPNESS * 0.45;
#else
    float sharpness = XON_SHARPNESS * 0.55;
#endif
    vec3 detail = center - (cN + cS + cE + cW) * 0.25;
    center = clamp(center + detail * (sharpness * motionFade), lowRGB, highRGB);
    if (centerDepth >= 0.999999) return center;

    float north = xonEdgeLuma(cN);
    float south = xonEdgeLuma(cS);
    float east = xonEdgeLuma(cE);
    float west = xonEdgeLuma(cW);
    float middle = xonEdgeLuma(center);
    float low = min(middle, min(min(north, south), min(east, west)));
    float high = max(middle, max(max(north, south), max(east, west)));
    if (high - low < max(0.025, high * 0.08)) return center;

    float eyeDepth = xonViewDepth(centerDepth);
    vec4 neighbors = vec4(xonViewDepth(texture(depthtex0, uvN).r),
                          xonViewDepth(texture(depthtex0, uvS).r),
                          xonViewDepth(texture(depthtex0, uvE).r),
                          xonViewDepth(texture(depthtex0, uvW).r));
    float curvature = max(abs(neighbors.x + neighbors.y - 2.0 * eyeDepth),
                          abs(neighbors.z + neighbors.w - 2.0 * eyeDepth)) / max(eyeDepth, 0.1);
    if (curvature < 0.002) return center;
    vec3 cNW = texture(colortex0, xonSourceUV(xonUV + vec2(-pixel.x, pixel.y))).rgb;
    vec3 cNE = texture(colortex0, xonSourceUV(xonUV + vec2(pixel.x, pixel.y))).rgb;
    vec3 cSW = texture(colortex0, xonSourceUV(xonUV + vec2(-pixel.x, -pixel.y))).rgb;
    vec3 cSE = texture(colortex0, xonSourceUV(xonUV + vec2(pixel.x, -pixel.y))).rgb;
    float nw = xonEdgeLuma(cNW), ne = xonEdgeLuma(cNE);
    float sw = xonEdgeLuma(cSW), se = xonEdgeLuma(cSE);
    float gradX = (east - west) * 2.0 + ne - nw + se - sw;
    float gradY = (north - south) * 2.0 + nw - sw + ne - se;
    float extent = max(abs(gradX), abs(gradY));
    vec3 filtered = (cN + cS + cE + cW) * 0.25;
    if (extent > 0.0001) {
        // Two symmetric bilinear positions reconstructed from the cached 3x3 neighborhood.
        vec2 along = abs(vec2(gradY, gradX)) * (0.75 / extent);
        vec3 diagonal = gradX * gradY <= 0.0 ? (cNE + cSW) * 0.5 : (cNW + cSE) * 0.5;
        filtered = center * ((1.0 - along.x) * (1.0 - along.y))
                 + (cE + cW) * (0.5 * along.x * (1.0 - along.y))
                 + (cN + cS) * (0.5 * along.y * (1.0 - along.x))
                 + diagonal * (along.x * along.y);
    }
    float distanceBlend = mix(0.66, 0.82, smoothstep(8.0, 96.0, eyeDepth));
    float edgeBlend = smoothstep(0.002, 0.018, curvature) * distanceBlend * motionFade;
    return mix(center, filtered, edgeBlend);
}

#endif
