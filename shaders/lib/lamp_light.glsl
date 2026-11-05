#ifndef XON_LAMP_LIGHT
#define XON_LAMP_LIGHT
#include "/lib/block_shapes.glsl"

const uint XON_LAMP_FIRST = 129u;
const uint XON_LAMP_LAST = 203u;
const float XON_LAMP_HISTORY_REACH = 16.0;
const float XON_LAMP_POOL_GAIN = 0.94;
const float XON_LAMP_SHADE_GAIN = 0.72;

// Precomputed peak linear radiance (RGB) and nominal open-path radius in blocks (A) for families 0..75.
const vec4 XON_LAMP_PROFILES[76] = vec4[76](
    vec4(0.0000000, 0.0000000, 0.0000000, 0.0000),
    vec4(0.0688000, 0.1280000, 0.0928000, 2.5000),
    vec4(0.4800000, 0.1920000, 0.0384000, 3.5000),
    vec4(1.2500000, 0.8375000, 0.3750000, 6.0000),
    vec4(0.1710000, 0.6650000, 0.9500000, 4.5000),
    vec4(1.0500000, 0.5250000, 0.1575000, 5.5000),
    vec4(0.2520000, 0.1400000, 0.3500000, 3.5000),
    vec4(0.0300000, 0.1800000, 0.2125000, 3.0000),
    vec4(0.1496000, 0.0990000, 0.2200000, 3.0000),
    vec4(1.0500000, 0.7560000, 0.2940000, 5.0000),
    vec4(0.1200000, 0.5200000, 0.8000000, 4.0000),
    vec4(0.7820000, 1.0810000, 1.1500000, 6.0000),
    vec4(0.9450000, 0.9870000, 1.0500000, 5.5000),
    vec4(1.1500000, 0.8970000, 0.4830000, 6.0000),
    vec4(1.1000000, 0.5280000, 0.1980000, 5.5000),
    vec4(1.1500000, 0.4945000, 0.1150000, 5.0000),
    vec4(0.1020000, 0.5525000, 0.8500000, 4.0000),
    vec4(0.6175000, 0.8740000, 0.9500000, 5.5000),
    vec4(0.2200000, 0.0484000, 0.0066000, 2.0000),
    vec4(0.8500000, 0.3995000, 0.1020000, 4.5000),
    vec4(1.1000000, 0.7480000, 0.3080000, 5.5000),
    vec4(0.3000000, 0.0300000, 0.0075000, 2.5000),
    vec4(1.2000000, 0.5520000, 0.1200000, 5.5000),
    vec4(0.1080000, 0.5850000, 0.9000000, 4.0000),
    vec4(1.1000000, 0.3080000, 0.0385000, 5.0000),
    vec4(1.0000000, 0.7800000, 0.4000000, 5.5000),
    vec4(0.5700000, 0.9500000, 0.6840000, 5.5000),
    vec4(0.8550000, 0.6840000, 0.9500000, 5.5000),
    vec4(0.3800000, 0.2356000, 0.0836000, 2.2500),
    vec4(0.5300000, 0.3286000, 0.1166000, 3.0000),
    vec4(0.6800000, 0.4216000, 0.1496000, 3.7500),
    vec4(0.8300000, 0.5146000, 0.1826000, 4.5000),
    vec4(0.1820000, 0.2800000, 0.1120000, 2.2500),
    vec4(0.2600000, 0.4000000, 0.1600000, 3.0000),
    vec4(0.3380000, 0.5200000, 0.2080000, 3.7500),
    vec4(0.4160000, 0.6400000, 0.2560000, 4.5000),
    vec4(0.1280000, 0.0600000, 0.2000000, 2.7500),
    vec4(0.2560000, 0.1200000, 0.4000000, 3.5000),
    vec4(0.3840000, 0.1800000, 0.6000000, 4.2500),
    vec4(0.5120000, 0.2400000, 0.8000000, 5.0000),
    vec4(0.2925000, 0.1260000, 0.4500000, 3.5000),
    vec4(0.4550000, 0.1625000, 0.6500000, 4.5000),
    vec4(0.3120000, 0.4550000, 0.6500000, 4.0000),
    vec4(0.1120000, 0.2100000, 0.2380000, 2.5000),
    vec4(0.1000000, 0.0480000, 0.0120000, 1.0000),
    vec4(0.0600000, 0.0520000, 0.0280000, 1.0000),
    vec4(0.1050000, 0.1400000, 0.0448000, 1.5000),
    vec4(1.0500000, 0.7350000, 0.3150000, 6.0000),
    vec4(0.7221000, 0.6308000, 0.3320000, 4.7500),
    vec4(0.4514000, 0.5002000, 0.3050000, 3.5000),
    vec4(0.2379000, 0.3432000, 0.2340000, 2.2500),
    vec4(0.5500000, 1.1000000, 0.7150000, 5.5000),
    vec4(0.5000000, 1.0000000, 0.6500000, 5.0000),
    vec4(0.4500000, 0.9000000, 0.5850000, 4.5000),
    vec4(0.4000000, 0.8000000, 0.5200000, 4.0000),
    vec4(0.4050000, 0.9000000, 0.5580000, 4.5000),
    vec4(0.2700000, 0.1584000, 0.3600000, 3.1000),
    vec4(0.2175000, 0.1276000, 0.2900000, 2.4500),
    vec4(0.1650000, 0.0968000, 0.2200000, 1.8000),
    vec4(0.1125000, 0.0660000, 0.1500000, 1.1500),
    vec4(0.6175000, 0.3575000, 0.1430000, 4.0000),
    vec4(0.0666667, 0.0586667, 0.0466667, 1.0000),
    vec4(0.1333333, 0.1173333, 0.0933333, 1.0000),
    vec4(0.2000000, 0.1760000, 0.1400000, 1.2000),
    vec4(0.2666667, 0.2346667, 0.1866667, 1.6000),
    vec4(0.3333333, 0.2933333, 0.2333333, 2.0000),
    vec4(0.4000000, 0.3520000, 0.2800000, 2.4000),
    vec4(0.4666667, 0.4106667, 0.3266667, 2.8000),
    vec4(0.5333333, 0.4693333, 0.3733333, 3.2000),
    vec4(0.6000000, 0.5280000, 0.4200000, 3.6000),
    vec4(0.6666667, 0.5866667, 0.4666667, 4.0000),
    vec4(0.7333333, 0.6453333, 0.5133333, 4.4000),
    vec4(0.8000000, 0.7040000, 0.5600000, 4.8000),
    vec4(0.8666667, 0.7626667, 0.6066667, 5.2000),
    vec4(0.9333333, 0.8213333, 0.6533333, 5.6000),
    vec4(1.0000000, 0.8800000, 0.7000000, 6.0000)
);

const int XON_LAMP_LEVELS[76] = int[76](
    15, 7, 14, 15, 10, 15, 5, 4, 4, 14, 10, 15, 14, 15, 15, 15,
    10, 15, 3, 13, 15, 7, 15, 10, 15, 15, 15, 15, 3, 6, 9, 12,
    6, 9, 12, 15, 3, 7, 11, 15, 10, 11, 15, 7, 1, 1, 2, 15,
    12, 8, 4, 15, 15, 15, 15, 14, 5, 4, 2, 1, 13, 1, 2, 3,
    4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15
);

uint xonLampFamily(float material) {
    int id = int(material + 0.5);
    if (id >= 11100 && id < 11100 + XON_SHAPE_COUNT) return 8u;
    if (id >= 10030 && id <= 10096) return uint(id - 10021);
    if (id == 10006) return 1u;
    if (id == 10024) return 2u;
    if (id == 10025) return 3u;
    if (id == 10026) return 4u;
    if (id == 10027) return 5u;
    if (id == 10019) return 6u;
    if (id == 10020) return 7u;
    if (id == 10023) return 8u;
    if (id == 10005) return 24u;
    if (id == 10021) return 41u;
    return 0u;
}

vec4 xonLampProfile(uint family) {
    return family <= 75u ? XON_LAMP_PROFILES[family] : vec4(0.0);
}

int xonLampLevel(uint family) {
    return family <= 75u ? XON_LAMP_LEVELS[family] : 0;
}

// Smooth inverse-square cushioned radial falloff: zero cusp at d=0, circular mid-pool, smooth zero at outer edge.
float xonLampFalloff(float distanceToSource, float radius) {
    float d = max(distanceToSource, 0.0);
    float rNorm = d / max(radius, 0.5);
    float u = clamp(1.0 - d / (radius * 0.98 + 1.05), 0.0, 1.0);
    float window = u * u * (3.0 - 2.0 * u);
    return (window * window) / (1.0 + 0.95 * rNorm * rNorm);
}

// Packs family (1..75) + fractional Euclidean level (0..15] losslessly at 1/8-block resolution in normal fp16,
// while preserving exact legacy integer codes >= 16.0 at integer levels for families 1..63.
float xonPackLampState(uint family, float level) {
    if (family == 0u || family > 75u || level <= 0.0) return 0.0;
    float rounded = floor(level + 0.5);
    if (family <= 63u && abs(level - rounded) < 0.001 && rounded >= 1.0 && rounded <= 15.0) {
        return float(family * 16u + uint(rounded));
    }
    uint group = family / 6u;
    uint sub = family - group * 6u;
    float slot = float(sub * 16u) + clamp(level, 0.0, 15.875);
    uint mant = uint(slot * 65536.0 + 0.5) & 0x7FFFFFu;
    return uintBitsToFloat(((113u + group) << 23u) | mant);
}

void xonUnpackLampState(float encodedState, out uint family, out float level) {
    family = 0u;
    level = 0.0;
    if (encodedState <= 0.0) return;
    if (encodedState >= 16.0) {
        int code = int(encodedState + 0.5);
        family = uint(code / 16);
        level = float(code % 16);
        if (family > 75u || level <= 0.0) {
            family = 0u;
            level = 0.0;
        }
        return;
    }
    uint bits = floatBitsToUint(encodedState);
    int group = int((bits >> 23u) & 255u) - 113;
    if (group < 0 || group > 12) return;
    float slot = float(bits & 0x7FFFFFu) * (1.0 / 65536.0);
    uint sub = min(uint(slot * 0.0625 + 0.0001), 5u);
    family = uint(group) * 6u + sub;
    level = max(slot - float(sub * 16u), 0.0);
    if (family == 0u || family > 75u || level <= 0.0) {
        family = 0u;
        level = 0.0;
    }
}

vec4 xonLampValueF(uint family, float level) {
    if (family == 0u || level <= 0.0) return vec4(0.0);
    vec4 profile = xonLampProfile(family);
    float distanceToSource = max(float(xonLampLevel(family)) - level, 0.0);
    return vec4(profile.rgb * xonLampFalloff(distanceToSource, profile.a), xonPackLampState(family, level));
}

vec4 xonLampValue(uint family, int level) {
    return xonLampValueF(family, float(level));
}

#ifdef XON_EMISSIVE_SAMPLING
uniform sampler3D xonLampTex0;
uniform sampler3D xonLampTex1;
#endif
#endif
