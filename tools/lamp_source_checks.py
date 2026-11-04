"""Generate and validate state-aware non-ore lamp mappings from installed client assets."""
import argparse
import json
from pathlib import Path
import zipfile

from indoor_block_shapes import CLIENT, run as full_blocks

ROOT = Path(__file__).resolve().parents[1]
COLORS = ['white', 'orange', 'magenta', 'light_blue', 'yellow', 'lime', 'pink', 'gray',
          'light_gray', 'cyan', 'purple', 'blue', 'brown', 'green', 'red', 'black']


def sources():
    result = {
        10030: ['torch', 'wall_torch'], 10031: ['soul_torch', 'soul_wall_torch'],
        10032: ['sea_lantern'], 10033: ['end_rod'], 10034: ['glowstone'], 10035: ['shroomlight'],
        10036: ['fire'], 10037: ['soul_fire'], 10038: ['beacon', 'conduit'], 10039: ['magma_block'],
        10040: [b + ':lit=true' for b in ['furnace', 'smoker', 'blast_furnace']],
        10041: ['redstone_lamp:lit=true'],
        10042: ['redstone_torch:lit=true', 'redstone_wall_torch:lit=true']
               + [f'redstone_wire:power={i}' for i in range(1, 16)],
        10043: ['campfire:lit=true'], 10044: ['soul_campfire:lit=true'], 10045: ['lava_cauldron'],
        10046: ['ochre_froglight'], 10047: ['verdant_froglight'], 10048: ['pearlescent_froglight'],
        10061: ['crying_obsidian'], 10063: ['end_portal', 'end_gateway'],
        10064: ['enchanting_table', 'ender_chest'], 10065: ['brewing_stand', 'end_portal_frame'],
        10066: ['brown_mushroom', 'potted_brown_mushroom', 'dragon_egg'],
        10067: ['firefly_bush'], 10076: ['copper_torch', 'copper_wall_torch'],
        10077: ['amethyst_cluster'], 10078: ['large_amethyst_bud'],
        10079: ['medium_amethyst_bud'], 10080: ['small_amethyst_bud'],
        10081: ['trial_spawner:trial_spawner_state=' + s for s in
                ['active', 'waiting_for_reward_ejection', 'ejecting_reward', 'cooldown']]
               + ['vault:vault_state=' + s for s in ['active', 'unlocking', 'ejecting']],
    }
    for count in range(1, 5):
        result[10048 + count] = [name + f':lit=true:candles={count}'
                                for name in ['candle'] + [c + '_candle' for c in COLORS]]
        result[10052 + count] = [f'sea_pickle:waterlogged=true:pickles={count}']
        result[10056 + count] = [f'respawn_anchor:charges={count}']
    result[10049] += [name + ':lit=true' for name in ['candle_cake'] + [c + '_candle_cake' for c in COLORS]]
    for age, prefix in enumerate(['', 'exposed_', 'weathered_', 'oxidized_']):
        result[10068 + age] = [wax + prefix + 'copper_bulb:lit=true' for wax in ['', 'waxed_']]
        result[10072 + age] = [wax + prefix + 'copper_lantern' for wax in ['', 'waxed_']]
    for level in range(1, 16):
        result[10081 + level] = [f'light:level={level}']
    return {key: ['minecraft:' + token for token in value] for key, value in result.items()}


def run(write=False):
    path = ROOT / 'shaders/block.properties'
    groups = sources()
    replacement_names = {':'.join(token.split(':')[:2]) for group in groups.values() for token in group}
    with zipfile.ZipFile(CLIENT) as client:
        for group in groups.values():
            for token in group:
                parts = token.split(':')
                state = json.loads(client.read('assets/minecraft/blockstates/' + parts[1] + '.json'))
                filters = dict(value.split('=') for value in parts[2:])
                if filters:
                    if parts[1] in ['redstone_wire', 'light']:
                        # These light/color values do not select different block models.
                        property_name = 'power' if parts[1] == 'redstone_wire' else 'level'
                        assert set(filters) == {property_name} and 1 <= int(filters[property_name]) <= 15
                        continue
                    variants = [dict(item.split('=') for item in key.split(',') if item)
                                for key in state.get('variants', {})]
                    assert any(all(v.get(k) == value for k, value in filters.items()) for v in variants), token
    if write:
        lines = []
        for line in path.read_text().splitlines():
            if not line.startswith('block.'):
                lines.append(line)
                continue
            key, value = line.split('=', 1)
            if int(key.split('.')[1]) in groups or key == 'block.10028':
                continue
            tokens = [token for token in value.split() if ':'.join(token.split(':')[:2]) not in replacement_names]
            if tokens:
                lines.append(key + '=' + ' '.join(tokens))
        lines += ['block.' + str(key) + '=' + ' '.join(value) for key, value in sorted(groups.items())]
        path.write_text('\n'.join(lines) + '\n')
        full_blocks(CLIENT, write=True)
    properties = path.read_text()
    for key, value in groups.items():
        assert f'block.{key}=' + ' '.join(value) in properties.splitlines()
    print(json.dumps({'passed': True, 'new_source_groups': len(groups),
                      'state_selectors': sum(map(len, groups.values())),
                      'state_validation': 'model predicates validated; wire power and light levels checked against legal 1-15 ranges'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    run(parser.parse_args().write)
