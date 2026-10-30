#ifndef XON_ATMOSPHERE
#define XON_ATMOSPHERE

// Computes distinct Overworld time-of-day weights from the 3D solar vector:
// x = Early Morning (East sunrise), y = High Noon, z = Warm Afternoon (West mid-sun), w = Evening Dusk (West sunset).
vec4 xonTimePhases(vec3 sun) {
    float day = smoothstep(-0.12, 0.10, sun.y);
    float eastBias = clamp(sun.x * 1.35 + 0.35, 0.0, 1.0);
    float westBias = clamp(-sun.x * 1.35 + 0.35, 0.0, 1.0);
    float lowSun = smoothstep(-0.08, 0.16, sun.y) * (1.0 - smoothstep(0.16, 0.52, sun.y));
    float midSun = smoothstep(0.18, 0.46, sun.y) * (1.0 - smoothstep(0.52, 0.84, sun.y));
    float highSun = smoothstep(0.48, 0.86, sun.y);
    float morning = lowSun * eastBias * day;
    float afternoon = midSun * westBias * day;
    float evening = lowSun * westBias * day;
    return vec4(morning, highSun * day, afternoon, evening) * XON_TIME_MOOD;
}

vec3 xonSunlightColor(vec3 sun) {
    float sunHeight = sun.y;
    vec4 phases = xonTimePhases(sun);
    float goldenHour = smoothstep(-0.04, 0.22, sunHeight) * (1.0 - smoothstep(0.22, 0.62, sunHeight));
    float noon = smoothstep(0.18, 0.72, sunHeight);
    vec3 dawnDusk = vec3(1.68, 0.88, 0.46);
    vec3 afternoon = vec3(1.42, 1.12, 0.78);
    vec3 midday = vec3(1.26, 1.19, 1.05);
    vec3 designed = mix(mix(dawnDusk, afternoon, smoothstep(0.02, 0.35, sunHeight)), midday, noon);
    designed = mix(designed, vec3(1.58, 0.94, 0.54), goldenHour * 0.45);
    // Distinct time-of-day moods: pearlescent rose-gold early morning, honey-gold afternoon, and fiery copper-amber evening.
    designed = mix(designed, vec3(1.54, 1.04, 0.82), clamp(phases.x * 0.65, 0.0, 0.85));
    designed = mix(designed, vec3(1.48, 1.08, 0.68), clamp(phases.z * 0.60, 0.0, 0.85));
    designed = mix(designed, vec3(1.74, 0.78, 0.38), clamp(phases.w * 0.70, 0.0, 0.85));
    return mix(vec3(1.15), designed, XON_WARMTH);
}

vec3 xonSunlightColor(float sunHeight) {
    return xonSunlightColor(vec3(0.0, sunHeight, 0.0));
}

vec3 xonSunlightColor() {
    return xonSunlightColor(xonSunDirection());
}

vec3 xonNightColor() {
    float phase = abs(float(moonPhase) - 4.0) * 0.25;
    return vec3(0.10, 0.15, 0.25) * mix(0.70, 1.0, phase);
}

vec3 xonSky(vec3 direction) {
#if XON_DIMENSION == -1
    vec3 base = max(xonToLinear(fogColor), vec3(0.012));
    return base * mix(0.70, 1.10, xonSaturate(direction.y * 0.5 + 0.5));
#elif XON_DIMENSION == 1
    float absY = abs(direction.y);
    float horizon = xonSquare(1.0 - absY) * (1.0 - absY);
    vec3 voidBlack = vec3(0.004, 0.002, 0.010);
    vec3 deepPurple = vec3(0.055, 0.024, 0.098);
    vec3 baseSky = mix(voidBlack, deepPurple, horizon);
    // Flowing cosmic End auroras and nebula ribbons across the upper and mid sky.
    float auraTime = frameTimeCounter * 0.18;
    float curtainA = sin(direction.x * 5.2 + direction.z * 3.7 + auraTime + sin(direction.z * 2.8 - auraTime * 0.7) * 1.4);
    float curtainB = cos(direction.z * 6.4 - direction.x * 4.1 - auraTime * 1.2 + cos(direction.x * 3.3 + auraTime * 0.5) * 1.3);
    float ribbon = xonSaturate(curtainA * 0.5 + 0.5) * xonSaturate(curtainB * 0.5 + 0.5);
    float verticalMask = smoothstep(-0.15, 0.35, direction.y) * (1.0 - smoothstep(0.45, 0.96, absY));
    float horizonAura = xonSquare(1.0 - absY) * xonSaturate(0.5 + 0.5 * sin(direction.x * 3.1 - direction.z * 2.4 + auraTime * 0.6));
    vec3 violetAura = vec3(0.18, 0.05, 0.34);
    vec3 magentaCore = vec3(0.32, 0.09, 0.42);
    vec3 nebulaGlow = mix(violetAura, magentaCore, ribbon) * (ribbon * verticalMask * 1.35 + horizonAura * 0.42) * XON_END_AURORA;
    return baseSky + nebulaGlow + vec3(0.18, 0.13, 0.28) * endFlashIntensity;
#else
    vec3 sun = xonSunDirection();
    float day = smoothstep(-0.12, 0.10, sun.y);
    vec4 phases = xonTimePhases(sun);
    float height = sqrt(xonSaturate(direction.y));
    float voidDepth = xonSaturate(-direction.y);
    float dusk = (1.0 - smoothstep(0.02, 0.52, abs(sun.y))) * day;
    float sunDot = dot(direction, sun);
    float towardSun = xonSaturate(sunDot * 0.5 + 0.5);
    vec3 zenith = vec3(0.08, 0.30, 0.80);
    vec3 horizon = vec3(0.46, 0.72, 0.99);
    // Shift zenith & horizon palette across Early Morning (rose-azure), Warm Afternoon (golden-teal), and Evening (twilight violet).
    zenith = mix(zenith, vec3(0.11, 0.34, 0.82), clamp(phases.x * 0.55, 0.0, 0.75));
    zenith = mix(zenith, vec3(0.09, 0.32, 0.76), clamp(phases.z * 0.50, 0.0, 0.75));
    zenith = mix(zenith, vec3(0.16, 0.18, 0.54), clamp(phases.w * 0.65, 0.0, 0.80));
    horizon = mix(horizon, vec3(0.76, 0.68, 0.86), clamp(phases.x * 0.55, 0.0, 0.75));
    horizon = mix(horizon, vec3(0.58, 0.73, 0.90), clamp(phases.z * 0.55, 0.0, 0.75));
    horizon = mix(horizon, vec3(0.62, 0.42, 0.64), clamp(phases.w * 0.60, 0.0, 0.80));
    vec3 vanillaTint = xonToLinear(skyColor);
    zenith *= mix(vec3(1.0), clamp(vanillaTint * 2.4 + 0.55, 0.70, 1.25), 0.25);
    vec3 clearDay = mix(horizon, zenith, height);
    float horizonCurve = xonSquare(xonSquare(1.0 - xonSaturate(abs(direction.y))));
    float sunsetBand = horizonCurve * dusk * (0.28 + 0.68 * towardSun * towardSun);
    vec3 morningBandHue = mix(vec3(0.76, 0.52, 0.72), vec3(1.32, 0.74, 0.48), towardSun);
    vec3 eveningBandHue = mix(vec3(0.85, 0.36, 0.54), vec3(1.36, 0.52, 0.20), towardSun);
    vec3 sunsetHue = mix(eveningBandHue, morningBandHue, clamp(sun.x * 1.5 + 0.5, 0.0, 1.0));
    clearDay = mix(clearDay, sunsetHue, sunsetBand);
    // Distinct lower-void mood below the horizon (direction.y < 0) so void color matches morning mist, afternoon warmth, or evening twilight.
    vec3 dayVoid = mix(vec3(0.18, 0.34, 0.58), vec3(0.28, 0.22, 0.38), clamp((phases.x + phases.w) * 0.65, 0.0, 0.85));
    clearDay = mix(clearDay, dayVoid, smoothstep(0.0, 0.45, voidDepth) * 0.65);
    vec3 clearNight = mix(vec3(0.032, 0.048, 0.092), vec3(0.008, 0.016, 0.040), height);
    clearNight = mix(clearNight, vec3(0.004, 0.008, 0.022), smoothstep(0.0, 0.45, voidDepth));
    vec3 result = mix(clearNight, clearDay, day);
    float storm = xonSaturate(rainStrength * 0.78 + thunderStrength * 0.22);
    vec3 overcast = mix(vec3(0.32, 0.41, 0.53), vec3(0.16, 0.23, 0.34), height);
    overcast *= mix(0.20, 1.0, day) * (1.0 - thunderStrength * 0.13);
    result = mix(result, overcast, storm);
    float s2 = xonSquare(xonSaturate(sunDot));
    float s4 = s2 * s2;
    float s8 = s4 * s4;
    float mieHaze = s4 * 0.045 + s8 * s8 * s8 * 0.11;
    result += xonSunlightColor(sun) * mieHaze * day * (1.0 - storm);
    // Subtle silver-blue nocturnal lunar glow around the moon direction (-sun) at night.
    float m2 = xonSquare(xonSaturate(-sunDot));
    float m4 = m2 * m2;
    result += xonNightColor() * (m4 * m4 * 0.38) * (1.0 - day) * (1.0 - storm);
    result += vec3(0.34, 0.39, 0.48) * lightningBoltPosition.w;
    return result;
#endif
}

vec3 xonFog(vec3 color, vec3 viewPosition, float skylight) {
    float distanceToEye = length(viewPosition);
    vec3 worldOffset = vec3(0.0);
    float borderFog = 0.0;
    if (isEyeInWater == 0) {
        worldOffset = mat3(gbufferModelViewInverse) * viewPosition;
        float radialDist = max(length(worldOffset.xz), distanceToEye * 0.92);
        if (far > 16.0) {
            float fogStartDist = min(far * (0.56 / clamp(XON_FOG_AMOUNT, 0.60, 1.40)), far * 0.78);
            float fogEndDist = max(far - 12.0, far * 0.90);
            borderFog = smoothstep(fogStartDist, fogEndDist, radialDist);
            borderFog = borderFog * borderFog * (3.0 - 2.0 * borderFog);
        }
    }
#if XON_DIMENSION == 0
#ifndef XON_AIR_FOG
    if (isEyeInWater == 0 && rainStrength < 0.001 && thunderStrength < 0.001 && borderFog < 0.0001) {
        return color * exp(-distanceToEye * max(blindness, darknessFactor) * 0.16);
    }
#endif
#endif
    vec3 fog;
    float amount;
    if (isEyeInWater == 1) {
        float exposure = max(xonSaturate(float(eyeBrightnessSmooth.y) / 240.0), skylight);
        float day = xonDaylight();
        vec3 waterTint = mix(vec3(0.035, 0.22, 0.30),
                            max(xonToLinear(fogColor), vec3(0.025)), 0.40);
        fog = waterTint * mix(0.28, 1.15, max(exposure, day * 0.65));
        float effectiveDist = max(distanceToEye - 6.0, 0.0);
        amount = (1.0 - exp(-effectiveDist * 0.016 * XON_FOG_AMOUNT)) * 0.82;
    } else if (isEyeInWater == 2) {
        fog = vec3(0.63, 0.075, 0.008);
        amount = 1.0 - exp(-distanceToEye * 1.8);
    } else if (isEyeInWater == 3) {
        fog = vec3(0.75, 0.83, 0.92);
        amount = 1.0 - exp(-distanceToEye * 0.9);
    } else {
#if XON_DIMENSION != -1
        // Normalizing after clamping the horizon is sufficient; the prior scale cancels.
        vec3 skyDir = xonSafeNormalize(vec3(worldOffset.x, max(worldOffset.y, 0.0), worldOffset.z));
        fog = xonSky(skyDir);
#endif
#if XON_DIMENSION == -1
        float density = 0.0065;
        fog = max(xonToLinear(fogColor), vec3(0.02, 0.01, 0.01));
        float netherDist = max(distanceToEye - 12.0, 0.0);
        amount = 1.0 - exp(-netherDist * density * XON_FOG_AMOUNT);
        float terrainFade = smoothstep(max(fogStart, far * 0.55),
                                       max(max(fogEnd, far), fogStart + 1.0), distanceToEye);
        amount = max(amount, max(terrainFade, borderFog));
#elif XON_DIMENSION == 1
        float density = 0.0012;
        amount = 1.0 - exp(-distanceToEye * density * XON_FOG_AMOUNT);
        float terrainFade = smoothstep(max(fogStart, far * 0.68),
                                       max(max(fogEnd, far), fogStart + 1.0), distanceToEye);
        amount = max(amount, max(terrainFade, borderFog));
#else
        float density = 0.0;
#ifdef XON_AIR_FOG
        density = mix(0.00065, 0.0042, rainStrength)
                + thunderStrength * 0.0012;
        density *= mix(0.25, 1.0, skylight);
#else
        if (rainStrength > 0.001 || thunderStrength > 0.001) {
            density = (rainStrength * 0.0035 + thunderStrength * 0.0012) * mix(0.25, 1.0, skylight);
        }
#endif
        amount = 1.0 - exp(-distanceToEye * density * XON_FOG_AMOUNT);
        float terrainFade = smoothstep(max(fogStart, far * 0.68),
                                       max(max(fogEnd, far), fogStart + 1.0), distanceToEye);
        amount = max(amount, max(terrainFade, borderFog));
#endif
    }
    float visionFog = 1.0 - exp(-distanceToEye * max(blindness, darknessFactor) * 0.16);
    color = mix(color, fog, xonSaturate(amount));
    return mix(color, vec3(0.0), xonSaturate(visionFog));
}

#endif
