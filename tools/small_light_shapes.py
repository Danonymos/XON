"""Classify small open decorations without making full wall faces transparent."""
from functools import lru_cache
import json
import math
from pathlib import Path
import sys
import zipfile

from indoor_block_shapes import CLIENT

ROOT = Path(__file__).resolve().parents[1]


def selectors():
    properties = (ROOT / 'shaders/block.properties').read_text()
    assigned = {':'.join(token.split(':')[:2]) for line in properties.splitlines()
                if line.startswith('block.') and not line.startswith('block.10029=')
                for token in line.split('=', 1)[1].split()}
    with zipfile.ZipFile(CLIENT) as archive:
        model_bounds = {}
        @lru_cache(None)
        def elements(model):
            namespace, name = model.split(':', 1) if ':' in model else ('minecraft', model)
            path = f'assets/{namespace}/models/{name}.json'
            try:
                data = json.loads(archive.read(path))
            except KeyError:
                return None
            if 'elements' in data:
                return data['elements']
            return elements(data['parent']) if 'parent' in data else None

        def small(model):
            boxes = elements(model)
            if not boxes:
                return False
            has_volume = any(all(abs(box['to'][a] - box['from'][a]) >= .0001 for a in range(3)) for box in boxes)
            points = []
            for box in boxes:
                lower, upper = box['from'], box['to']
                # Crossed flower/leaf planes have texture coverage, not solid volume.
                if has_volume and any(abs(upper[a] - lower[a]) < .0001 for a in range(3)):
                    continue
                if sum(upper[a] - lower[a] >= 16 for a in range(3)) >= 2:
                    return False
                rotation = box.get('rotation')
                for corner in range(8):
                    point = [upper[a] if corner & (1 << a) else lower[a] for a in range(3)]
                    if rotation:
                        axis = 'xyz'.index(rotation['axis'])
                        u, v = (axis + 1) % 3, (axis + 2) % 3
                        origin = rotation['origin']
                        angle = math.radians(rotation['angle'])
                        sine, cosine = math.sin(angle), math.cos(angle)
                        x, y = point[u] - origin[u], point[v] - origin[v]
                        scale = 1 / abs(cosine) if rotation.get('rescale') else 1
                        point[u] = origin[u] + (x * cosine - y * sine) * scale
                        point[v] = origin[v] + (x * sine + y * cosine) * scale
                    points.append(point)
            if not points:
                return False
            bounds = [max(p[a] for p in points) - min(p[a] for p in points) for a in range(3)]
            model_bounds[model] = ([min(p[a] for p in points) for a in range(3)],
                                   [max(p[a] for p in points) for a in range(3)])
            return all(-.001 <= p[a] <= 16.001 for p in points for a in range(3)) and math.prod(bounds) <= 16 ** 3 * .30

        result = []
        for path in sorted(archive.namelist()):
            if not path.startswith('assets/minecraft/blockstates/') or not path.endswith('.json'):
                continue
            name = 'minecraft:' + Path(path).stem
            if name in assigned:
                continue
            state = json.loads(archive.read(path))
            models = []
            def collect(value):
                if isinstance(value, dict):
                    if 'model' in value:
                        models.append(value['model'])
                    for child in value.values():
                        collect(child)
                elif isinstance(value, list):
                    for child in value:
                        collect(child)
            collect(state)
            if models and all(small(model) for model in models):
                combined = [max(model_bounds[m][1][a] for m in models)
                            - min(model_bounds[m][0][a] for m in models) for a in range(3)]
                if math.prod(combined) <= 16 ** 3 * .30:
                    result.append(name)
    assert 'minecraft:flower_pot' in result
    assert 'minecraft:potted_poppy' in result and 'minecraft:potted_dandelion' in result
    with zipfile.ZipFile(CLIENT) as archive:
        potted = {'minecraft:' + Path(path).stem for path in archive.namelist()
                  if path.startswith('assets/minecraft/blockstates/potted_') and path.endswith('.json')}
    assert potted <= set(result) | assigned, 'A planted-pot variant has no explicit light classification'
    assert any('chain' in name for name in result)
    assert not any(name in result for name in ['minecraft:oak_door', 'minecraft:oak_trapdoor',
                                              'minecraft:oak_slab', 'minecraft:oak_stairs',
                                              'minecraft:stone', 'minecraft:quartz_pillar'])
    return result


if __name__ == '__main__':
    entries = selectors()
    path = ROOT / 'shaders/block.properties'
    line = 'block.10029=' + ' '.join(entries)
    if '--write' in sys.argv:
        text = path.read_text()
        retained = '\n'.join(value for value in text.splitlines() if not value.startswith('block.10029=')
                             and value != '# Small open decorations use native shape shading instead of a whole-voxel blocker.')
        path.write_text(retained.rstrip() + '\n# Small open decorations use native shape shading instead of a whole-voxel blocker.\n' + line + '\n')
    else:
        print(json.dumps({'count': len(entries), 'selectors': entries}, indent=2))
