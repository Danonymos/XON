"""Build a conservative indoor-occluder map from installed Minecraft block models."""
import argparse
from functools import lru_cache
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CLIENT = Path.home() / 'AppData/Roaming/ModrinthApp/meta/versions/26.3-0.20.1/26.3-0.20.1.jar'


def selectors(client, properties):
    assigned = {':'.join(token.split(':')[:2]) for line in properties.splitlines()
                if line.startswith('block.') and not line.startswith('block.10028=')
                for token in line.split('=', 1)[1].split()}
    with zipfile.ZipFile(client) as archive:
        names = set(archive.namelist())
        @lru_cache(None)
        def full_cube(model):
            namespace, name = model.split(':', 1) if ':' in model else ('minecraft', model)
            path = f'assets/{namespace}/models/{name}.json'
            if path not in names:
                return False
            data = json.loads(archive.read(path))
            if 'elements' not in data:
                return full_cube(data['parent']) if 'parent' in data else False
            return any(element.get('from') == [0, 0, 0] and element.get('to') == [16, 16, 16]
                       and not element.get('rotation') and len(element.get('faces', {})) == 6
                       for element in data['elements'])

        def full_variant(value):
            values = value if isinstance(value, list) else [value]
            return bool(values) and all(full_cube(item['model']) and item.get('x', 0) % 90 == 0
                                        and item.get('y', 0) % 90 == 0 for item in values)

        result = []
        for path in sorted(archive.namelist()):
            if not path.startswith('assets/minecraft/blockstates/') or not path.endswith('.json'):
                continue
            name = 'minecraft:' + Path(path).stem
            if name in assigned:
                continue
            variants = json.loads(archive.read(path)).get('variants', {})
            if variants and all(full_variant(value) for value in variants.values()):
                result.append(name)
            else:
                result.extend(name + ':' + state for state, value in variants.items()
                              if state and ',' not in state and full_variant(value))
    assert 'minecraft:oak_planks' in result and 'minecraft:stone' in result
    assert 'minecraft:oak_slab:type=double' in result
    assert not any(name in result for name in ['minecraft:red_carpet', 'minecraft:oak_slab',
                                              'minecraft:oak_stairs', 'minecraft:oak_fence', 'minecraft:chain'])
    return result


def run(client, write=False):
    path = ROOT / 'shaders/block.properties'
    newline = '\r\n' if b'\r\n' in path.read_bytes() else '\n'
    properties = path.read_text()
    entries = selectors(client, properties)
    line = 'block.10028=' + ' '.join(entries)
    if write:
        retained = '\n'.join(value for value in properties.splitlines() if not value.startswith('block.10028='))
        path.write_text(retained.rstrip() + '\n' + line + '\n', newline=newline)
    else:
        assert line in properties.splitlines(), 'Indoor occluder map differs from installed block geometry'
    print(json.dumps({'passed': True, 'verified_full_cube_selectors': len(entries),
                      'client': str(client), 'partial_and_unknown_shapes_excluded': True}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minecraft-jar', type=Path, default=CLIENT)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    run(args.minecraft_jar, args.write)
