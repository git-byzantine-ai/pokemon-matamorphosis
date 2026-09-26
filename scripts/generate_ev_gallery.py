"""Five real gameplay-pipeline examples, including canonical references."""
import json
import time
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from companion.generator import Generator
from companion.recipe import make_recipe
from companion.sprites import canonical

def main():
    config=json.loads(Path('config.example.json').read_text())
    catalog=json.loads(Path(config['catalog']).read_text());gen=Generator(config,catalog)
    out=Path('build/ev-gallery');out.mkdir(parents=True,exist_ok=True)
    examples=[(1,10,{'16':2,'19':3}),(4,22,{'16':60,'43':40}),
              (7,35,{'74':90,'41':60,'43':30}),(25,50,{'12':70,'27':80,'58':50}),
              (94,80,{'25':120,'12':85,'74':15})]
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',19)
    title=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',25)
    sheet=Image.new('RGB',(1080,1790),'#152830');d=ImageDraw.Draw(sheet)
    d.text((28,15),'Metamorphosis: 5 to 510 EVs',font=title,fill='white')
    d.text((28,51),'64 x 64 exports at 3x. Below 100 EVs: original sprite. At 100+: local DreamShaper 8.',font=font,fill='#b9ced3')
    records=[]
    for index,(species,level,counts) in enumerate(examples):
        recipe=make_recipe(f'ee000003:{0x99887700+index:08x}',level,species,counts,catalog,multiplier=1)
        started=time.time();print(f'Generating {catalog[str(species)]["name"]}: {sum(recipe["ev_totals"])} EVs',flush=True)
        key,payload=gen.generate(recipe);folder=payload.parent
        record={'key':key,'recipe':recipe,'seconds':round(time.time()-started,2),'folder':str(folder)}
        records.append(record);(out/'recipes.json').write_text(json.dumps(records,indent=2))
        y=95+index*336;d.rectangle((16,y,1064,y+321),fill='#25414b')
        appearance='Original sprite' if sum(recipe['ev_totals'])<100 else f'Base {recipe["lineage_mass"]:.1%}'
        d.text((30,y+10),f'{catalog[str(species)]["name"].title()} | {sum(recipe["ev_totals"])} EVs | {appearance}',font=title,fill='white')
        donors=', '.join(f'{n} {catalog[k]["name"].title()}' for k,n in counts.items())
        d.text((30,y+47),donors,font=font,fill='#b5e6ce')
        for col,(label,im) in enumerate((('BASE',canonical(gen.root,catalog,species,'front')),('NEW FRONT',Image.open(folder/'front.png')),('NEW BACK',Image.open(folder/'back.png')))):
            x=60+col*345
            d.text((x,y+79),label,font=font,fill='#d6e4e7')
            sprite=im.convert('RGBA').resize((192,192),Image.Resampling.NEAREST)
            sheet.paste(sprite,(x,y+108),sprite)
        sheet.crop((16,y,1064,y+321)).save(out/f'example-{index+1}.png')
        sheet.save(out/'gallery.png');print(f'Finished {key[:12]} in {record["seconds"]}s',flush=True)
    (out/'README.md').write_text('# EV metamorphosis gallery\n\nFive examples: original sprites below 100 EVs, four real local Stable Diffusion pairs at 100, 180, 340 and 510 EVs. Columns: canonical base / current front / current back.\n\n![Gallery](gallery.png)\n\n[Recipes, times and cache paths](recipes.json). Each cache directory retains the exact front/back prompts and raw AI images.\n',encoding='utf-8')
    print(out/'gallery.png',flush=True)

if __name__=='__main__':main()
