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

float xonEmissiveId(float material, vec3 textureColor) {
#ifdef XON_EMISSIVE_ORES
#ifdef XON_COLORED_EMISSIVE_LIGHTING
    float glow = xonOreEmission(material, textureColor);
    if (abs(material - 10010.0) < 0.5 && glow > 0.05) return 0.10;
    if (abs(material - 10018.0) < 0.5) {
        float luma = dot(textureColor, vec3(0.299, 0.587, 0.114));
        if (luma > 0.65 || glow > 0.05) return 0.20;
    }
    if (abs(material - 10011.0) < 0.5 && glow > 0.05) return 0.30;
    if (abs(material - 10012.0) < 0.5) return 0.40;
    if (abs(material - 10013.0) < 0.5 && glow > 0.05) return 0.50;
    if ((abs(material - 10014.0) < 0.5 || abs(material - 10017.0) < 0.5) && glow > 0.05) return 0.60;
    if (abs(material - 10016.0) < 0.5 && glow > 0.05) return 0.70;
    if (abs(material - 10019.0) < 0.5) return 0.80;
    if (abs(material - 10020.0) < 0.5 && glow > 0.05) return 0.90;
#endif
#endif
    return 1.0;
}

bool xonGetEmissiveProfile(float id, out vec3 emitColor, out float emitRadius, out float emitIntensity) {
    if (id < 0.05 || id > 0.95) return false;
    int type = int(id * 10.0 + 0.5);
    if (type == 1) {
        emitColor = vec3(0.12, 0.88, 0.98);
        emitRadius = 2.8;
        emitIntensity = 1.30;
    } else if (type == 2) {
        emitColor = vec3(0.98, 0.92, 0.84);
        emitRadius = 2.4;
        emitIntensity = 1.10;
    } else if (type == 3) {
        emitColor = vec3(0.12, 0.98, 0.38);
        emitRadius = 2.8;
        emitIntensity = 1.30;
    } else if (type == 4) {
        emitColor = vec3(1.00, 0.10, 0.04);
        emitRadius = 3.0;
        emitIntensity = 1.50;
    } else if (type == 5) {
        emitColor = vec3(0.10, 0.38, 1.00);
        emitRadius = 2.8;
        emitIntensity = 1.30;
    } else if (type == 6) {
        emitColor = vec3(1.00, 0.78, 0.15);
        emitRadius = 2.5;
        emitIntensity = 1.20;
    } else if (type == 7) {
        emitColor = vec3(0.95, 0.48, 0.18);
        emitRadius = 2.5;
        emitIntensity = 1.20;
    } else if (type == 8) {
        emitColor = vec3(0.78, 0.28, 1.00);
        emitRadius = 2.8;
        emitIntensity = 1.30;
    } else if (type == 9) {
        emitColor = vec3(0.04, 0.72, 0.82);
        emitRadius = 2.8;
        emitIntensity = 1.30;
    } else {
        return false;
    }
#ifdef XON_EMISSIVE_RADIUS
    emitRadius *= (XON_EMISSIVE_RADIUS / 2.5);
#endif
#ifdef XON_EMISSIVE_INTENSITY
    emitIntensity *= XON_EMISSIVE_INTENSITY;
#endif
    return true;
}

#endif
