"""Frozen application entry point; CLI modes support package verification."""
import argparse
import json
import logging
import sys
from pathlib import Path
from portable.backend import Installation,default_data


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir');parser.add_argument('--rom');parser.add_argument('--model-file')
    parser.add_argument('--report');parser.add_argument('--companion')
    parser.add_argument('--setup',action='store_true');parser.add_argument('--test-ai',action='store_true')
    parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    if args.companion:
        from companion.server import serve
        logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
        serve(json.loads(Path(args.companion).read_text()));return 0
    data=args.data_dir
    if not data and getattr(sys,'frozen',False):
        preference=Path(sys.executable).parent/'portable-settings.json'
        if preference.exists():data=json.loads(preference.read_text())['data']
    data=data or default_data()
    if not (args.setup or args.test_ai or args.verify):
        from portable.gui import Launcher
        try:Launcher(data).run();return 0
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror('Metamorphosis could not start',str(e));return 1
    install=Installation(data)
    from portable.windows import DataLock
    lock=DataLock(install.data/'launcher.lock')
    try:
        def progress(text,fraction):
            if sys.stdout:print(text,flush=True)
            if args.report:Path(args.report+'.progress').write_text(text,encoding='utf-8')
        if args.setup:result=install.setup(args.rom,args.model_file,progress)
        elif args.test_ai:result=install.test_ai(progress)
        else:
            from portable.downloads import sha256
            if not install.ready():raise ValueError('Installation is incomplete')
            assert sha256(install.game)==install.manifest['rom_sha256']
            result={'ready':True,'rom_sha256':sha256(install.game),'state':install.state()}
        if args.report:Path(args.report).write_text(json.dumps(result,indent=2),encoding='utf-8')
        if sys.stdout:print(json.dumps(result,indent=2))
        return 0
    except Exception as e:
        if args.report:Path(args.report).write_text(json.dumps({'error':str(e)}),encoding='utf-8')
        if sys.stderr:print(str(e),file=sys.stderr)
        return 1
    finally:lock.close()


if __name__=='__main__':sys.exit(main())
