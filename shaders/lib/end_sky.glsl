#ifndef XON_END_SKY
#define XON_END_SKY

#if XON_DIMENSION == 1
uniform sampler2D noisetex;

vec3 xonEndHash(vec3 cell) {
    cell = fract(cell * vec3(0.1031, 0.1030, 0.0973));
    cell += dot(cell, cell.yxz + 33.33);
    return fract((cell.xxy + cell.yzz) * cell.zyx);
}

vec3 xonEndStarLayer(vec3 direction, float scale, float threshold) {
    vec3 grid = direction * scale;
    vec3 cell = floor(grid);
    vec3 random = xonEndHash(cell);
    vec3 offset = fract(grid) - (0.20 + random * 0.60);
    float distanceToStar = length(offset);
    float radius = 0.035 + random.z * 0.060;
    float pixelWidth = max(length(fwidth(grid)), 0.025);
    float core = 1.0 - smoothstep(max(radius - pixelWidth, 0.0), radius + pixelWidth, distanceToStar);
    float footprint = min(1.0, radius * radius / (pixelWidth * pixelWidth));
    float selected = step(threshold, random.x);
    float twinkle = 0.88 + 0.12 * sin(frameTimeCounter * 0.7 + random.y * 80.0);
    vec3 tint = mix(vec3(0.55, 0.72, 1.0), vec3(1.0, 0.86, 0.68), random.y);
    return tint * core * footprint * selected * twinkle;
}

vec3 xonEndStars(vec3 direction) {
    vec3 fine = xonEndStarLayer(direction, 190.0, 0.90);
    vec3 bright = xonEndStarLayer(direction, 72.0, 0.96);
    return (fine * 1.15 + bright * 2.0) * XON_END_STARS;
}

vec3 xonEndGalaxy(vec3 direction) {
    vec2 uv = vec2(direction.x * 0.72 + direction.z * 0.48, direction.y * 0.83 - direction.z * 0.36);
    vec3 broad = texture(noisetex, uv * 0.42 + vec2(0.23, 0.41)).rgb;
    vec2 warped = uv + (broad.gb - 0.5) * 0.24;
    vec3 clouds = texture(noisetex, warped * 1.15 + vec2(0.61, 0.17)).rgb;
    vec3 folds = texture(noisetex, warped * 2.8 + vec2(0.37, 0.73)).rgb;
    float fine = texture(noisetex, warped * 7.0).r;
    float latitude = dot(direction, vec3(0.34, -0.72, 0.604)) + (broad.r - 0.5) * 0.055;
    float wideBand = exp2(-latitude * latitude * 12.0);
    float band = exp2(-latitude * latitude * 75.0);
    float coreFocus = max(dot(direction, vec3(0.885, 0.460, 0.050)), 0.0);
    coreFocus *= coreFocus;
    coreFocus *= coreFocus;
    coreFocus *= coreFocus;
    float structure = smoothstep(0.26, 0.76, broad.r * 0.30 + clouds.g * 0.46 + folds.b * 0.24);
    float dust = smoothstep(0.34, 0.68, folds.r * 0.65 + clouds.b * 0.35);
    float filaments = smoothstep(0.40, 0.82, clouds.r * 0.54 + folds.g * 0.30 + fine * 0.16);
    vec3 hue = mix(vec3(0.012, 0.028, 0.115), vec3(0.055, 0.012, 0.095), broad.b);
    hue = mix(hue, vec3(0.14, 0.016, 0.09), smoothstep(0.55, 0.85, clouds.b) * 0.65);
    vec3 nebula = hue * (0.15 + structure * 0.80) * wideBand * 0.60;
    nebula += vec3(0.54, 0.59, 0.75) * band * filaments * filaments * (0.10 + coreFocus * 0.36);
    float lane = latitude + 0.02 + (clouds.r - 0.5) * 0.12;
    float darkLane = exp2(-lane * lane * 1800.0) * (0.30 + folds.g * 0.70);
    nebula *= (1.0 - dust * 0.50) * (1.0 - darkLane * 0.75);
    nebula += vec3(0.008, 0.025, 0.09) * wideBand * (1.0 - coreFocus) * 0.35;
    return nebula * XON_END_AURORA * smoothstep(-0.40, 0.05, direction.y);
}

#ifdef XON_END_BLACK_HOLE
uniform sampler2D xonBlackHoleLUT;
#endif

vec3 xonEndBlackHole(vec3 sky, vec3 direction) {
#ifdef XON_END_BLACK_HOLE
    const vec3 center = vec3(-0.35046, 0.42055, 0.83609);
    const vec3 right = vec3(0.92226, 0.0, 0.38658);
    const vec3 up = vec3(0.16258, 0.90727, -0.38786);
    const float angularRadius = 0.105;
    const float diskExtent = 6.0;
    float facing = dot(direction, center);
    if (facing < 0.70) return sky;
    vec2 p = vec2(dot(direction, right), dot(direction, up)) / (facing * angularRadius);
    p = mat2(0.9992, -0.0400, 0.0400, 0.9992) * p;
    if (max(abs(p.x), abs(p.y)) >= diskExtent) return sky;
    vec2 uv = vec2(p.x, -p.y) / (2.0 * diskExtent) + 0.5;
    // RGB encodes sqrt(linear radiance / 16); alpha encodes disk/horizon occlusion.
    vec4 transfer = texture(xonBlackHoleLUT, uv);
    vec3 emission = transfer.rgb * transfer.rgb * 16.0;
    return sky * (1.0 - transfer.a) + emission * 0.42;
#else
    return sky;
#endif
}

vec3 xonEndSky(vec3 direction) {
    vec3 sky = xonSky(direction) * 0.06 + vec3(0.0015, 0.002, 0.007) + xonEndGalaxy(direction);
    sky += xonEndStars(direction) * smoothstep(-0.30, -0.05, direction.y);
    return xonEndBlackHole(sky, direction);
}
#endif

#endif
