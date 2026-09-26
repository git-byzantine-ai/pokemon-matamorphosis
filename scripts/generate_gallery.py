"""Generate representative examples with the current gameplay AI pipeline.

Run from the project root: python -m scripts.generate_gallery
Original guides, prompts, raw AI outputs, and exported sprites stay in the cache.
"""
import json
import argparse
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from companion.generator import Generator
from companion.recipe import make_recipe


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='build/anatomy-gallery')
    args=parser.parse_args()
    config = json.loads(Path('config.example.json').read_text())
    catalog = json.loads(Path(config['catalog']).read_text())
    generator = Generator(config, catalog)
    destination = Path(args.output)
    destination.mkdir(parents=True, exist_ok=True)
    examples = [
        ('Bulbasaur line', 14, 1, {'10': 10, '43': 5}, '00000002:12345678'),
        ('Squirtle line', 34, 8, {'74': 80, '41': 40}, '00000002:22345678'),
        ('Gengar', 80, 94, {'25': 100, '12': 80}, '00000002:32345678'),
    ]
    font_path = Path('C:/Windows/Fonts/segoeui.ttf')
    font = ImageFont.truetype(str(font_path), 19) if font_path.exists() else ImageFont.load_default()
    title_font = ImageFont.truetype(str(font_path), 27) if font_path.exists() else font
    small = ImageFont.truetype(str(font_path), 16) if font_path.exists() else font
    sheet = Image.new('RGB', (1000, 1160), '#14232b')
    draw = ImageDraw.Draw(sheet)
    draw.text((28, 18), 'Metamorphosis from anatomical traits', font=title_font, fill='white')
    draw.text((28, 57), 'Actual game exports: 64 x 64 pixels, 15 colors + transparency; enlarged without smoothing.', font=small, fill='#b3c9ce')
    records = []
    for index, (name, level, species, counts, identity) in enumerate(examples):
        recipe = make_recipe(identity, level, species, counts, catalog,multiplier=1)
        print(f'Generating {name}, level {level}', flush=True)
        start = time.perf_counter()
        key, payload = generator.generate(recipe)
        elapsed = time.perf_counter() - start
        folder = payload.parent
        (destination/f'level-{level}-raw.png').write_bytes((folder/'generated.png').read_bytes())
        record = {'name': name, 'key': key, 'elapsed_seconds': elapsed, 'recipe': recipe,
                  'prompt': (folder/'prompt.txt').read_text(), 'asset_directory': str(folder),
                  'design': json.loads((folder/'design.json').read_text())}
        records.append(record)
        (destination/'recipes.json').write_text(json.dumps(records, indent=2))
        y = 100 + index * 350
        draw.rounded_rectangle((16, y, 984, y+334), radius=12, fill='#233842')
        draw.text((34, y+14), f'{name} | Level {level}', font=title_font, fill='white')
        donors = ', '.join(f'{n:,} {catalog[k]["name"].title()}' for k,n in counts.items())
        draw.text((34, y+53), 'Essence spent: ' + donors, font=font, fill='#9bdac2')
        draw.text((34, y+93), 'RECIPE INFLUENCE', font=small, fill='#b3c9ce')
        for row, (k, weight) in enumerate(sorted(recipe['shares'].items(), key=lambda x: -x[1])):
            draw.text((34, y+123+row*29), f'{catalog[k]["name"].title():<14} {weight:5.1%}', font=font, fill='white')
        draw.text((470, y+55), 'FRONT', font=small, fill='#b3c9ce')
        draw.text((740, y+55), 'BACK', font=small, fill='#b3c9ce')
        pair = Image.new('RGB', (512,256), '#233842')
        for v, view in enumerate(('front','back')):
            sprite = Image.open(folder/f'{view}.png').convert('RGBA').resize((256,256), Image.Resampling.NEAREST)
            pair.paste(sprite,(v*256,0),sprite)
            sheet.paste(sprite,(445+v*265,y+74),sprite)
        pair.save(destination/f'level-{level}-pair.png')
        print(f'Finished {key} in {elapsed:.1f}s', flush=True)
        sheet.save(destination/'gallery.png')
    notes = ['# Additional Stable Diffusion examples', '',
             'The gallery shows final GBA exports. The raw sheets below precede background removal, resizing, and palette reduction.', '',
             '[Exact recipes, prompts, generation times, and cache directories](recipes.json)', '']
    for record in records:
        level = record['recipe']['level']
        notes.extend([f'## {record["name"]}, level {level}', '',
                      record['design']['description'], '',
                      f'![Raw Stable Diffusion output](level-{level}-raw.png)', '',
                      f'Prompt: {record["prompt"]}', ''])
    (destination/'README.md').write_text('\n'.join(notes))
    print(str(destination/'gallery.png'), flush=True)


if __name__ == '__main__':
    main()
