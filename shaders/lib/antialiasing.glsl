#ifndef XON_ANTIALIASING
#define XON_ANTIALIASING

float xonEdgeLuma(vec3 color) {
    float value = dot(color, vec3(0.2126, 0.7152, 0.0722));
    return value / (1.0 + value);
}

vec3 xonEdgeAA(vec3 center, float centerDepth, float motionPixels, float handMask) {
    if (motionPixels > 0.45) return center;
#if XON_RENDER_MODE == 0
    if ((handMask > 0.01 || centerDepth >= 0.999999) && XON_SHARPNESS <= 0.001) return center;
#endif
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
    center = clamp(center + detail * (0.24 + XON_SHARPNESS * 0.45), lowRGB, highRGB);
#else
    if (XON_SHARPNESS > 0.001 && centerDepth < 0.999999) {
        vec3 lowRGB = min(center, min(min(cN, cS), min(cE, cW)));
        vec3 highRGB = max(center, max(max(cN, cS), max(cE, cW)));
        vec3 detail = center - (cN + cS + cE + cW) * 0.25;
        center = clamp(center + detail * (XON_SHARPNESS * 0.55), lowRGB, highRGB);
    }
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
    float perspectiveSlope = max(abs(neighbors.x - neighbors.y),
                                 abs(neighbors.z - neighbors.w)) / max(eyeDepth, 0.1);
#if XON_ANISOTROPIC > 0
    // Allow AA on both silhouette edges (curvature >= 0.002) and receding flat floors/roads (perspectiveSlope >= 0.0035).
    if (curvature < 0.002 && perspectiveSlope < 0.0035) return center;
#else
    if (curvature < 0.002) return center;
#endif
    // 8-neighbor Sobel gradient gives accurate tangent direction on diagonal floor lines and shallow perspective edges.
    float nw = xonEdgeLuma(texture(colortex0, xonSourceUV(xonUV + vec2(-pixel.x,  pixel.y))).rgb);
    float ne = xonEdgeLuma(texture(colortex0, xonSourceUV(xonUV + vec2( pixel.x,  pixel.y))).rgb);
    float sw = xonEdgeLuma(texture(colortex0, xonSourceUV(xonUV + vec2(-pixel.x, -pixel.y))).rgb);
    float se = xonEdgeLuma(texture(colortex0, xonSourceUV(xonUV + vec2( pixel.x, -pixel.y))).rgb);
    float gradX = (east - west) * 2.0 + (ne - nw) + (se - sw);
    float gradY = (north - south) * 2.0 + (nw - sw) + (ne - se);
    vec2 direction = vec2(-gradY, gradX);
    float extent = max(abs(direction.x), abs(direction.y));
    if (extent < 0.0001) return center;
    vec2 stepVec = clamp(direction / extent, vec2(-1.0), vec2(1.0)) * pixel;
    vec3 innerA = texture(colortex0, xonSourceUV(xonUV + stepVec * 0.45)).rgb;
    vec3 innerB = texture(colortex0, xonSourceUV(xonUV - stepVec * 0.45)).rgb;
    vec3 outerA = texture(colortex0, xonSourceUV(xonUV + stepVec * 0.95)).rgb;
    vec3 outerB = texture(colortex0, xonSourceUV(xonUV - stepVec * 0.95)).rgb;
    vec3 filtered = (innerA + innerB) * 0.34 + (outerA + outerB) * 0.16;
#if XON_ANISOTROPIC >= 4
    vec3 farA = texture(colortex0, xonSourceUV(xonUV + stepVec * 1.48)).rgb;
    vec3 farB = texture(colortex0, xonSourceUV(xonUV - stepVec * 1.48)).rgb;
    filtered = filtered * 0.72 + (farA + farB) * 0.14;
#endif
#if XON_ANISOTROPIC >= 6
    vec3 ultraA = texture(colortex0, xonSourceUV(xonUV + stepVec * 2.05)).rgb;
    vec3 ultraB = texture(colortex0, xonSourceUV(xonUV - stepVec * 2.05)).rgb;
    filtered = filtered * 0.80 + (ultraA + ultraB) * 0.10;
#endif
    float silhouetteBlend = smoothstep(0.002, 0.020, curvature) * 0.88;
#if XON_ANISOTROPIC > 0
    float anisoBoost = XON_ANISOTROPIC == 2 ? 0.82 : (XON_ANISOTROPIC == 4 ? 0.90 : 0.96);
    float floorBlend = smoothstep(0.0035, 0.014, perspectiveSlope) * smoothstep(0.032, 0.14, high - low) * anisoBoost;
    float edgeBlend = max(silhouetteBlend, floorBlend);
#else
    float edgeBlend = silhouetteBlend;
#endif
    vec3 tangentResult = mix(center, filtered, edgeBlend);

#if XON_AA_MODE >= 1
    // Skip long-span staircase walk on subtle low-contrast micro-edges where 4-tap tangentResult is already sufficient.
    if (high - low < max(0.055, high * 0.16)) return tangentResult;
    // Modern FXAA 3.11 Quality (mode 1) & SMAA-Lite Ultra (mode 2): walk along long horizontal/vertical staircase spans on floors and walls.
    float edgeHorz = abs(nw + ne - 2.0 * north) + abs(west + east - 2.0 * middle) * 2.0 + abs(sw + se - 2.0 * south);
    float edgeVert = abs(nw + sw - 2.0 * west)  + abs(north + south - 2.0 * middle) * 2.0 + abs(ne + se - 2.0 * east);
    bool isHorizontal = edgeHorz >= edgeVert;
    float luma1 = isHorizontal ? south : west;
    float luma2 = isHorizontal ? north : east;
    float grad1 = abs(luma1 - middle);
    float grad2 = abs(luma2 - middle);
    bool is1Steepest = grad1 >= grad2;
    float gradScaled = 0.25 * max(grad1, grad2);
    float stepLength = isHorizontal ? pixel.y : pixel.x;
    if (is1Steepest) stepLength = -stepLength;
    float lumaLocalAvg = 0.5 * ((is1Steepest ? luma1 : luma2) + middle);
    vec2 edgeUV = xonUV;
    if (isHorizontal) edgeUV.y += stepLength * 0.5;
    else              edgeUV.x += stepLength * 0.5;

    vec2 tangentStep = isHorizontal ? vec2(pixel.x, 0.0) : vec2(0.0, pixel.y);
    float anisoSpan = XON_ANISOTROPIC == 0 ? 0.85 : (XON_ANISOTROPIC == 2 ? 1.15 : (XON_ANISOTROPIC == 4 ? 1.45 : 1.80));
    vec2 uvPos = edgeUV + tangentStep;
    vec2 uvNeg = edgeUV - tangentStep;
    float lumaEndPos = xonEdgeLuma(texture(colortex0, xonSourceUV(uvPos)).rgb) - lumaLocalAvg;
    float lumaEndNeg = xonEdgeLuma(texture(colortex0, xonSourceUV(uvNeg)).rgb) - lumaLocalAvg;
    bool donePos = abs(lumaEndPos) >= gradScaled;
    bool doneNeg = abs(lumaEndNeg) >= gradScaled;

    const int SPAN_STEPS = (XON_AA_MODE == 2) ? 7 : 5;
    const float STRIDES[7] = float[7](1.0, 1.5, 2.0, 2.0, 2.5, 3.0, 4.0);
    for (int i = 0; i < SPAN_STEPS; ++i) {
        float stride = STRIDES[i] * anisoSpan;
        if (!donePos) {
            uvPos += tangentStep * stride;
            lumaEndPos = xonEdgeLuma(texture(colortex0, xonSourceUV(uvPos)).rgb) - lumaLocalAvg;
            donePos = abs(lumaEndPos) >= gradScaled;
        }
        if (!doneNeg) {
            uvNeg -= tangentStep * stride;
            lumaEndNeg = xonEdgeLuma(texture(colortex0, xonSourceUV(uvNeg)).rgb) - lumaLocalAvg;
            doneNeg = abs(lumaEndNeg) >= gradScaled;
        }
        if (donePos && doneNeg) break;
    }

    float distPos = isHorizontal ? (uvPos.x - xonUV.x) : (uvPos.y - xonUV.y);
    float distNeg = isHorizontal ? (xonUV.x - uvNeg.x) : (xonUV.y - uvNeg.y);
    float distMin = min(distPos, distNeg);
    float spanLength = max(distPos + distNeg, 0.00001);
    float lumaEndCloser = (distPos < distNeg) ? lumaEndPos : lumaEndNeg;
    bool correctVariation = (lumaEndCloser < 0.0) != (middle < lumaLocalAvg);
    float spanOffset = correctVariation ? clamp(0.5 - distMin / spanLength, 0.0, 0.5) : 0.0;

    float lumaAvg = (1.0 / 12.0) * (2.0 * (north + south + east + west) + nw + ne + sw + se);
    float subpix = clamp(abs(lumaAvg - middle) / max(high - low, 0.0001), 0.0, 1.0);
    float subpixOffset = (-2.0 * subpix + 3.0) * subpix * subpix;
    subpixOffset = subpixOffset * subpixOffset * (XON_AA_MODE == 2 ? 0.80 : 0.65);
    float finalOffset = max(spanOffset, subpixOffset * 0.45);

    vec2 finalUV = xonUV;
    if (isHorizontal) finalUV.y += finalOffset * stepLength;
    else              finalUV.x += finalOffset * stepLength;
    vec3 oppositeColor = isHorizontal ? (is1Steepest ? cS : cN) : (is1Steepest ? cW : cE);
    vec3 spanColor = mix(texture(colortex0, xonSourceUV(finalUV)).rgb, mix(center, oppositeColor, finalOffset), 0.45);
#if XON_AA_MODE == 2
    // SMAA-Lite Ultra: blend span reconstruction with diagonal tangent filter so both shallow floor spans and 45-deg diagonals are silky smooth.
    return mix(tangentResult, spanColor, edgeBlend * 0.72);
#else
    return mix(tangentResult, spanColor, edgeBlend * 0.60);
#endif
#else
    return tangentResult;
#endif
#else
    return center;
#endif
#else
    return center;
#endif
}

#endif
