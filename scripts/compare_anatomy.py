"""Run an honest text-vs-sketch comparison using the same anatomical recipe."""
import copy
import argparse
import json
import time
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from companion.generator import Generator
from companion.recipe import make_recipe

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model')
    parser.add_argument('--output',default='build/anatomy-comparison')
    parser.add_argument('--modes',nargs='+',default=['sketch','text'],choices=['sketch','text'])
    args=parser.parse_args()
    config=json.loads(Path('config.example.json').read_text())
    if args.model:
        config['generator'].update(model=args.model,model_revision='228d79cb20811466f5c5710aa91f05dabd0b8a14')
    catalog=json.loads(Path(config['catalog']).read_text())
    recipe=make_recipe('00000002:32345678',80,94,{'25':100,'12':80},catalog,multiplier=1)
    root=Path(args.output);root.mkdir(exist_ok=True)
    records=[]
    for mode in args.modes:
        settings=copy.deepcopy(config);settings['generator']['conditioning']=mode
        generator=Generator(settings,catalog)
        start=time.perf_counter()
        print('Generating',mode,flush=True)
        try:
            key,payload=generator.generate(recipe)
            records.append({'mode':mode,'key':key,'seconds':time.perf_counter()-start,'folder':str(payload.parent)})
        except Exception as exc:
            key=generator.key(recipe)
            records.append({'mode':mode,'key':key,'folder':str(generator.cache/key),'error':str(exc)})
        (root/'results.json').write_text(json.dumps(records,indent=2))
        print(records[-1],flush=True)
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',23)
    sheet=Image.new('RGB',(1120,720),'#20333d');d=ImageDraw.Draw(sheet)
    for row,r in enumerate(records):
        y=row*360
        d.text((20,y+10),r['mode']+' conditioning / actual AI result',font=font,fill='white')
        folder=Path(r['folder'])
        if not (folder/'generated.png').exists():continue
        raw=Image.open(folder/'generated.png').convert('RGB');raw.thumbnail((620,310))
        sheet.paste(raw,(10,y+45))
        if 'error' in r:
            d.text((646,y+85),'Rejected export',font=font,fill='#ffaaaa')
            continue
        for column,view in enumerate(('front','back')):
            im=Image.open(folder/f'{view}.png').convert('RGBA').resize((224,224),Image.Resampling.NEAREST)
            sheet.paste(im,(646+column*230,y+85),im)
    sheet.save(root/'comparison.png')

if __name__=='__main__':main()
