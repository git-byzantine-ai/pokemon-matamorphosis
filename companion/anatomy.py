"""Compile numerical ancestry into one anatomical design, never a pixel collage.

Species names and ancestry percentages are deliberately absent from image prompts.
The editable vocabulary is an artistic description, not a biological taxonomy.
"""
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw

VERSION = 10
DATA = Path(__file__).with_name('data') / 'traits.tsv'
FORMS = {
    'biped': ('a compact upright creature with one head, two arms and two legs', .64, 1.),
    'quadruped': ('a low four-legged creature with one head and a continuous torso', 1., .65),
    'bird': ('a feathered creature with one head, two wings and two legs', .64, .9),
    'winged': ('a flying creature with one head, paired wings and two small feet', .6, .85),
    'insect': ('a compact insect creature with one head and a segmented abdomen', .5, .9),
    'crawler': ('a low segmented creature with one head and short paired legs', 1., .5),
    'cocoon': ('one tapered oval cocoon with a small recessed face', .55, .9),
    'serpent': ('one long curved serpentine body with a single head', .35, 1.2),
    'fish': ('one streamlined fish with a single head, paired fins and a tail fin', .9, .6),
    'aquatic': ('one rounded aquatic creature with paired flippers and a tapering tail', .9, .65),
    'plant': ('one compact plant creature with a rounded trunk and rooted feet', .65, .8),
    'burrower': ('one rounded upright burrowing body emerging from the ground', .6, .8),
    'amorphous': ('one cohesive soft-bodied creature with a single face', .95, .7),
    'shell': ('one compact creature enclosed in a continuous rounded shell', .85, .75),
    'star': ('one radial creature with a central body and tapered connected arms', .9, .9),
    'round': ('one rounded creature with a single face and short limbs', .9, .8),
    'floating': ('one compact hovering creature with a single central face', .75, .8),
}
COLORS = {
    'blue green': (65,160,135), 'orange': (235,139,55), 'red orange': (204,76,42),
    'light blue': (116,187,215), 'blue': (68,133,188), 'green': (106,170,79),
    'purple': (136,92,159), 'tan': (181,143,100), 'yellow': (240,203,65),
    'brown': (140,104,74), 'red': (208,79,71), 'ochre': (205,169,70),
    'pink': (228,145,169), 'rust red': (181,92,62), 'cream': (231,217,172),
    'lavender': (174,155,194), 'gold': (209,166,57), 'gray blue': (119,148,165),
    'gray': (143,145,149), 'white': (227,226,220), 'silver': (170,181,187),
    'gray purple': (151,139,160), 'dark teal': (66,113,119), 'ice blue': (128,196,220),
    'pale green': (165,207,138), 'yellow green': (172,189,91), 'pale yellow': (239,222,125),
    'pale blue': (157,196,214), 'black': (66,61,76), 'teal': (68,145,155),
    'blue gray': (118,148,164), 'pale gray': (193,198,203),
}
# Competing features share an attachment region. No two species' complete
# heads, bodies, or faces are ever placed next to or on top of each other.
REGIONS = {'ears': 'crown', 'head': 'crown', 'face': 'expression', 'eyes': 'expression',
           'wings': 'back', 'back': 'back', 'neck': 'neck', 'skin': 'surface',
           'markings': 'markings', 'belly': 'belly', 'tail': 'tail',
           'hands': 'forelimbs', 'limbs': 'forelimbs', 'feet': 'feet', 'fins': 'back'}
NATIVE_BODIES = {
    'MACHAMP': 'one muscular upright creature with one head, four arms and two legs',
    'GRAVELER': 'one rounded rocky creature with one head, four arms and two legs',
    'DODUO': 'one running bird body with two long necks and two heads',
    'DODRIO': 'one running bird body with three long necks and three heads',
    'DUGTRIO': 'three connected rounded burrowing heads emerging from a shared base',
    'MAGNETON': 'three connected spherical metal lobes forming one hovering creature',
    'WEEZING': 'one hovering creature with two connected unequal round head lobes',
    'EXEGGCUTE': 'six small egg-shaped lobes grouped as one compact creature',
    'EXEGGUTOR': 'one palm-shaped trunk with three small faces beneath its leaf crown',
}


class Traits:
    def __init__(self, catalog, path=DATA):
        raw = Path(path).read_text(encoding='utf-8')
        self.digest = hashlib.sha256(raw.encode()).hexdigest()
        profiles = {}
        for line in raw.splitlines():
            if not line or line.startswith('#'):
                continue
            parts = line.split('|')
            if len(parts) not in (4,5):
                raise ValueError('A trait row must have four fields and an optional body description')
            symbol, form, color, features = parts[:4]
            if symbol in profiles or form not in FORMS or color not in COLORS:
                raise ValueError(f'Invalid or duplicate trait profile: {symbol}')
            parsed = []
            for feature in features.split(';'):
                slot, text = (s.strip() for s in feature.split(':', 1))
                if slot not in REGIONS or not text:
                    raise ValueError(f'Invalid trait slot: {symbol}/{slot}')
                parsed.append({'slot': slot, 'description': text})
            profiles[symbol] = {'symbol': symbol, 'form': form, 'color': color, 'features': parsed,
                                'body': parts[4] if len(parts)==5 else None}
        self.by_id = {}
        for species, entry in catalog.items():
            symbol = entry['symbol']
            source = 'UNOWN' if symbol.startswith('OLD_UNOWN_') or symbol.startswith('UNOWN_') else symbol
            if source not in profiles:
                raise ValueError(f'Missing anatomical traits: {symbol}')
            self.by_id[str(species)] = {**profiles[source], 'name': entry['name'], 'source_symbol': source}

    def __getitem__(self, species):
        return self.by_id[str(species)]


def compile_design(recipe, traits):
    shares = {k: v for k, v in recipe['shares'].items() if v > 0}
    anchor = max(recipe['lineage'], key=lambda k: (recipe['lineage'][k], -int(k)))
    profile = traits[anchor]
    # Every contributor affects continuous geometry and palette, even when it
    # is too small to justify one of the four visible signature features.
    rgb = tuple(round(sum(COLORS[traits[k]['color']][i]*w for k,w in shares.items())) for i in range(3))
    dims = [sum(FORMS[traits[k]['form']][i+1]*w for k,w in shares.items()) for i in range(2)]
    candidates = []
    for species, share in shares.items():
        for rank, feature in enumerate(traits[species]['features']):
            candidates.append({**feature, 'species': species, 'share': share,
                               'score': share/(1+rank*.8), 'region': REGIONS[feature['slot']]})
    # Reserve one recognizable lineage feature, independently of donor rank.
    first = next(f for f in candidates if f['species']==anchor)
    selected = [first]
    regions = {first['region']}
    ranked = sorted(candidates, key=lambda f: (-f['score'], int(f['species']), f['slot']))
    def eligible(feature):
        if feature['region'] in regions or feature['share'] < .025:
            return False
        if 'eyeless' in feature['description'] and feature['share'] < .5:
            return False
        if feature['slot'] in ('hands','limbs','feet') and profile['form'] in ('fish','serpent','cocoon','shell'):
            return False
        return True
    def choose(feature):
        selected.append(feature)
        regions.add(feature['region'])
    # Give each substantial donor a chance before filling spare slots with
    # second or third traits from the strongest species.
    donors = sorted((k for k in shares if k not in recipe['lineage'] and shares[k]>=.1),
                    key=lambda k:(-shares[k],int(k)))[:3]
    for donor in donors:
        feature = next((f for f in ranked if f['species']==donor and eligible(f)),None)
        if feature: choose(feature)
    for feature in ranked:
        if len(selected)>=4: break
        if eligible(feature): choose(feature)
    for feature in selected:
        x = max(0., min(1., feature['share']/.5))
        feature['prominence'] = x*x*(3-2*x)
        feature['extent'] = 'subtle' if x < .25 else 'moderate' if x < .6 else 'prominent'
    dominant = max(shares, key=lambda k: (shares[k], -int(k)))
    accent = profile['color']
    primary = traits[dominant]['color']
    body = NATIVE_BODIES.get(profile['symbol'], profile['body'] or FORMS[profile['form']][0])
    features = '; '.join(f"{f['description']} with {f['extent']} emphasis" for f in selected)
    palette = f'{primary} body' if primary==accent else f'{primary} body with coordinated {accent} undersides'
    # Specify composition first, then anatomy, then style. Never ask the model
    # to draw named donors or to interpret numerical ancestry percentages.
    description = f'{body}; {features}; {palette}'
    prompt = ('character turnaround sheet, two full body views of the same fantasy monster, '
              'front view on the left, back view on the right. '
              f'{description}. '
              'Pixel art game creature, naturally attached anatomy, simple clean silhouette, crisp outline, flat colors, '
              'plain white background, separated views, entire body visible.')
    negative = ('collage, patchwork, overlapping creatures, creature inside creature, duplicate faces, '
                'extra heads, extra limbs, detached parts, human, person, clothing, costume, '
                '3d render, plastic, glossy, human anatomy, buttocks, human butt, text, letters, watermark, scenery, blurry, cropped, '
                'digital painting, vector illustration, smooth gradients, airbrush, antialiasing, dithering, ground shadow')
    if not any(word in description for word in ('hair','fur','mane','ruff')):
        negative += ', hair, long hair, wig, beard'
    crown = next((f for f in selected if f['region']=='crown'),None)
    if crown and crown['slot']=='ears' and 'horn' not in crown['description']:
        negative += ', horns, antlers'
    wings = next((f for f in selected if f['slot']=='wings'),None)
    if wings and ('dark borders' in wings['description'] or 'moth' in wings['description']):
        negative += ', feathers, feathered wings, bat wings'
    if profile['symbol'] in NATIVE_BODIES:
        negative = negative.replace('extra heads, extra limbs, ', '')
    # Rear prompts never repeat face, eye, mouth, or cheek instructions. That
    # was causing two front views when a global turnaround prompt was used.
    rear_features = [f for f in selected if f['slot'] not in ('face','eyes')
                     and not (f['slot']=='markings' and 'cheek' in f['description'])]
    rear_description = body+'; '+'; '.join(f['description'] for f in rear_features)+f'; {primary} back and shoulders'
    style = ('pixel art monster sprite, clean dark outline, flat cel shading, limited color palette, '
             'white background, centered, full body, generous empty margin')
    view_prompts = {
        'front': f'One creature, front three-quarter view. {description}. {style}.',
        'back': f'One creature seen from BEHIND, rear three-quarter view, facing away from viewer. {rear_description}. Back of head and shoulders visible. {style}.',
    }
    return {'version': VERSION, 'identity': recipe['identity'], 'level': recipe['level'],
            'anchor': anchor, 'body_plan': profile['form'], 'body_description': body,
            'dimensions': dims, 'palette_rgb': rgb, 'primary_color': primary, 'accent_color': accent,
            'features': selected, 'contributors': shares, 'description': description,
            'prompt': prompt, 'negative_prompt': negative, 'view_prompts': view_prompts,
            'traits_digest': traits.digest, 'seed': int(hashlib.sha256(recipe['identity'].encode()).hexdigest()[:8],16)&0x7fffffff}


def sketch(design, size=512):
    """A paired anatomical block-in made only from connected geometric shapes.

    No game sprites are read here. This is a model input, never presented as AI
    artwork. Complex native multi-headed forms use text conditioning instead.
    """
    sheet = Image.new('RGB', (size*2,size), 'white')
    primary = tuple(round(.75*c+.25*m) for c,m in zip(COLORS[design['primary_color']],design['palette_rgb']))
    accent = COLORS[design['accent_color']]
    outline = tuple(max(20,round(c*.35)) for c in primary)
    features = {f['slot']: f for f in design['features']}
    for view in range(2):
        im = Image.new('RGB',(512,512),'white')
        d = ImageDraw.Draw(im)
        def ellipse(box, color=primary): d.ellipse(box, fill=color, outline=outline, width=4)
        def polygon(points, color=primary): d.polygon(points,fill=color); d.line(points+[points[0]],fill=outline,width=4,joint='curve')
        width = 112 + int(design['dimensions'][0]*75)
        cx,cy = 256,293
        form = design['body_plan']
        neckless = 'without a neck' in design['body_description']
        ornament = features.get('back')
        def back_ornament():
            if not ornament: return
            text = ornament['description']
            if 'shell' in text:
                ellipse((cx-width*.62,219,cx+width*.62,396),(130,103,66))
                d.arc((cx-width*.48,232,cx+width*.48,385),0,360,fill=outline,width=4)
                if 'cannon' in text:
                    for sign in (-1,1):
                        x=cx+sign*width*.42
                        polygon([(x-13,246),(x-15,166),(x+15,166),(x+14,247)],(145,155,161))
                        ellipse((x-15,160,x+15,177),outline)
            elif 'closed plant bulb' in text:
                # A squat bulb seated on the torso, not a flower on a stalk.
                x = cx+(40 if view==0 else 0)
                ellipse((x-64,181,x+64,279),(79,137,64))
                polygon([(x-57,228),(x-27,174),(x,150),(x+31,175),(x+58,228)],(101,157,75))
                d.line((x,159,x-12,237,x,271),fill=outline,width=4)
            elif any(word in text for word in ('bulb','flower','leaves','mushroom')):
                x=cx+(36 if view==0 else 0)
                d.line((x,285,x,131),fill=(80,117,60),width=18)
                for sign in (-1,1):
                    polygon([(x,197),(x+sign*92,134),(x+sign*71,202),(x,236)],(94,154,74))
                ellipse((x-38,88,x+38,171),(210,105,145) if 'pink' in text or 'flower' in text else (94,154,74))
        quadruped = form in ('quadruped','crawler')
        if view==0 and not quadruped:back_ornament()
        wing = features.get('wings') or features.get('fins')
        if wing or form in ('bird','winged'):
            amount = wing['prominence'] if wing else .65
            reach = 55+int(50*amount)
            for sign in (-1,1):
                if wing and ('dark borders' in wing['description'] or 'moth' in wing['description']):
                    # Rounded moth/butterfly lobes with pale membranes; never
                    # substitute a bat-wing silhouette for this inherited trait.
                    x=cx+sign*(width*.45+reach*.4)
                    ellipse((x-reach*.62,151,x+reach*.62,310),(229,222,198))
                    ellipse((x-reach*.52,256,x+reach*.52,358),(218,210,191))
                    d.line((cx+sign*width*.35,294,x,201),fill=outline,width=4)
                    d.line((cx+sign*width*.35,294,x,324),fill=outline,width=4)
                else:
                    polygon([(cx+sign*width//2,260),(cx+sign*(width//2+reach),142),
                             (cx+sign*(width//2+reach+20),291),(cx+sign*width//2,349)],accent)
        tail = features.get('tail')
        if tail and form not in ('serpent','fish','aquatic'):
            amount = tail['prominence']
            x = cx+width//2-5
            points=[(x,345),(x+40,365),(x+73,285-int(amount*42)),(x+46,298),(x+56,248),(x+21,293),(x+29,322),(x,323)]
            polygon(points,accent)
        if quadruped:
            # Both views share a low torso and four grounded legs. The old
            # centered upright head turned quadrupeds into bipedal mascots.
            for x,y in ((185,327),(306,327),(152,345),(334,345)):
                ellipse((x-19,y,x+22,y+54),primary)
            ellipse((130,248,378,365))
        elif form in ('serpent','fish','aquatic'):
            ellipse((140,215,375,370))
            polygon([(352,287),(439,226),(425,360),(350,322)],accent)
        elif form in ('cocoon','shell','round','floating','star','amorphous'):
            ellipse((cx-width//2,172,cx+width//2,401))
        else:
            # All appendages overlap their attachment points: one continuous body.
            for sign in (-1,1):
                x=cx+sign*width*.27
                ellipse((int(x-31),364,int(x+34),428),accent)
                x=cx+sign*width*.48
                ellipse((int(x-24),267,int(x+27),353))
            ellipse((cx-width//2,165 if neckless else 218,cx+width//2,401))
        if view==0 and not quadruped:
            ellipse((cx-width*.32,274,cx+width*.32,384),accent)
        # Head and torso overlap, giving a single attached head.
        if quadruped:
            if view==0:
                back_ornament()
                ellipse((113,251,258,354))
            else:
                # Distant back of head is partly hidden by the torso/bulb.
                ellipse((225,217,359,296))
        elif not neckless:
            ellipse((cx-width*.47,155,cx+width*.47,299))
        if view==1 and not quadruped:back_ornament()
        crown = features.get('ears') or features.get('head')
        if crown:
            # Prominence is influence, not literal length. Short ears should
            # never become rabbit ears just because lineage share is high.
            short = 'short' in crown['description'] or 'small' in crown['description']
            length=(16+int(12*crown['prominence'])) if short else (24+int(80*crown['prominence']))
            for sign in (-1,1):
                head_x = (185 if view==0 else 296) if quadruped else cx
                offset_y = 105 if quadruped and view==0 else 64 if quadruped else 0
                x=head_x+sign*(48 if quadruped else width*.30)
                tipx,tipy=x+sign*14,157-length+offset_y
                points=[(x-16,186+offset_y),(x-18,156+offset_y),(tipx-10,tipy+16),(tipx,tipy),
                        (tipx+9,tipy+16),(x+18,156+offset_y),(x+18,182+offset_y)]
                polygon(points)
                if 'dark' in crown['description'] or 'black' in crown['description']:
                    polygon([(tipx,tipy),(tipx-10,tipy+28),(tipx+9,tipy+28)],outline)
                if view==0 and crown['slot']=='ears':
                    if tipy+12 < 174+offset_y:
                        d.ellipse((x-5,tipy+12,x+6,174+offset_y),fill=(210,137,141))
        if view==1 and quadruped:back_ornament()
        if view==0:
            face_cx = 180 if quadruped else cx
            face_dy = 72 if quadruped else 0
            for sign in (-1,1):
                x=face_cx+sign*(35 if quadruped else width*.23)
                ellipse((x-16,215+face_dy,x+15,238+face_dy),(245,241,224))
                d.ellipse((x-5,218+face_dy,x+4,236+face_dy),fill=outline)
            face = features.get('face') or features.get('eyes')
            if face and ('grin' in face['description'] or 'tooth' in face['description']):
                d.chord((face_cx-47,235+face_dy,face_cx+47,275+face_dy),0,180,fill=(243,236,211),outline=outline,width=3)
                for x in range(face_cx-30,face_cx+40,15): d.line((x,254+face_dy,x,269+face_dy),fill=outline,width=2)
            else:
                d.arc((face_cx-22,241+face_dy,face_cx+22,265+face_dy),0,180,fill=outline,width=3)
            marking=features.get('markings')
            if marking and 'cheek' in marking['description']:
                for x in (cx-width*.37,cx+width*.37): d.ellipse((x-12,240,x+12,258),fill=(200,88,79))
        sheet.paste(im.resize((size,size),Image.Resampling.LANCZOS),(view*size,0))
    return sheet
