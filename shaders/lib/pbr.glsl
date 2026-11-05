#ifndef XON_PBR_LIBRARY
#define XON_PBR_LIBRARY

// LabPBR 1.3 & OldPBR Material and Lighting Library for XON Shader

uniform sampler2D normals;
uniform sampler2D specular;

vec4 xonSamplePBRTexture(sampler2D surfaceTexture, vec2 coord, vec2 dcdx, vec2 dcdy, bool retainMipmaps) {
    ivec2 size = textureSize(surfaceTexture, 0);
    vec2 fSize = vec2(size);
    if (retainMipmaps) {
        vec2 dx = dcdx * fSize;
        vec2 dy = dcdy * fSize;
        if (max(dot(dx, dx), dot(dy, dy)) > 1.0) return textureGrad(surfaceTexture, coord, dcdx, dcdy);
    }

    // Iris can bind nearest filtering; height intersections need a continuous surface.
    vec2 texel = coord * fSize - 0.5;
    ivec2 base = ivec2(floor(texel));
    vec2 weight = fract(texel);
    ivec2 limit = size - 1;
    vec4 a = texelFetch(surfaceTexture, clamp(base, ivec2(0), limit), 0);
    vec4 b = texelFetch(surfaceTexture, clamp(base + ivec2(1, 0), ivec2(0), limit), 0);
    vec4 c = texelFetch(surfaceTexture, clamp(base + ivec2(0, 1), ivec2(0), limit), 0);
    vec4 d = texelFetch(surfaceTexture, clamp(base + ivec2(1, 1), ivec2(0), limit), 0);
    return mix(mix(a, b, weight.x), mix(c, d, weight.x), weight.y);
}

vec4 xonSamplePBRNormal(vec2 coord, vec2 dcdx, vec2 dcdy) {
    return xonSamplePBRTexture(normals, coord, dcdx, dcdy, true);
}

vec2 xonPBRAtlasCoord(vec2 localUV, vec4 atlasAM) {
    vec2 inset = min(0.5 / vec2(textureSize(normals, 0)), atlasAM.pq * 0.499);
    return clamp(fract(localUV) * atlasAM.pq + atlasAM.st,
                 atlasAM.st + inset, atlasAM.st + atlasAM.pq - inset);
}

vec2 xonPBRAtlasCoordFast(vec2 localUV, vec4 atlasAM, vec2 minBound, vec2 maxBound) {
    return clamp(fract(localUV) * atlasAM.pq + atlasAM.st, minBound, maxBound);
}

float xonSamplePBRHeight(vec2 coord, vec2 fSize, ivec2 limit) {
    vec2 texel = coord * fSize - 0.5;
    ivec2 base = ivec2(floor(texel));
    vec2 weight = fract(texel);
    float a = texelFetch(normals, clamp(base, ivec2(0), limit), 0).a;
    float b = texelFetch(normals, clamp(base + ivec2(1, 0), ivec2(0), limit), 0).a;
    float c = texelFetch(normals, clamp(base + ivec2(0, 1), ivec2(0), limit), 0).a;
    float d = texelFetch(normals, clamp(base + ivec2(1, 1), ivec2(0), limit), 0).a;
    return mix(mix(a, b, weight.x), mix(c, d, weight.x), weight.y);
}

vec2 xonGetParallaxCoord(vec2 texCoord, vec2 localUV, vec4 atlasAM, vec3 viewVector, float parallaxFade) {
    float viewLength = length(viewVector);
    if (viewVector != viewVector || viewLength < 0.0001 || parallaxFade >= 1.0 || viewVector.z >= -0.00001
        || atlasAM.p <= 0.00001 || atlasAM.q <= 0.00001) {
        return texCoord;
    }

    float viewFacing = -viewVector.z / viewLength;
    float grazingFade = smoothstep(0.04, 0.16, viewFacing);
    if (grazingFade <= 0.001) return texCoord;

    ivec2 texSize = textureSize(normals, 0);
    vec2 fSize = vec2(texSize);
    ivec2 limit = texSize - 1;
    vec2 inset = min(0.5 / fSize, atlasAM.pq * 0.499);
    vec2 minBound = atlasAM.st + inset;
    vec2 maxBound = atlasAM.st + atlasAM.pq - inset;

    vec2 initialCoord = clamp(texCoord, minBound, maxBound);
    vec4 initialNormal = xonSamplePBRTexture(normals, initialCoord, vec2(0.0), vec2(0.0), false);
    if (initialNormal.x + initialNormal.y < 0.0005) return texCoord;

    float height = initialNormal.a;
    if (height >= 0.999) return texCoord;

    vec2 scaledDir = viewVector.xy * (XON_PARALLAX_DEPTH / -viewVector.z)
                   * ((1.0 - parallaxFade) * grazingFade);
    vec2 rayTexels = abs(scaledDir) * atlasAM.pq * fSize;
    int quality = int(clamp(max(float(XON_PARALLAX_QUALITY), ceil(max(rayTexels.x, rayTexels.y) * 2.0)),
                            float(XON_PARALLAX_QUALITY), min(float(XON_PARALLAX_QUALITY) * 8.0, 512.0)));
    float sampleStep = 1.0 / float(quality);
    float currentStep = 1.0;
    vec2 stepDir = scaledDir * sampleStep;
    vec2 coord = localUV;
    float previousHeight = height;

    for (int i = 0; i < quality; ++i) {
        if (currentStep <= height) break;
        previousHeight = height;
        coord += stepDir;
        height = xonSamplePBRHeight(xonPBRAtlasCoordFast(coord, atlasAM, minBound, maxBound), fSize, limit);
        currentStep -= sampleStep;
    }

    vec2 aboveCoord = coord - stepDir;
    float aboveDepth = currentStep + sampleStep;
    float aboveHeight = previousHeight;
    for (int i = 0; i < 5; ++i) {
        vec2 middleCoord = (aboveCoord + coord) * 0.5;
        float middleDepth = (aboveDepth + currentStep) * 0.5;
        float middleHeight = xonSamplePBRHeight(xonPBRAtlasCoordFast(middleCoord, atlasAM, minBound, maxBound), fSize, limit);
        if (middleDepth > middleHeight) {
            aboveCoord = middleCoord;
            aboveDepth = middleDepth;
            aboveHeight = middleHeight;
        } else {
            coord = middleCoord;
            currentStep = middleDepth;
            height = middleHeight;
        }
    }
    float aboveGap = max(aboveDepth - aboveHeight, 0.0);
    float belowGap = max(height - currentStep, 0.0);
    float denominator = aboveGap + belowGap;
    float weight = denominator > 0.000001 ? clamp(aboveGap / denominator, 0.0, 1.0) : 0.5;
    coord = mix(aboveCoord, coord, weight);

    return xonPBRAtlasCoordFast(coord, atlasAM, minBound, maxBound);
}

vec3 xonGetMetalColor(float f0) {
    int metalIdx = int(f0 * 255.0 + 0.5);
    if (metalIdx == 230) return vec3(0.56, 0.57, 0.58); // Iron
    if (metalIdx == 231) return vec3(1.00, 0.77, 0.34); // Gold
    if (metalIdx == 232) return vec3(0.91, 0.92, 0.92); // Aluminum
    if (metalIdx == 233) return vec3(0.55, 0.56, 0.55); // Chrome
    if (metalIdx == 234) return vec3(0.95, 0.64, 0.54); // Copper
    if (metalIdx == 235) return vec3(0.66, 0.67, 0.68); // Lead
    if (metalIdx == 236) return vec3(0.68, 0.67, 0.63); // Platinum
    if (metalIdx == 237) return vec3(0.95, 0.93, 0.88); // Silver
    return vec3(1.0);
}

void xonGetMaterials(out float smoothness, out float metalness, out float f0, out float emission,
                     out float ao, out vec3 normalMap, vec2 coord, vec2 dcdx, vec2 dcdy) {
#if XON_MATERIAL_FORMAT == 1
    // LabPBR 1.3 Specification
    // Metal IDs and the alpha=255 non-emissive sentinel must not be mip-averaged.
    vec4 spec = textureLod(specular, coord, 0.0);
    smoothness = spec.r;

    f0 = spec.g;
    metalness = f0 >= 0.90 ? 1.0 : 0.0;

    // LabPBR 1.3 Emissive: values 0..254 are emissive; 255 (1.0) and 0.0 are NOT emissive
    emission = spec.a < 1.0 ? clamp(spec.a * (255.0 / 254.0), 0.0, 1.0) : 0.0;

    // LabPBR Normals: XY is tangent normal (-1 to 1), Z is AO, W is height
    vec4 normTex = xonSamplePBRNormal(coord, dcdx, dcdy);
    vec2 normXY = normTex.xy * 2.0 - 1.0;
    ao = normTex.z;

    if (normXY.x + normXY.y > -1.999) {
        if (max(abs(normXY.x), abs(normXY.y)) <= 1.0 / 255.0 + 0.00001) normXY = vec2(0.0);
        float lenSq = dot(normXY, normXY);
        if (lenSq > 1.0) normXY *= inversesqrt(lenSq);
        float normZ = sqrt(max(1.0 - dot(normXY, normXY), 0.0));
        normalMap = normalize(vec3(normXY, normZ));
    } else {
        normalMap = vec3(0.0, 0.0, 1.0);
        ao = 1.0;
    }
#else
    // OldPBR / SEUS Format
    vec4 spec = textureGrad(specular, coord, dcdx, dcdy);
    smoothness = spec.r;
    metalness = spec.g;
    f0 = 0.04;
    emission = spec.b * spec.b;

    vec4 normTex = xonSamplePBRNormal(coord, dcdx, dcdy);
    normalMap = normTex.xyz * 2.0 - 1.0;
    ao = 1.0;
    if (normalMap.x + normalMap.y < -1.999 || dot(normalMap, normalMap) < 0.00001) {
        normalMap = vec3(0.0, 0.0, 1.0);
    } else {
        if (max(abs(normalMap.x), abs(normalMap.y)) <= 1.0 / 255.0 + 0.00001) normalMap.xy = vec2(0.0);
        normalMap = normalize(normalMap);
    }
#endif
}

vec3 xonGetPBRSpecular(vec3 normal, vec3 playerPos, float smoothness, float metalness, float f0,
                       vec3 albedo, vec3 sunlightCol, float sunVis) {
    if (smoothness < 0.02 || sunVis < 0.001) return vec3(0.0);

    vec3 viewDir = -xonSafeNormalize(playerPos);
    vec3 lightDir = xonKeyDirection();
    vec3 halfVec = xonSafeNormalize(lightDir + viewDir);

    float nDotL = max(dot(normal, lightDir), 0.0);
    float nDotV = max(dot(normal, viewDir), 0.001);
    float nDotH = max(dot(normal, halfVec), 0.0);
    float vDotH = max(dot(viewDir, halfVec), 0.0);

    if (nDotL <= 0.0) return vec3(0.0);

    float roughness = max(1.0 - smoothness, 0.04);
    float alpha = roughness * roughness;
    float alpha2 = alpha * alpha;

    // GGX Trowbridge-Reitz Distribution
    float denom = nDotH * nDotH * (alpha2 - 1.0) + 1.0;
    float D = alpha2 / max(3.14159265 * denom * denom, 0.0001);

    // Fresnel-Schlick
#if XON_MATERIAL_FORMAT == 1
    vec3 metalReflectance = f0 < 254.5 / 255.0 ? xonGetMetalColor(f0) * albedo : albedo;
    vec3 baseReflectance = mix(vec3(f0), metalReflectance, metalness);
#else
    vec3 baseReflectance = mix(vec3(f0), albedo, metalness);
#endif
    float fBase = clamp(1.0 - vDotH, 0.0, 1.0);
    float f2 = fBase * fBase;
    vec3 F = baseReflectance + (1.0 - baseReflectance) * (f2 * f2 * fBase);

    // Smith-Schlick Geometry Masking
    float k = (roughness + 1.0) * (roughness + 1.0) * 0.125;
    float g1 = nDotL / (nDotL * (1.0 - k) + k);
    float g2 = nDotV / (nDotV * (1.0 - k) + k);
    float G = g1 * g2;

    vec3 specular = (D * F * G) / max(4.0 * nDotL * nDotV, 0.0001);
    return clamp(specular * nDotL * sunlightCol * sunVis * (XON_SUN_STRENGTH * XON_DAY_KEY_GAIN), vec3(0.0), vec3(1.0));
}

#endif
