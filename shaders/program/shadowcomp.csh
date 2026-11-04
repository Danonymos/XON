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

const ivec3 NEIGHBORS[6] = ivec3[6](ivec3(1, 0, 0), ivec3(-1, 0, 0), ivec3(0, 1, 0),
                                    ivec3(0, -1, 0), ivec3(0, 0, 1), ivec3(0, 0, -1));

vec4 xonPreviousLight(ivec3 voxel, bool readFirst) {
    if (frameCounter == 0) return vec4(0.0);
    if (any(greaterThan(abs(cameraPosition - previousCameraPosition), vec3(XON_EMISSIVE_REACH + 1.0)))) return vec4(0.0);
    if (!xonVoxelInBounds(voxel)) return vec4(0.0);
    return readFirst ? texelFetch(xonLightTex0, voxel, 0) : texelFetch(xonLightTex1, voxel, 0);
}

vec4 xonPreviousLamp(ivec3 voxel, bool readFirst) {
    if (frameCounter == 0 || !xonVoxelInBounds(voxel)) return vec4(0.0);
    if (any(greaterThan(abs(cameraPosition - previousCameraPosition), vec3(XON_LAMP_HISTORY_REACH)))) return vec4(0.0);
    return readFirst ? texelFetch(xonLampTex0, voxel, 0) : texelFetch(xonLampTex1, voxel, 0);
}

shared uint xonOccupancyTile[1000];

int xonTileIndex(ivec3 position) {
    return position.x + 10 * (position.y + 10 * position.z);
}

uint xonContactPlanes(ivec3 local) {
    uint planes = 0u;
    for (int v = -1; v <= 1; ++v) {
        for (int u = -1; u <= 1; ++u) {
            uint bit = uint((v + 1) * 3 + u + 1);
            planes |= uint(xonOccupancyTile[xonTileIndex(local + ivec3(0, u, v))] == XON_VOXEL_OCCLUDER) << bit;
            planes |= uint(xonOccupancyTile[xonTileIndex(local + ivec3(u, 0, v))] == XON_VOXEL_OCCLUDER) << (bit + 9u);
            planes |= uint(xonOccupancyTile[xonTileIndex(local + ivec3(u, v, 0))] == XON_VOXEL_OCCLUDER) << (bit + 18u);
        }
    }
    return planes;
}

// One flood-fill step per frame: the volume converges within reach + 1 frames and
// re-converges at the same rate when blocks change. Solid blocks stop propagation.
void main() {
    ivec3 voxel = ivec3(gl_GlobalInvocationID);
    ivec3 tileOrigin = ivec3(gl_WorkGroupID) * 8 - 1;
    for (uint index = gl_LocalInvocationIndex; index < 1000u; index += 512u) {
        ivec3 position = ivec3(int(index % 10u), int((index / 10u) % 10u), int(index / 100u));
        ivec3 cell = tileOrigin + position;
        xonOccupancyTile[index] = xonVoxelInBounds(cell) ? texelFetch(xonVoxelTex, cell, 0).r : XON_VOXEL_EMPTY;
    }
    barrier();
    ivec3 local = ivec3(gl_LocalInvocationID) + 1;
    uint data = xonOccupancyTile[xonTileIndex(local)];
    imageStore(xonContactImg, voxel, uvec4(xonContactPlanes(local), 0u, 0u, 0u));
    bool lampSource = data >= XON_LAMP_FIRST && data <= XON_LAMP_LAST;
    vec4 light = vec4(0.0, 0.0, 0.0, -1.0);
    if (data == XON_VOXEL_OCCLUDER) {
        light.a = -2.0;
    } else if (data >= XON_VOXEL_FIRST_EMITTER && !lampSource) {
        light = vec4(xonSaturateEmitterColor(xonVoxelEmitterColor(data)), 1.0);
    } else if (data == XON_VOXEL_EMPTY || lampSource) {
        bool writeFirst = (frameCounter & 1) == 0;
        ivec3 previousVoxel = voxel + ivec3(floor(cameraPosition) - floor(previousCameraPosition));
        float brightest = 0.0;
        vec3 colorSum = vec3(0.0);
        float levelSum = 0.0;
        for (int i = 0; i < 6; ++i) {
            vec4 neighbor = xonPreviousLight(previousVoxel + NEIGHBORS[i], !writeFirst);
            float level = max(neighbor.a, 0.0);
            brightest = max(brightest, level);
            colorSum += neighbor.rgb * level;
            levelSum += level;
        }
        float level = max(brightest - XON_EMISSIVE_STEP, 0.0);
        light = vec4(level > 0.0 ? colorSum / levelSum : vec3(0.0), level);
    }
    vec4 lamp = vec4(0.0, 0.0, 0.0, light.a < 0.0 ? -1.0 : 0.0);
    if (lampSource) {
        uint family = data - 128u;
        lamp = xonLampValue(family, xonLampLevel(family));
    } else if (data == XON_VOXEL_EMPTY || (data >= XON_VOXEL_FIRST_EMITTER && data < XON_LAMP_FIRST)) {
        ivec3 previousVoxel = voxel + ivec3(floor(cameraPosition) - floor(previousCameraPosition));
        float bestScore = -1.0;
        int bestLevel = 0;
        uint bestFamily = 0u;
        for (int i = 0; i < 6; ++i) {
            vec4 neighbor = xonPreviousLamp(previousVoxel + NEIGHBORS[i], (frameCounter & 1) != 0);
            int code = int(max(neighbor.a, 0.0) + 0.5);
            int level = code % 16 - 1;
            if (level <= 0) continue;
            uint family = uint(code / 16);
            if (family == bestFamily && level <= bestLevel) continue;
            vec4 candidate = xonLampValue(family, level);
            float score = dot(candidate.rgb, vec3(0.2126, 0.7152, 0.0722));
            if (score > bestScore + 0.00001 || (abs(score - bestScore) <= 0.00001 && level > bestLevel)) {
                lamp = candidate;
                bestScore = score;
                bestLevel = level;
                bestFamily = family;
            }
        }
    }
    if ((frameCounter & 1) == 0) imageStore(xonLightImg0, voxel, light);
    else imageStore(xonLightImg1, voxel, light);
    if ((frameCounter & 1) == 0) imageStore(xonLampImg0, voxel, lamp);
    else imageStore(xonLampImg1, voxel, lamp);
}
#else
layout(local_size_x = 1) in;
const ivec3 workGroups = ivec3(1);
void main() {}
#endif
