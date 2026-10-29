#ifndef XON_CLOUD_LIBRARY
#define XON_CLOUD_LIBRARY

#if (XON_CLOUD_STYLE == 1 && XON_DIMENSION == 0) || defined XON_WATER || defined XON_TERRAIN
uniform sampler2D noisetex;
#endif

#if XON_CLOUD_STYLE == 1 && XON_DIMENSION == 0
const mat2 XON_CLOUD_ROT = mat2(0.80, -0.60, 0.60, 0.80);

// True 2D Worley cellular sphere field (1.0 at spherical puff center, 0.0 at cell crease) for genuine fluffy cumulus domes.
float xonWorleyDomes(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    float minDistSq = 4.0;
    for (int y = -1; y <= 1; ++y) {
        for (int x = -1; x <= 1; ++x) {
            vec2 neighbor = vec2(float(x), float(y));
            vec2 cell = i + neighbor;
            vec2 rnd = fract(sin(vec2(dot(cell, vec2(127.1, 311.7)),
                                      dot(cell, vec2(269.5, 183.3)))) * 43758.5453);
            vec2 diff = neighbor + 0.15 + 0.70 * rnd - f;
            minDistSq = min(minDistSq, dot(diff, diff));
        }
    }
    float puff = xonSaturate(1.0 - sqrt(minDistSq) * 1.05);
    return puff * (1.35 - 0.35 * puff);
}

// Evaluates the continuous 3D heightfield H(x,z) of the cumulus cloud deck:
// x = opacity/density [0..1], y = 3D dome relief height [0..1] for normal & self-shadow calculation.
vec2 xonCloudHeightfield(vec2 position, float distFadeDetail, bool detailed) {
    vec2 uv = position * (1.0 / 3600.0);
    vec3 n0 = texture(noisetex, uv).rgb;
    vec2 warp = (n0.gb - 0.5) * 0.10;
    vec3 n1 = texture(noisetex, XON_CLOUD_ROT * (uv * 2.15 + warp) + vec2(0.17, 0.31)).rgb;
    vec3 n2 = texture(noisetex, XON_CLOUD_ROT * (uv * 4.65 - warp * 1.3) + vec2(0.43, 0.67)).rgb;

    // Macro cloud continents from smooth periodic noise.
    float continent = xonSaturate((n0.r * 0.62 + n0.g * 0.38 - 0.5) * 2.15 + 0.52);
    float subContinent = xonSaturate((n1.r * 0.58 + n1.b * 0.42 - 0.5) * 2.05 + 0.50);

    // True Perlin-Worley cellular spheres warped by wind flow for round, fluffy cauliflower cumulus domes.
    vec2 cellCoord = position * (1.0 / 240.0) + (n0.rg - 0.5) * 1.55 + (n1.gb - 0.5) * 0.70;
    float majorDomes = xonWorleyDomes(cellCoord);
    float midPuffs = xonWorleyDomes(XON_CLOUD_ROT * cellCoord * 2.25 + (n2.rg - 0.5) * 0.75);
    float fineCurls = detailed && distFadeDetail > 0.02
                    ? xonWorleyDomes(XON_CLOUD_ROT * (cellCoord * 4.80) + (n2.gb - 0.5) * 0.65)
                    : xonSaturate((n2.r * 0.55 + n2.g * 0.45 - 0.5) * 2.0 + 0.5);

    float billows = majorDomes * 0.52 + midPuffs * 0.30 + mix(midPuffs, fineCurls, distFadeDetail) * 0.18;

    // Combine macro cloud islands with cellular Worley domes so edges have round puffy cumulus silhouettes.
    float macroMass = continent * 0.60 + subContinent * 0.40;
    float field = macroMass * 0.70 + billows * 0.30;

    float threshold = mix(0.475, 0.305, rainStrength);
    float raw = smoothstep(threshold, threshold + 0.22, field);
    float density = raw * raw * (3.0 - 2.0 * raw);

    // 3D dome relief height rises smoothly on every spherical Worley dome and macro crown.
    float domeHeight = xonSaturate(raw * 0.42 + billows * 0.64 + (subContinent - 0.45) * 0.25) * smoothstep(0.0, 0.22, raw);
    return vec2(density, domeHeight);
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
    vec2 position = cameraPosition.xz + direction.xz * distanceToCloud + vec2(2.2, 0.55) * frameTimeCounter;
    float density = xonCloudHeightfield(position, 0.0, false).x;
    return (1.0 - exp(-density * 4.0)) * smoothstep(0.015, 0.11, direction.y)
         * (1.0 - smoothstep(1600.0, 3200.0, distanceToCloud));
}

// Evaluates a slow, gradually morphing ~15-20 block radius Voronoi shadow & highlight field moving over the terrain.
// Returns [-1.0..+1.0]: negative inside dark Voronoi shadow cells, positive in bright Voronoi highlight zones.
float xonCloudGroundLight(vec2 worldXZ) {
    if (cameraPosition.y > 320.0) return 0.0;
    vec2 drift = vec2(0.725, 0.29) * frameTimeCounter;
    float morphTime = frameTimeCounter * 0.12;
    vec2 warpedXZ = worldXZ + drift;
    vec2 macroWarp = (texture(noisetex, warpedXZ * (1.0 / 1200.0)).rg - 0.5) * 11.0;

    // 34-block Voronoi grid with per-cell radius jitter (0.78..1.24) yields random ~14 to 22 block radius shadow cells.
    vec2 p = (warpedXZ + macroWarp) * (1.0 / 34.0);
    vec2 cellBase = floor(p);
    vec2 f = fract(p);

    float d1 = 8.0;
    float d2 = 8.0;
    float cellWeight = 1.0;

    for (int y = -1; y <= 1; ++y) {
        for (int x = -1; x <= 1; ++x) {
            vec2 neighbor = vec2(float(x), float(y));
            vec2 cell = cellBase + neighbor;
            vec3 rnd = fract(sin(vec3(
                dot(cell, vec2(127.1, 311.7)),
                dot(cell, vec2(269.5, 183.3)),
                dot(cell, vec2(419.2, 371.9))
            )) * 43758.5453);

            vec2 animOffset = 0.5 + 0.36 * sin(morphTime + 6.2831853 * rnd.xy);
            vec2 diff = neighbor + animOffset - f;
            float radiusScale = mix(0.78, 1.24, rnd.z);
            float dist = length(diff) * radiusScale;

            if (dist < d1) {
                d2 = d1;
                d1 = dist;
                cellWeight = rnd.z;
            } else if (dist < d2) {
                d2 = dist;
            }
        }
    }

    float shadowCore = 1.0 - smoothstep(0.12, 0.68, d1);
    float highlightZone = smoothstep(0.42, 0.92, d1) * (0.65 + 0.35 * (1.0 - smoothstep(0.0, 0.35, d2 - d1)));
    float signal = highlightZone - shadowCore * (0.78 + 0.22 * cellWeight);
    return clamp(signal * 1.25, -1.0, 1.0) * (1.0 - rainStrength * 0.78);
}

vec3 xonCloudSky(vec3 direction, bool detailed) {
    vec3 sky = xonSky(direction);
    if (direction.y < 0.012 || cameraPosition.y > 340.0) return sky;

    vec3 sun = xonSunDirection();
    float day = xonDaylight(sun.y);
    float dusk = (1.0 - smoothstep(0.02, 0.48, abs(sun.y))) * day;
    float storm = xonSaturate(rainStrength * 0.78 + thunderStrength * 0.22);
    float cDot = max(dot(direction, sun), 0.0);
    float c2 = cDot * cDot;
    float c4 = c2 * c2;
    float hgPhase = c4 * c4 * 0.65 + c2 * 0.25;
    vec3 sunColor = xonSunlightColor(sun.y);
    vec2 wind = vec2(2.2, 0.55) * frameTimeCounter;
    float horizonFade = smoothstep(0.012, 0.095, direction.y);

    // Spherical atmospheric dome projection keeps clouds cohesive and naturally scaled from zenith to horizon.
    float domeY = sqrt(direction.y * direction.y + 0.035);
    float altitudeScale = max(1.0 - max(cameraPosition.y - 80.0, 0.0) / 260.0, 0.25);

    // Layer 1: High-altitude sweeping fantasy cirrus wisps.
    float cirrusDist = (520.0 * altitudeScale) / domeY;
    if (cirrusDist > 0.0 && cirrusDist < 3800.0) {
        vec2 cirrusPos = cameraPosition.xz + direction.xz * cirrusDist + wind * 0.45;
        float cirrus = xonCirrusDensity(cirrusPos) * horizonFade
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
    vec2 center = xonCloudHeightfield(pos, detailFade, detailed);
    float density = center.x;
    if (density < 0.002) return sky;

    // Evaluate directional 3D billow slope toward the sun and along the view ray for true sculptural lighting.
    vec2 sunDir2D = xonSafeNormalize(vec3(sun.x, 0.0, sun.z)).xz;
    vec2 viewStep = direction.xz * min(18.0 / (direction.y + 0.18), 42.0);
    vec2 sunNear = xonCloudHeightfield(pos + sunDir2D * 42.0, detailFade * 0.5, detailed);
    vec2 upperProbe = detailed ? xonCloudHeightfield(pos + viewStep, 0.0, false) : center;

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

    // Painterly fantasy-realistic palette: velvety cerulean-lavender undersides and warm ivory/golden crowns (HDR-balanced to preserve 3D puff detail).
    vec3 dayShadow = mix(vec3(0.24, 0.39, 0.62), vec3(0.36, 0.24, 0.52), dusk * 0.75);
    vec3 undersideColor = mix(vec3(0.028, 0.046, 0.088), dayShadow, day);
    vec3 twilightCrown = mix(vec3(1.18, 0.54, 0.62), vec3(1.62, 0.86, 0.42), xonSaturate(cDot * 0.65 + 0.35));
    vec3 dayHighlight = mix(sunColor * 1.18, twilightCrown, dusk * 0.62);
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
