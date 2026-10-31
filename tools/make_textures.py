"""Generate XON's original periodic cloud field and neutral-safe grading LUT."""

from pathlib import Path
import argparse
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def make_textures():
    target = ROOT / 'shaders' / 'textures'
    target.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(60429)
    axis = np.arange(256, dtype=np.float32) / 256.0
    x, y = np.meshgrid(axis, axis)
    channels = []
    for channel in range(3):
        field = np.zeros((256, 256), dtype=np.float32)
        for _ in range(36):
            kx, ky = rng.integers(-9, 10, size=2)
            if kx == 0 and ky == 0:
                continue
            amplitude = 1.0 / (1.0 + float(kx * kx + ky * ky) * 0.12)
            field += np.cos((x * kx + y * ky) * (2 * np.pi) + rng.uniform(0, 2 * np.pi)) * amplitude
        field = np.clip(0.5 + field / max(float(field.std()), 0.001) * 0.17, 0, 1)
        channels.append(field)
    Image.fromarray(np.uint8(np.stack(channels, axis=-1) * 255)).save(target / 'xon-noise.png')

    make_grade(target)
    print('Generated original cloud noise and 16-cube color LUT.')


def make_grade(target):
    lut = np.zeros((16, 256, 3), dtype=np.float32)
    for blue in range(16):
        for green in range(16):
            for red in range(16):
                color = np.array([red, green, blue], dtype=np.float32) / 15.0
                luminance = float(np.dot(color, [0.2126, 0.7152, 0.0722]))
                contrast = color + 0.120 * color * (1 - color) * (2 * color - 1)
                saturation = luminance + (contrast - luminance) * 1.140
                midtone = 4.0 * luminance * (1.0 - luminance)
                warm = np.array([0.014, 0.009, -0.012]) * midtone * luminance
                cool = np.array([-0.010, 0.005, 0.013]) * midtone * (1.0 - luminance)
                lut[green, blue * 16 + red] = np.clip(saturation + warm + cool, 0, 1)
    Image.fromarray(np.uint8(np.rint(lut * 255))).save(target / 'xon-grade.png')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grade-only', action='store_true', help='Rebuild the color LUT without touching cloud noise')
    if parser.parse_args().grade_only:
        make_grade(ROOT / 'shaders/textures')
        print('Generated the 16-cube color LUT; cloud noise preserved.')
    else:
        make_textures()
