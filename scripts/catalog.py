"""Export species IDs, graphic paths and unconditional level evolutions."""
import json
import re
from pathlib import Path


def export(source, destination):
    source, destination = Path(source), Path(destination)
    ids = dict(re.findall(r'^#define SPECIES_(\w+)\s+(\d+)\s*$', (source / 'include/constants/species.h').read_text(), re.M))
    graphics = dict(re.findall(r'gMonFrontPic_(\w+)\[\].*?"graphics/pokemon/([^";]+)/front\.4bpp', (source / 'src/data/graphics/pokemon.h').read_text()))
    mappings = re.findall(r'SPECIES_SPRITE\((\w+), gMonFrontPic_(\w+)\)', (source / 'src/data/pokemon_graphics/front_pic_table.h').read_text())
    catalog = {}
    for symbol, graphic in mappings:
        if symbol in ids and graphic in graphics and symbol not in ('NONE', 'EGG'):
            catalog[ids[symbol]] = {'name': graphic, 'symbol': symbol, 'path': graphics[graphic]}
    evolution_text = (source / 'src/data/pokemon/evolution.h').read_text()
    for origin, level, target in re.findall(r'\[SPECIES_(\w+)\]\s*=\s*\{\{EVO_LEVEL,\s*(\d+),\s*SPECIES_(\w+)\}\}', evolution_text):
        if ids.get(origin) in catalog and ids.get(target) in catalog:
            catalog[ids[origin]]['evolution'] = {'level': int(level), 'target': int(ids[target])}
            catalog[ids[target]]['evolved_at'] = int(level)
    stats = (source / 'src/data/pokemon/species_info.h').read_text()
    fields = ('HP','Attack','Defense','Speed','SpAttack','SpDefense')
    yields = {}
    for symbol,body in re.findall(r'\[SPECIES_(\w+)\]\s*=\s*\n    \{(.*?)\n    \}',stats,re.S):
        values = dict(re.findall(r'\.evYield_(\w+)\s*=\s*(\d+)',body))
        if values:
            yields[symbol] = [int(values.get(field,0)) for field in fields]
    for entry in catalog.values():
        symbol = entry['symbol']
        entry['ev_yield'] = yields.get(symbol, [2]*6 if symbol.startswith('OLD_UNOWN') else None)
        if entry['ev_yield'] is None:
            raise ValueError(f'Missing EV yield for {symbol}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(catalog, indent=2) + '\n')
    return catalog


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(f'Exported {len(export(args.source, args.destination))} species')
