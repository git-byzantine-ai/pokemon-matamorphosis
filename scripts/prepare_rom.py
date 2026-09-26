"""Prepare a pinned, disposable upstream tree and apply the tracked overlay."""
import argparse
import hashlib
import shutil
import urllib.request
import zipfile
from pathlib import Path
from catalog import export

ROOT = Path(__file__).resolve().parents[1]
REVISION = 'c75f352304d529f6ba92d4f74b9cf8b5c3810788'


def prepare():
    source = ROOT / 'research/source/pret-pokefirered-c75f352'
    if not source.exists():
        archive = ROOT / '.tools/pokefirered.zip'
        archive.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(f'https://api.github.com/repos/pret/pokefirered/zipball/{REVISION}', archive)
        with zipfile.ZipFile(archive) as z:
            z.extractall(ROOT / 'research/source')
        source = next((ROOT / 'research/source').glob('pret-pokefirered-c75f352*'))
    target = ROOT / 'rom/pokefirered'
    if not target.exists():
        shutil.copytree(source, target)
    export(source, ROOT / 'build/catalog.json')
    return source, target


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    source, target = prepare()
    if args.baseline:
        patch = ROOT / 'rom/metamorphosis.patch'
        if patch.exists():
            for line in patch.read_text().splitlines():
                if line.startswith('+++ b/'):
                    relative = line[6:]
                    original, destination = source / relative, target / relative
                    if original.is_file():
                        pristine = original.read_bytes()
                        if not destination.exists() or destination.read_bytes() != pristine:
                            # A restored file must be newer than patched objects.
                            destination.write_bytes(pristine)
                    elif destination.is_file():
                        destination.unlink()
                        obj = target / 'build/firered' / Path(relative).with_suffix('.o')
                        obj.unlink(missing_ok=True)
    else:
        from patch_rom import apply
        apply(source, target)
    print(f'Prepared {target} at {REVISION}')
