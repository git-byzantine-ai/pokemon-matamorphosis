"""Free local generation, with a clearly labeled non-AI diagnostic provider."""
import json
import hashlib
import os
import subprocess
from pathlib import Path
from PIL import Image
from .recipe import digest, MIN_ART_EVS
from .sprites import fit, pixel_finish, encode_pair, encode_canonical, canonical, EXPORT_VERSION
from .anatomy import Traits, compile_design, sketch, NATIVE_BODIES, VERSION as ANATOMY_VERSION

GENERATOR_VERSION = 2


class Generator:
    def __init__(self, config, catalog):
        self.config = config
        self.catalog = catalog
        self.root = Path(config['source']).resolve()
        self.cache = Path(config['cache']).resolve()
        self.cache.mkdir(parents=True, exist_ok=True)
        self.settings = dict(config['generator'])
        self.settings.setdefault('conditioning', 'sketch')
        self.settings.setdefault('view_mode', 'reference')
        self.traits = Traits(catalog, config.get('traits', Path(__file__).with_name('data')/'traits.tsv'))

    def key(self, recipe):
        if sum(recipe.get('ev_totals',[])) < MIN_ART_EVS:
            return digest({'canonical':recipe['species'],'identity':recipe['identity'],'shiny':recipe.get('shiny',False),
                           'references':[hashlib.sha256(canonical(self.root,self.catalog,recipe['species'],v,recipe.get('shiny',False)).tobytes()).hexdigest() for v in ('front','back')]})
        reference = self.base_reference(recipe,'front')
        return digest({'recipe': recipe, 'generator': self.settings, 'export_version': EXPORT_VERSION,
                       'generator_version':GENERATOR_VERSION,
                       'base_reference_digest':hashlib.sha256(reference.tobytes()).hexdigest(),
                       'design': compile_design(recipe, self.traits),
                       'anatomy_version': ANATOMY_VERSION, 'traits_digest': self.traits.digest})

    def base_reference(self,recipe,view):
        sprite=canonical(self.root,self.catalog,recipe['species'],view,recipe.get('shiny',False))
        box=sprite.getchannel('A').getbbox()
        if box is None:raise ValueError('base species reference is empty')
        sprite=sprite.crop(box)
        scale=min(352/sprite.width,352/sprite.height)
        sprite=sprite.resize((round(sprite.width*scale),round(sprite.height*scale)),Image.Resampling.NEAREST)
        canvas=Image.new('RGB',(512,512),'white')
        canvas.paste(sprite,((512-sprite.width)//2,432-sprite.height),sprite)
        return canvas

    def generate(self, recipe):
        key = self.key(recipe)
        folder = self.cache / key
        folder.mkdir(exist_ok=True)
        payload = folder / 'sprite.bin'
        if payload.exists():
            return key, payload
        recipe_path = folder / 'recipe.json'
        recipe_path.write_text(json.dumps(recipe, indent=2))
        if sum(recipe['ev_totals']) < MIN_ART_EVS:
            binary,previews=encode_canonical(*(canonical(self.root,self.catalog,recipe['species'],v,recipe.get('shiny',False)) for v in ('front','back')))
            for name,im in zip(('front','back'),previews):im.save(folder/f'{name}.png')
            (folder/'metadata.json').write_text(json.dumps({'key':key,'provider':'canonical','ai_generated':False,'threshold':MIN_ART_EVS}))
            temporary=folder/'sprite.tmp';temporary.write_bytes(binary);os.replace(temporary,payload)
            return key,payload
        design = compile_design(recipe, self.traits)
        (folder/'design.json').write_text(json.dumps(design, indent=2))
        sheet = sketch(design)
        self.base_reference(recipe,'front').save(folder/'base-front-reference.png')
        if self.traits[design['anchor']]['symbol'] in NATIVE_BODIES:
            # Canonical guides represent native multi-headed/multi-armed forms
            # more faithfully than the generic geometric block-in.
            sheet.paste(self.base_reference(recipe,'front'),(0,0))
            sheet.paste(self.base_reference(recipe,'back'),(512,0))
        sheet.save(folder / 'anatomy-sketch.png')
        conditioning = self.settings['conditioning']
        if conditioning not in ('text', 'sketch'):
            raise ValueError('conditioning must be text or sketch')
        # Legacy non-reference modes use text for complex native forms. The
        # default reference mode always supplies the canonical guides above.
        if self.traits[design['anchor']]['symbol'] in NATIVE_BODIES:
            conditioning = 'text'
        provider = self.settings['provider']
        if provider == 'local-sd':
            executable = Path(self.settings['executable']).resolve()
            model = Path(self.settings['model']).resolve()
            if not executable.is_file() or not model.is_file():
                raise RuntimeError('local AI model is not installed; run scripts/setup-local-ai.ps1')
            mode = self.settings['view_mode']
            if mode not in ('separate','paired','reference'):
                raise ValueError('view_mode must be separate, reference, or paired')
            views = ('pair',) if mode=='paired' else ('front','back')
            prompts, logs, generated = [], [], []
            for index, view in enumerate(views):
                reference_back = mode=='reference' and view=='back'
                reference_front = mode=='reference' and view=='front'
                prompt = design['prompt'] if mode=='paired' else design['view_prompts'][view]
                negative = design['negative_prompt']
                if view=='back' and not reference_back:
                    negative += ', front view, visible face, visible eyes, visible mouth, looking at viewer'
                output = folder/f'generated-{view}.png'
                init = folder/f'sketch-{view}.png'
                wide = mode=='paired' or reference_back or reference_front
                if reference_back or reference_front:
                    # Keep the base / accepted front visible to the pass that
                    # draws the new front / rear. Only the right half is editable.
                    # This is contextual inpainting, not an identity adapter.
                    reference = Image.new('RGB',(1024,512),'white')
                    reference.paste(generated[0] if reference_back else self.base_reference(recipe,'front'),(0,0))
                    reference.paste(sheet.crop((index*512,0,index*512+512,512)),(512,0))
                    reference.save(init)
                    mask = Image.new('L',(1024,512),0)
                    mask.paste(255,(512,0,1024,512))
                    mask.save(folder/f'{view}-mask.png')
                    prompt = (('Two views of the same creature. Left: existing front reference. '
                              'Right: rear view, facing away, back of head, no face visible. '
                              'Match the reference body shape, ears, proportions, colors and art style. '
                              + design['view_prompts']['back']) if reference_back else
                              ('Left: original creature reference. Right: new FRONT view of that creature, '
                               'naturally integrating the following inherited features. Preserve the reference identity '
                               'and pixel-art style while integrating the anatomy. '+design['view_prompts']['front']))
                else:
                    (sheet if mode=='paired' else sheet.crop((index*512,0,index*512+512,512))).save(init)
                prompts.append(view.upper()+'\n'+prompt+'\nNEGATIVE: '+negative)
                (folder/f'prompt-{view}.txt').write_text(prompt+'\nNEGATIVE: '+negative)
                args = [str(executable), '-m', str(model), '-p', prompt, '-n', negative,
                        '-W', '1024' if wide else '512', '-H', '512',
                        '--steps', str(self.settings.get('steps', 28)), '--seed', str(design['seed']),
                        '--cfg-scale', '6', '--sampling-method', 'euler_a', '-o', str(output),
                        '--vae-tiling', '--backend', self.settings.get('backend', 'te=cpu,diffusion=Vulkan1,vae=Vulkan1'), '--type', 'f16']
                if conditioning == 'sketch' or reference_back or reference_front:
                    strength = self.settings.get('back_strength',.55) if view=='back' else self.settings.get('strength',.72)
                    args += ['--init-img', str(init), '--strength', str(strength)]
                if reference_back or reference_front:
                    args += ['--mask', str(folder/f'{view}-mask.png')]
                log_path = folder/f'generation-{view}.log'
                with log_path.open('w') as log:
                    subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, check=True,
                                   timeout=self.settings.get('timeout_seconds', 600),
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                logs.append(log_path.read_text(errors='replace'))
                rendered = Image.open(output).convert('RGB')
                if reference_back or reference_front:
                    rendered.save(folder/f'generated-{view}-context.png')
                    rendered = rendered.crop((512,0,1024,512))
                    rendered.save(output)
                generated.append(rendered)
            output = folder/'generated.png'
            if mode!='paired':
                paired = Image.new('RGB',(1024,512),'white')
                for i,im in enumerate(generated):paired.paste(im,(512*i,0))
                paired.save(output)
            else:
                generated[0].save(output)
            (folder/'prompt.txt').write_text('\n\n'.join(prompts))
            (folder/'generation.log').write_text('\n\n'.join(logs))
            image = Image.open(output).convert('RGBA')
            if image.width < 128 or image.height < 64:
                raise ValueError('generated sheet is too small')
            middle = image.width // 2
            front = fit(image.crop((0, 0, middle, image.height)))
            back = fit(image.crop((middle, 0, image.width, image.height)))
        elif provider == 'preview':
            front = fit(sheet.crop((0,0,512,512)))
            back = fit(sheet.crop((512,0,1024,512)))
        else:
            raise ValueError(f'unknown provider: {provider}')
        binary, previews = encode_pair(pixel_finish(front), pixel_finish(back))
        for name, image in zip(('front', 'back'), previews):
            image.save(folder / f'{name}.png')
        temporary = folder / 'sprite.tmp'
        temporary.write_bytes(binary)
        (folder / 'metadata.json').write_text(json.dumps({'key': key, 'provider': provider,
            'ai_generated': provider == 'local-sd', 'settings': self.settings,
            'conditioning': conditioning, 'anatomy_version': ANATOMY_VERSION,
            'effective_view_mode': mode if provider=='local-sd' else 'preview',
            'export_version': EXPORT_VERSION,
            'traits_digest': self.traits.digest}, indent=2))
        os.replace(temporary, payload)
        return key, payload
