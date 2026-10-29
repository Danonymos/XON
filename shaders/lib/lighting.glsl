#ifndef XON_LIGHTING
#define XON_LIGHTING

vec3 xonLighting(vec3 albedo, vec3 normal, vec3 viewPosition, vec3 playerPosition, vec2 lightLevels,
                 float emission, float foliage, out float sunVisibility) {
    sunVisibility = 1.0;
    float sky = xonSquare(lightLevels.y);
    float block = lightLevels.x * lightLevels.x * lightLevels.x;
    float hemisphere = (0.74 + max(normal.y, 0.0) * 0.26) * (0.94 + abs(normal.z) * 0.06);
#if XON_DIMENSION == -1
    vec3 biomeAmbient = max(xonToLinear(fogColor), vec3(0.05, 0.03, 0.03));
    float netherVertical = 0.72 + abs(normal.y + 0.35) * 0.28;
    float lavaUpfill = max(-normal.y, 0.0) * 0.45 + abs(normal.x) * 0.15;
    vec3 illumination = (vec3(0.46, 0.35, 0.34) + biomeAmbient * 1.15) * netherVertical
                      + vec3(0.32, 0.14, 0.06) * lavaUpfill;
#elif XON_DIMENSION == 1
    float endVertical = 0.75 + abs(normal.y + 0.25) * 0.25;
    vec3 illumination = vec3(0.38, 0.33, 0.48) * endVertical;
    illumination += vec3(0.28, 0.20, 0.36) * endFlashIntensity;
#else
    vec3 sun = xonSunDirection();
    float day = smoothstep(-0.12, 0.10, sun.y);
    float golden = smoothstep(-0.04, 0.22, sun.y) * (1.0 - smoothstep(0.22, 0.58, sun.y));
    vec3 keyDirection = sun * (sun.y >= 0.0 ? 1.0 : -1.0);
    float facing = max(dot(normal, keyDirection), 0.0);
    facing = mix(facing, facing * 0.48 + 0.52, foliage);
    float openSky = smoothstep(0.55, 0.97, lightLevels.y);
#if defined XON_SHADOWS && !defined XON_HAND
    if (facing > 0.001 && openSky > 0.001) {
        sunVisibility = xonShadowVisibility(playerPosition, normal, facing, lightLevels.y, foliage);
    }
    openSky *= sunVisibility;
#endif
    float direct = facing * openSky * (1.0 - rainStrength * 0.90);
    // Subsurface foliage back-scattering when looking toward the sun.
    vec3 viewDir = xonSafeNormalize(playerPosition);
    float vDotS = xonSaturate(dot(viewDir, keyDirection));
    float sss = foliage * openSky * (vDotS * vDotS * vDotS) * 0.38 * (1.0 - rainStrength * 0.85);
    vec3 ambientClear = mix(vec3(0.26, 0.37, 0.58), vec3(0.34, 0.35, 0.52), golden * 0.55) * hemisphere;
    vec3 ambientRain = vec3(0.38, 0.46, 0.61) * hemisphere;
    vec3 ambient = mix(xonNightColor(), mix(ambientClear, ambientRain, rainStrength), day);
    vec3 key = mix(xonNightColor() * 0.68, xonSunlightColor(sun.y), day);
    // Subtle warm bounce light into shaded faces under open sky.
    vec3 bounce = key * (sky * (1.0 - direct) * 0.055 * day * (1.0 - rainStrength));
    vec3 illumination = sky * ambient + bounce + (direct + sss) * key * 1.88;
#if defined XON_CLOUD_LIBRARY && !defined XON_HAND
    float skyExposure = smoothstep(0.35, 0.92, lightLevels.y);
    if (skyExposure > 0.001 && isEyeInWater == 0) {
        // Separate overhead zenith light with ~15-20 block radius moving Voronoi shadow cells and bright highlight zones.
        float cloudSignal = xonCloudGroundLight(playerPosition.xz + cameraPosition.xz) * skyExposure;
        float cloudShadow = max(-cloudSignal, 0.0);
        float cloudBreak = max(cloudSignal, 0.0);
        float zenithFacing = mix(0.52 + 0.48 * max(normal.y, 0.0), 0.92, foliage);
        vec3 shadowTint = mix(vec3(1.0), vec3(0.48, 0.55, 0.68), cloudShadow * zenithFacing);
        illumination *= shadowTint;
        vec3 zenithLight = mix(vec3(0.12, 0.18, 0.30), vec3(1.12, 1.04, 0.90), day);
        illumination *= 1.0 + cloudBreak * zenithFacing * 0.22;
        illumination += zenithLight * (cloudBreak * zenithFacing * (0.28 + 0.20 * openSky));
    }
#endif
    if (lightningBoltPosition.w > 0.001) {
        float boltDistance = length((playerPosition - lightningBoltPosition.xyz).xz);
        float flash = lightningBoltPosition.w * exp(-boltDistance * 0.012) * sky;
        illumination += vec3(0.65, 0.73, 0.92) * flash;
    }
#endif
    float minimumLight = (1.0 - sky) * 0.010;
    illumination += minimumLight * vec3(0.82, 0.91, 1.0);
    if (isEyeInWater == 1) {
        float waterDay = smoothstep(-0.15, 0.15, xonSunDirection().y);
        vec3 underwaterFill = mix(vec3(0.06, 0.13, 0.20), vec3(0.22, 0.42, 0.52), waterDay);
        illumination = max(illumination, underwaterFill * hemisphere);
        illumination += vec3(0.08, 0.18, 0.24) * sky * waterDay;
    }
    illumination += block * vec3(2.65, 1.55, 0.69);
#ifdef XON_HAND_LIGHT
    int maxHeld = max(heldBlockLightValue, heldBlockLightValue2);
    if (maxHeld > 0) {
        float heldLight = float(maxHeld) * (1.0 / 15.0);
        float handFalloff = xonSaturate(1.0 - length(viewPosition) * (1.0 / 12.0));
        illumination += vec3(1.10, 0.71, 0.35) * heldLight * handFalloff * handFalloff;
    }
#endif
    illumination = mix(illumination, max(illumination, vec3(0.78)), nightVision);
    illumination = mix(illumination, max(illumination, vec3(3.20)), emission);
    return albedo * illumination;
}

#endif
