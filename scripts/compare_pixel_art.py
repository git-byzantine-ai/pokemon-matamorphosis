"""Compare the same source art's export and a fresh pixel-prompt generation."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from companion.sprites import fit, pixel_finish, encode_pair


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--before', default='build/anatomy-final')
    parser.add_argument('--after', default='build/pixel-art-final')
    parser.add_argument('--output', default='build/pixel-art-comparison')
    args = parser.parse_args()
    before = json.loads((Path(args.before)/'recipes.json').read_text())
    after = json.loads((Path(args.after)/'recipes.json').read_text())
    destination = Path(args.output)
    destination.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 19)
    small = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 16)
    title = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 26)
    sheet = Image.new('RGB', (1240, 950), '#14232b')
    draw = ImageDraw.Draw(sheet)
    draw.text((24,16), 'Creature design retained; pixel rendering compared', font=title, fill='white')
    for x,label in zip((24,432,840), ('Previous export', 'Same AI image + pixel finishing', 'Pixel-art prompt + pixel finishing')):
        draw.text((x,62), label, font=font, fill='#b3c9ce')
    records = []
    for row,(old,new) in enumerate(zip(before,after)):
        assert old['recipe'] == new['recipe']
        old_folder = Path(old['asset_directory'])
        new_folder = Path(new['asset_directory'])
        raw = Image.open(old_folder/'generated.png').convert('RGBA')
        middle = raw.width//2
        fitted = [pixel_finish(fit(raw.crop(box))) for box in
                  ((0,0,middle,raw.height),(middle,0,raw.width,raw.height))]
        payload, refinished = encode_pair(*fitted)
        (destination/f'level-{old["recipe"]["level"]}-refinished.bin').write_bytes(payload)
        groups = [[Image.open(old_folder/f'{view}.png').convert('RGBA') for view in ('front','back')],
                  refinished,
                  [Image.open(new_folder/f'{view}.png').convert('RGBA') for view in ('front','back')]]
        y = 105+row*278
        draw.text((24,y), f'{old["name"]} / level {old["recipe"]["level"]}',font=font,fill='white')
        for col,group in enumerate(groups):
            for v,sprite in enumerate(group):
                scaled = sprite.resize((192,192),Image.Resampling.NEAREST)
                sheet.paste(scaled,(24+col*408+v*194,y+40),scaled)
                draw.text((70+col*408+v*194,y+233),('FRONT','BACK')[v],font=small,fill='#b3c9ce')
        records.append({'old_key':old['key'],'new_key':new['key'],'recipe':old['recipe'],
                        'middle_column':'Deterministic re-export of old raw AI output; no new generation.'})
    sheet.save(destination/'comparison.png')
    # A compact, light-background comparison makes the native pixel contours
    # readable without the dark dashboard background concealing them.
    compact = Image.new('RGB',(1080,760),'#eef0df')
    cd = ImageDraw.Draw(compact)
    cd.text((24,16),'Previous export',font=title,fill='#243337')
    cd.text((564,16),'Pixel-art rendering',font=title,fill='#243337')
    for row,(old,new) in enumerate(zip(before[-2:],after[-2:])):
        y = 70+row*338
        cd.text((24,y),f'{old["name"]} / level {old["recipe"]["level"]}',font=font,fill='#243337')
        for column,record in enumerate((old,new)):
            for view_index,view in enumerate(('front','back')):
                sprite = Image.open(Path(record['asset_directory'])/f'{view}.png').convert('RGBA')
                sprite = sprite.resize((256,256),Image.Resampling.NEAREST)
                compact.paste(sprite,(column*540+12+view_index*256,y+32),sprite)
                cd.text((column*540+100+view_index*256,y+293),view.upper(),font=small,fill='#536568')
    compact.save(destination/'before-after.png')
    (destination/'provenance.json').write_text(json.dumps(records,indent=2))
    print(destination/'comparison.png')


if __name__ == '__main__':
    main()
