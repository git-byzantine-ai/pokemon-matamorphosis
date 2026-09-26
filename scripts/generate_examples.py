"""Generate the two requested compositions using the configured real AI backend."""
import json
from pathlib import Path
from PIL import Image, ImageDraw
from companion.generator import Generator
from companion.recipe import make_recipe

config = json.loads(Path('config.example.json').read_text())
catalog = json.loads(Path(config['catalog']).read_text())
generator = Generator(config, catalog)
examples = [(6, 4, {'16': 3}), (80, 6, {'16': 255, '74': 255})]
sheet = Image.new('RGB', (700, 400), '#18262d')
draw = ImageDraw.Draw(sheet)
records = []
for index, (level, species, counts) in enumerate(examples):
    recipe = make_recipe('00000001:12345678', level, species, counts, catalog,multiplier=1)
    key, payload = generator.generate(recipe)
    folder = payload.parent
    records.append({'key':key, 'recipe':recipe})
    x = 20 + index * 350
    draw.text((x, 20), f'LEVEL {level} / AI-GENERATED', fill='white')
    label = '3 Pidgey essence' if level == 6 else '255 Pidgey + 255 Geodude essence'
    draw.text((x, 42), label, fill='#9bdac2')
    for v, name in enumerate(('front', 'back')):
        sprite = Image.open(folder / (name + '.png')).convert('RGBA').resize((256,256),Image.Resampling.NEAREST)
        # Show the front large and back smaller without smoothing the pixels.
        if v == 1:
            sprite = sprite.resize((96,96),Image.Resampling.NEAREST)
        sheet.paste(sprite, (x + (225 if v else 0), 240 if v else 85), sprite)
    draw.text((x, 355), f"Lineage: {recipe['lineage_mass']:.1%}", fill='white')
sheet.save('build/ai-examples.png')
Path('build/ai-examples.json').write_text(json.dumps(records, indent=2))
print('build/ai-examples.png')
