#ifndef XON_BLOCK_SHAPES
#define XON_BLOCK_SHAPES
const int XON_SHAPE_COUNT = 30;
const uint XON_SHAPE_SOLID[30] = uint[30](15u,51u,55u,59u,63u,85u,115u,119u,127u,170u,179u,187u,191u,204u,205u,206u,207u,220u,221u,223u,236u,238u,239u,240u,243u,247u,251u,252u,253u,254u);
const uint XON_TRAPDOOR_SHAPES[6] = uint[6](5u,9u,1u,13u,0u,23u);
// A partial voxel's repeated AO centre bit is always zero, so it can tag thin panels without reducing the shape index.
const uint XON_TRAPDOOR_META = 1u << 13u;
bool xonTrapdoorVoxel(uint data) { return data >= 64u && data < 70u; }
bool xonPartialVoxel(uint data) { return (data >= 10u && data < 10u + uint(XON_SHAPE_COUNT)) || xonTrapdoorVoxel(data); }
uint xonVoxelShapeIndex(uint data) { return xonTrapdoorVoxel(data) ? XON_TRAPDOOR_SHAPES[data - 64u] : data - 10u; }
uint xonVoxelOpenOctants(uint data) {
    if (xonPartialVoxel(data)) return 255u ^ XON_SHAPE_SOLID[xonVoxelShapeIndex(data)];
    return data == 1u || data == 255u ? 0u : 255u;
}
bool xonTrapdoorPointSolid(uint solid, vec3 point) {
    float coordinate = solid == 85u || solid == 170u ? point.x : (solid == 51u || solid == 204u ? point.y : point.z);
    bool high = solid == 170u || solid == 204u || solid == 240u;
    return high ? coordinate >= 13.0 / 16.0 : coordinate <= 3.0 / 16.0;
}
bool xonShapeFaceOpen(uint a, uint b, int axis, bool positive) {
    uint shift = 1u << uint(axis);
    uint high = axis == 0 ? 170u : (axis == 1 ? 204u : 240u);
    return positive ? (a & high & (b << shift)) != 0u : (b & high & (a << shift)) != 0u;
}
#endif
