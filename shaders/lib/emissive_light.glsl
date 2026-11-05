#ifndef XON_EMISSIVE_LIGHT
#define XON_EMISSIVE_LIGHT
#include "/lib/block_shapes.glsl"

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

const vec3 XON_ORE_COLORS[10] = vec3[10](
    vec3(0.0),
    vec3(0.0),
    vec3(0.25, 0.90, 1.00),
    vec3(0.20, 1.00, 0.40) * 0.90,
    vec3(1.00, 0.12, 0.06),
    vec3(0.18, 0.35, 1.00),
    vec3(1.00, 0.74, 0.20) * 0.90,
    vec3(0.95, 0.72, 0.58) * 0.45,
    vec3(1.00, 0.52, 0.28) * 0.70,
    vec3(0.64, 0.32, 1.00) * 0.60
);

uint xonLampFamily(float material);

uint xonVoxelEmitterId(float material) {
    int id = int(material + 0.5);
    if (id >= 11000 && id < 11000 + XON_SHAPE_COUNT) return uint(id - 11000) + 10u;
    if (id >= 11100 && id < 11100 + XON_SHAPE_COUNT) return uint(id - 11100) + 10u;
    if (id >= 11200 && id < 11206) return uint(id - 11200) + 64u;
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
    return id <= 9u ? XON_ORE_COLORS[id] : vec3(0.0);
}

ivec3 xonWorldToVoxel(vec3 playerPos) {
    return ivec3(floor(playerPos + fract(cameraPosition))) + XON_VOXEL_HALF;
}

bool xonVoxelInBounds(ivec3 voxel) {
    return all(greaterThanEqual(voxel, ivec3(0))) && all(lessThan(voxel, XON_VOXEL_SIZE));
}

float xonLocalLightVolumeFade(vec3 playerPos) {
    vec3 position = playerPos + fract(cameraPosition) + vec3(XON_VOXEL_HALF);
    vec3 margin = min(position, vec3(XON_VOXEL_SIZE) - position);
    return smoothstep(2.0, 8.0, min(margin.x, min(margin.y, margin.z)));
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
            uint contact = texelFetch(xonContactTex, plane, 0).r;
            if ((contact >> 27u) != 0u) contact &= ~XON_TRAPDOOR_META;
            uint occupancy = (contact >> uint(axis * 9)) & 511u;
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

uint xonAdjacentLightCorners(uint corners) {
    return ((corners & 85u) << 1u) | ((corners & 170u) >> 1u)
         | ((corners & 51u) << 2u) | ((corners & 204u) >> 2u)
         | ((corners & 15u) << 4u) | ((corners & 240u) >> 4u);
}

uint xonConnectedLightCorners(uint open, uint anchor) {
    uint reachable = open & (1u << anchor);
    if (open == 255u || reachable == 0u) return reachable == 0u ? 0u : open;
    // Neighboring open anchors share one component, so crossing a cell edge cannot change the filter abruptly.
    for (int step = 0; step < 7; ++step) {
        uint neighbors = xonAdjacentLightCorners(reachable);
        uint connected = (reachable | neighbors) & open;
        if (connected == reachable) break;
        reachable = connected;
    }
    return reachable;
}

uint xonVisibleLampCorners(uint open, uint terminals, uint anchor) {
    uint visible = xonConnectedLightCorners(open, anchor);
    // Opaque emitters contribute their own light as endpoints, never as paths to other samples.
    return visible | (terminals & (xonAdjacentLightCorners(visible) | (1u << anchor)));
}

uint xonShapeNeighbors(uint reached, uvec3 edges) {
    return ((reached & edges.x) << 1u) | ((reached >> 1u) & edges.x)
         | ((reached & edges.y) << 2u) | ((reached >> 2u) & edges.y)
         | ((reached & edges.z) << 4u) | ((reached >> 4u) & edges.z);
}

uint xonVisibleShapeCorners(uint open, uint terminals, uint anchor, uvec3 edges) {
    uint reached = open & (1u << anchor);
    for (int step = 0; step < 7; ++step) {
        uint next = (reached | xonShapeNeighbors(reached, edges)) & open;
        if (next == reached) break;
        reached = next;
    }
    return reached | (terminals & (xonShapeNeighbors(reached, edges) | (1u << anchor)));
}

uint xonStencilVoid(uvec2 shapes, int corner) {
    return (shapes[corner >> 2] >> uint((corner & 3) * 8)) & 255u;
}

void xonSampleLocalLights(vec3 playerPos, vec3 normal, uint receiverFamily, bool sampleOre, bool sampleLamp,
                           out vec3 oreLight, out vec4 lampLight) {
    oreLight = vec3(0.0);
    lampLight = vec4(0.0);
    if (!sampleOre && !sampleLamp) return;
    vec3 position = playerPos + fract(cameraPosition) + vec3(XON_VOXEL_HALF);
    vec3 projected = xonVoxelSurfacePosition(position, normal);
    vec3 voxelPos = projected + normal * 0.5 - 0.5;
    if (dot(projected - position, projected - position) > 0.0001) {
        ivec3 owner = ivec3(floor(position - normal * 0.01));
        uint shape = xonVoxelInBounds(owner) ? texelFetch(xonContactTex, owner, 0).r >> 27u : 0u;
        if (shape != 0u) {
            // A 3/16 trapdoor face needs the empty side of its conservative half-cell, not the outer cube boundary.
            float faceInset = dot(vec3(owner) + 0.5 - position, normal);
            const float trapdoorInset = 0.5 - 3.0 / 16.0;
            if (abs(faceInset - trapdoorInset) < 0.001) position += normal * faceInset;
            voxelPos = position + normal * 0.02 - 0.5;
        }
    }
    vec3 edgeDistance = min(voxelPos, vec3(XON_VOXEL_SIZE) - 1.0 - voxelPos);
    float volumeFade = smoothstep(0.0, 6.0, min(edgeDistance.x, min(edgeDistance.y, edgeDistance.z)));
    if (volumeFade <= 0.0) return;
    ivec3 base = ivec3(floor(voxelPos));
    vec3 blend = voxelPos - vec3(base);
    ivec3 fOff = clamp(ivec3(floor(voxelPos + 0.5)) - base, 0, 1);
    int fc = fOff.x | (fOff.y << 1) | (fOff.z << 2);
    bool readFirst = (frameCounter & 1) == 0;
    vec4 oreSamples[8];
    vec4 lampSamples[8];
    uint oreOpen = 0u;
    uint lampOpen = 0u;
    uint lampTerminals = 0u;
    uint shapeCandidates = 0u;
    for (int corner = 0; corner < 8; ++corner) {
        ivec3 cell = base + ivec3(corner & 1, (corner >> 1) & 1, (corner >> 2) & 1);
        if (sampleOre) {
            vec4 s = readFirst ? texelFetch(xonLightTex0, cell, 0) : texelFetch(xonLightTex1, cell, 0);
            if (s.a > -1.0 && (floatBitsToUint(s.a) & 0x80000000u) != 0u) shapeCandidates |= 1u << uint(corner);
            oreSamples[corner] = s;
            if (s.a >= 0.0) oreOpen |= 1u << uint(corner);
        }
        if (sampleLamp) {
            vec4 s = readFirst ? texelFetch(xonLampTex0, cell, 0) : texelFetch(xonLampTex1, cell, 0);
            if (s.a != -1.0 && (floatBitsToUint(s.a) & 0x80000000u) != 0u) shapeCandidates |= 1u << uint(corner);
            lampSamples[corner] = s;
            if (s.a >= 0.0) lampOpen |= 1u << uint(corner);
            if (s.a < -16.0) lampTerminals |= 1u << uint(corner);
        }
    }
    vec3 colorSum = vec3(0.0);
    float levelSum = 0.0;
    float weightSum = 0.0;
    vec3 lampColor = vec3(0.0);
    float lampRemaining = 0.0, lampWeight = 0.0;
    uint oreVisible = sampleOre ? xonConnectedLightCorners(oreOpen, uint(fc)) : 0u;
    uint lampVisible = sampleLamp ? xonVisibleLampCorners(lampOpen, lampTerminals, uint(fc)) : 0u;
    if (shapeCandidates != 0u) {
        uint shapeCorners = 0u;
        uint thinCorners = 0u;
        uvec2 shapeCodes = uvec2(0xFFFFFFFFu);
        for (int corner = 0; corner < 8; ++corner) {
            uint bit = 1u << uint(corner);
            if ((shapeCandidates & bit) == 0u) continue;
            ivec3 cell = base + ivec3(corner & 1, (corner >> 1) & 1, (corner >> 2) & 1);
            uint contact = texelFetch(xonContactTex, cell, 0).r;
            uint shape = contact >> 27u;
            if (shape == 0u) continue;
            shapeCorners |= bit;
            if ((contact & XON_TRAPDOOR_META) != 0u) thinCorners |= bit;
            shapeCodes[corner >> 2] &= ~(XON_SHAPE_SOLID[shape - 1u] << uint((corner & 3) * 8));
            if (sampleOre) {
                oreSamples[corner].a = abs(oreSamples[corner].a);
                oreOpen |= bit;
            }
            if (sampleLamp) {
                lampSamples[corner].a = abs(lampSamples[corner].a);
                lampOpen |= bit;
                lampTerminals &= ~bit;
            }
        }
        uvec3 edges = uvec3(0u);
        edges.x = uint(xonShapeFaceOpen(xonStencilVoid(shapeCodes, 0), xonStencilVoid(shapeCodes, 1), 0, true))
                | (uint(xonShapeFaceOpen(xonStencilVoid(shapeCodes, 2), xonStencilVoid(shapeCodes, 3), 0, true)) << 2u)
                | (uint(xonShapeFaceOpen(xonStencilVoid(shapeCodes, 4), xonStencilVoid(shapeCodes, 5), 0, true)) << 4u)
                | (uint(xonShapeFaceOpen(xonStencilVoid(shapeCodes, 6), xonStencilVoid(shapeCodes, 7), 0, true)) << 6u);
        edges.y = uint(xonShapeFaceOpen(xonStencilVoid(shapeCodes, 0), xonStencilVoid(shapeCodes, 2), 1, true))
                | (uint(xonShapeFaceOpen(xonStencilVoid(shapeCodes, 1), xonStencilVoid(shapeCodes, 3), 1, true)) << 1u)
                | (uint(xonShapeFaceOpen(xonStencilVoid(shapeCodes, 4), xonStencilVoid(shapeCodes, 6), 1, true)) << 4u)
                | (uint(xonShapeFaceOpen(xonStencilVoid(shapeCodes, 5), xonStencilVoid(shapeCodes, 7), 1, true)) << 5u);
        edges.z = uint(xonShapeFaceOpen(xonStencilVoid(shapeCodes, 0), xonStencilVoid(shapeCodes, 4), 2, true))
                | (uint(xonShapeFaceOpen(xonStencilVoid(shapeCodes, 1), xonStencilVoid(shapeCodes, 5), 2, true)) << 1u)
                | (uint(xonShapeFaceOpen(xonStencilVoid(shapeCodes, 2), xonStencilVoid(shapeCodes, 6), 2, true)) << 2u)
                | (uint(xonShapeFaceOpen(xonStencilVoid(shapeCodes, 3), xonStencilVoid(shapeCodes, 7), 2, true)) << 3u);
        oreVisible = sampleOre ? xonVisibleShapeCorners(oreOpen, 0u, uint(fc), edges) : 0u;
        lampVisible = sampleLamp ? xonVisibleShapeCorners(lampOpen, lampTerminals, uint(fc), edges) : 0u;
        if ((shapeCorners & (1u << uint(fc))) != 0u) {
            vec3 point = position + normal * 0.02 - vec3(base + fOff);
            uint octant = uint(point.x >= 0.5) | (uint(point.y >= 0.5) << 1u) | (uint(point.z >= 0.5) << 2u);
            uint solid = 255u ^ xonStencilVoid(shapeCodes, fc);
            bool inside = (thinCorners & (1u << uint(fc))) != 0u ? xonTrapdoorPointSolid(solid, point) : (solid & (1u << octant)) != 0u;
            if (inside) {
                oreVisible = 0u;
                lampVisible = 0u;
            }
        }
    }
    for (int corner = 0; corner < 8; ++corner) {
        ivec3 offset = ivec3(corner & 1, (corner >> 1) & 1, (corner >> 2) & 1);
        vec3 axis = mix(1.0 - blend, blend, vec3(offset));
        float interpolation = axis.x * axis.y * axis.z;
        if (interpolation == 0.0) continue;
        uint cornerBit = 1u << uint(corner);
        if ((oreVisible & cornerBit) != 0u) {
            vec4 light = oreSamples[corner];
            colorSum += light.rgb * (light.a * interpolation);
            levelSum += light.a * interpolation;
            weightSum += interpolation;
        }
        if (sampleLamp) {
            vec4 light = lampSamples[corner];
            uint family;
            float unpackedLevel;
            xonUnpackLampState(abs(light.a), family, unpackedLevel);
            bool decorative = (family >= 6u && family <= 8u) || family == 21u;
            // Coverage identifies captured Minecraft light even when its radiance is occluded.
            // Losing visibility must not restore the brighter, unoccluded scalar fallback.
            lampRemaining += decorative ? 0.0 : unpackedLevel * (interpolation / 15.0);
            if ((lampVisible & cornerBit) != 0u) {
                bool ownAura = receiverFamily >= 6u && receiverFamily <= 8u && receiverFamily == family;
                lampColor += ownAura ? vec3(0.0) : light.rgb * interpolation;
                lampWeight += interpolation;
            }
        }
    }
    if (levelSum > 0.0001) {
        float level = levelSum / weightSum;
        float falloff = level * level * level * (level * (level * 6.0 - 15.0) + 10.0);
        float occlusionFade = smoothstep(0.0, 0.5, weightSum);
        oreLight = (colorSum / levelSum) * falloff * volumeFade * occlusionFade * XON_EMISSIVE_INTENSITY;
    }
    float confidence = smoothstep(0.0, 0.5, lampWeight) * volumeFade / max(lampWeight, 0.0001);
    lampLight = vec4(lampColor * confidence, lampRemaining * volumeFade);
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
