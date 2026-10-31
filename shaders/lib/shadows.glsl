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

vec2 xonShadowDepthGradient(vec3 shadowNDC, vec3 normal) {
    vec3 plane = (mat3(shadowModelView) * normal)
               / vec3(shadowProjection[0][0], shadowProjection[1][1], shadowProjection[2][2]);
    if (abs(plane.z) < 0.0001) return vec2(0.0);
    vec2 slope = -plane.xy / plane.z;
    float radial = length(shadowNDC.xy);
    float distortion = 0.32 + radial * 0.68;
    // Inverse distortion Jacobian maps a filtered texel offset back onto the receiving plane.
    vec2 radialSlope = shadowNDC.xy * (dot(shadowNDC.xy, slope) * 0.68 / (0.32 * max(radial, 0.0001)));
    return 0.20 * distortion * (slope + radialSlope);
}

float xonSurfaceShadowTap(vec3 coordinate, vec2 offset, vec2 depthGradient) {
    return texture(shadowtex0, coordinate + vec3(offset, dot(depthGradient, offset)));
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
    float distanceBias = length(playerPosition);
    // Tight close-range normal bias (~0.048 blocks) + sun-axis foliage offset prevents backlit grass/crop self-shadow flicker.
    vec3 lightDir = shadowModelViewInverse[2].xyz;
    float normalBias = (0.048 + 0.00070 * distanceBias + distortFactor * 0.042) * (1.70 - 0.70 * facing) * mix(1.0, 1.35, foliage);
    vec3 offsetPosition = playerPosition + normal * normalBias + lightDir * (0.022 + 0.115 * foliage);
    vec3 coordinate = xonShadowCoordinate(offsetPosition);
    if (any(lessThan(coordinate, vec3(0.005))) || any(greaterThan(coordinate, vec3(0.995)))) return fallback;
    coordinate.z -= 0.000032 + 0.000065 * (1.0 - facing) + foliage * 0.00024;
    vec2 depthGradient = vec2(0.0);
    if (foliage < 1.0) depthGradient = xonShadowDepthGradient(shadowNDC, normal) * (1.0 - foliage);
    // Hardware PCF also compares four neighboring texels, each at a different plane depth.
    coordinate.z -= (abs(depthGradient.x) + abs(depthGradient.y)) / float(shadowMapResolution);
    float radius = 0.75 / float(shadowMapResolution);
    // 3-tier distance-LOD hardware-PCF: 4 taps within 20m, 2 taps within 42m, 1 bilinear hardware-PCF tap (4 texels) beyond 42m.
    float visibility;
    if (distSq >= 1764.0) {
        visibility = texture(shadowtex0, coordinate);
    } else {
        vec2 o1 = vec2(radius, radius * 0.48);
#ifdef XON_SMOOTH_SHADOW_LOD
        // Collapse the two-tap kernel continuously into the distant hardware-PCF sample.
        float kernelScale = 1.0 - smoothstep(1296.0, 1764.0, distSq);
        o1 *= kernelScale;
#endif
        visibility = xonSurfaceShadowTap(coordinate, o1, depthGradient)
                   + xonSurfaceShadowTap(coordinate, -o1, depthGradient);
        if (distSq < 400.0) {
            vec2 o2 = vec2(-o1.y, o1.x);
#ifdef XON_SMOOTH_SHADOW_LOD
            o2 = mix(o2, o1, smoothstep(256.0, 400.0, distSq));
#endif
            visibility = (visibility
                        + xonSurfaceShadowTap(coordinate, o2, depthGradient)
                        + xonSurfaceShadowTap(coordinate, -o2, depthGradient)) * 0.25;
        } else {
            visibility *= 0.5;
        }
    }
    float boxFade = smoothstep(0.75, 0.97, edgeDist);
    float rangeFade = max(boxFade, smoothstep(shadowDistance * 0.88, maxDist, dist));
    return mix(visibility, fallback, rangeFade);
}

float xonRayVisibilityClip(vec3 shadowClip) {
    vec3 coordinate = xonDistortShadow(shadowClip) * 0.5 + 0.5;
    if (any(lessThan(coordinate, vec3(0.005))) || any(greaterThan(coordinate, vec3(0.995)))) return 0.0;
    coordinate.z -= 0.000025;
    return texture(shadowtex0, coordinate);
}

float xonWaterRayVisibilityClip(vec3 shadowClip) {
    vec3 coordinate = xonDistortShadow(shadowClip) * 0.5 + 0.5;
    if (any(lessThan(coordinate, vec3(0.005))) || any(greaterThan(coordinate, vec3(0.995)))) return 0.0;
    coordinate.z -= 0.000025;
    vec2 radius = vec2(1.25, 0.60) / float(shadowMapResolution);
    return 0.5 * (texture(shadowtex0, coordinate + vec3(radius, 0.0))
                + texture(shadowtex0, coordinate - vec3(radius, 0.0)));
}

float xonRayVisibility(vec3 playerPosition) {
    return xonRayVisibilityClip((shadowProjection * (shadowModelView * vec4(playerPosition, 1.0))).xyz);
}

float xonWaterRayVisibility(vec3 playerPosition) {
    return xonWaterRayVisibilityClip((shadowProjection * (shadowModelView * vec4(playerPosition, 1.0))).xyz);
}
#endif
#endif

#endif
