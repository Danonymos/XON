"""Bake Schwarzschild null-geodesic disk transfer; runtime uses one filtered lookup."""
from pathlib import Path
import json

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SIZE = 1024
IMPACT_SAMPLES = 4096
PHI_STEP = .003
PHI_SAMPLES = int(3 * np.pi / PHI_STEP) + 1
CRITICAL_IMPACT = np.sqrt(27) / 2
EXTENT = 6.0
INNER_RADIUS = 3.0
OUTER_RADIUS = 12.0
HDR_RANGE = 16.0


def blackbody(temperature):
    t = np.clip(temperature / 100, 10, 200)
    red = np.where(t <= 66, 255, 329.698727446 * np.maximum(t - 60, 1) ** -.1332047592)
    green = np.where(t <= 66, 99.4708025861 * np.log(t) - 161.1195681661,
                     288.1221695283 * np.maximum(t - 60, 1) ** -.0755148492)
    blue = np.where(t >= 66, 255, 138.5177312231 * np.log(np.maximum(t - 10, 1)) - 305.0447927307)
    return np.clip(np.stack([red, green, blue], axis=-1) / 255, 0, 1) ** 2.2


def run():
    impact = np.linspace(.001, EXTENT * CRITICAL_IMPACT * np.sqrt(2), IMPACT_SAMPLES)
    inverse_radius = np.zeros(IMPACT_SAMPLES)
    derivative = 1 / impact
    active = np.ones(IMPACT_SAMPLES, bool)
    invariant_error = 0.0
    table = np.full((PHI_SAMPLES, IMPACT_SAMPLES), np.nan, np.float32)
    slope = np.full_like(table, np.nan)

    def acceleration(u):
        return 1.5 * u * u - u

    for step in range(PHI_SAMPLES):
        table[step, active] = inverse_radius[active]
        slope[step, active] = derivative[active]
        invariant = derivative[active] ** 2 + inverse_radius[active] ** 2 - inverse_radius[active] ** 3
        invariant_error = max(invariant_error, float(np.max(np.abs(invariant * impact[active] ** 2 - 1))))
        u, v = inverse_radius[active], derivative[active]
        k1u, k1v = v, acceleration(u)
        k2u, k2v = v + PHI_STEP * k1v / 2, acceleration(u + PHI_STEP * k1u / 2)
        k3u, k3v = v + PHI_STEP * k2v / 2, acceleration(u + PHI_STEP * k2u / 2)
        k4u, k4v = v + PHI_STEP * k3v, acceleration(u + PHI_STEP * k3u)
        inverse_radius[active] += PHI_STEP / 6 * (k1u + 2 * k2u + 2 * k3u + k4u)
        derivative[active] += PHI_STEP / 6 * (k1v + 2 * k2v + 2 * k3v + k4v)
        active &= (inverse_radius >= 0) & (inverse_radius < 1)

    axis = ((np.arange(SIZE) + .5) / SIZE * 2 - 1) * EXTENT
    x, y = np.meshgrid(axis, axis[::-1])
    radius = np.sqrt(x * x + y * y)
    b = np.maximum(radius * CRITICAL_IMPACT, .001)
    ex, ey = x / np.maximum(radius, 1e-8), y / np.maximum(radius, 1e-8)
    inclination = np.deg2rad(86)
    normal = np.array([0, np.sin(inclination), np.cos(inclination)])
    first_phi = np.mod(np.arctan2(-normal[2], ey * normal[1]), np.pi)
    emission = np.zeros((SIZE, SIZE, 3))
    covered = np.zeros((SIZE, SIZE), bool)
    count = []
    noise = np.asarray(Image.open(ROOT / 'shaders/textures/xon-noise.png').convert('RGB'), float) / 255

    def disk_noise(r, angle, radial_frequency, angular_frequency, channel):
        uv = np.stack([r * radial_frequency + .08 * np.sin(angle), angle * (angular_frequency / (2 * np.pi))], axis=-1)
        pixel = np.mod(uv, 1) * 256
        base = np.floor(pixel).astype(int)
        fraction = pixel - base
        fx, fy = fraction[..., 0], fraction[..., 1]
        ix, iy = base[..., 0], base[..., 1]
        return ((1 - fy) * ((1 - fx) * noise[iy, ix, channel] + fx * noise[iy, (ix + 1) % 256, channel])
                + fy * ((1 - fx) * noise[(iy + 1) % 256, ix, channel] + fx * noise[(iy + 1) % 256, (ix + 1) % 256, channel]))

    def lookup(data, phi):
        row = np.clip(phi / PHI_STEP, 0, PHI_SAMPLES - 1.001)
        col = np.clip((b - impact[0]) / (impact[-1] - impact[0]) * (IMPACT_SAMPLES - 1), 0, IMPACT_SAMPLES - 1.001)
        i, j = row.astype(int), col.astype(int)
        fy, fx = row - i, col - j
        return ((1 - fy) * ((1 - fx) * data[i, j] + fx * data[i, j + 1])
                + fy * ((1 - fx) * data[i + 1, j] + fx * data[i + 1, j + 1]))

    for order in range(3):
        phi = first_phi + order * np.pi
        u = lookup(table, phi)
        du = lookup(slope, phi)
        r = 1 / np.maximum(np.nan_to_num(u, nan=0), 1e-8)
        hit = np.isfinite(u) & (r > INNER_RADIUS) & (r < OUTER_RADIUS) & ~covered
        radial = np.stack([np.sin(phi) * ex, np.sin(phi) * ey, np.cos(phi)], axis=-1)
        tangent = np.stack([np.cos(phi) * ex, np.cos(phi) * ey, -np.sin(phi)], axis=-1)
        velocity = np.cross(normal, radial)
        velocity /= np.maximum(np.linalg.norm(velocity, axis=-1, keepdims=True), 1e-8)
        beta = np.sqrt(1 / np.maximum(2 * (r - 1), 1e-8))
        beta = np.minimum(beta, .5)
        to_observer = np.nan_to_num(du / np.maximum(u, 1e-8))[..., None] * radial - tangent
        to_observer /= np.maximum(np.linalg.norm(to_observer, axis=-1, keepdims=True), 1e-8)
        doppler = np.sqrt(1 - beta * beta) / (1 - beta * np.sum(velocity * to_observer, axis=-1))
        redshift = np.sqrt(np.maximum(1 - 1 / r, 0)) * doppler
        flux = (INNER_RADIUS / r) ** 3 * np.maximum(1 - np.sqrt(INNER_RADIUS / r), 0) / .05665
        angle = np.arctan2(radial[..., 2], radial[..., 0])
        structure = np.clip(.50 + 1.1 * (disk_noise(r, angle, .10, 5, 0) * .65 + disk_noise(r, angle, .31, 13, 1) * .35 - .5), .1, 1)
        temperature = 6100 * np.maximum(flux, 0) ** .25 * redshift
        radiance = blackbody(temperature) * (flux ** 2.2 * redshift ** 4 * structure * 5)[..., None]
        outer_fade = np.clip((OUTER_RADIUS - r) / 3, 0, 1)
        radiance *= (outer_fade * outer_fade * (3 - 2 * outer_fade))[..., None]
        emission[hit] = radiance[hit]
        covered |= hit
        count.append(int(hit.sum()))

    captured = b < CRITICAL_IMPACT
    opacity = np.maximum(captured.astype(float), np.clip(emission.max(axis=-1) * 3, 0, 1))
    encoded = np.concatenate([np.sqrt(np.clip(emission / HDR_RANGE, 0, 1)), opacity[..., None]], axis=-1)
    image = Image.fromarray(np.uint8(np.rint(encoded * 255)))
    output = ROOT / 'shaders/textures/xon-black-hole.png'
    image.save(output, optimize=True)
    assert invariant_error < .00001, invariant_error
    print(json.dumps({'texture': str(output), 'size': SIZE, 'bytes': output.stat().st_size,
                      'maximum_null_geodesic_invariant_error': invariant_error,
                      'disk_intersections_by_order': count, 'maximum_linear_radiance': float(emission.max()),
                      'model': 'Schwarzschild u\'\' + u = 1.5 u^2 in Schwarzschild-radius units; RK4; 86-degree thin disk; ISCO 3rs; gravitational and orbital Doppler transfer; shaped emissivity'}, indent=2))


if __name__ == '__main__':
    run()
