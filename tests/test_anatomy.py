import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from companion.anatomy import DATA, Traits, compile_design, sketch
from companion.generator import Generator
from companion.recipe import make_recipe
from companion.server import Application

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT/'build/catalog.json').read_text())


class AnatomyTests(unittest.TestCase):
    def setUp(self):
        self.traits = Traits(CATALOG)
        self.recipe = make_recipe('00000002:32345678',80,94,{'25':100,'12':80},CATALOG,multiplier=1)

    def test_complete_catalog_and_form_mapping(self):
        self.assertEqual(len(self.traits.by_id),len(CATALOG))
        self.assertEqual(len({p['source_symbol'] for p in self.traits.by_id.values()}),386)
        for species,p in self.traits.by_id.items():
            self.assertGreaterEqual(len(p['features']),2)
            self.assertTrue(compile_design(make_recipe('test',30,int(species),{},CATALOG),self.traits)['description'])

    def test_gengar_has_integrated_traits_without_species_in_prompt(self):
        design=compile_design(self.recipe,self.traits)
        self.assertEqual(design['body_plan'],'biped')
        self.assertEqual([f['slot'] for f in design['features']],['face','wings','ears','markings'])
        self.assertEqual(len({f['region'] for f in design['features']}),4)
        self.assertIn('head merging directly into its torso',design['description'])
        self.assertIn('black tips',design['description'])
        for name in ('gengar','pikachu','butterfree','45%'):
            self.assertNotIn(name,design['prompt'].lower())
        self.assertNotIn('toothy grin',design['view_prompts']['back'])
        self.assertNotIn('cheek',design['view_prompts']['back'])
        self.assertIn('facing away',design['view_prompts']['back'])
        self.assertEqual(design,compile_design(self.recipe,self.traits))

    def test_competing_head_traits_and_low_mass_contributors(self):
        recipe=make_recipe('test',80,94,{'25':60,'26':40,'74':1},CATALOG,multiplier=1)
        d=compile_design(recipe,self.traits)
        self.assertEqual(sum(f['region']=='crown' for f in d['features']),1)
        self.assertIn('74',d['contributors'])
        self.assertNotIn('74',[f['species'] for f in d['features']])
        changed=copy.deepcopy(recipe)
        changed['shares']['25']-=.0005;changed['shares']['74']+=.0005
        e=compile_design(changed,self.traits)
        self.assertNotEqual(d['dimensions'],e['dimensions'])
        self.assertEqual(d['seed'],e['seed'])

    def test_preview_and_cache_do_not_read_donor_sprite_pixels(self):
        with tempfile.TemporaryDirectory() as temp:
            config=json.loads((ROOT/'config.example.json').read_text())
            config['cache']=temp;config['generator']['provider']='preview'
            gen=Generator(config,CATALOG)
            from companion.sprites import canonical
            with patch('companion.generator.canonical',wraps=canonical) as refs:
                key,path=gen.generate(self.recipe)
            self.assertTrue(refs.called)
            self.assertTrue(all(str(call.args[2])=='94' for call in refs.call_args_list))
            self.assertEqual(len(path.read_bytes()),4128)
            self.assertTrue((path.parent/'design.json').is_file())
            with patch('companion.generator.sketch',side_effect=AssertionError('cache missed')):
                self.assertEqual(gen.generate(self.recipe),(key,path))
            # Both edits and renderer options must invalidate previous artwork.
            data=Path(temp)/'traits.tsv'
            data.write_text(DATA.read_text().replace('mischievous toothy grin','mischievous broad grin'))
            config['traits']=str(data)
            self.assertNotEqual(key,Generator(config,CATALOG).key(self.recipe))

    def test_separate_view_commands_and_payload_publication(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            config=json.loads((ROOT/'config.example.json').read_text())
            config['cache']=temp
            executable=Path(temp)/'sd-cli.exe';executable.touch()
            model=Path(temp)/'model.safetensors';model.touch()
            config['generator'].update(executable=str(executable),model=str(model),view_mode='separate')
            calls=[]
            def run(args,**kwargs):
                calls.append(args)
                # Use a known valid fixture; this tests orchestration, not AI quality.
                Image.open(args[args.index('--init-img')+1]).save(args[args.index('-o')+1])
            gen=Generator(config,CATALOG)
            with patch('companion.generator.subprocess.run',side_effect=run):
                key,payload=gen.generate(self.recipe)
            self.assertEqual(len(calls),2)
            self.assertIn('front three-quarter',calls[0][calls[0].index('-p')+1])
            self.assertIn('facing away',calls[1][calls[1].index('-p')+1])
            self.assertIn('visible face',calls[1][calls[1].index('-n')+1])
            self.assertEqual(len(payload.read_bytes()),4128)
            self.assertTrue((payload.parent/'metadata.json').exists())
            config['generator']['strength']=.73
            gen=Generator(config,CATALOG)
            with patch('companion.generator.subprocess.run',side_effect=RuntimeError('GPU failed')):
                with self.assertRaises(RuntimeError):gen.generate(self.recipe)
            self.assertFalse((gen.cache/gen.key(self.recipe)/'sprite.bin').exists())

    def test_old_pending_keys_are_not_marked_ready_under_new_renderer(self):
        with tempfile.TemporaryDirectory() as temp:
            config=json.loads((ROOT/'config.example.json').read_text())
            config.update(database=str(Path(temp)/'history.db'),cache=str(Path(temp)/'sprites'))
            config['generator']['provider']='preview'
            app=Application(config)
            with app.history.db:
                app.history.db.execute('INSERT INTO jobs(key,campaign,head,identity,level,recipe) VALUES(?,?,?,?,?,?)',
                    ('old-key','c','0','i',80,json.dumps(self.recipe)))
                app.history.db.execute("INSERT INTO jobs(key,campaign,head,identity,level,recipe,status) VALUES(?,?,?,?,?,?,'failed')",
                    ('old-failed-key','c','0','i',80,json.dumps(self.recipe)))
            app.history.close()
            app=Application(config)
            self.assertEqual(app.status()['counts'],{'superseded':2})
            app.history.close()

    def test_reference_back_sees_front_and_cannot_replace_it(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            config=json.loads((ROOT/'config.example.json').read_text())
            config['cache']=temp
            executable=Path(temp)/'sd.exe';executable.touch()
            model=Path(temp)/'model.safetensors';model.touch()
            config['generator'].update(executable=str(executable),model=str(model),view_mode='reference')
            calls=[]
            def run(args,**kwargs):
                calls.append(args)
                init=Image.open(args[args.index('--init-img')+1]).convert('RGB')
                if len(calls)==1:
                    self.assertEqual(args[args.index('-W')+1],'1024')
                    reference=Image.open(Path(args[args.index('-o')+1]).parent/'base-front-reference.png')
                    self.assertEqual(init.crop((0,0,512,512)).tobytes(),reference.tobytes())
                    mask=Image.open(args[args.index('--mask')+1])
                    self.assertEqual(mask.crop((0,0,512,512)).getextrema(),(0,0))
                    self.assertEqual(mask.crop((512,0,1024,512)).getextrema(),(255,255))
                if len(calls)==2:
                    self.assertEqual(args[args.index('-W')+1],'1024')
                    mask=Image.open(args[args.index('--mask')+1])
                    self.assertEqual(mask.crop((0,0,512,512)).getextrema(),(0,0))
                    self.assertEqual(mask.crop((512,0,1024,512)).getextrema(),(255,255))
                    front=Image.open(Path(args[args.index('-o')+1]).parent/'generated-front.png')
                    self.assertEqual(init.crop((0,0,512,512)).tobytes(),front.tobytes())
                    # Even if the backend changes the reference half, the
                    # accepted front must remain the original first-pass art.
                    init.paste('red',(0,0,512,512))
                init.save(args[args.index('-o')+1])
            gen=Generator(config,CATALOG)
            with patch('companion.generator.subprocess.run',side_effect=run):
                _,payload=gen.generate(self.recipe)
            pair=Image.open(payload.parent/'generated.png')
            front=Image.open(payload.parent/'generated-front.png')
            self.assertEqual(pair.crop((0,0,512,512)).tobytes(),front.tobytes())
            self.assertEqual(len(payload.read_bytes()),4128)

    def test_export_rejects_partial_background_or_clipping(self):
        from PIL import Image,ImageDraw
        from companion.sprites import fit
        im=Image.new('RGBA',(128,128),'white')
        d=ImageDraw.Draw(im)
        d.rectangle((0,0,127,25),fill=(160,160,160,255))
        d.ellipse((40,50,90,110),fill=(20,90,150,255))
        with self.assertRaisesRegex(ValueError,'background|clipped'):
            fit(im)

    def test_renderer_upgrade_does_not_queue_old_level_events(self):
        from companion.history import ZERO,pack_event
        with tempfile.TemporaryDirectory() as temp:
            config=json.loads((ROOT/'config.example.json').read_text())
            config.update(database=str(Path(temp)/'history.db'),cache=str(Path(temp)/'sprites'))
            config['generator']['provider']='preview'
            app=Application(config)
            head=ZERO;campaign='0000000000000001'
            for i in range(1,4):
                event,_=app.history.append(campaign,pack_event(i,head,123,456,4,0,5+i,2))
                head=event['head']
            app.command(f'POLL {campaign} {head} - 000001c8,0000007b,4,8')
            self.assertEqual(app.status()['counts'],{})
            app.history.close()


if __name__=='__main__':unittest.main()
