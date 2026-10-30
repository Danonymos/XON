"""Direct GPU validation of colored emissive block lighting in XON."""
from pathlib import Path
import numpy as np
import ctypes as ct

from validate import Driver, SHADERS, variant_source
from render_checks import Renderer

ROOT = Path(__file__).resolve().parents[1]

def run():
    driver = Driver()
    renderer = Renderer(driver, 960, 540)
    stages, programs = [], []

    def compile_pair(v_src, f_src, label):
        pair = []
        for src, stage in [(v_src, '.vsh'), (f_src, '.fsh')]:
            shader, warning = driver.compile(src, stage, label)
            if warning: raise AssertionError(f"{label}: {warning}")
            stages.append(shader)
            pair.append(shader)
        prog, warning = driver.link(*pair, label)
        if warning: raise AssertionError(f"{label}: {warning}")
        programs.append(prog)
        return prog

    # Compile composite program
    comp_prog = compile_pair(*(variant_source(SHADERS / ('composite.' + stage), {'XON_BLOOM': False})
                              for stage in ['vsh', 'fsh']), 'composite emissive')
    
    soften_prog = compile_pair(*(variant_source(SHADERS / ('composite1.' + stage), {})
                                for stage in ['vsh', 'fsh']), 'composite1 emissive')

    # Setup textures:
    # unit 0: colortex0 (contains albedo in rgb, emitterId in a)
    # unit 1: depthtex0
    # unit 2: depthtex1
    w, h = 960, 540
    
    # Let's test a receiver surface at z = -4.0 (depth ~ 0.99)
    # In perspective projection (near=0.05, far=1024):
    def z_to_depth(z_dist):
        return ((1024.0 + 0.05) / (1024.0 - 0.05) - 2.0 * 1024.0 * 0.05 / ((1024.0 - 0.05) * z_dist) + 1.0) * 0.5

    depth_4m = z_to_depth(4.0)

    # Test 1: Diamond ore emitter (id = 0.10) illuminating nearby wall
    # Receiver is at center (x=480, y=270). Emitter is at (x=540, y=270).
    colortex0 = np.zeros((h, w, 4), dtype=np.float32)
    colortex0[:, :, 3] = 1.0 # default non-emissive
    # Put diamond ore emitter at (x=530..550, y=260..280)
    # A 1-block ore at 4 meters is ~80 pixels wide
    colortex0[230:310, 530:610, :3] = [0.12, 0.88, 0.98]
    colortex0[230:310, 530:610, 3] = 0.10 # Diamond Ore ID

    depth0 = np.full((h, w), depth_4m, dtype=np.float32)
    depth1 = np.full((h, w), depth_4m, dtype=np.float32)

    # Minecraft perspective projection
    fov_y = 1.37
    aspect = 960.0 / 540.0
    near, far = 0.05, 1024.0
    proj = np.zeros((4, 4), dtype=np.float32)
    proj[0, 0] = fov_y / aspect
    proj[1, 1] = fov_y
    proj[2, 2] = -(far + near) / (far - near)
    proj[2, 3] = -2.0 * far * near / (far - near)
    proj[3, 2] = -1.0
    proj_inv = np.linalg.inv(proj)

    def draw_emissive(c0, d0, d1):
        renderer.setup(comp_prog)
        renderer.uniform1i(renderer.location('isEyeInWater'), 0)
        renderer.texture(0, c0)
        renderer.texture(2, d0)
        renderer.texture(9, d1)
        matrix_data = [
            ('gbufferProjection', proj),
            ('gbufferProjectionInverse', proj_inv),
            ('gbufferModelView', np.eye(4, dtype=np.float32)),
            ('gbufferModelViewInverse', np.eye(4, dtype=np.float32)),
            ('shadowModelView', np.eye(4, dtype=np.float32)),
            ('shadowProjection', np.eye(4, dtype=np.float32)),
        ]
        for name, mat in matrix_data:
            data = np.ascontiguousarray(mat.T, dtype=np.float32)
            renderer.uniform_matrix(renderer.location(name), 1, 0, data.ctypes.data)
        raw_effects = renderer.draw(raw=True)
        # Apply composite1 spatial filter (as done in the pipeline)
        renderer.setup(soften_prog)
        renderer.texture(3, raw_effects) # colortex5 is unit 3
        soft_effects = renderer.draw(raw=True)
        return soft_effects

    # Draw
    result = draw_emissive(colortex0, depth0, depth1)
    
    # Check receiver pixels at increasing distances from the emitter:
    # Emitter edge is at x=530.
    p_close = result[270, 515, :3]
    p_mid   = result[270, 440, :3]
    p_far   = result[270, 350, :3]
    p_edge  = result[270, 240, :3]
    print(f"Close receiver (d~0.2 blocks): {p_close.tolist()}")
    print(f"Mid receiver   (d~1.0 blocks): {p_mid.tolist()}")
    print(f"Far receiver   (d~2.0 blocks): {p_far.tolist()}")
    print(f"Beyond radius  (d>3.0 blocks): {p_edge.tolist()}")

    # Assert diamond color (cyan: G > R, B > R)
    if p_close[1] < 0.1 or p_close[2] < 0.1:
        raise AssertionError(f"Diamond ore did not illuminate close receiver: {p_close}")
    if p_close[0] > p_close[1]:
        raise AssertionError(f"Illumination color is not cyan: {p_close}")

    # Assert smooth falloff curve: close > mid > far >= p_edge
    luma_close = float(np.mean(p_close))
    luma_mid   = float(np.mean(p_mid))
    luma_far   = float(np.mean(p_far))
    luma_edge  = float(np.mean(p_edge))
    print(f"Falloff luma profile: close={luma_close:.4f}, mid={luma_mid:.4f}, far={luma_far:.4f}, edge={luma_edge:.4f}")
    if not (luma_close > luma_mid > luma_far >= luma_edge):
        raise AssertionError(f"Falloff is not smooth and monotonically decreasing: {luma_close}, {luma_mid}, {luma_far}, {luma_edge}")
    if luma_edge > 0.001:
        raise AssertionError(f"Light did not smoothly fade to zero at radius boundary: {luma_edge}")
    print("PASS: Diamond Ore correctly illuminated receiver surface with cyan light and smooth falloff to zero at radius boundary!")

    # Test 2: Wall occlusion: place a protruding wall between emitter and receiver
    # Emitter is at x=530..610. Receiver is at x=510.
    # Put an occluding wall at x=518..532 with closer depth (z=2.0)
    depth0_wall = depth0.copy()
    depth0_wall[:, 518:532] = z_to_depth(2.0)
    depth1_wall = depth1.copy()
    depth1_wall[:, 518:532] = z_to_depth(2.0)

    result_occluded = draw_emissive(colortex0, depth0_wall, depth1_wall)
    lit_occluded = result_occluded[270, 510, :3]
    print(f"Receiver light with occluding wall in between: {lit_occluded.tolist()}")
    if np.max(lit_occluded) > 0.005:
        raise AssertionError(f"Light leaked through solid wall: {lit_occluded}")
    print("PASS: Solid wall completely blocked light propagation (no light leaking through walls)!")

    # Test 3: Multiple emitters blending naturally (Redstone + Lapis)
    # Emitter A (Redstone, red) at x=530..545. Emitter B (Lapis, blue) at x=475..490.
    # Receiver at midpoint x=510.
    colortex0_blend = np.zeros((h, w, 4), dtype=np.float32)
    colortex0_blend[:, :, 3] = 1.0
    colortex0_blend[260:280, 530:545, :3] = [1.0, 0.1, 0.04]
    colortex0_blend[260:280, 530:545, 3] = 0.40 # Redstone ID
    colortex0_blend[260:280, 475:490, :3] = [0.1, 0.38, 1.0]
    colortex0_blend[260:280, 475:490, 3] = 0.50 # Lapis ID

    result_blend = draw_emissive(colortex0_blend, depth0, depth1)
    lit_blend = result_blend[270, 510, :3]
    print(f"Midpoint blended light from Redstone + Lapis: {lit_blend.tolist()}")
    # Blended color should have both strong Red and strong Blue (purple)
    if lit_blend[0] < 0.05 or lit_blend[2] < 0.05:
        raise AssertionError(f"Redstone and Lapis did not blend on receiver: {lit_blend}")
    print("PASS: Redstone + Lapis blended naturally into purple light!")

    # Test 4: Non-emissive block does not emit light
    colortex0_plain = np.zeros((h, w, 4), dtype=np.float32)
    colortex0_plain[260:280, 530:550, :3] = [0.8, 0.8, 0.8] # white wool / stone
    colortex0_plain[:, :, 3] = 1.0 # non-emissive
    result_plain = draw_emissive(colortex0_plain, depth0, depth1)
    lit_plain = result_plain[270, 510, :3]
    print(f"Receiver light from non-emissive block: {lit_plain.tolist()}")
    if np.max(lit_plain) > 0.0001:
        raise AssertionError(f"Non-emissive block emitted light: {lit_plain}")
    print("PASS: Non-emissive blocks emit zero light!")

    # Cleanup
    for p in programs: driver.delete_program(p)
    for s in stages: driver.delete_shader(s)
    driver.close()
    print("ALL 4 EMISSIVE LIGHTING VERIFICATIONS PASSED 100%!")

if __name__ == '__main__':
    run()
