#ifndef XON_END_ATMOSPHERE
#define XON_END_ATMOSPHERE

#if XON_DIMENSION == 1
vec3 xonEndAmbient(vec3 normal) {
    float upperHemisphere = normal.y * 0.5 + 0.5;
    vec3 ambient = mix(vec3(0.280, 0.215, 0.430), vec3(0.400, 0.285, 0.620), upperHemisphere);
    float auraFacing = max(dot(normal, vec3(0.480, 0.400, -0.781)), 0.0);
    return ambient + vec3(0.055, 0.018, 0.075) * auraFacing;
}

float xonEndLayerMean(float startHeight, float endHeight) {
    const float layerCenter = 56.0;
    const float layerHalfHeight = 88.0;
    float start = (startHeight - layerCenter) / layerHalfHeight;
    float finish = (endHeight - layerCenter) / layerHalfHeight;
    float span = finish - start;
    if (abs(span) < 0.001) return 1.0 - smoothstep(0.0, 1.0, abs((start + finish) * 0.5));
    vec2 height = clamp(vec2(start, finish), -1.0, 1.0);
    vec2 height2 = height * height;
    // Integrating the smooth height layer avoids view-angle bands and ray-march noise.
    vec2 integral = height * (1.0 - height2 + 0.5 * height2 * abs(height));
    return xonSaturate((integral.y - integral.x) / span);
}

vec4 xonEndHaze(vec3 worldOffset, float distanceToEye) {
    const float clearDistance = 8.0;
    float hazeDistance = max(distanceToEye - clearDistance, 0.0);
    if (hazeDistance <= 0.0 || XON_ATMOSPHERE_DENSITY < 0.001) return vec4(0.0);
    vec3 startOffset = worldOffset * (clearDistance / max(distanceToEye, clearDistance));
    float layer = xonEndLayerMean(cameraPosition.y + startOffset.y, cameraPosition.y + worldOffset.y);
    const mat2 driftFrequency = mat2(0.018, -0.009, 0.011, 0.024);
    vec2 halfSpan = driftFrequency * (worldOffset.xz - startOffset.xz) * 0.5;
    vec2 meanWave;
    meanWave.x = abs(halfSpan.x) < 0.01 ? 1.0 - halfSpan.x * halfSpan.x / 6.0 : sin(halfSpan.x) / halfSpan.x;
    meanWave.y = abs(halfSpan.y) < 0.01 ? 1.0 - halfSpan.y * halfSpan.y / 6.0 : sin(halfSpan.y) / halfSpan.y;
    vec2 phase = driftFrequency * cameraPosition.xz - frameTimeCounter * vec2(6.2831853 / 180.0, -6.2831853 / 300.0);
    // A path-averaged wave keeps distant wisps smooth instead of painting patterns on blocks.
    float drift = 0.5 + dot(sin(phase + driftFrequency * startOffset.xz + halfSpan) * meanWave, vec2(0.32, 0.18));
    float opticalDepth = hazeDistance * (0.0020 * layer + 0.0004 * (0.5 + drift))
                       * XON_ATMOSPHERE_DENSITY * XON_FOG_AMOUNT;
    vec3 radiance = mix(vec3(0.105, 0.047, 0.235), vec3(0.190, 0.048, 0.220), drift * 0.65);
    radiance += vec3(0.10, 0.035, 0.14) * endFlashIntensity;
    return vec4(radiance, 1.0 - exp(-opticalDepth));
}
#endif

#endif
