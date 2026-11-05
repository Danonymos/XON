#include "/lib/settings.glsl"

#ifdef XON_COLORED_EMISSIVE_LIGHTING
layout(local_size_x = 8, local_size_y = 8, local_size_z = 8) in;
const ivec3 workGroups = ivec3(12, 6, 12);

uniform int frameCounter;
uniform vec3 cameraPosition;
uniform vec3 previousCameraPosition;
uniform usampler3D xonVoxelTex;
uniform sampler3D xonLightTex0;
uniform sampler3D xonLightTex1;
layout(rgba16f) writeonly uniform image3D xonLightImg0;
layout(rgba16f) writeonly uniform image3D xonLightImg1;
uniform sampler3D xonLampTex0;
uniform sampler3D xonLampTex1;
layout(rgba16f) writeonly uniform image3D xonLampImg0;
layout(rgba16f) writeonly uniform image3D xonLampImg1;
layout(r32ui) writeonly uniform uimage3D xonContactImg;

#include "/lib/emissive_light.glsl"

// 12x12x12 halo tile (margin 2 around 8x8x8 core): 25,828 bytes total (< 32 KB GL 4.3 minimum).
shared uint xonOccTile[1728];
shared uint xonLampStateA[1728];
shared uint xonLampStateB[1000];
shared uvec2 xonRgbTile[1000];
shared uint xonTileFlags; // bit 0: active ore, bit 1: active lamp, bit 2: occluder present

uvec2 xonPackVec4(vec4 v) {
    return uvec2(packHalf2x16(v.xy), packHalf2x16(v.zw));
}

vec4 xonUnpackVec4(uvec2 p) {
    return vec4(unpackHalf2x16(p.x), unpackHalf2x16(p.y));
}

int xonTile12(ivec3 p) {
    return p.x + 12 * (p.y + 12 * p.z);
}

int xonTile10(ivec3 p) {
    return p.x + 10 * (p.y + 10 * p.z);
}

bool xonIsSolidOcc(uint occ) {
    return occ == XON_VOXEL_SOLID || occ == XON_VOXEL_OCCLUDER;
}

bool xonBlocksLightStep(uint occ) {
    return xonIsSolidOcc(occ)
        || xonPartialVoxel(occ)
        || (occ >= XON_VOXEL_FIRST_EMITTER && occ <= 9u)
        || (occ >= 134u && occ <= 136u);
}

// Diagonal and corner steps require a continuous face-connected open path so light never leaks through or around walls,
// while flush-embedded floor/wall/ceiling emitters still radiate isotropically through their exposed open face.
bool xonStepOpen12(ivec3 dst12, ivec3 d) {
    uint srcOcc = xonOccTile[xonTile12(dst12 + d)];
    if (xonIsSolidOcc(srcOcc)) return false;
    int manhattan = abs(d.x) + abs(d.y) + abs(d.z);
    uint dstOcc = xonOccTile[xonTile12(dst12)];
    bool partial = xonPartialVoxel(srcOcc) || xonPartialVoxel(dstOcc);
    if (manhattan == 0) return true;
    if (manhattan == 1) {
        int axis = d.x != 0 ? 0 : (d.y != 0 ? 1 : 2);
        return !partial || xonShapeFaceOpen(xonVoxelOpenOctants(dstOcc), xonVoxelOpenOctants(srcOcc), axis, d[axis] > 0);
    }
    if (partial) return false;
    bool fromEmitter = srcOcc >= XON_VOXEL_FIRST_EMITTER && srcOcc < XON_VOXEL_OCCLUDER && !(srcOcc >= 134u && srcOcc <= 136u);
    if (manhattan == 2) {
        ivec3 a = d.x != 0 ? ivec3(d.x, 0, 0) : ivec3(0, d.y, 0);
        ivec3 b = d - a;
        bool openA = !xonBlocksLightStep(xonOccTile[xonTile12(dst12 + a)]);
        bool openB = !xonBlocksLightStep(xonOccTile[xonTile12(dst12 + b)]);
        return fromEmitter ? (openA || openB) : (openA && openB);
    }
    bool fx = !xonBlocksLightStep(xonOccTile[xonTile12(dst12 + ivec3(d.x, 0, 0))]);
    bool fy = !xonBlocksLightStep(xonOccTile[xonTile12(dst12 + ivec3(0, d.y, 0))]);
    bool fz = !xonBlocksLightStep(xonOccTile[xonTile12(dst12 + ivec3(0, 0, d.z))]);
    bool exy = !xonBlocksLightStep(xonOccTile[xonTile12(dst12 + ivec3(d.x, d.y, 0))]);
    bool exz = !xonBlocksLightStep(xonOccTile[xonTile12(dst12 + ivec3(d.x, 0, d.z))]);
    bool eyz = !xonBlocksLightStep(xonOccTile[xonTile12(dst12 + ivec3(0, d.y, d.z))]);
    if (fromEmitter) {
        return (exy && fx && fy) || (exz && fx && fz) || (eyz && fy && fz);
    }
    return fx && fy && fz && exy && exz && eyz;
}

// Exact 1/8-block binary-fraction quasi-Euclidean step weights (1.0 = 8/8, 1.375 = 11/8, 1.75 = 14/8).
float xonStepCost(ivec3 d) {
    int m = abs(d.x) + abs(d.y) + abs(d.z);
    return m == 1 ? 1.0 : (m == 2 ? 1.375 : 1.75);
}

uint xonContactPlanes(ivec3 local12) {
    uint planes = 0u;
    for (int v = -1; v <= 1; ++v) {
        for (int u = -1; u <= 1; ++u) {
            uint bit = uint((v + 1) * 3 + u + 1);
            planes |= uint(xonOccTile[xonTile12(local12 + ivec3(0, u, v))] == XON_VOXEL_OCCLUDER) << bit;
            planes |= uint(xonOccTile[xonTile12(local12 + ivec3(u, 0, v))] == XON_VOXEL_OCCLUDER) << (bit + 9u);
            planes |= uint(xonOccTile[xonTile12(local12 + ivec3(u, v, 0))] == XON_VOXEL_OCCLUDER) << (bit + 18u);
        }
    }
    return planes;
}

// Shared-memory 26-neighbor quasi-Euclidean light propagation for both ores and lamps,
// followed by non-recursive open-air isotropic 3x3x3 RGB smoothing, with empty-tile workgroup skips.
void main() {
    if (gl_LocalInvocationIndex == 0u) xonTileFlags = 0u;
    barrier();

    ivec3 voxel = ivec3(gl_GlobalInvocationID);
    ivec3 tileOrigin = ivec3(gl_WorkGroupID) * 8 - 2;
    bool writeFirst = (frameCounter & 1) == 0;
    ivec3 camShift = ivec3(floor(cameraPosition) - floor(previousCameraPosition));
    vec3 camDelta = abs(cameraPosition - previousCameraPosition);
    bool oreHistoryValid = frameCounter > 0 && all(lessThanEqual(camDelta, vec3(XON_EMISSIVE_REACH + 1.0)));
    bool lampHistoryValid = frameCounter > 0 && all(lessThanEqual(camDelta, vec3(XON_LAMP_HISTORY_REACH)));

    uint threadFlags = 0u;
    for (uint index = gl_LocalInvocationIndex; index < 1728u; index += 512u) {
        ivec3 pos = ivec3(int(index % 12u), int((index / 12u) % 12u), int(index / 144u));
        ivec3 cell = tileOrigin + pos;
        uint occ = xonVoxelInBounds(cell) ? texelFetch(xonVoxelTex, cell, 0).r : XON_VOXEL_EMPTY;
        xonOccTile[index] = occ;
        if (occ == XON_VOXEL_OCCLUDER) threadFlags |= 4u;
        else if (occ >= XON_LAMP_FIRST && occ <= XON_LAMP_LAST) threadFlags |= 2u;
        else if (occ >= XON_VOXEL_FIRST_EMITTER && occ <= 9u) threadFlags |= 1u;

        float prevLampA = 0.0;
        if (lampHistoryValid) {
            ivec3 prevCell = cell + camShift;
            if (xonVoxelInBounds(prevCell)) {
                prevLampA = (!writeFirst ? texelFetch(xonLampTex0, prevCell, 0) : texelFetch(xonLampTex1, prevCell, 0)).a;
                if ((occ >= 134u && occ <= 136u) || xonPartialVoxel(occ)) prevLampA = abs(prevLampA);
                if (prevLampA > 0.0) threadFlags |= 2u;
            }
        }
        xonLampStateA[index] = floatBitsToUint(prevLampA);
    }
    if (oreHistoryValid) {
        for (uint index = gl_LocalInvocationIndex; index < 1000u; index += 512u) {
            ivec3 p10 = ivec3(int(index % 10u), int((index / 10u) % 10u), int(index / 100u));
            ivec3 prevCell = tileOrigin + p10 + 1 + camShift;
            vec4 prevOre = vec4(0.0);
            if (xonVoxelInBounds(prevCell)) {
                prevOre = !writeFirst ? texelFetch(xonLightTex0, prevCell, 0) : texelFetch(xonLightTex1, prevCell, 0);
                if (prevOre.a > -1.0) prevOre.a = abs(prevOre.a);
                if (prevOre.a > 0.0) threadFlags |= 1u;
            }
            xonRgbTile[index] = xonPackVec4(prevOre);
        }
    }
    if (threadFlags != 0u) atomicOr(xonTileFlags, threadFlags);
    barrier();

    uint tileFlags = xonTileFlags;
    ivec3 local12 = ivec3(gl_LocalInvocationID) + 2;
    ivec3 c10 = ivec3(gl_LocalInvocationID) + 1;
    uint data = xonOccTile[xonTile12(local12)];
    uint contactMask = (tileFlags & 4u) != 0u ? xonContactPlanes(local12) : 0u;
    if (xonPartialVoxel(data)) contactMask |= (xonVoxelShapeIndex(data) + 1u) << 27u;
    if (xonTrapdoorVoxel(data)) contactMask |= XON_TRAPDOOR_META;
    imageStore(xonContactImg, voxel, uvec4(contactMask, 0u, 0u, 0u));

    bool lampSource = data >= XON_LAMP_FIRST && data <= XON_LAMP_LAST;
    bool decorativeSolid = data >= 134u && data <= 136u;
    vec4 light = vec4(0.0, 0.0, 0.0, -1.0);
    if (data == XON_VOXEL_OCCLUDER) {
        light.a = -2.0;
    } else if (decorativeSolid) {
        light.a = -1.0;
    } else if (data >= XON_VOXEL_FIRST_EMITTER && data <= 9u) {
        light = vec4(xonSaturateEmitterColor(xonVoxelEmitterColor(data)), 1.0);
    } else if (lampSource) {
        light = vec4(0.0);
    } else if (data == XON_VOXEL_EMPTY || xonPartialVoxel(data)) {
        if ((tileFlags & 1u) != 0u && oreHistoryValid) {
            float brightest = 0.0;
            vec3 colorSum = vec3(0.0);
            float levelSum = 0.0;
            for (int dz = -1; dz <= 1; ++dz) {
                for (int dy = -1; dy <= 1; ++dy) {
                    for (int dx = -1; dx <= 1; ++dx) {
                        if (dx == 0 && dy == 0 && dz == 0) continue;
                        ivec3 d = ivec3(dx, dy, dz);
                        uint sourceOcc = xonOccTile[xonTile12(local12 + d)];
                        if (sourceOcc != XON_VOXEL_EMPTY && !xonPartialVoxel(sourceOcc) && !(sourceOcc >= XON_VOXEL_FIRST_EMITTER && sourceOcc <= 9u)) continue;
                        uvec2 packedNeighbor = xonRgbTile[xonTile10(c10 + d)];
                        uint alphaHalf = packedNeighbor.y >> 16u;
                        if (alphaHalf == 0u || alphaHalf >= 0x8000u) continue;
                        if (!xonStepOpen12(local12, d)) continue;
                        vec4 neighbor = xonUnpackVec4(packedNeighbor);
                        float nLevel = max(neighbor.a, 0.0);
                        if (nLevel <= 0.0) continue;
                        float candLevel = max(nLevel - xonStepCost(d) * XON_EMISSIVE_STEP, 0.0);
                        brightest = max(brightest, candLevel);
                        colorSum += neighbor.rgb * nLevel;
                        levelSum += nLevel;
                    }
                }
            }
            light = vec4(brightest > 0.0 && levelSum > 0.0 ? colorSum / levelSum : vec3(0.0), brightest);
        } else {
            light = vec4(0.0);
        }
    }

    vec4 lamp = vec4(0.0, 0.0, 0.0, light.a < 0.0 ? -1.0 : 0.0);
    if ((tileFlags & 2u) != 0u) {
        barrier();
        for (uint index = gl_LocalInvocationIndex; index < 1000u; index += 512u) {
            ivec3 p10 = ivec3(int(index % 10u), int((index / 10u) % 10u), int(index / 100u));
            ivec3 p12 = p10 + 1;
            uint occ = xonOccTile[xonTile12(p12)];
            if (occ >= XON_LAMP_FIRST && occ <= XON_LAMP_LAST) {
                uint fam = occ - 128u;
                vec4 val = xonLampValue(fam, xonLampLevel(fam));
                xonLampStateB[index] = floatBitsToUint(val.a);
                xonRgbTile[index] = xonPackVec4(vec4(val.rgb, float(fam)));
            } else if (xonIsSolidOcc(occ) || (occ >= XON_VOXEL_FIRST_EMITTER && occ <= 9u)) {
                xonLampStateB[index] = floatBitsToUint(-1.0);
                xonRgbTile[index] = xonPackVec4(vec4(0.0, 0.0, 0.0, -1.0));
            } else {
                float bestScore = -1.0;
                float bestLevel = 0.0;
                uint bestFamily = 0u;
                vec3 bestRgb = vec3(0.0);
                bool bestDecorative = true;
                if (lampHistoryValid) {
                    for (int dz = -1; dz <= 1; ++dz) {
                        for (int dy = -1; dy <= 1; ++dy) {
                            for (int dx = -1; dx <= 1; ++dx) {
                                if (dx == 0 && dy == 0 && dz == 0) continue;
                                ivec3 d = ivec3(dx, dy, dz);
                                uint rawState = xonLampStateA[xonTile12(p12 + d)];
                                if (rawState == 0u || rawState >= 0x80000000u) continue;
                                uint sourceOcc = xonOccTile[xonTile12(p12 + d)];
                                if (sourceOcc >= XON_VOXEL_FIRST_EMITTER && sourceOcc <= 9u) continue;
                                if (!xonStepOpen12(p12, d)) continue;
                                uint family;
                                float prevLevel;
                                xonUnpackLampState(uintBitsToFloat(rawState), family, prevLevel);
                                if (sourceOcc >= XON_LAMP_FIRST && sourceOcc <= XON_LAMP_LAST && family != sourceOcc - 128u) continue;
                                float level = prevLevel - xonStepCost(d);
                                if (level <= 0.0) continue;
                                if (family == bestFamily && level <= bestLevel) continue;
                                vec4 profile = xonLampProfile(family);
                                float dist = max(float(xonLampLevel(family)) - level, 0.0);
                                vec3 rgb = profile.rgb * xonLampFalloff(dist, profile.a);
                                bool isDeco = (family >= 6u && family <= 8u) || family == 21u;
                                float score = dot(rgb, vec3(0.2126, 0.7152, 0.0722));
                                bool stronger = score > bestScore + 0.00001 || (abs(score - bestScore) <= 0.00001 && level > bestLevel);
                                // Native-light coverage must survive beyond the shorter colored pool.
                                bool preferred = bestFamily == 0u || (bestDecorative && !isDeco)
                                              || (bestDecorative == isDeco && stronger);
                                if (preferred) {
                                    bestScore = score;
                                    bestLevel = level;
                                    bestFamily = family;
                                    bestRgb = rgb;
                                    bestDecorative = isDeco;
                                }
                            }
                        }
                    }
                }
                xonLampStateB[index] = floatBitsToUint(xonPackLampState(bestFamily, bestLevel));
                xonRgbTile[index] = xonPackVec4(vec4(bestRgb, float(bestFamily)));
            }
        }
        barrier();

        int idx10 = xonTile10(c10);
        float outPacked = uintBitsToFloat(xonLampStateB[idx10]);
        vec4 centerRgbFam = xonUnpackVec4(xonRgbTile[idx10]);
        if (lampSource) {
            // Opaque decorative emitters radiate outwards but remain closed to surface interpolation.
            lamp = vec4(centerRgbFam.rgb, decorativeSolid ? -outPacked : outPacked);
        } else if ((!xonBlocksLightStep(data) || xonPartialVoxel(data)) && outPacked > 0.0) {
            uint centerFam = uint(centerRgbFam.a + 0.5);
            bool selfExcluded = centerFam >= 6u && centerFam <= 8u;
            vec3 rgbAcc = vec3(0.0);
            float wAcc = 0.0;
            for (int dz = -1; dz <= 1; ++dz) {
                float wz = dz == 0 ? 4.0 : 1.0;
                for (int dy = -1; dy <= 1; ++dy) {
                    float wyz = wz * (dy == 0 ? 4.0 : 1.0);
                    for (int dx = -1; dx <= 1; ++dx) {
                        ivec3 d = ivec3(dx, dy, dz);
                        uvec2 packedN = xonRgbTile[xonTile10(c10 + d)];
                        if ((packedN.y >> 16u) >= 0x8000u) continue;
                        if (!xonStepOpen12(local12, d)) continue;
                        vec4 nVal = xonUnpackVec4(packedN);
                        uint nFam = uint(max(nVal.a, 0.0) + 0.5);
                        if (selfExcluded && nFam != centerFam && nFam != 0u) continue;
                        if (!selfExcluded && nFam >= 6u && nFam <= 8u) continue;
                        float w = wyz * (dx == 0 ? 4.0 : 1.0);
                        rgbAcc += nVal.rgb * w;
                        wAcc += w;
                    }
                }
            }
            lamp = vec4(wAcc > 0.0 ? rgbAcc / wAcc : centerRgbFam.rgb, outPacked);
        }
    }

    if (xonPartialVoxel(data)) {
        light.a = -max(light.a, 0.0);
        lamp.a = -max(lamp.a, 0.0);
    }
    if (writeFirst) imageStore(xonLightImg0, voxel, light);
    else imageStore(xonLightImg1, voxel, light);
    if (writeFirst) imageStore(xonLampImg0, voxel, lamp);
    else imageStore(xonLampImg1, voxel, lamp);
}
#else
layout(local_size_x = 1) in;
const ivec3 workGroups = ivec3(1);
void main() {}
#endif
