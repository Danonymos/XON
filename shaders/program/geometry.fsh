#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"
#include "/lib/atmosphere.glsl"
#include "/lib/clouds.glsl"
#include "/lib/shadows.glsl"
#include "/lib/lighting.glsl"
#include "/lib/materials.glsl"
#if defined XON_COLORED_EMISSIVE_LIGHTING && !defined XON_UNLIT && !defined XON_BASIC && !defined XON_CLOUD && !defined XON_WATER && !defined XON_HAND
#define XON_EMISSIVE_SAMPLING
#include "/lib/emissive_light.glsl"
#endif

uniform sampler2D gtexture;
uniform sampler2D depthtex1;
#if defined XON_WATER && defined XON_REFRACTION
uniform sampler2D colortex7;
#endif

in vec2 xonTexCoord;
in vec4 xonAtlasBounds;
in vec2 xonLightLevels;
in vec4 xonVertexColor;
in vec3 xonViewPosition;
in vec3 xonPlayerPosition;
in vec3 xonWorldNormal;
flat in float xonMaterial;

layout(location = 0) out vec4 xonScene;
#ifdef XON_HAND
layout(location = 1) out float xonHandMask;
#endif

#if defined XON_TERRAIN || defined XON_WATER
vec2 xonPortalHash(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
}

// Smooth borderless 2x2 Voronoi light field (0.0 = dark shadow pocket, 1.0 = bright highlight/exposure pocket) with zero cell web lines.
float xonPortalLightField(vec2 x, float time) {
    vec2 n = floor(x);
    vec2 f = fract(x);
    vec2 start = step(vec2(0.5), f) - 1.0;
    float d1 = 8.0;
    for (int j = 0; j < 2; ++j) {
        for (int i = 0; i < 2; ++i) {
            vec2 g = start + vec2(float(i), float(j));
            vec2 rnd = xonPortalHash(n + g);
            vec2 anim = abs(fract(rnd + time * (0.14 + 0.10 * rnd.yx)) * 2.0 - 1.0);
            anim = anim * anim * (3.0 - 2.0 * anim);
            vec2 d = g + 0.14 + 0.72 * anim - f;
            d1 = min(d1, dot(d, d));
        }
    }
    return 1.0 - smoothstep(0.04, 0.78, sqrt(max(d1, 0.0001)));
}
#endif

vec4 xonSampleAnisotropic(vec2 uv) {
#if defined XON_TERRAIN || (XON_ANISOTROPIC > 0 && defined XON_WATER && !defined XON_HAND)
    vec2 du = dFdx(uv);
    vec2 dv = dFdy(uv);
#endif
#ifdef XON_TERRAIN
    vec2 atlasSize = vec2(textureSize(gtexture, 0));
    vec2 texelU = du * atlasSize;
    vec2 texelV = dv * atlasSize;
    float footprint = max(dot(texelU, texelU), dot(texelV, texelV));
    float mipBlend = smoothstep(1.0, 4.0, footprint);
    // Preserve cutout coverage; only minified opaque terrain gets the small stability bias.
    if (abs(xonMaterial - 10003.0) < 0.5 || abs(xonMaterial - 10004.0) < 0.5
        || abs(xonMaterial - 10006.0) < 0.5) mipBlend = 0.0;
    vec4 base = texture(gtexture, uv, mipBlend * 0.32);
    if (mipBlend > 0.001 && base.a < 0.99) return textureGrad(gtexture, uv, du, dv);
#else
    vec4 base = texture(gtexture, uv);
#endif
#if XON_ANISOTROPIC > 0 && (defined XON_TERRAIN || defined XON_WATER) && !defined XON_HAND
    if (base.a < 0.99 || abs(xonMaterial - 10004.0) < 0.5) return base;
    float viewDistSq = dot(xonViewPosition, xonViewPosition);
    if (viewDistSq < 4.0 || viewDistSq > 1444.0) return base;
    vec3 surfNormal = xonSafeNormalize(xonWorldNormal);
    if (abs(surfNormal.y) < 0.72) return base;
    vec3 viewDir = xonSafeNormalize(xonPlayerPosition);
    float NoV = abs(dot(viewDir, surfNormal));
    // Extra grazing-angle taps stay local; the base mip footprint remains stable at every distance.
    float anisoStrength = (1.0 - smoothstep(0.08, 0.76, NoV))
                        * smoothstep(4.0, 25.0, viewDistSq)
                        * (1.0 - smoothstep(900.0, 1444.0, viewDistSq));
    if (anisoStrength <= 0.01) return base;
    float lenU = dot(du, du);
    float lenV = dot(dv, dv);
    if (max(lenU, lenV) < min(lenU, lenV) * 1.75) return base;
    vec2 major = (lenV >= lenU ? dv : du) * 0.46;
    vec2 minor = (lenV >= lenU ? du : dv) * 0.34;
    bool hasBounds = xonAtlasBounds.z > 0.00001 && xonAtlasBounds.w > 0.00001;
    vec2 minBound = hasBounds ? (xonAtlasBounds.xy - xonAtlasBounds.zw * 0.985) : (uv - abs(major) * 2.0);
    vec2 maxBound = hasBounds ? (xonAtlasBounds.xy + xonAtlasBounds.zw * 0.985) : (uv + abs(major) * 2.0);
    vec3 accum = base.rgb;
    float weight = 1.0;
    vec4 s1 = textureGrad(gtexture, clamp(uv + major * 0.45, minBound, maxBound), du, dv);
    vec4 s2 = textureGrad(gtexture, clamp(uv - major * 0.45, minBound, maxBound), du, dv);
    if (s1.a >= 0.99 && s2.a >= 0.99) {
        accum += s1.rgb + s2.rgb;
        weight += 2.0;
    }
#if XON_ANISOTROPIC >= 4
    vec4 s3 = textureGrad(gtexture, clamp(uv + major * 0.95, minBound, maxBound), du, dv);
    vec4 s4 = textureGrad(gtexture, clamp(uv - major * 0.95, minBound, maxBound), du, dv);
    if (s3.a >= 0.99 && s4.a >= 0.99) {
        accum += (s3.rgb + s4.rgb) * 0.85;
        weight += 1.7;
    }
#endif
#if XON_ANISOTROPIC >= 6
    vec4 s5 = textureGrad(gtexture, clamp(uv + minor * 0.75, minBound, maxBound), du, dv);
    vec4 s6 = textureGrad(gtexture, clamp(uv - minor * 0.75, minBound, maxBound), du, dv);
    if (s5.a >= 0.99 && s6.a >= 0.99) {
        accum += (s5.rgb + s6.rgb) * 0.65;
        weight += 1.3;
    }
#endif
    float tapStrength = XON_ANISOTROPIC == 2 ? 0.82 : (XON_ANISOTROPIC == 4 ? 0.90 : 0.96);
    return vec4(mix(base.rgb, accum / weight, anisoStrength * tapStrength), base.a);
#else
    return base;
#endif
}

void main() {
#if XON_RENDER_MODE > 0
    if (any(greaterThanEqual(gl_FragCoord.xy, vec2(viewWidth, viewHeight) * XON_RENDER_SCALE))) discard;
#endif
#ifdef XON_LINE
    vec3 worldPos = xonPlayerPosition + cameraPosition;
    // Block selection outline has low vertex RGB (vanilla black with 0.4 alpha); keep debug lines (F3+B) colored.
    bool isSelectionOutline = max(xonVertexColor.r, max(xonVertexColor.g, xonVertexColor.b)) < 0.15;
    if (isSelectionOutline) {
#if XON_BLOCK_OUTLINE == 1
        float phase = fract((worldPos.x + worldPos.y + worldPos.z) * 0.65 - frameTimeCounter * 0.675) * 8.0;
        const vec3 colors[8] = vec3[8](
            vec3(1.00, 0.16, 0.24), vec3(1.00, 0.50, 0.06),
            vec3(1.00, 0.85, 0.14), vec3(0.16, 1.00, 0.44),
            vec3(0.08, 0.86, 1.00), vec3(0.16, 0.32, 1.00),
            vec3(0.62, 0.18, 1.00), vec3(1.00, 0.16, 0.68));
        int stop = int(floor(phase));
        float blend = fract(phase);
        blend = blend * blend * (3.0 - 2.0 * blend);
        vec3 rainbow = mix(colors[stop], colors[(stop + 1) % 8], blend);
        vec3 lineColor = xonToLinear(mix(vec3(1.0), rainbow, 0.88));
        // Equalize perceived brightness to tame flashing as yellow rotates into blue.
        lineColor *= 0.55 / max(xonLuminance(lineColor), 0.08);
        lineColor /= max(1.0, max(lineColor.r, max(lineColor.g, lineColor.b)) / 1.6);
        xonScene = vec4(lineColor, 0.95);
#else
        xonScene = vec4(vec3(0.002), 0.88);
#endif
    } else {
        xonScene = vec4(xonToLinear(xonVertexColor.rgb), xonVertexColor.a);
    }
    return;
#endif
#ifdef XON_BASIC
    vec4 texel = vec4(1.0);
    vec4 surface = xonVertexColor;
#else
    vec4 texel = xonSampleAnisotropic(xonTexCoord);
    vec4 surface = vec4(texel.rgb * xonVertexColor.rgb, texel.a);
#endif
#ifndef XON_TERRAIN
    surface.a *= xonVertexColor.a;
#endif
    if (surface.a < alphaTestRef) discard;
#ifdef XON_TERRAIN
    bool isCrossPlant = abs(xonMaterial - 10004.0) < 0.5;
#else
    bool isCrossPlant = false;
#endif
#ifdef XON_ENTITY
    surface.rgb = mix(surface.rgb, entityColor.rgb, entityColor.a);
#endif
    vec3 color = xonToLinear(surface.rgb);
    vec3 normal = isCrossPlant ? vec3(0.0, 1.0, 0.0) : xonSafeNormalize(xonWorldNormal);
    bool isLava = abs(xonMaterial - 10005.0) < 0.5;
    float emission = float(abs(xonMaterial - 10002.0) < 0.5 || isLava);
    float foliage = float(abs(xonMaterial - 10003.0) < 0.5 || isCrossPlant);
    float sunVisibility = 1.0;
    bool composedWater = false;
#ifdef XON_TERRAIN
    float rawAO = xonVertexColor.a < 0.05 ? 1.0 : clamp(xonVertexColor.a, 0.28, 1.0);
    if (emission < 0.5) {
        // Architectural cavity shading: recessed castle blocks take cool shadow depth while flat/lit blocks never overexpose.
        float aoCurve = isCrossPlant ? mix(0.92, 1.0, rawAO) : pow(rawAO, 1.18 * XON_AO_STRENGTH);
        float cavity = xonSaturate((0.90 - rawAO) * 1.45) * (1.0 - float(isCrossPlant));
        vec3 aoTint = mix(vec3(1.0), vec3(0.86, 0.92, 1.04), cavity);
        color *= clamp(aoCurve, 0.36, 1.0) * aoTint;
    }
#endif
#ifdef XON_EMISSIVE_SAMPLING
    vec3 emissiveAlbedo = color;
#endif

#if defined XON_CLOUD
#ifdef XON_CLOUD_LIGHTING
    float day = xonDaylight();
    vec3 cloudTint = mix(vec3(0.10, 0.15, 0.25), vec3(1.35, 1.32, 1.25), day);
    cloudTint = mix(cloudTint, mix(vec3(0.08, 0.11, 0.16), vec3(0.49, 0.59, 0.72), day), rainStrength);
    cloudTint *= 0.72 + max(normal.y, 0.0) * 0.28;
    color *= cloudTint;
#endif
#elif !defined XON_UNLIT && !defined XON_BASIC
    // These materials replace surface lighting entirely below.
    bool independentMaterial = false;
#if defined XON_TERRAIN || defined XON_WATER
    independentMaterial = isLava || abs(xonMaterial - 10021.0) < 0.5 || abs(xonMaterial - 10022.0) < 0.5;
#endif
#if defined XON_WATER && defined XON_REFRACTION && !defined XON_HAND
    independentMaterial = independentMaterial || abs(xonMaterial - 10001.0) < 0.5;
#endif
    if (!independentMaterial) {
        color = xonLighting(color, normal, xonViewPosition, xonPlayerPosition, xonLightLevels, emission, foliage, sunVisibility);
#ifdef XON_EMISSIVE_SAMPLING
        // Peak matches a strong but sub-torch block light; the voxel field supplies colour and falloff.
        if (xonVoxelEmitterId(xonMaterial) == XON_VOXEL_EMPTY) {
            color += emissiveAlbedo * xonEmissiveLight(xonPlayerPosition, normal) * 1.45;
        }
#endif
#ifdef XON_TERRAIN
        if (emission < 0.5 && abs(xonMaterial - 10019.0) > 0.5 && !isCrossPlant) {
            float viewDistSq = dot(xonViewPosition, xonViewPosition);
            if (viewDistSq < 625.0) {
                // Zero-mean derivative micro-bevel relief within 25m so light plays across castle stone bricks without distant overdraw cost.
                float closeFade = 1.0 - smoothstep(100.0, 625.0, viewDistSq);
                float texLuma = dot(texel.rgb, vec3(0.30, 0.59, 0.11));
                vec2 texGrad = vec2(dFdx(texLuma), dFdy(texLuma));
                vec3 sunWorld = xonSunDirection();
                vec3 keyWorld = xonSafeNormalize(vec3(sunWorld.x, max(abs(sunWorld.y), 0.35), sunWorld.z));
                vec2 lightScreen = (mat3(gbufferModelView) * keyWorld).xy;
                float bevel = clamp(dot(texGrad, lightScreen) * 2.4, -0.14, 0.14) * closeFade * (0.30 + 0.70 * sunVisibility);
                float wallRelief = (rawAO - 0.85) * 0.22 * closeFade * sunVisibility * (1.0 - abs(normal.y) * 0.65);
                color *= 1.0 + bevel + wallRelief;
            }
        }
#endif
    }
#endif

#if defined XON_TERRAIN || defined XON_WATER
    if (isLava) {
        vec3 worldPos = xonPlayerPosition + cameraPosition;
        vec2 lavaPos = worldPos.xz + worldPos.y * 0.35;
        float lavaTime = frameTimeCounter * 0.018;
        // Voronoi-like convection cells: dark cooling crust and white-hot glowing magma fissures.
        vec2 cellUV1 = lavaPos * 0.042 + vec2(lavaTime, -lavaTime * 0.7);
        vec2 cellUV2 = vec2(lavaPos.x * 0.068 - lavaPos.y * 0.051, lavaPos.x * 0.051 + lavaPos.y * 0.068)
                     + vec2(-lavaTime * 1.2, lavaTime * 0.9);
        vec3 n1 = texture(noisetex, cellUV1).rgb;
        vec3 n2 = texture(noisetex, cellUV2 + (n1.xy - 0.5) * 0.06).rgb;
        float voronoiCell = abs(n1.r - n2.g) * 1.35 + abs(n1.b - n2.r) * 0.85;
        float fissure = 1.0 - smoothstep(0.04, 0.42, voronoiCell);
        float crust = smoothstep(0.38, 0.88, voronoiCell);
        float texLuma = dot(texel.rgb, vec3(0.35, 0.55, 0.10));
        float heat = clamp(fissure * 0.68 + smoothstep(0.32, 0.85, texLuma) * 0.55 - crust * 0.38, 0.0, 1.0);
        vec3 darkCrust = vec3(0.28, 0.028, 0.004);
        vec3 moltenOrange = vec3(2.35, 0.58, 0.05);
        vec3 brightCore = vec3(4.20, 2.35, 0.48);
        color = mix(mix(darkCrust, moltenOrange, smoothstep(0.0, 0.58, heat)),
                    brightCore, smoothstep(0.55, 1.0, heat));
    } else if (abs(xonMaterial - 10019.0) < 0.5) {
        // Amethyst & crystal clusters: preserve exact vanilla pale lilac-white tips and lavender base without orange torch tint or solid purple override.
        float crystalGlow = xonOreEmission(xonMaterial, texel.rgb);
        vec3 baseLinear = clamp(xonToLinear(texel.rgb), 0.001, 1.0);
        float baseLuma = max(dot(baseLinear, vec3(0.2126, 0.7152, 0.0722)), 0.05);
        float litIntensity = clamp(dot(color, vec3(0.2126, 0.7152, 0.0722)) / baseLuma, 0.72, 1.12);
        color = baseLinear * (litIntensity + crystalGlow * 0.28);
    } else if (abs(xonMaterial - 10021.0) < 0.5) {
        // Nether Portal (block.10021): keep 100% vanilla portal texture/swirl, while driving its lighting, contrast, and exposure with a smooth 3D Voronoi light field.
        vec3 worldPos = xonPlayerPosition + cameraPosition;
        vec3 viewDir = xonSafeNormalize(xonPlayerPosition);
        float NoV = max(abs(dot(viewDir, normal)), 0.28);
        vec3 p0 = worldPos;
        vec3 p1 = worldPos + viewDir * (0.48 / NoV);
        vec2 uv0 = abs(normal.x) > 0.5 ? p0.zy : (abs(normal.z) > 0.5 ? p0.xy : p0.xz);
        vec2 uv1 = abs(normal.x) > 0.5 ? p1.zy : (abs(normal.z) > 0.5 ? p1.xy : p1.xz);
        float pTime = frameTimeCounter * 0.36;
        vec2 warp = (texture(noisetex, uv0 * 0.035 + vec2(pTime * 0.02, -pTime * 0.015)).rg - 0.5) * 0.65;
        vec2 rotUV1 = vec2(uv1.x * 0.866 - uv1.y * 0.500, uv1.x * 0.500 + uv1.y * 0.866);
        // Smooth borderless Voronoi lighting pools (~2.5-block radius, zero cell web lines).
        float vFront = xonPortalLightField(uv0 * 0.42 + warp + vec2(0.0, -pTime * 0.18), pTime);
        float vDeep  = xonPortalLightField(rotUV1 * 0.58 - warp * 0.6 + vec2(pTime * 0.14, pTime * 0.11), pTime * 0.85);
        float lightWave = clamp(vFront * 0.58 + vDeep * 0.52, 0.0, 1.0);
        float shadowZone = 1.0 - smoothstep(0.10, 0.48, lightWave);
        float highlightZone = smoothstep(0.45, 0.92, lightWave);
        // Pure vanilla portal texture: modulate ONLY its brightness, contrast, and highlight exposure.
        vec3 vanillaLinear = max(xonToLinear(texel.rgb), vec3(0.001));
        vec3 contrastedVanilla = pow(vanillaLinear, vec3(mix(1.38, 0.86, lightWave)));
        float exposure = mix(0.28, 2.05, lightWave * lightWave) * (0.82 + 0.22 * NoV);
        vec3 highlightBoost = pow(vanillaLinear, vec3(1.55)) * (highlightZone * highlightZone * 1.75);
        vec3 deepShadowTint = mix(vec3(1.0), vec3(0.72, 0.42, 1.08), shadowZone * 0.65);
        color = contrastedVanilla * exposure * deepShadowTint + highlightBoost;
    } else if (abs(xonMaterial - 10022.0) < 0.5) {
        // Froglights (Ochre, Verdant, Pearlescent): preserve aged colored borders and soft pastel centers without white HDR/bloom blowout.
        vec3 srgb = clamp(texel.rgb, 0.001, 1.0);
        float texLuma = dot(srgb, vec3(0.299, 0.587, 0.114));
        float borderMask = 1.0 - smoothstep(0.68, 0.94, texLuma);
        vec3 shaped = pow(srgb, vec3(mix(2.45, 3.15, borderMask)));
        float shapedLuma = dot(shaped, vec3(0.2126, 0.7152, 0.0722));
        vec3 richFroglight = mix(vec3(shapedLuma), shaped, 1.0 + 0.38 * borderMask);
        float faceShade = 0.88 + 0.12 * abs(normal.y);
        color = max(richFroglight, vec3(0.01)) * (0.76 * faceShade);
    } else if (abs(xonMaterial - 10020.0) < 0.5) {
        float accentGlow = xonOreEmission(xonMaterial, texel.rgb);
        vec3 accentColor = pow(clamp(xonToLinear(texel.rgb), 0.001, 1.0), vec3(1.30));
        color += accentColor * accentGlow * 0.95;
    } else if (xonMaterial > 10009.5) {
        float oreGlow = xonOreEmission(xonMaterial, texel.rgb);
        vec3 oreColor = xonToLinear(texel.rgb);
        oreColor /= max(max(oreColor.r, max(oreColor.g, oreColor.b)), 0.08);
        color += oreColor * oreGlow * 2.25;
    }
#endif
#ifdef XON_TERRAIN
#ifdef XON_CAUSTICS
    if (isEyeInWater == 1 && !isLava && xonLightLevels.y > 0.05) {
        vec3 worldPos = xonPlayerPosition + cameraPosition;
        vec2 cUV1 = worldPos.xz * 0.032 + vec2(frameTimeCounter * 0.022, -frameTimeCounter * 0.016);
        vec2 cUV2 = worldPos.xz * 0.039 + vec2(-frameTimeCounter * 0.019, frameTimeCounter * 0.024);
        float c1 = texture(noisetex, cUV1).r;
        float c2 = texture(noisetex, cUV2).g;
        float caustic = smoothstep(0.02, 0.26, 1.0 - abs(c1 - c2) * 3.2);
        color += color * vec3(0.35, 0.65, 0.80) * caustic * xonLightLevels.y * xonDaylight() * 0.65;
    }
#endif
#endif

#ifdef XON_EMISSIVE
    color = max(color, xonToLinear(surface.rgb) * 1.8);
#endif

#ifdef XON_WATER
    if (abs(xonMaterial - 10001.0) < 0.5) {
        vec2 wavePosition = mod(xonPlayerPosition.xz + mod(cameraPosition.xz, 1024.0), 1024.0);
        vec3 waterNormal = normal;
        vec3 worldView = xonSafeNormalize(xonPlayerPosition);
        float rawFacing = xonSaturate(abs(dot(-worldView, normal)));
        float crestHeight = 0.0;
#if XON_WATER_DETAIL == 1
        float viewDistSq = dot(xonViewPosition, xonViewPosition);
        if (viewDistSq < 16384.0) {
            float waveTime = mod(frameTimeCounter, 2048.0);
            float distanceFade = 1.0 - smoothstep(256.0, 16384.0, viewDistSq);
            float rippleFade = 1.0 - smoothstep(64.0, 2304.0, viewDistSq);
            // Grazing-angle suppression prevents sub-pixel horizon shimmer.
            float grazingFilter = smoothstep(0.02, 0.26, rawFacing);

            // Tier 1: Rolling wind swell.
            vec2 uv1 = wavePosition * 0.024 + vec2(waveTime * 0.014, -waveTime * 0.009);
            // Tier 2: Crisp interlocking trochoidal wavelets.
            vec2 uv2 = vec2(wavePosition.x * 0.062 - wavePosition.y * 0.046,
                            wavePosition.x * 0.046 + wavePosition.y * 0.062)
                     + vec2(-waveTime * 0.022, waveTime * 0.017);
            // Tier 3: Fine liquid capillary surface ripples.
            vec2 uv3 = vec2(wavePosition.x * 0.145 + wavePosition.y * 0.115,
                            -wavePosition.x * 0.115 + wavePosition.y * 0.145)
                     + vec2(waveTime * 0.029, waveTime * 0.024);

            vec3 n1 = texture(noisetex, uv1).rgb * 2.0 - 1.0;
            vec3 n2 = texture(noisetex, uv2 + n1.xy * 0.055).rgb * 2.0 - 1.0;
            vec3 n3 = texture(noisetex, uv3 + n2.yz * 0.045).rgb * 2.0 - 1.0;

            // Trochoidal crest sharpening gives distinct liquid wave ridges and smooth troughs.
            vec2 swellSlope = n1.xy * (1.0 + 0.45 * abs(n1.xy)) * 0.068;
            vec2 waveletSlope = n2.yz * (1.0 + 0.65 * abs(n2.yz)) * 0.058
                              + vec2(n1.z - n2.x, n2.z - n1.y) * 0.032;
            vec2 capillarySlope = (n3.xy * 0.038 + vec2(n3.z - n3.y, n3.x - n3.z) * 0.024) * rippleFade;

            vec2 organicSlope = (swellSlope + waveletSlope + capillarySlope)
                              * distanceFade * grazingFilter * (1.0 + rainStrength * 0.45) * abs(normal.y) * XON_WAVE_HEIGHT;
            waterNormal = xonSafeNormalize(normal + vec3(organicSlope.x, 0.0, organicSlope.y));
            crestHeight = xonSaturate((n1.z * 0.45 + n2.x * 0.40 + n3.z * 0.25 * rippleFade) * 1.45 + 0.18)
                        * distanceFade * abs(normal.y) * XON_WAVE_HEIGHT;
        }
#endif
        float facing = xonSaturate(abs(dot(-worldView, waterNormal)));
        float oneMinusFacing = 1.0 - facing;
        float omf2 = oneMinusFacing * oneMinusFacing;
        float fresnel = 0.034 + 0.966 * omf2 * omf2 * oneMinusFacing;
        vec2 sourceUV = gl_FragCoord.xy / vec2(viewWidth, viewHeight);
        float solidDepth = texture(depthtex1, sourceUV).r;
        float waterDepth = max(xonViewDepth(solidDepth) - abs(xonViewPosition.z), 0.0);
        waterDepth = min(waterDepth, isEyeInWater == 1 ? 18.0 : 64.0);
        float absorption = 1.0 - exp(-waterDepth * (isEyeInWater == 1 ? 0.045 : 0.105));
        vec3 biomeWater = max(xonToLinear(xonVertexColor.rgb), vec3(0.02));
        vec3 shallowTint = mix(vec3(0.038, 0.22, 0.25), biomeWater * 0.44, 0.35);
        vec3 deepTint = mix(vec3(0.015, 0.105, 0.175), biomeWater * 0.32, 0.30);
        vec3 waterTint = mix(shallowTint, deepTint, smoothstep(0.0, 12.0, waterDepth));
        vec3 sunDir = xonSunDirection();
        float day = xonDaylight(sunDir.y);
        vec3 scatterLight = vec3(0.14) + vec3(0.72, 0.81, 0.92) * max(xonLightLevels.y, isEyeInWater == 1 ? 0.65 : 0.0);
#if XON_DIMENSION == 0 && XON_CLOUD_STYLE == 1
        float waterCloudLight = xonCloudGroundLight(xonPlayerPosition.xz + cameraPosition.xz) * smoothstep(0.35, 0.92, xonLightLevels.y);
        scatterLight *= 1.0 + waterCloudLight * 0.35;
#endif
        waterTint *= scatterLight;
        // Luminous turquoise subsurface scattering through sunlit wave crests on the water surface.
        vec3 crestGlow = vec3(0.045, 0.34, 0.36) * (crestHeight * crestHeight)
                       * (0.30 + 0.70 * day) * smoothstep(0.25, 0.92, xonLightLevels.y);
        waterTint += crestGlow;
        color = mix(color * 0.68, waterTint, 0.25 + absorption * 0.35);
#ifdef XON_REFRACTION
#ifndef XON_HAND
        vec2 displayUV = sourceUV / XON_RENDER_SCALE;
        vec3 viewPerturbation = mat3(gbufferModelView) * (waterNormal - normal);
        vec2 refractedUV = displayUV + viewPerturbation.xy * 0.032 / (1.0 + abs(xonViewPosition.z) * 0.025);
        vec2 border = 1.0 / vec2(viewWidth, viewHeight);
        refractedUV = clamp(refractedUV, border, 1.0 - border);
        float refractedDepth = texture(depthtex1, xonSourceUV(refractedUV)).r;
        if (xonViewDepth(refractedDepth) < abs(xonViewPosition.z) + 0.03) refractedUV = displayUV;
        vec3 absorbRate = isEyeInWater == 1 ? vec3(0.045, 0.016, 0.010) : vec3(0.125, 0.038, 0.024);
        vec3 transmission = exp(-absorbRate * waterDepth);
        // Thin indoor sheets need a visible surface even without sky reflections.
        float shallowFilm = isEyeInWater == 0 ? 1.0 - smoothstep(0.0, 1.5, waterDepth) : 0.0;
        transmission *= vec3(1.0) - vec3(0.34, 0.16, 0.025) * shallowFilm;
        color = texture(colortex7, refractedUV).rgb * transmission + waterTint * (1.0 - transmission);
        if (isEyeInWater != 1) color += crestGlow * 0.55;
        composedWater = true;
#endif
#endif
        if (isEyeInWater != 1) {
            vec3 reflDir = reflect(worldView, waterNormal);
            reflDir.y = max(reflDir.y, abs(reflDir.y) * 0.35 + 0.022);
            vec3 reflection = xonCloudSky(xonSafeNormalize(reflDir), false);
            reflection *= smoothstep(0.20, 0.92, xonLightLevels.y);
            color = mix(color, reflection, min(fresnel, 0.90));
        }
#if XON_DIMENSION == 0
        if (isEyeInWater != 1) {
#if defined XON_REFRACTION && defined XON_SHADOWS && !defined XON_HAND
            // Refractive water replaces diffuse lighting; only its glint needs the receiver shadow.
            vec3 keyDirection = xonKeyDirection();
            float nDotL = dot(normal, keyDirection);
            float keyFacing = max(nDotL, 0.0);
            float grazing = xonSquare(clamp(nDotL * 0.45 + 0.30, 0.0, 1.0)) * (1.0 - keyFacing) * 0.16 * xonSaturate(nDotL * 6.25);
            float openSky = smoothstep(0.55, 0.97, xonLightLevels.y);
            if (keyFacing + grazing > 0.001 && openSky > 0.001) {
                sunVisibility = xonShadowVisibility(xonPlayerPosition, normal, keyFacing, xonLightLevels.y, 0.0);
            }
#endif
            vec3 lightDir = sunDir.y >= -0.05 ? sunDir : -sunDir;
            vec3 halfVector = xonSafeNormalize(lightDir - worldView);
            float nh = max(dot(waterNormal, halfVector), 0.0);
            float nh2 = nh * nh;
            float nh4 = nh2 * nh2;
            float nh8 = nh4 * nh4;
            float nh16 = nh8 * nh8;
            float nh64 = nh16 * nh16 * nh16 * nh16;
            // Dual-lobe water surface glitter: crisp sun/moon diamond glints + warm/silver shimmer path.
            float sunGlint = (nh64 * nh64 * nh64 * 3.4 + nh16 * nh8 * 0.42 + nh8 * 0.08 * crestHeight)
                           * (1.0 - rainStrength * 0.85) * smoothstep(0.50, 0.95, xonLightLevels.y);
            vec3 glintColor = mix(xonNightColor() * 2.6, xonSunlightColor(sunDir) * sunVisibility, day);
            color += glintColor * sunGlint;
        }
#endif
        surface.a = composedWater ? 1.0 : clamp(0.24 + absorption * 0.48 + fresnel * 0.32, 0.24, 0.95);
    }
#endif

#ifndef XON_HAND
#ifdef XON_UNLIT
    color *= exp(-length(xonViewPosition) * max(blindness, darknessFactor) * 0.16);
#else
    if (!composedWater || isEyeInWater == 0) color = xonFog(color, xonViewPosition, xonLightLevels.y);
#endif
#endif
    xonScene = vec4(max(color, vec3(0.0)), surface.a);
#ifdef XON_HAND
    xonHandMask = 1.0;
#endif
}
