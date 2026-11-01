#ifndef XON_CLOUD_LIBRARY
#define XON_CLOUD_LIBRARY

#if (XON_CLOUD_STYLE == 1 && XON_DIMENSION == 0) || defined XON_WATER || defined XON_TERRAIN
uniform sampler2D noisetex;
#endif

#if XON_CLOUD_STYLE == 1 && XON_DIMENSION == 0
const mat2 XON_CLOUD_ROT = mat2(0.80, -0.60, 0.60, 0.80);
const float XON_CLOUD_CYCLE = 900.0;

vec3 xonCloudFormationWeights() {
#if XON_CLOUD_FORMATION == 1
    return vec3(1.0, 0.0, 0.0);
#elif XON_CLOUD_FORMATION == 2
    return vec3(0.0, 1.0, 0.0);
#elif XON_CLOUD_FORMATION == 3
    return vec3(0.0, 0.0, 1.0);
#else
    float phase = mod(frameTimeCounter * (3.0 / XON_CLOUD_CYCLE), 3.0);
    vec3 distanceToStyle = abs(vec3(phase) - vec3(0.0, 1.0, 2.0));
    distanceToStyle = min(distanceToStyle, 3.0 - distanceToStyle);
    return 1.0 - smoothstep(vec3(0.0), vec3(1.0), distanceToStyle);
#endif
}

vec2 xonCloudWind() {
    // Close the path at Iris's hourly timer reset, including each sheared noise layer.
    const float frequency = 6.28318530718 / 3600.0;
    float phase = mod(frameTimeCounter, 3600.0) * frequency;
    return mat2(2.2, 0.55, -0.55, 2.2) * vec2(sin(phase), 1.0 - cos(phase)) / frequency;
}

// Pure ALU hashes (zero SFU sin() stalls and full precision at large server coordinates).
vec2 xonHash22(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
}

// Fast 2x2 nearest-quadrant Worley cellular sphere field (4 ALU-only iterations + 1 sqrt, zero sin() stalls).
float xonWorleyDomes(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 start = step(vec2(0.5), f) - vec2(1.0);
    float minDistSq = 4.0;
    for (int y = 0; y <= 1; ++y) {
        for (int x = 0; x <= 1; ++x) {
            vec2 neighbor = start + vec2(float(x), float(y));
            vec2 rnd = xonHash22(i + neighbor);
            vec2 diff = neighbor + 0.16 + 0.68 * rnd - f;
            minDistSq = min(minDistSq, dot(diff, diff));
        }
    }
    float puff = xonSaturate(1.0 - sqrt(minDistSq) * 1.05);
    return puff * (1.35 - 0.35 * puff);
}

// Evaluates the continuous 3D heightfield H(x,z) of the cumulus cloud deck:
// x = opacity/density [0..1], y = 3D dome relief height [0..1] for normal & self-shadow calculation.
vec2 xonCloudHeightfield(vec2 position, float distFadeDetail, bool detailed, vec3 formation, vec2 wind) {
    vec2 shape = mix(vec2(1.0), vec2(0.38, 1.45), formation.z);
    float scale = dot(formation, vec3(1.0, 1.65, 0.78));
    vec2 uv = position * shape * (scale / 3600.0);
    vec3 n0 = texture(noisetex, uv).rgb;
    vec2 warp = (n0.gb - 0.5) * 0.10;
    vec3 n1 = texture(noisetex, XON_CLOUD_ROT * (uv * 2.15 + warp - wind * 0.00008) + vec2(0.17, 0.31)).rgb;
    vec3 n2 = texture(noisetex, XON_CLOUD_ROT * (uv * 4.65 - warp * 1.3 + wind * 0.00012) + vec2(0.43, 0.67)).rgb;

    // Macro cloud continents from smooth periodic noise.
    float continent = xonSaturate((n0.r * 0.62 + n0.g * 0.38 - 0.5) * 2.15 + 0.52);
    float subContinent = xonSaturate((n1.r * 0.58 + n1.b * 0.42 - 0.5) * 2.05 + 0.50);

    // True Perlin-Worley cellular spheres warped by wind flow for round, fluffy cauliflower cumulus domes.
    vec2 cellCoord = position * shape * (scale / 240.0) + (n0.rg - 0.5) * 1.55 + (n1.gb - 0.5) * 0.70;
    float majorDomes = xonWorleyDomes(cellCoord);
    float midPuffs = detailed ? xonWorleyDomes(XON_CLOUD_ROT * cellCoord * 2.25 + (n2.rg - 0.5) * 0.75)
                              : (1.0 - abs(n1.g * 2.0 - 1.0));
    float fineCurls = 1.0 - abs(n2.r * 1.2 + n2.g * 0.8 - 1.0);

    float billows = majorDomes * 0.54 + midPuffs * 0.30 + mix(midPuffs, fineCurls, distFadeDetail) * 0.16;

    // Combine macro cloud islands with cellular Worley domes so edges have round puffy cumulus silhouettes.
    float macroMass = continent * 0.60 + subContinent * 0.40;
    float field = mix(macroMass, billows, dot(formation, vec3(0.30, 0.64, 0.16)));

    float threshold = clamp(mix(0.475, 0.305, rainStrength) + formation.y * 0.035 - (XON_CLOUD_DENSITY - 1.0) * 0.11, 0.22, 0.65);
    float raw = smoothstep(threshold, threshold + dot(formation, vec3(0.22, 0.18, 0.28)), field);
    float density = raw * raw * (3.0 - 2.0 * raw);

    // 3D dome relief height rises smoothly on every spherical Worley dome and macro crown.
    float domeHeight = xonSaturate(raw * 0.42 + billows * 0.64 + (subContinent - 0.45) * 0.25) * smoothstep(0.0, 0.22, raw);
    return vec2(density, domeHeight * (1.0 - formation.z * 0.52));
}

float xonCirrusDensity(vec2 position) {
    vec2 uv = position * vec2(1.0 / 6800.0, 1.0 / 3100.0);
    vec2 flow = XON_CLOUD_ROT * uv;
    vec3 c0 = texture(noisetex, flow).rgb;
    vec2 wispUV = XON_CLOUD_ROT * (flow * vec2(1.75, 2.85) + (c0.rg - 0.5) * 0.22) + vec2(0.29, 0.53);
    vec3 c1 = texture(noisetex, wispUV).rgb;
    float wisp = xonSaturate((c0.b - 0.5) * 2.1 + 0.5) * 0.58
               + xonSaturate((c1.r * 0.6 + c1.g * 0.4 - 0.5) * 2.2 + 0.5) * 0.42;
    float veil = smoothstep(0.55, 0.76, wisp);
    return veil * veil * 0.48;
}

float xonCloudCover(vec3 direction) {
    if (direction.y < 0.015 || cameraPosition.y >= 320.0) return 0.0;
    float domeY = sqrt(direction.y * direction.y + 0.035);
    float distanceToCloud = max(320.0 - max(cameraPosition.y - 80.0, 0.0), 80.0) / domeY;
    vec2 wind = xonCloudWind();
    vec2 position = cameraPosition.xz + direction.xz * distanceToCloud + wind;
    float density = xonCloudHeightfield(position, 0.0, false, xonCloudFormationWeights(), wind).x;
    return (1.0 - exp(-density * 4.0)) * smoothstep(0.015, 0.11, direction.y)
         * (1.0 - smoothstep(1600.0, 3200.0, distanceToCloud));
}

// Signed cloud cover leaves broad openings instead of highlighting Voronoi cell borders.
// Reuse the filtered noise atlas: three taps, no cellular search or extra render pass.
float xonCloudGroundLight(vec2 worldXZ) {
    if (cameraPosition.y > 320.0 || XON_GROUND_SHADOW_STRENGTH <= 0.001) return 0.0;
    // Iris resets this timer hourly; a closed wind path keeps that boundary seamless.
    const float windFrequency = 6.28318530718 / 3600.0;
    const float windSpeed = 0.5;
    const float windScale = windSpeed / length(vec2(0.32, 0.08));
    float windPhase = frameTimeCounter * windFrequency;
    vec2 windFlow = vec2(sin(windPhase), 1.0 - cos(windPhase)) * (windScale / windFrequency);
    vec2 drift = mat2(0.32, 0.08, -0.08, 0.32) * windFlow;
    vec2 advected = worldXZ + drift;
    vec2 warp = (texture(noisetex, advected * (1.0 / 800.0) + vec2(0.17, 0.43)).rg - 0.5) * 36.0;
    float broad = texture(noisetex, (advected + warp) * (1.0 / 420.0)).r;
    // Gentle wind shear changes the silhouettes continuously, allowing banks to join and part.
    vec2 detailDrift = mat2(0.12, -0.07, 0.07, 0.12) * windFlow;
    vec2 detailUV = XON_CLOUD_ROT * ((worldXZ + detailDrift + warp) * (1.0 / 210.0));
    float detail = texture(noisetex, detailUV + vec2(0.37, 0.61)).g;
    float field = broad * 0.78 + detail * 0.22 + (XON_CLOUD_DENSITY - 1.0) * 0.06;
    // A wide quintic penumbra reaches both plateaus with zero slope and curvature.
    float edge = clamp((field - 0.28) * (1.0 / 0.44), 0.0, 1.0);
    float cover = edge * edge * edge * (edge * (edge * 6.0 - 15.0) + 10.0);
    return (1.0 - 2.0 * cover) * (1.0 - rainStrength * 0.78) * XON_GROUND_SHADOW_STRENGTH;
}

vec3 xonCloudSky(vec3 direction, bool detailed) {
    vec3 sky = xonSky(direction);
    if (direction.y < 0.012 || cameraPosition.y > 340.0) return sky;

    vec3 sun = xonSunDirection();
    float day = xonDaylight(sun.y);
    vec4 phases = xonTimePhases(sun);
    float dusk = (1.0 - smoothstep(0.02, 0.48, abs(sun.y))) * day;
    float storm = xonSaturate(rainStrength * 0.78 + thunderStrength * 0.22);
    float cDot = max(dot(direction, sun), 0.0);
    float c2 = cDot * cDot;
    float c4 = c2 * c2;
    float hgPhase = c4 * c4 * 0.65 + c2 * 0.25;
    vec3 sunColor = xonSunlightColor(sun);
    vec2 wind = xonCloudWind();
    vec3 formation = xonCloudFormationWeights();
    float horizonFade = smoothstep(0.012, 0.095, direction.y);

    // Spherical atmospheric dome projection keeps clouds cohesive and naturally scaled from zenith to horizon.
    float domeY = sqrt(direction.y * direction.y + 0.035);
    float altitudeScale = max(1.0 - max(cameraPosition.y - 80.0, 0.0) / 260.0, 0.25);

    // Layer 1: High-altitude sweeping fantasy cirrus wisps.
    float cirrusDist = (520.0 * altitudeScale) / domeY;
    if (cirrusDist > 0.0 && cirrusDist < 3800.0) {
        vec2 cirrusPos = cameraPosition.xz + direction.xz * cirrusDist + wind * 0.45;
        float cirrus = xonCirrusDensity(cirrusPos) * (0.70 + formation.z * 0.65) * horizonFade
                     * (1.0 - smoothstep(1800.0, 3600.0, cirrusDist)) * (1.0 - storm * 0.65);
        if (cirrus > 0.002) {
            vec3 cirrusDay = mix(vec3(0.96, 0.98, 1.06), sunColor * 1.38, 0.42 + dusk * 0.45);
            vec3 cirrusDusk = mix(vec3(1.02, 0.52, 0.70), vec3(1.65, 0.84, 0.42), xonSaturate(cDot * 0.7 + 0.3));
            vec3 cirrusColor = mix(vec3(0.08, 0.13, 0.24), mix(cirrusDay, cirrusDusk, dusk * 0.75), day);
            cirrusColor += sunColor * hgPhase * day * 0.48;
            sky = mix(sky, cirrusColor, cirrus);
        }
    }

    // Layer 2: Single-silhouette 3D Perlin-Worley Cumulus Deck (zero ghosting or double outlines).
    float cloudDist = (320.0 * altitudeScale) / domeY;
    if (cloudDist <= 0.0 || cloudDist > 3200.0) return sky;

    float detailFade = 1.0 - smoothstep(650.0, 2100.0, cloudDist);
    vec2 pos = cameraPosition.xz + direction.xz * cloudDist + wind;
    vec2 center = xonCloudHeightfield(pos, detailFade, detailed, formation, wind);
    float density = center.x;
    if (density < 0.002) return sky;

    // Evaluate directional 3D billow slope toward the sun and along the view ray using fast macro probes.
    vec2 sunDir2D = xonSafeNormalize(vec3(sun.x, 0.0, sun.z)).xz;
    vec2 viewStep = direction.xz * min(18.0 / (direction.y + 0.18), 42.0);
    vec2 sunNear = xonCloudHeightfield(pos + sunDir2D * 42.0, 0.0, false, formation, wind);
    vec2 upperProbe = detailed ? xonCloudHeightfield(pos + viewStep, 0.0, false, formation, wind) : center;

    // 3D normal-like illumination on each rounded Worley cumulus dome:
    // sunSlope > 0 on the sunlit side of every puff and upper crown; < 0 on the shaded backside and flat cloud base.
    float baseShadow = clamp((upperProbe.x - center.x) * 1.15 + (center.y - 0.48) * 0.95, -0.60, 0.65);
    float sunSlope = clamp((center.y - sunNear.y) * 2.65 + baseShadow, -0.65, 0.95);
    float opticalDepth = sunNear.x * 1.25 + max(center.x - upperProbe.x, 0.0) * 0.75;
    float sunTransmittance = exp(-opticalDepth * 2.25);
    float powder = 1.0 - exp(-density * 3.8);

    float directLight = xonSaturate(sunTransmittance * (0.38 + 0.62 * powder) * 0.52
                                  + center.y * 0.38 + sunSlope * 0.46);
    directLight = smoothstep(0.08, 0.92, directLight);

    // Painterly fantasy-realistic palette with distinct Early Morning, Noon, Warm Afternoon, Evening Sunset, and Night moods.
    vec3 dayShadow = mix(vec3(0.24, 0.39, 0.62), vec3(0.36, 0.24, 0.52), dusk * 0.75);
    dayShadow = mix(dayShadow, vec3(0.32, 0.42, 0.66), clamp(phases.x * 0.60, 0.0, 0.75));
    dayShadow = mix(dayShadow, vec3(0.28, 0.36, 0.58), clamp(phases.z * 0.55, 0.0, 0.75));
    dayShadow = mix(dayShadow, vec3(0.38, 0.22, 0.50), clamp(phases.w * 0.70, 0.0, 0.80));
    vec3 undersideColor = mix(vec3(0.028, 0.046, 0.088), dayShadow, day);
    vec3 twilightCrown = mix(vec3(1.18, 0.54, 0.62), vec3(1.62, 0.86, 0.42), xonSaturate(cDot * 0.65 + 0.35));
    vec3 morningCrown = mix(vec3(1.15, 0.78, 0.90), vec3(1.52, 1.05, 0.78), xonSaturate(cDot * 0.60 + 0.40));
    vec3 dayHighlight = mix(sunColor * 1.18, mix(twilightCrown, morningCrown, clamp(sun.x * 1.5 + 0.5, 0.0, 1.0)), dusk * 0.62);
    vec3 sunlitColor = mix(vec3(0.14, 0.21, 0.34), dayHighlight, day);

    vec3 cloud = mix(undersideColor, sunlitColor, directLight);
    cloud += mix(vec3(0.015, 0.025, 0.048), vec3(0.06, 0.11, 0.20), day) * center.y * (1.0 - storm * 0.5);
    cloud *= 1.0 - rainStrength * 0.46 - thunderStrength * 0.12;

    float silverLining = (c4 * c4 * c4 * 0.85 + hgPhase * 0.45) * sunTransmittance * (1.0 - density * 0.48);
    cloud += sunColor * silverLining * day * (1.0 - rainStrength) * 0.80;
    cloud += vec3(0.45, 0.50, 0.61) * lightningBoltPosition.w;

    float distFade = 1.0 - smoothstep(1500.0, 2800.0, cloudDist);
    float atmoBlend = smoothstep(900.0, 2500.0, cloudDist) * 0.55;
    cloud = mix(cloud, sky, atmoBlend);
    float finalOpacity = (1.0 - exp(-density * 4.2)) * horizonFade * distFade;
    return mix(sky, cloud, finalOpacity);
}
#else
float xonCloudCover(vec3 direction) { return 0.0; }
float xonCloudGroundLight(vec2 worldXZ) { return 0.0; }
vec3 xonCloudSky(vec3 direction, bool detailed) { return xonSky(direction); }
#endif

#endif
