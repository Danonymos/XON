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

#include "/lib/emissive_light.glsl"

const ivec3 NEIGHBORS[6] = ivec3[6](ivec3(1, 0, 0), ivec3(-1, 0, 0), ivec3(0, 1, 0),
                                    ivec3(0, -1, 0), ivec3(0, 0, 1), ivec3(0, 0, -1));

vec4 xonPreviousLight(ivec3 voxel, bool readFirst) {
    if (frameCounter == 0) return vec4(0.0);
    if (any(greaterThan(abs(cameraPosition - previousCameraPosition), vec3(XON_EMISSIVE_REACH + 1.0)))) return vec4(0.0);
    if (!xonVoxelInBounds(voxel)) return vec4(0.0);
    return readFirst ? texelFetch(xonLightTex0, voxel, 0) : texelFetch(xonLightTex1, voxel, 0);
}

// One flood-fill step per frame: the volume converges within reach + 1 frames and
// re-converges at the same rate when blocks change. Solid blocks stop propagation.
void main() {
    ivec3 voxel = ivec3(gl_GlobalInvocationID);
    uint data = texelFetch(xonVoxelTex, voxel, 0).r;
    vec4 light = vec4(0.0, 0.0, 0.0, -1.0);
    if (data >= XON_VOXEL_FIRST_EMITTER) {
        light = vec4(xonSaturateEmitterColor(xonVoxelEmitterColor(data)), 1.0);
    } else if (data == XON_VOXEL_EMPTY) {
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
    if ((frameCounter & 1) == 0) imageStore(xonLightImg0, voxel, light);
    else imageStore(xonLightImg1, voxel, light);
}
#else
layout(local_size_x = 1) in;
const ivec3 workGroups = ivec3(1);
void main() {}
#endif
