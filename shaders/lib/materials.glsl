#ifndef XON_MATERIAL_LIBRARY
#define XON_MATERIAL_LIBRARY

float xonOreEmission(float material, vec3 textureColor) {
#ifdef XON_EMISSIVE_ORES
    float brightness = max(max(textureColor.r, textureColor.g), textureColor.b);
    float chroma = brightness - min(min(textureColor.r, textureColor.g), textureColor.b);
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
    if (abs(material - 10019.0) < 0.5) {
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

#endif
