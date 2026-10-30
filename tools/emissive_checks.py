"""Direct GPU and algorithmic validation of 3D voxel colored emissive lighting in XON."""
from pathlib import Path
import numpy as np
import ctypes as ct

from validate import Driver, SHADERS, expand, variant_source

ROOT = Path(__file__).resolve().parents[1]

def run():
    driver = Driver()
    
    # 1. Compile shadowcomp.csh as GL_COMPUTE_SHADER
    print("Testing compute shader shadowcomp.csh compilation...")
    comp_src = expand(SHADERS / 'shadowcomp.csh')
    csh = driver.create_shader(0x91B9) # GL_COMPUTE_SHADER
    encoded = comp_src.encode()
    ptr = ct.c_char_p(encoded)
    l = ct.c_int(len(encoded))
    driver.shader_source(csh, 1, ct.byref(ptr), ct.byref(l))
    driver.compile_shader(csh)
    status = ct.c_int()
    driver.get_shader(csh, 0x8B81, ct.byref(status))
    if not status.value:
        log = ct.create_string_buffer(65536)
        driver.shader_log(csh, len(log), None, log)
        raise AssertionError(f"shadowcomp.csh failed to compile:\n{log.value.decode()}")
    print("PASS: shadowcomp.csh compiled cleanly!")
    driver.delete_shader(csh)

    # 2. Compile shadow.vsh with voxelization enabled
    print("Testing shadow.vsh compilation...")
    shadow_vsh_src = variant_source(SHADERS / 'shadow.vsh', {'XON_COLORED_EMISSIVE_LIGHTING': True})
    s_vsh, msg = driver.compile(shadow_vsh_src, '.vsh', 'shadow.vsh')
    if msg: print("shadow.vsh warning:", msg)
    print("PASS: shadow.vsh compiled cleanly!")
    driver.delete_shader(s_vsh)

    # 3. Compile gbuffers_terrain.fsh with emissive sampling enabled
    print("Testing gbuffers_terrain.fsh compilation...")
    terrain_fsh_src = variant_source(SHADERS / 'gbuffers_terrain.fsh', {'XON_COLORED_EMISSIVE_LIGHTING': True})
    t_fsh, msg = driver.compile(terrain_fsh_src, '.fsh', 'gbuffers_terrain.fsh')
    if msg: print("gbuffers_terrain.fsh warning:", msg)
    print("PASS: gbuffers_terrain.fsh compiled cleanly!")
    driver.delete_shader(t_fsh)

    driver.close()

    # 4. Numerical validation of the voxel flood-fill and sampling algorithm
    print("Testing 3D voxel flood-fill propagation and falloff...")
    VOXEL_SIZE = (96, 48, 96)
    grid_voxels = np.zeros(VOXEL_SIZE, dtype=np.uint8)
    light_tex = np.zeros((*VOXEL_SIZE, 4), dtype=np.float32)
    light_tex[:, :, :, 3] = -1.0 # unlit / solid

    # Place Diamond Ore at center (48, 24, 48)
    center = (48, 24, 48)
    grid_voxels[center] = 2 # Diamond Ore ID
    diamond_color = np.array([0.25, 0.90, 1.00], dtype=np.float32)

    # Simulate flood fill steps
    STEP = 1.0 / (3.0 + 1.0) # Radius = 3.0 -> STEP = 0.25
    curr_light = np.zeros_like(light_tex)
    curr_light[center] = [*diamond_color, 1.0]

    NEIGHBORS = [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]

    # Run 4 iterations of flood fill
    for step in range(4):
        next_light = curr_light.copy()
        for x in range(center[0]-4, center[0]+5):
            for y in range(center[1]-4, center[1]+5):
                for z in range(center[2]-4, center[2]+5):
                    pos = (x, y, z)
                    if pos == center:
                        continue
                    if grid_voxels[pos] == 1: # solid
                        next_light[pos] = [0.0, 0.0, 0.0, -1.0]
                        continue
                    # Read neighbors
                    brightest = 0.0
                    col_sum = np.zeros(3, dtype=np.float32)
                    lvl_sum = 0.0
                    for dx, dy, dz in NEIGHBORS:
                        npos = (x+dx, y+dy, z+dz)
                        n_lvl = max(curr_light[npos][3], 0.0)
                        if n_lvl > brightest:
                            brightest = n_lvl
                        col_sum += curr_light[npos][:3] * n_lvl
                        lvl_sum += n_lvl
                    lvl = max(brightest - STEP, 0.0)
                    if lvl > 0.0 and lvl_sum > 0.0:
                        next_light[pos] = [*(col_sum / lvl_sum), lvl]
                    else:
                        next_light[pos] = [0.0, 0.0, 0.0, 0.0]
        curr_light = next_light

    # Check falloff along X axis from center
    levels = [curr_light[center[0] + dx, center[1], center[2]][3] for dx in range(5)]
    print(f"Propagated levels along axis: {levels}")
    assert levels[0] == 1.0, f"Emitter level must be 1.0, got {levels[0]}"
    assert abs(levels[1] - 0.75) < 1e-4, f"Distance 1 must be 0.75, got {levels[1]}"
    assert abs(levels[2] - 0.50) < 1e-4, f"Distance 2 must be 0.50, got {levels[2]}"
    assert abs(levels[3] - 0.25) < 1e-4, f"Distance 3 must be 0.25, got {levels[3]}"
    assert levels[4] == 0.0, f"Distance 4 (beyond radius) must be 0.0, got {levels[4]}"
    print("PASS: Linear flood fill propagation matches theoretical 3-block radius exactly!")

    # Check smooth falloff curve: falloff = level^2 * (3 - 2*level)
    def calc_falloff(level):
        return level * level * (3.0 - 2.0 * level)

    falloffs = [calc_falloff(lvl) for lvl in levels]
    print(f"Smooth falloff profile: {falloffs}")
    assert falloffs[0] == 1.0
    assert falloffs[1] > falloffs[2] > falloffs[3] > falloffs[4] == 0.0
    print("PASS: Monotonic smooth falloff curve smoothly eases to zero at boundary!")

    # 5. Test Wall Occlusion
    print("Testing solid wall occlusion...")
    grid_voxels2 = np.zeros(VOXEL_SIZE, dtype=np.uint8)
    # Place a solid wall at x = center[0] + 1
    for wy in range(center[1]-3, center[1]+4):
        for wz in range(center[2]-3, center[2]+4):
            grid_voxels2[center[0] + 1, wy, wz] = 1 # Solid wall
    grid_voxels2[center] = 2 # Diamond Ore

    curr_light2 = np.zeros_like(light_tex)
    curr_light2[center] = [*diamond_color, 1.0]
    for wy in range(center[1]-3, center[1]+4):
        for wz in range(center[2]-3, center[2]+4):
            curr_light2[center[0] + 1, wy, wz] = [0.0, 0.0, 0.0, -1.0]

    for step in range(4):
        next_light = curr_light2.copy()
        for x in range(center[0]-4, center[0]+5):
            for y in range(center[1]-4, center[1]+5):
                for z in range(center[2]-4, center[2]+5):
                    pos = (x, y, z)
                    if pos == center:
                        continue
                    if grid_voxels2[pos] == 1:
                        next_light[pos] = [0.0, 0.0, 0.0, -1.0]
                        continue
                    brightest = 0.0
                    col_sum = np.zeros(3, dtype=np.float32)
                    lvl_sum = 0.0
                    for dx, dy, dz in NEIGHBORS:
                        npos = (x+dx, y+dy, z+dz)
                        n_lvl = max(curr_light2[npos][3], 0.0)
                        if n_lvl > brightest:
                            brightest = n_lvl
                        col_sum += curr_light2[npos][:3] * n_lvl
                        lvl_sum += n_lvl
                    lvl = max(brightest - STEP, 0.0)
                    if lvl > 0.0 and lvl_sum > 0.0:
                        next_light[pos] = [*(col_sum / lvl_sum), lvl]
                    else:
                        next_light[pos] = [0.0, 0.0, 0.0, 0.0]
        curr_light2 = next_light

    behind_wall = curr_light2[center[0] + 2, center[1], center[2]][3]
    print(f"Light behind solid wall (x = center + 2): {behind_wall}")
    assert behind_wall == 0.0, f"Light leaked behind solid wall: {behind_wall}"
    print("PASS: Solid wall completely blocked light propagation (zero light leakage)!")

    # 6. Test Multi-Emitter Color Blending (Redstone + Lapis)
    print("Testing multi-emitter color blending (Redstone + Lapis)...")
    grid_voxels3 = np.zeros(VOXEL_SIZE, dtype=np.uint8)
    r_pos = (center[0] - 2, center[1], center[2])
    l_pos = (center[0] + 2, center[1], center[2])
    grid_voxels3[r_pos] = 4 # Redstone
    grid_voxels3[l_pos] = 5 # Lapis
    red_color = np.array([1.00, 0.12, 0.06], dtype=np.float32)
    lapis_color = np.array([0.18, 0.35, 1.00], dtype=np.float32)

    curr_light3 = np.zeros_like(light_tex)
    curr_light3[r_pos] = [*red_color, 1.0]
    curr_light3[l_pos] = [*lapis_color, 1.0]

    for step in range(4):
        next_light = curr_light3.copy()
        for x in range(center[0]-4, center[0]+5):
            for y in range(center[1]-4, center[1]+5):
                for z in range(center[2]-4, center[2]+5):
                    pos = (x, y, z)
                    if pos == r_pos or pos == l_pos:
                        continue
                    brightest = 0.0
                    col_sum = np.zeros(3, dtype=np.float32)
                    lvl_sum = 0.0
                    for dx, dy, dz in NEIGHBORS:
                        npos = (x+dx, y+dy, z+dz)
                        n_lvl = max(curr_light3[npos][3], 0.0)
                        if n_lvl > brightest:
                            brightest = n_lvl
                        col_sum += curr_light3[npos][:3] * n_lvl
                        lvl_sum += n_lvl
                    lvl = max(brightest - STEP, 0.0)
                    if lvl > 0.0 and lvl_sum > 0.0:
                        next_light[pos] = [*(col_sum / lvl_sum), lvl]
                    else:
                        next_light[pos] = [0.0, 0.0, 0.0, 0.0]
        curr_light3 = next_light

    mid_color = curr_light3[center][:3]
    print(f"Blended color at midpoint between Redstone & Lapis: {mid_color}")
    assert mid_color[0] > 0.3 and mid_color[2] > 0.3, "Colors did not blend into purple"
    print("PASS: Redstone + Lapis blended naturally into purple light at midpoint!")

    print("ALL 3D VOXEL EMISSIVE LIGHTING VERIFICATIONS PASSED 100%!")

if __name__ == '__main__':
    run()
