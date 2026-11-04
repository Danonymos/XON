#ifndef XON_EMISSIVE_LIGHT
#define XON_EMISSIVE_LIGHT

// Camera-centred voxel volume shared by the shadow pass (voxelization), shadowcomp
// (flood fill) and geometry passes (sampling). Must match the image sizes in shaders.properties.
const ivec3 XON_VOXEL_SIZE = ivec3(96, 48, 96);
const ivec3 XON_VOXEL_HALF = XON_VOXEL_SIZE / 2;

const uint XON_VOXEL_EMPTY = 0u;
const uint XON_VOXEL_SOLID = 1u;
const uint XON_VOXEL_FIRST_EMITTER = 2u;
const uint XON_VOXEL_OCCLUDER = 255u;

// Reserve three additional open blocks for the outer aura to ease into darkness.
const float XON_EMISSIVE_REACH = XON_EMISSIVE_RADIUS + 3.0;
const float XON_EMISSIVE_STEP = 1.0 / (XON_EMISSIVE_REACH + 1.0);
const float XON_EMISSIVE_COLOR_FLOOR = 0.01;

uint xonLampFamily(float material);

uint xonVoxelEmitterId(float material) {
    int id = int(material + 0.5);
    uint family = xonLampFamily(material);
    if (family > 0u) return 128u + family;
    if (id == 10010) return 2u;
    if (id == 10011) return 3u;
    if (id == 10012) return 4u;
    if (id == 10013) return 5u;
    if (id == 10014 || id == 10017) return 6u;
    if (id == 10015) return 7u;
    if (id == 10016) return 8u;
    if (id == 10018) return 9u;
    return XON_VOXEL_EMPTY;
}

// Preserve luminance/hue and a faint color floor; already-pure colors must not desaturate.
vec3 xonSaturateEmitterColor(vec3 color) {
    if (XON_EMISSIVE_SATURATION == 1.00) return color;
    float luminance = dot(color, vec3(0.2126, 0.7152, 0.0722));
    float minimum = min(color.r, min(color.g, color.b));
    float saturationLimit = max(1.0, luminance * (1.0 - XON_EMISSIVE_COLOR_FLOOR) / max(luminance - minimum, 0.00001));
    float saturation = min(XON_EMISSIVE_SATURATION, saturationLimit);
    return max(vec3(luminance) + (color - luminance) * saturation, vec3(0.0));
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
    return vec3(0.0);
}

ivec3 xonWorldToVoxel(vec3 playerPos) {
    return ivec3(floor(playerPos + fract(cameraPosition))) + XON_VOXEL_HALF;
}

bool xonVoxelInBounds(ivec3 voxel) {
    return all(greaterThanEqual(voxel, ivec3(0))) && all(lessThan(voxel, XON_VOXEL_SIZE));
}

vec3 xonVoxelSurfacePosition(vec3 position, vec3 normal) {
    ivec3 receiver = ivec3(floor(position - normal * 0.01));
    float receiverFace = dot(vec3(receiver) + 0.5 - position, normal) + dot(abs(normal), vec3(0.5));
    return position + normal * max(receiverFace, 0.0);
}

#include "/lib/lamp_light.glsl"

#ifdef XON_EMISSIVE_SAMPLING
uniform sampler3D xonLightTex0;
uniform sampler3D xonLightTex1;
uniform usampler3D xonContactTex;

vec4 xonFetchInteriorLight(ivec3 voxel) {
    return (frameCounter & 1) == 0 ? texelFetch(xonLightTex0, voxel, 0) : texelFetch(xonLightTex1, voxel, 0);
}

float xonOcclusionWeight(ivec3 voxel, ivec3 receiver, vec3 position, vec3 normal) {
    vec3 delta = vec3(voxel) + 0.5 - position;
    float distanceSq = dot(delta, delta);
    float facing = dot(normal, delta);
    if (distanceSq >= 2.25 || facing <= 0.0 || all(equal(voxel, receiver))) return 0.0;
    float weight = 1.0 - distanceSq * (1.0 / 2.25);
    weight *= weight * facing * inversesqrt(max(distanceSq, 0.0001));
    return weight;
}

void xonAccumulateOcclusion(ivec3 voxel, ivec3 receiver, vec3 position, vec3 normal,
                            inout float blocked, inout float total) {
    float weight = xonOcclusionWeight(voxel, receiver, position, normal);
    total += weight;
    if (weight > 0.0 && xonFetchInteriorLight(voxel).a < -1.5) blocked += weight;
}

float xonIndoorOcclusion(vec3 playerPos, vec3 normal) {
    vec3 position = playerPos + fract(cameraPosition) + vec3(XON_VOXEL_HALF);
    ivec3 receiver = ivec3(floor(position - normal * 0.01));
    // Start outside the receiver's coarse cell, including inset/slab/carpet surfaces.
    position = xonVoxelSurfacePosition(position, normal);
    vec3 edge = min(position, vec3(XON_VOXEL_SIZE) - position);
    float volumeFade = smoothstep(2.0, 6.0, min(edge.x, min(edge.y, edge.z)));
    if (volumeFade <= 0.0) return 1.0;
    ivec3 base = ivec3(floor(position));
    float blocked = 0.0;
    float total = 0.0;
    vec3 normalAxis = step(vec3(0.99999), abs(normal));
    int axis = normalAxis.x > 0.5 ? 0 : (normalAxis.y > 0.5 ? 1 : 2);
    bool exactAxis = all(equal(abs(normal), normalAxis));
    if (dot(normalAxis, vec3(1.0)) == 1.0 && (exactAxis || position[axis] == float(base[axis]))) {
        if (position[axis] == float(base[axis])) {
            // At this boundary, support and hemisphere tests admit only this plane,
            // even with small camera-roundtrip components in the geometric normal.
            ivec3 plane = base;
            if (normal[axis] < 0.0) plane[axis] -= 1;
            uint occupancy = (texelFetch(xonContactTex, plane, 0).r >> uint(axis * 9)) & 511u;
            if (occupancy == 0u) return 1.0;
            for (int v = -1; v <= 1; ++v) {
                for (int u = -1; u <= 1; ++u) {
                    ivec3 offset = axis == 0 ? ivec3(0, u, v) : (axis == 1 ? ivec3(u, 0, v) : ivec3(u, v, 0));
                    float weight = xonOcclusionWeight(plane + offset, receiver, position, normal);
                    total += weight;
                    if ((occupancy & (1u << uint((v + 1) * 3 + u + 1))) != 0u) blocked += weight;
                }
            }
            return 1.0 - 0.72 * volumeFade * blocked / max(total, 0.0001);
        }
        for (int layer = -1; layer <= 1; ++layer) {
            float delta = float(base[axis] + layer) + 0.5 - position[axis];
            if (delta * normal[axis] <= 0.0 || delta * delta >= 2.25) continue;
            for (int v = -1; v <= 1; ++v) {
                for (int u = -1; u <= 1; ++u) {
                    ivec3 offset = axis == 0 ? ivec3(layer, u, v) : (axis == 1 ? ivec3(u, layer, v) : ivec3(u, v, layer));
                    xonAccumulateOcclusion(base + offset, receiver, position, normal, blocked, total);
                }
            }
        }
    } else {
        for (int z = -1; z <= 1; ++z) {
            for (int y = -1; y <= 1; ++y) {
                for (int x = -1; x <= 1; ++x) {
                    xonAccumulateOcclusion(base + ivec3(x, y, z), receiver, position, normal, blocked, total);
                }
            }
        }
    }
    return 1.0 - 0.72 * volumeFade * blocked / max(total, 0.0001);
}

void xonSampleLocalLights(vec3 playerPos, vec3 normal, uint receiverFamily, bool sampleOre, bool sampleLamp,
                           out vec3 oreLight, out vec4 lampLight) {
    oreLight = vec3(0.0);
    lampLight = vec4(0.0);
    if (!sampleOre && !sampleLamp) return;
    vec3 voxelPos = xonVoxelSurfacePosition(playerPos + fract(cameraPosition) + vec3(XON_VOXEL_HALF), normal)
                  + normal * 0.5 - 0.5;
    vec3 edgeDistance = min(voxelPos, vec3(XON_VOXEL_SIZE) - 1.0 - voxelPos);
    float volumeFade = smoothstep(0.0, 6.0, min(edgeDistance.x, min(edgeDistance.y, edgeDistance.z)));
    if (volumeFade <= 0.0) return;
    ivec3 base = ivec3(floor(voxelPos));
    vec3 blend = voxelPos - vec3(base);
    vec3 colorSum = vec3(0.0);
    float levelSum = 0.0;
    float weightSum = 0.0;
    vec3 lampColor = vec3(0.0);
    float lampRemaining = 0.0, lampWeight = 0.0;
    for (int corner = 0; corner < 8; ++corner) {
        ivec3 offset = ivec3(corner & 1, (corner >> 1) & 1, (corner >> 2) & 1);
        vec3 axis = mix(1.0 - blend, blend, vec3(offset));
        float interpolation = axis.x * axis.y * axis.z;
        if (interpolation == 0.0) continue;
        ivec3 cell = base + offset;
        if (sampleOre) {
            vec4 light = xonFetchInteriorLight(cell);
            float weight = interpolation * step(0.0, light.a);
            colorSum += light.rgb * (light.a * weight);
            levelSum += light.a * weight;
            weightSum += weight;
        }
        if (sampleLamp) {
            vec4 light = (frameCounter & 1) == 0 ? texelFetch(xonLampTex0, cell, 0) : texelFetch(xonLampTex1, cell, 0);
            float weight = interpolation * step(0.0, light.a);
            int code = int(max(light.a, 0.0) + 0.5);
            int family = code / 16;
            bool ownAura = receiverFamily >= 6u && receiverFamily <= 8u && receiverFamily == uint(family);
            lampColor += ownAura ? vec3(0.0) : light.rgb * weight;
            bool decorative = (family >= 6 && family <= 8) || family == 21;
            lampRemaining += decorative ? 0.0 : float(code % 16) * (weight / 15.0);
            lampWeight += weight;
        }
    }
    if (levelSum > 0.0001) {
        float level = levelSum / weightSum;
        float falloff = level * level * level * (level * (level * 6.0 - 15.0) + 10.0);
        float occlusionFade = smoothstep(0.0, 0.5, weightSum);
        oreLight = (colorSum / levelSum) * falloff * volumeFade * occlusionFade * XON_EMISSIVE_INTENSITY;
    }
    float confidence = smoothstep(0.0, 0.5, lampWeight) * volumeFade / max(lampWeight, 0.0001);
    lampLight = vec4(lampColor, lampRemaining) * confidence;
}

vec3 xonEmissiveLight(vec3 playerPos, vec3 normal) {
    vec3 oreLight;
    vec4 lampLight;
    xonSampleLocalLights(playerPos, normal, 0u, true, false, oreLight, lampLight);
    return oreLight;
}

vec4 xonLampLight(vec3 playerPos, vec3 normal, uint receiverFamily) {
    vec3 oreLight;
    vec4 lampLight;
    xonSampleLocalLights(playerPos, normal, receiverFamily, false, true, oreLight, lampLight);
    return lampLight;
}

vec4 xonLampLight(vec3 playerPos, vec3 normal) {
    return xonLampLight(playerPos, normal, 0u);
}
#endif

#endif
