#ifndef XON_LAMP_LIGHT
#define XON_LAMP_LIGHT

const uint XON_LAMP_FIRST = 129u;
const uint XON_LAMP_LAST = 203u;
const float XON_LAMP_HISTORY_REACH = 16.0;
const float XON_LAMP_POOL_GAIN = 0.85;
const float XON_LAMP_SHADE_GAIN = 0.85;

uint xonLampFamily(float material) {
    int id = int(material + 0.5);
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

// RGB is peak linear radiance; alpha is the visible open-path radius in blocks.
vec4 xonLampProfile(uint family) {
    if (family == 1u) return vec4(vec3(0.43, 0.80, 0.58) * 0.16, 2.5);
    if (family == 2u) return vec4(vec3(1.00, 0.40, 0.08) * 0.48, 3.5);
    if (family == 3u) return vec4(vec3(1.00, 0.67, 0.30) * 1.25, 6.0);
    if (family == 4u) return vec4(vec3(0.18, 0.70, 1.00) * 0.95, 4.5);
    if (family == 5u) return vec4(vec3(1.00, 0.50, 0.15) * 1.05, 5.5);
    if (family == 6u) return vec4(vec3(0.72, 0.40, 1.00) * 0.35, 3.5);
    if (family == 7u) return vec4(vec3(0.12, 0.72, 0.85) * 0.25, 3.0);
    if (family == 8u) return vec4(vec3(0.68, 0.45, 1.00) * 0.22, 3.0);
    if (family == 9u) return vec4(vec3(1.00, 0.72, 0.28) * 1.05, 5.0);
    if (family == 10u) return vec4(vec3(0.15, 0.65, 1.00) * 0.80, 4.0);
    if (family == 11u) return vec4(vec3(0.68, 0.94, 1.00) * 1.15, 6.0);
    if (family == 12u) return vec4(vec3(0.90, 0.94, 1.00) * 1.05, 5.5);
    if (family == 13u) return vec4(vec3(1.00, 0.78, 0.42) * 1.15, 6.0);
    if (family == 14u) return vec4(vec3(1.00, 0.48, 0.18) * 1.10, 5.5);
    if (family == 15u) return vec4(vec3(1.00, 0.43, 0.10) * 1.15, 5.0);
    if (family == 16u) return vec4(vec3(0.12, 0.65, 1.00) * 0.85, 4.0);
    if (family == 17u) return vec4(vec3(0.65, 0.92, 1.00) * 0.95, 5.5);
    if (family == 18u) return vec4(vec3(1.00, 0.22, 0.03) * 0.22, 2.0);
    if (family == 19u) return vec4(vec3(1.00, 0.47, 0.12) * 0.85, 4.5);
    if (family == 20u) return vec4(vec3(1.00, 0.68, 0.28) * 1.10, 5.5);
    if (family == 21u) return vec4(vec3(1.00, 0.10, 0.025) * 0.30, 2.5);
    if (family == 22u) return vec4(vec3(1.00, 0.46, 0.10) * 1.20, 5.5);
    if (family == 23u) return vec4(vec3(0.12, 0.65, 1.00) * 0.90, 4.0);
    if (family == 24u) return vec4(vec3(1.00, 0.28, 0.035) * 1.10, 5.0);
    if (family == 25u) return vec4(vec3(1.00, 0.78, 0.40) * 1.00, 5.5);
    if (family == 26u) return vec4(vec3(0.60, 1.00, 0.72) * 0.95, 5.5);
    if (family == 27u) return vec4(vec3(0.90, 0.72, 1.00) * 0.95, 5.5);
    if (family >= 28u && family <= 31u) {
        float count = float(family - 27u);
        return vec4(vec3(1.00, 0.62, 0.22) * (0.23 + count * 0.15), 1.5 + count * 0.75);
    }
    if (family >= 32u && family <= 35u) {
        float count = float(family - 31u);
        return vec4(vec3(0.65, 1.00, 0.40) * (0.16 + count * 0.12), 1.5 + count * 0.75);
    }
    if (family >= 36u && family <= 39u) {
        float charge = float(family - 35u);
        return vec4(vec3(0.64, 0.30, 1.00) * (charge * 0.20), 2.0 + charge * 0.75);
    }
    if (family == 40u) return vec4(vec3(0.65, 0.28, 1.00) * 0.45, 3.5);
    if (family == 41u) return vec4(vec3(0.70, 0.25, 1.00) * 0.65, 4.5);
    if (family == 42u) return vec4(vec3(0.48, 0.70, 1.00) * 0.65, 4.0);
    if (family == 43u) return vec4(vec3(0.40, 0.75, 0.85) * 0.28, 2.5);
    if (family == 44u) return vec4(vec3(1.00, 0.48, 0.12) * 0.10, 1.0);
    if (family == 45u) return vec4(vec3(0.75, 0.65, 0.35) * 0.08, 1.0);
    if (family == 46u) return vec4(vec3(0.75, 1.00, 0.32) * 0.14, 1.5);
    if (family >= 47u && family <= 50u) {
        float age = float(family - 47u);
        return vec4(vec3(1.00 - age * 0.13, 0.70 + age * 0.06, 0.30 + age * 0.10)
                    * (1.05 - age * 0.22), 6.0 - age * 1.25);
    }
    if (family >= 51u && family <= 54u) {
        float age = float(family - 51u);
        return vec4(vec3(0.50, 1.00, 0.65) * (1.10 - age * 0.10), 5.5 - age * 0.50);
    }
    if (family == 55u) return vec4(vec3(0.45, 1.00, 0.62) * 0.90, 4.5);
    if (family >= 56u && family <= 59u) {
        float size = float(60u - family);
        return vec4(vec3(0.75, 0.44, 1.00) * (0.08 + size * 0.07), 0.5 + size * 0.65);
    }
    if (family == 60u) return vec4(vec3(0.95, 0.55, 0.22) * 0.65, 4.0);
    if (family >= 61u && family <= 75u) {
        float level = float(family - 60u);
        return vec4(vec3(1.00, 0.88, 0.70) * (level / 15.0), max(1.0, level * 0.40));
    }
    return vec4(0.0);
}

int xonLampLevel(uint family) {
    if (family == 6u) return 5;
    if (family == 7u || family == 8u) return 4;
    if (family == 1u || family == 43u || family == 21u) return 7;
    if (family == 2u || family == 9u || family == 12u || family == 55u) return 14;
    if (family == 4u || family == 10u || family == 16u || family == 23u) return 10;
    if (family == 18u) return 3;
    if (family == 19u || family == 60u) return 13;
    if (family == 41u) return 11;
    if (family >= 28u && family <= 31u) return int(family - 27u) * 3;
    if (family >= 32u && family <= 35u) return int(family - 31u) * 3 + 3;
    if (family >= 36u && family <= 39u) return int(family - 35u) * 4 - 1;
    if (family == 40u) return 10;
    if (family == 44u || family == 45u) return 1;
    if (family == 46u) return 2;
    if (family >= 47u && family <= 50u) return family == 47u ? 15 : (family == 48u ? 12 : (family == 49u ? 8 : 4));
    if (family >= 56u && family <= 59u) return family == 56u ? 5 : (family == 57u ? 4 : (family == 58u ? 2 : 1));
    if (family >= 61u && family <= 75u) return int(family - 60u);
    return 15;
}

float xonLampFalloff(float distanceToSource, float radius) {
    float t = clamp(1.0 - distanceToSource / (radius + 1.0), 0.0, 1.0);
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0);
}

vec4 xonLampValue(uint family, int level) {
    if (family == 0u || level <= 0) return vec4(0.0);
    vec4 profile = xonLampProfile(family);
    float distanceToSource = float(xonLampLevel(family) - level);
    return vec4(profile.rgb * xonLampFalloff(distanceToSource, profile.a), float(family * 16u + uint(level)));
}

#ifdef XON_EMISSIVE_SAMPLING
uniform sampler3D xonLampTex0;
uniform sampler3D xonLampTex1;
#endif
#endif
