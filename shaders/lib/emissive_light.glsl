#ifndef XON_EMISSIVE_LIGHT
#define XON_EMISSIVE_LIGHT

// Camera-centred voxel volume shared by the shadow pass (voxelization), shadowcomp
// (flood fill) and geometry passes (sampling). Must match the image sizes in shaders.properties.
const ivec3 XON_VOXEL_SIZE = ivec3(96, 48, 96);
const ivec3 XON_VOXEL_HALF = XON_VOXEL_SIZE / 2;

const uint XON_VOXEL_EMPTY = 0u;
const uint XON_VOXEL_SOLID = 1u;
const uint XON_VOXEL_FIRST_EMITTER = 2u;

// Reserve three additional open blocks for the outer aura to ease into darkness.
const float XON_EMISSIVE_REACH = XON_EMISSIVE_RADIUS + 3.0;
const float XON_EMISSIVE_STEP = 1.0 / (XON_EMISSIVE_REACH + 1.0);

uint xonVoxelEmitterId(float material) {
    int id = int(material + 0.5);
    if (id == 10006) return 13u;
    if (id == 10010) return 2u;
    if (id == 10011) return 3u;
    if (id == 10012) return 4u;
    if (id == 10013) return 5u;
    if (id == 10014 || id == 10017) return 6u;
    if (id == 10015) return 7u;
    if (id == 10016) return 8u;
    if (id == 10018) return 9u;
    if (id == 10019) return 10u;
    if (id == 10020) return 11u;
    if (id == 10023) return 12u;
    if (id == 10024) return 14u;
    return XON_VOXEL_EMPTY;
}

// Linear light colour premultiplied by per-family strength.
vec3 xonVoxelEmitterColor(uint id) {
    if (id == 2u) return vec3(0.25, 0.90, 1.00);
    if (id == 3u) return vec3(0.20, 1.00, 0.40) * 0.90;
    if (id == 4u) return vec3(1.00, 0.12, 0.06);
    if (id == 5u) return vec3(0.18, 0.35, 1.00);
    if (id == 6u) return vec3(1.00, 0.74, 0.20) * 0.90;
    if (id == 7u) return vec3(0.95, 0.72, 0.58) * 0.45;
    if (id == 8u) return vec3(1.00, 0.52, 0.28) * 0.70;
    if (id == 9u) return vec3(0.64, 0.32, 1.00) * 0.60;
    if (id == 10u) return vec3(0.72, 0.38, 1.00) * 0.90;
    if (id == 11u) return vec3(0.15, 0.75, 0.85) * 0.80;
    if (id == 12u) return vec3(0.64, 0.32, 1.00) * 0.45;
    if (id == 13u) return vec3(0.42, 0.78, 0.62) * 0.26;
    if (id == 14u) return vec3(1.00, 0.56, 0.18) * 0.35;
    return vec3(0.0);
}

ivec3 xonWorldToVoxel(vec3 playerPos) {
    return ivec3(floor(playerPos + fract(cameraPosition))) + XON_VOXEL_HALF;
}

bool xonVoxelInBounds(ivec3 voxel) {
    return all(greaterThanEqual(voxel, ivec3(0))) && all(lessThan(voxel, XON_VOXEL_SIZE));
}

#ifdef XON_EMISSIVE_SAMPLING
uniform sampler3D xonLightTex0;
uniform sampler3D xonLightTex1;

vec4 xonFetchLight(ivec3 voxel) {
    if (!xonVoxelInBounds(voxel)) return vec4(0.0, 0.0, 0.0, -1.0);
    return (frameCounter & 1) == 0 ? texelFetch(xonLightTex0, voxel, 0) : texelFetch(xonLightTex1, voxel, 0);
}

// Trilinear blend over open voxels only (solid voxels store alpha -1), so walls do not
// darken the light pooled on the floor beside them. Returns colour already scaled by falloff.
vec3 xonEmissiveLight(vec3 playerPos, vec3 normal) {
    vec3 voxelPos = playerPos + fract(cameraPosition) + vec3(XON_VOXEL_HALF) + normal * 0.5 - 0.5;
    vec3 edgeDistance = min(voxelPos, vec3(XON_VOXEL_SIZE) - 1.0 - voxelPos);
    float volumeFade = smoothstep(0.0, 6.0, min(edgeDistance.x, min(edgeDistance.y, edgeDistance.z)));
    if (volumeFade <= 0.0) return vec3(0.0);
    ivec3 base = ivec3(floor(voxelPos));
    vec3 blend = voxelPos - vec3(base);
    vec3 colorSum = vec3(0.0);
    float levelSum = 0.0;
    float weightSum = 0.0;
    for (int corner = 0; corner < 8; ++corner) {
        ivec3 offset = ivec3(corner & 1, (corner >> 1) & 1, (corner >> 2) & 1);
        vec3 axis = mix(1.0 - blend, blend, vec3(offset));
        vec4 light = xonFetchLight(base + offset);
        float weight = axis.x * axis.y * axis.z * step(0.0, light.a);
        colorSum += light.rgb * (light.a * weight);
        levelSum += light.a * weight;
        weightSum += weight;
    }
    if (levelSum <= 0.0001) return vec3(0.0);
    float level = levelSum / weightSum;
    // Quintic easing has zero slope and curvature at the bright core and dark outer edge.
    float falloff = level * level * level * (level * (level * 6.0 - 15.0) + 10.0);
    // Tiny surviving corner weights must fade rather than normalize into a bright occluder-edge flash.
    float occlusionFade = smoothstep(0.0, 0.5, weightSum);
    return (colorSum / levelSum) * falloff * volumeFade * occlusionFade * XON_EMISSIVE_INTENSITY;
}
#endif

#endif
