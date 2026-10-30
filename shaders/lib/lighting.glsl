#ifndef XON_LIGHTING
#define XON_LIGHTING

vec3 xonLighting(vec3 albedo, vec3 normal, vec3 viewPosition, vec3 playerPosition, vec2 lightLevels,
                 float emission, float foliage, out float sunVisibility) {
    sunVisibility = 1.0;
    // Soft skylight curve keeps partial shade readable without boosting full open-sky brightness.
    float sky = mix(lightLevels.y, xonSquare(lightLevels.y), 0.55);
    float block = lightLevels.x * lightLevels.x * (0.72 + 0.28 * lightLevels.x);
    // Sculptural 6-axis directional face contrast so castle walls, pillars, and ledges separate cleanly in both sun and shade.
    float hemisphere = (0.74 + max(normal.y, 0.0) * 0.26) * (0.92 + abs(normal.x) * 0.08 - abs(normal.z) * 0.04);
    float shadowForm = (0.72 + 0.28 * abs(normal.y + 0.25)) * (0.90 + 0.10 * abs(normal.x));
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
    vec4 phases = xonTimePhases(sun);
    float golden = smoothstep(-0.04, 0.22, sun.y) * (1.0 - smoothstep(0.22, 0.58, sun.y));
    vec3 keyDirection = xonKeyDirection();
    float nDotL = dot(normal, keyDirection);
    float facing = max(nDotL, 0.0);
    facing = mix(facing, facing * 0.48 + 0.52, foliage);
    // Wrapped grazing light lets sunlight play softly across castle reliefs and side walls without flattening shadow contrast.
    float grazing = xonSquare(clamp(nDotL * 0.45 + 0.30, 0.0, 1.0)) * (1.0 - facing) * (1.0 - foliage) * 0.16 * xonSaturate(nDotL * 6.25);
    float openSky = smoothstep(0.55, 0.97, lightLevels.y);
#if defined XON_SHADOWS && !defined XON_HAND
    if ((facing + grazing) > 0.001 && openSky > 0.001) {
        sunVisibility = xonShadowVisibility(playerPosition, normal, facing, lightLevels.y, foliage);
    }
    openSky *= sunVisibility;
#endif
    float diffuseFacing = facing * (0.86 + 0.14 * facing);
    float direct = (diffuseFacing + grazing) * openSky * (1.0 - rainStrength * 0.90);
    float sss = 0.0;
    if (foliage > 0.0) {
        vec3 viewDir = xonSafeNormalize(playerPosition);
        float vDotS = xonSaturate(dot(viewDir, keyDirection));
        sss = foliage * openSky * (vDotS * vDotS * vDotS) * 0.36 * (1.0 - rainStrength * 0.85);
    }
    // Surface form follows the light, avoiding camera-dependent shine on matte blocks.
    float edgeRim = facing * (1.0 - facing) * direct * (1.0 - foliage) * 0.16;
    // Subtle blue shade is baked into the fill palette, avoiding another per-pixel grading operation.
    vec3 ambientBase = mix(vec3(0.2813, 0.39156, 0.5852), vec3(0.3395, 0.37148, 0.53295), golden * 0.55);
    // Shift ambient shadow mood across Early Morning (dewy cyan-rose), Afternoon (cobalt-indigo), and Evening (twilight violet).
    ambientBase = mix(ambientBase, vec3(0.28, 0.40, 0.63), clamp(phases.x * 0.55, 0.0, 0.75));
    ambientBase = mix(ambientBase, vec3(0.27, 0.36, 0.60), clamp(phases.z * 0.50, 0.0, 0.75));
    ambientBase = mix(ambientBase, vec3(0.35, 0.28, 0.54), clamp(phases.w * 0.65, 0.0, 0.80));
    vec3 hemisphereTint = mix(vec3(1.08, 1.00, 0.88), vec3(0.97, 1.00, 1.04), normal.y * 0.5 + 0.5);
    float skyHemisphere = 0.58 + 0.42 * max(normal.y, 0.0);
    vec3 ambientClear = ambientBase * hemisphere * hemisphereTint * skyHemisphere;
    vec3 ambientRain = vec3(0.38, 0.46, 0.61) * hemisphere;
    vec3 ambient = mix(xonNightColor(), mix(ambientClear, ambientRain, rainStrength), day);
    vec3 key = mix(xonNightColor() * 0.68, xonSunlightColor(sun), day);
    // Subtle bounce into shaded faces only ((1.0 - direct) keeps sunlit surfaces untouched).
    float archUpfill = max(-normal.y, 0.0) * 0.10 + (1.0 - abs(normal.y)) * 0.035;
    vec3 bounce = (key * (0.035 + archUpfill * 0.5) + ambient * 0.08) * (sky * (1.0 - direct) * day * (1.0 - rainStrength * 0.5));
    vec3 celestialLight = (direct + sss + edgeRim) * key * (1.80 * XON_SUN_STRENGTH);
    vec3 illumination = sky * ambient + bounce + celestialLight;
#if defined XON_CLOUD_LIBRARY && !defined XON_HAND
    float skyExposure = smoothstep(0.35, 0.92, lightLevels.y);
    float cloudDistSq = dot(playerPosition.xz, playerPosition.xz);
    float cloudRange = max(far, 128.0);
    if (skyExposure > 0.001 && isEyeInWater == 0 && cloudDistSq < cloudRange * cloudRange && XON_GROUND_SHADOW_STRENGTH > 0.001) {
        // Let landscape-scale patches reach the horizon instead of disappearing in a 96-block camera bubble.
        float distFade = 1.0 - smoothstep(cloudRange * cloudRange * 0.64, cloudRange * cloudRange, cloudDistSq);
        float cloudSignal = xonCloudGroundLight(playerPosition.xz + cameraPosition.xz) * skyExposure * distFade;
        float cloudShadow = min(max(-cloudSignal, 0.0), 1.35);
        float cloudBreak = max(cloudSignal, 0.0);
        float zenithFacing = mix(0.52 + 0.48 * max(normal.y, 0.0), 0.92, foliage);
        // Removing key light reveals the existing cool sky fill; clear gaps retain the sun/moon's own color.
        illumination += celestialLight * (cloudBreak * 0.08 - cloudShadow * 0.64);
        illumination -= sky * ambient * (cloudShadow * zenithFacing * 0.08);
        float moonOpening = cloudBreak * (1.0 - day) * openSky * facing;
        illumination *= 1.0 + moonOpening * 0.28;
    }
#endif
    if (lightningBoltPosition.w > 0.001) {
        float boltDistance = length((playerPosition - lightningBoltPosition.xyz).xz);
        float flash = lightningBoltPosition.w * exp(-boltDistance * 0.012) * sky;
        illumination += vec3(0.65, 0.73, 0.92) * flash;
    }
    // Strictly target dark/unlit areas: shadowDeficit is 0.0 wherever illumination is already >= minShadowLight (zero impact on bright/lit areas).
    vec3 dayShadowFill = vec3(0.2425, 0.32128, 0.42845) * shadowForm;
    vec3 nightShadowFill = vec3(0.1164, 0.15562, 0.214225) * shadowForm;
    vec3 minShadowLight = mix(nightShadowFill, dayShadowFill, day) * XON_DARK_LIFT;
    vec3 shadowDeficit = max(minShadowLight - illumination, vec3(0.0));
    illumination += shadowDeficit * (1.0 - direct);
#endif
#if XON_DIMENSION != 0
    vec3 dimShadowDeficit = max(vec3(0.08, 0.09, 0.12) * shadowForm * XON_DARK_LIFT - illumination, vec3(0.0));
    illumination += dimShadowDeficit;
#endif
    if (isEyeInWater == 1) {
        float waterDay = smoothstep(-0.15, 0.15, xonSunDirection().y);
        vec3 underwaterFill = mix(vec3(0.06, 0.13, 0.20), vec3(0.14, 0.26, 0.34), waterDay);
        illumination = max(illumination, underwaterFill * hemisphere);
        illumination += vec3(0.025, 0.06, 0.08) * sky * waterDay;
    }
    vec3 torchColor = mix(vec3(2.05, 1.82, 1.48), vec3(2.55, 1.50, 0.67), clamp(XON_BLOCKLIGHT_WARMTH, 0.0, 1.5));
    // Warm falloff and a restrained ivory core keep nearby pale blocks from turning orange.
    vec3 localLightColor = mix(torchColor, vec3(2.30, 1.72, 1.04), block * 0.35 * XON_BLOCKLIGHT_WARMTH);
    illumination += block * localLightColor * XON_LOCAL_LIGHT_STRENGTH;
#ifdef XON_HAND_LIGHT
    int maxHeld = max(heldBlockLightValue, heldBlockLightValue2);
    if (maxHeld > 0) {
        float heldLight = float(maxHeld) * (1.0 / 15.0);
        float handFalloff = xonSaturate(1.0 - length(viewPosition) * (1.0 / 12.0));
        illumination += torchColor * (0.44 * XON_LOCAL_LIGHT_STRENGTH) * heldLight * handFalloff * handFalloff;
    }
#endif
    illumination = mix(illumination, illumination * 1.35 + vec3(0.08, 0.10, 0.14), nightVision);
    illumination = mix(illumination, max(illumination, vec3(3.20)), emission);
    // Dark-albedo toe lift activates ONLY inside dark shadows (isDarkArea -> 0 in sunlit or torchlit areas).
    float maxIllum = max(illumination.r, max(illumination.g, illumination.b));
    float isDarkArea = 1.0 - smoothstep(0.18, 0.52, maxIllum);
    float peakAlbedo = max(albedo.r, max(albedo.g, albedo.b));
    float darkAlbedoLift = (1.0 - smoothstep(0.015, 0.22, peakAlbedo)) * (1.0 - emission) * isDarkArea;
    vec3 effectiveAlbedo = mix(albedo, pow(max(albedo, vec3(0.0005)), vec3(0.68)) * 0.72, darkAlbedoLift * 0.65);
    // Sunlit high-albedo damper (sand, snow, white wool): dims outdoor sunlit glare to ~70% while leaving indoor quartz/whites 100% untouched.
    float albedoLuma = dot(albedo, vec3(0.2126, 0.7152, 0.0722));
    float minChannel = min(albedo.r, min(albedo.g, albedo.b));
    float brightAlbedo = smoothstep(0.45, 0.75, albedoLuma) * smoothstep(0.25, 0.55, minChannel) * (1.0 - emission);
    float excessLight = smoothstep(1.10, 2.25, maxIllum);
    illumination *= mix(1.0, 0.68, brightAlbedo * excessLight);
    return effectiveAlbedo * illumination + illumination * (0.018 * darkAlbedoLift);
}

#endif
