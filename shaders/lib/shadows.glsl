#ifndef XON_SHADOW_LIBRARY
#define XON_SHADOW_LIBRARY

vec3 xonDistortShadow(vec3 position) {
    position.xy /= 0.32 + length(position.xy) * 0.68;
    position.z *= 0.20;
    return position;
}

#if XON_DIMENSION == 0
#ifdef XON_SHADOWS
uniform sampler2DShadow shadowtex0;

vec3 xonShadowCoordinate(vec3 playerPosition) {
    vec4 position = shadowProjection * shadowModelView * vec4(playerPosition, 1.0);
    return xonDistortShadow(position.xyz / position.w) * 0.5 + 0.5;
}

float xonShadowVisibility(vec3 playerPosition, vec3 normal, float facing, float skylight, float foliage) {
    float distSq = dot(playerPosition.xz, playerPosition.xz);
    float maxDist = shadowDistance * 0.98;
    float fallback = smoothstep(0.60, 0.96, skylight);
    if (distSq >= maxDist * maxDist) return fallback;
    vec4 rawShadow = shadowProjection * shadowModelView * vec4(playerPosition, 1.0);
    vec3 shadowNDC = rawShadow.xyz / max(abs(rawShadow.w), 0.00001);
    float edgeDist = max(abs(shadowNDC.x), abs(shadowNDC.y));
    if (edgeDist >= 0.98) return fallback;
    float dist = sqrt(distSq);
    float distortFactor = 0.32 + length(shadowNDC.xy) * 0.68;
    float pDistSq = dot(playerPosition, playerPosition);
    float distanceBias = pDistSq * inversesqrt(sqrt(max(pDistSq, 0.0001)));
    float normalBias = (0.095 + 0.00075 * distanceBias + distortFactor * 0.05) * (1.85 - 0.85 * facing) * mix(1.0, 1.35, foliage);
    vec3 offsetPosition = playerPosition + normal * normalBias;
    vec3 coordinate = xonShadowCoordinate(offsetPosition);
    if (any(lessThan(coordinate, vec3(0.005))) || any(greaterThan(coordinate, vec3(0.995)))) return fallback;
    coordinate.z -= 0.000035 + 0.000075 * (1.0 - facing) + foliage * 0.00012;
    float radius = 0.72 / float(shadowMapResolution);
    // Rotated 2-tap hardware-PCF kernel for smooth penumbra edges at minimum bandwidth.
    float angle = fract(52.9829189 * fract(dot(playerPosition.xz + playerPosition.y, vec2(7.13, 13.71)))) * 3.14159265;
    vec2 rot = vec2(cos(angle), sin(angle)) * radius;
    float visibility = (texture(shadowtex0, coordinate + vec3(rot, 0.0))
                      + texture(shadowtex0, coordinate - vec3(rot, 0.0))) * 0.5;
    float boxFade = smoothstep(0.75, 0.97, edgeDist);
    float rangeFade = max(boxFade, smoothstep(shadowDistance * 0.72, maxDist, dist));
    return mix(visibility, fallback, rangeFade);
}

float xonRayVisibility(vec3 playerPosition) {
    vec3 coordinate = xonShadowCoordinate(playerPosition);
    if (any(lessThan(coordinate, vec3(0.005))) || any(greaterThan(coordinate, vec3(0.995)))) return 0.0;
    coordinate.z -= 0.000025;
    return texture(shadowtex0, coordinate);
}
#endif
#endif

#endif
