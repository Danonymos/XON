#ifndef XON_GRADE_LIBRARY
#define XON_GRADE_LIBRARY

#ifdef XON_COLOR_GRADE
uniform sampler2D xonGradeLUT;
#endif

vec3 xonApplyGrade(vec3 displayColor) {
#ifdef XON_COLOR_GRADE
    vec3 coordinate = clamp(displayColor, 0.0, 1.0) * 15.0;
    float slice = floor(coordinate.b);
    float nextSlice = min(slice + 1.0, 15.0);
    vec2 uvA = vec2(coordinate.r + slice * 16.0 + 0.5, coordinate.g + 0.5) * vec2(1.0 / 256.0, 1.0 / 16.0);
    vec2 uvB = vec2(coordinate.r + nextSlice * 16.0 + 0.5, coordinate.g + 0.5) * vec2(1.0 / 256.0, 1.0 / 16.0);
    vec3 graded = mix(texture(xonGradeLUT, uvA).rgb, texture(xonGradeLUT, uvB).rgb, fract(coordinate.b));
    vec3 result = mix(displayColor, graded, XON_GRADE_STRENGTH);
    // Default XON_SATURATION = 0.70 scales saturation softly (~0.88x of 0.2); 1.00 = full 0.2 saturation; >1.00 = boosted.
    float satFactor = XON_SATURATION < 0.70
                    ? (XON_SATURATION / 0.70) * 0.88
                    : 0.88 + (XON_SATURATION - 0.70) * (0.12 / 0.30);
    float luma = dot(result, vec3(0.2126, 0.7152, 0.0722));
    result = clamp(mix(vec3(luma), result, satFactor), 0.0, 1.0);
    if (abs(XON_CONTRAST - 1.0) > 0.001) {
        result = clamp(0.5 + (result - 0.5) * XON_CONTRAST, 0.0, 1.0);
    }
    return result;
#else
    return displayColor;
#endif
}

#endif
