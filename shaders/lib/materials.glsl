#ifndef XON_MATERIAL_LIBRARY
#define XON_MATERIAL_LIBRARY

float xonLampSurfaceEmission(float material, vec3 color) {
    int id = int(material + 0.5);
    if (id == 10032 || id == 10033 || id == 10034 || id == 10035 || id == 10036
        || id == 10037 || id == 10038 || id == 10039 || id == 10041 || id == 10061
        || id == 10063 || (id >= 10068 && id <= 10071)) return 1.0;
    if (id == 10030 || id == 10031 || id == 10040 || id == 10042 || id == 10043
        || id == 10044 || id == 10076 || (id >= 10049 && id <= 10052)) {
        float flame = max(color.r - color.b, min(color.g, color.b) - color.r);
        return smoothstep(0.08, 0.30, flame) * smoothstep(0.45, 0.85, max(color.r, max(color.g, color.b)));
    }
    return 0.0;
}

float xonOreEmission(float material, vec3 textureColor) {
#ifdef XON_EMISSIVE_ORES
    float brightness = max(max(textureColor.r, textureColor.g), textureColor.b);
    float chroma = brightness - min(min(textureColor.r, textureColor.g), textureColor.b);
    if (abs(material - 10006.0) < 0.5) {
        return smoothstep(0.18, 0.65, brightness) * XON_ORE_GLOW * 0.07;
    }
    if (abs(material - 10024.0) < 0.5) {
        float berryMask = smoothstep(0.06, 0.28, textureColor.r - textureColor.g)
                       * smoothstep(0.08, 0.28, textureColor.g - textureColor.b)
                       * smoothstep(0.45, 0.78, brightness);
        return berryMask * XON_ORE_GLOW * 0.16;
    }
    if (material > 10009.5 && material < 10017.5) {
        float colorMask = smoothstep(0.05, 0.23, chroma);
        float lightMask = smoothstep(0.16, 0.48, brightness);
        if (abs(material - 10017.0) < 0.5) colorMask *= smoothstep(0.08, 0.30, textureColor.g - textureColor.b);
        return colorMask * lightMask * XON_ORE_GLOW;
    }
    if (abs(material - 10018.0) < 0.5) {
        float paleVein = smoothstep(0.55, 0.82, min(textureColor.r, min(textureColor.g, textureColor.b)));
        return paleVein * XON_ORE_GLOW;
    }
    if (abs(material - 10019.0) < 0.5 || (material > 10076.5 && material < 10080.5)) {
        // Amethyst & purple crystals: highlight saturated violet facets while rejecting near-white tips so shards stay rich purple.
        float purpleDominance = max(min(textureColor.r, textureColor.b) - textureColor.g, 0.0);
        float facetMask = smoothstep(0.04, 0.28, purpleDominance + chroma * 0.5) * smoothstep(0.18, 0.75, brightness);
        return facetMask * XON_ORE_GLOW * 0.32;
    }
    if (abs(material - 10020.0) < 0.5) {
        float accentMask = smoothstep(0.12, 0.36, chroma) * smoothstep(0.22, 0.65, brightness);
        return accentMask * XON_ORE_GLOW * 0.42;
    }
#endif
    return 0.0;
}

float xonLanternCoreMask(float material, vec3 textureColor) {
    float brightness = max(textureColor.r, max(textureColor.g, textureColor.b));
    float paleCore = smoothstep(0.65, 0.92, min(textureColor.r, min(textureColor.g, textureColor.b)));
    float chromaticCore = abs(material - 10026.0) < 0.5 || (material > 10071.5 && material < 10075.5)
        ? smoothstep(0.08, 0.28, min(textureColor.g, textureColor.b) - textureColor.r)
        : smoothstep(0.04, 0.22, textureColor.r - textureColor.b);
    return max(paleCore, chromaticCore) * smoothstep(0.24, 0.72, brightness);
}

#endif
