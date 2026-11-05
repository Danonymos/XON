"""Generate conservative half-block occupancy for native stairs, slabs and trapdoors."""
from functools import lru_cache
import json
from pathlib import Path
import sys
import zipfile
import numpy as np
from indoor_block_shapes import CLIENT

ROOT = Path(__file__).resolve().parents[1]


def generate(write=False):
    groups = {}
    with zipfile.ZipFile(CLIENT) as archive:
        @lru_cache(None)
        def elements(model):
            path = 'assets/minecraft/models/' + model.removeprefix('minecraft:') + '.json'
            data = json.loads(archive.read(path))
            return data['elements'] if 'elements' in data else elements(data['parent'])

        def mask(model):
            result = 0
            boxes = elements(model['model'])
            if '_trapdoor_' in model['model']:
                assert len(boxes) == 1 and sorted(boxes[0]['to'][a] - boxes[0]['from'][a] for a in range(3)) == [3, 16, 16]
            for box in boxes:
                assert not box.get('rotation')
                assert all(v in (0, 3, 8, 13, 16) for v in box['from'] + box['to']), model
            for bit in range(8):
                point = np.array([4 + 8 * ((bit >> a) & 1) for a in range(3)], float)
                # Inverse blockstate rotation maps a world octant into the model.
                for axis, angle in [(1, model.get('y', 0)), (0, model.get('x', 0))]:
                    angle = np.deg2rad(angle)
                    u, v = ((2, 0) if axis == 1 else (1, 2))
                    x, y = point[u] - 8, point[v] - 8
                    point[u], point[v] = 8 + x * np.cos(angle) - y * np.sin(angle), 8 + x * np.sin(angle) + y * np.cos(angle)
                # Thin trapdoors occupy the intersected half, rather than disappearing between octant centres.
                if any(all(box['from'][a] < point[a] + 4 - .00001 and box['to'][a] > point[a] - 4 + .00001
                           for a in range(3)) for box in boxes):
                    result |= 1 << bit
            return result

        for path in archive.namelist():
            name = Path(path).stem
            if not path.startswith('assets/minecraft/blockstates/') or not name.endswith(('_stairs', '_slab', '_trapdoor')):
                continue
            state = json.loads(archive.read(path))
            for selector, models in state['variants'].items():
                models = models if isinstance(models, list) else [models]
                masks = {mask(model) for model in models}
                assert len(masks) == 1
                value = masks.pop()
                if value not in (0, 255):
                    groups.setdefault(value, []).append('minecraft:' + name + ':' + selector.replace(',', ':'))
    masks = sorted(groups)
    assert len(masks) <= 31
    # Bottom slab and top slab must close opposite vertical faces.
    assert 51 in masks and 204 in masks
    for facing, expected in [('north', 63), ('west', 119), ('east', 187), ('south', 243)]:
        assert f'minecraft:oak_stairs:facing={facing}:half=bottom:shape=straight' in groups[expected]
    trapdoors = [s for entries in groups.values() for s in entries if '_trapdoor:' in s]
    trapdoor_masks = [85, 170, 51, 204, 15, 240]
    for half, expected in [('bottom', 51), ('top', 204)]:
        assert f'minecraft:oak_trapdoor:facing=north:half={half}:open=false' in groups[expected]
    for facing, expected in [('north', 240), ('south', 15), ('west', 170), ('east', 85)]:
        assert f'minecraft:oak_trapdoor:facing={facing}:half=bottom:open=true' in groups[expected]
    if not write:
        actual = {int(line.split('=', 1)[0].split('.')[1]): set(line.split('=', 1)[1].split())
                  for line in (ROOT / 'shaders/block.properties').read_text().splitlines()
                  if line.startswith(('block.110', 'block.111', 'block.112'))}
        expected = {}
        for index, value in enumerate(masks):
            for quartz, base in [(False, 11000), (True, 11100)]:
                entries = {s for s in groups[value]
                           if '_trapdoor:' not in s and s.startswith(('minecraft:quartz_', 'minecraft:smooth_quartz_')) == quartz}
                if entries:
                    expected[base + index] = entries
        for index, value in enumerate(trapdoor_masks):
            expected[11200 + index] = {s for s in groups[value] if '_trapdoor:' in s}
        assert actual == expected, 'Partial-block state map differs from installed model geometry'
        glsl = (ROOT / 'shaders/lib/block_shapes.glsl').read_text()
        assert f'uint[{len(masks)}](' + ','.join(str(m) + 'u' for m in masks) + ');' in glsl
    if write:
        path = ROOT / 'shaders/block.properties'
        lines = [line for line in path.read_text().splitlines() if not line.startswith(('block.110', 'block.111', 'block.112'))]
        # Keep quartz's full double slab material; partial quartz is shape-classified.
        for i, line in enumerate(lines):
            if line.startswith('block.10023='):
                tokens = line.split('=', 1)[1].split()
                tokens = [token for token in tokens if not token.endswith(('_stairs', '_slab'))]
                tokens += ['minecraft:quartz_slab:type=double', 'minecraft:smooth_quartz_slab:type=double']
                lines[i] = 'block.10023=' + ' '.join(dict.fromkeys(tokens))
        for index, value in enumerate(masks):
            ordinary = [s for s in groups[value] if '_trapdoor:' not in s and not s.startswith(('minecraft:quartz_', 'minecraft:smooth_quartz_'))]
            quartz = [s for s in groups[value] if s.startswith(('minecraft:quartz_', 'minecraft:smooth_quartz_'))]
            if ordinary:
                lines.append(f'block.{11000 + index}=' + ' '.join(ordinary))
            if quartz:
                lines.append(f'block.{11100 + index}=' + ' '.join(quartz))
        for index, value in enumerate(trapdoor_masks):
            lines.append(f'block.{11200 + index}=' + ' '.join(s for s in groups[value] if '_trapdoor:' in s))
        path.write_text('\n'.join(lines) + '\n')
        (ROOT / 'shaders/lib/block_shapes.glsl').write_text(
            '#ifndef XON_BLOCK_SHAPES\n#define XON_BLOCK_SHAPES\n'
            + f'const int XON_SHAPE_COUNT = {len(masks)};\n'
            + f'const uint XON_SHAPE_SOLID[{len(masks)}] = uint[{len(masks)}]('
            + ','.join(str(m) + 'u' for m in masks) + ');\n'
            + 'const uint XON_TRAPDOOR_SHAPES[6] = uint[6](' + ','.join(str(masks.index(m)) + 'u' for m in trapdoor_masks) + ');\n'
            + '''// A partial voxel's repeated AO centre bit is always zero, so it can tag thin panels without reducing the shape index.
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
''')
    print(json.dumps({'masks': masks, 'classes': len(masks), 'state_selectors': sum(map(len, groups.values())),
                      'trapdoor_states': len(trapdoors)}))


if __name__ == '__main__':
    generate('--write' in sys.argv)
