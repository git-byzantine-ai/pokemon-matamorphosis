"""Export the editable trait vocabulary as a reviewable table and JSON catalog."""
import json
from pathlib import Path
from companion.anatomy import Traits

def main():
    catalog=json.loads(Path('build/catalog.json').read_text())
    traits=Traits(catalog)
    destination=Path('build/trait-catalog');destination.mkdir(parents=True,exist_ok=True)
    (destination/'traits.json').write_text(json.dumps(traits.by_id,indent=2))
    rows=['# Creature trait catalog','',
          'Hand-authored visual design vocabulary; an editable artistic starting point, not a biological taxonomy. All 386 species and 25 legacy Unown entries in this ROM catalog resolve to a profile. Source: `companion/data/traits.tsv`.','',
          '| ROM ID | Species | Body plan | Color | Anatomical features |',
          '|---|---|---|---|---|']
    for key,p in sorted(traits.by_id.items(),key=lambda x:int(x[0])):
        features='; '.join(f"{f['slot']}: {f['description']}" for f in p['features'])
        body=p['body'] or p['form']
        rows.append(f"| {key} | {p['name']} | {body} | {p['color']} | {features} |")
    (destination/'TRAITS.md').write_text('\n'.join(rows)+'\n')
    print(f'Exported {len(traits.by_id)} profiles to {destination}')

if __name__=='__main__':main()
