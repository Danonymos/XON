#include "/lib/settings.glsl"
#include "/lib/uniforms.glsl"
#include "/lib/math.glsl"
#include "/lib/atmosphere.glsl"
#include "/lib/clouds.glsl"
#include "/lib/shadows.glsl"
#include "/lib/lighting.glsl"
#include "/lib/materials.glsl"

uniform sampler2D gtexture;
uniform sampler2D depthtex1;
#if defined XON_WATER && defined XON_REFRACTION
uniform sampler2D colortex7;
#endif

in vec2 xonTexCoord;
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
        float phase = (worldPos.x + worldPos.y + worldPos.z) * 0.65 - frameTimeCounter * 1.35;
        vec3 rainbow = 0.5 + 0.5 * cos(6.2831853 * (phase + vec3(0.0, 0.3333, 0.6667)));
        vec3 lineColor = xonToLinear(mix(vec3(1.0), rainbow, 0.88)) * 2.1;
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
    vec4 texel = texture(gtexture, xonTexCoord);
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
    if (emission < 0.5) {
        float rawAO = xonVertexColor.a < 0.05 ? 1.0 : clamp(xonVertexColor.a, 0.20, 1.0);
        float aoCurve = isCrossPlant ? mix(0.92, 1.0, rawAO) : pow(rawAO, 1.28 * XON_AO_STRENGTH);
        color *= clamp(aoCurve, 0.20, 1.0);
    }
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
    color = xonLighting(color, normal, xonViewPosition, xonPlayerPosition, xonLightLevels, emission, foliage, sunVisibility);
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
        // Amethyst & purple crystals/portals: transform pale whitish crystal tips into rich royal amethyst purple and prevent white washout.
        float crystalGlow = xonOreEmission(xonMaterial, texel.rgb);
        vec3 baseLinear = clamp(xonToLinear(texel.rgb), 0.001, 1.0);
        float luma = dot(baseLinear, vec3(0.2126, 0.7152, 0.0722));
        vec3 royalAmethyst = vec3(0.56, 0.16, 0.92) * (0.35 + 0.75 * luma);
        vec3 tintedCrystal = mix(baseLinear * vec3(0.85, 0.36, 1.15), royalAmethyst, smoothstep(0.35, 0.85, baseLinear.g));
        float lightScale = min(max(max(color.r, color.g), color.b) / max(luma, 0.08), 1.15);
        color = tintedCrystal * lightScale + royalAmethyst * crystalGlow * 0.55;
        color = min(color, vec3(0.78, 0.34, 1.02));
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
                              * distanceFade * grazingFilter * (1.0 + rainStrength * 0.45) * abs(normal.y);
            waterNormal = xonSafeNormalize(normal + vec3(organicSlope.x, 0.0, organicSlope.y));
            crestHeight = xonSaturate((n1.z * 0.45 + n2.x * 0.40 + n3.z * 0.25 * rippleFade) * 1.45 + 0.18)
                        * distanceFade * abs(normal.y);
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
        color = texture(colortex7, refractedUV).rgb * transmission + waterTint * (1.0 - transmission);
        if (isEyeInWater != 1) color += crestGlow * 0.55;
        composedWater = true;
#endif
#endif
        vec3 reflDir = reflect(worldView, waterNormal);
        reflDir.y = max(reflDir.y, abs(reflDir.y) * 0.35 + 0.022);
        vec3 reflection = xonCloudSky(xonSafeNormalize(reflDir), false);
        reflection *= smoothstep(0.20, 0.92, xonLightLevels.y);
        reflection = xonFog(reflection, xonViewPosition, xonLightLevels.y);
        if (isEyeInWater != 1) color = mix(color, reflection, min(fresnel, 0.90));
#if XON_DIMENSION == 0
        if (isEyeInWater != 1) {
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
            vec3 glintColor = mix(xonNightColor() * 2.6, xonSunlightColor(sunDir.y) * sunVisibility, day);
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
    if (!composedWater) color = xonFog(color, xonViewPosition, xonLightLevels.y);
#endif
#endif
    xonScene = vec4(max(color, vec3(0.0)), surface.a);
#ifdef XON_HAND
    xonHandMask = 1.0;
#endif
}
