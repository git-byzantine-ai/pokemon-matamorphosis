import hashlib
import json
import subprocess
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from companion.sprites import canonical,tiles
from portable.backend import Installation,devices,preferred_device
from portable.downloads import download,safe_member
from portable.rom import apply_ips,decompress,extract_references,untile,validate_base

ROOT=Path(__file__).resolve().parents[1]


class PortableTests(unittest.TestCase):
    def test_patch_rejects_wrong_rom_truncation_and_overflow(self):
        with self.assertRaises(ValueError):validate_base(b'not a ROM')
        for bad in (b'',b'PATCH',b'PATCH\0\0\0\0\x05a',b'PATCH\xff\xff\xff\0\x02aaEOF'):
            with self.assertRaises(ValueError):apply_ips(bytes(16*1024*1024),bad)
        self.assertEqual(apply_ips(b'abcd',b'PATCH\0\0\x01\0\0\0\x02xEOF'),b'axxd')

    def test_tile_roundtrip_and_bad_compressed_reference(self):
        pixels=bytes(i%16 for i in range(4096))
        self.assertEqual(untile(tiles(pixels)),pixels)
        with self.assertRaises(ValueError):decompress(b'\x10\x04\0\0\x80\0\0',0)

    def test_download_resume_hash_and_completed_partial(self):
        payload=b'fixture-data'*500;seen=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                start=int(self.headers.get('Range','bytes=0-').split('=')[1].split('-')[0]);seen.append(start)
                self.send_response(206 if start else 200)
                self.send_header('Content-Length',str(len(payload)-start))
                if start:self.send_header('Content-Range',f'bytes {start}-{len(payload)-1}/{len(payload)}')
                self.end_headers();self.wfile.write(payload[start:])
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                target=Path(temp)/'model';part=Path(temp)/'model.partial';part.write_bytes(payload[:25])
                spec={'url':f'http://127.0.0.1:{server.server_port}/model','sha256':hashlib.sha256(payload).hexdigest()}
                download(spec,target);self.assertEqual(target.read_bytes(),payload);self.assertEqual(seen,[25])
                target.unlink();part.write_bytes(payload);download(spec,target);self.assertEqual(seen,[25])
                target.unlink()
                with self.assertRaises(ValueError):download(dict(spec,sha256='0'*64),target)
                self.assertFalse(target.exists());self.assertFalse(part.exists())
        finally:server.shutdown();server.server_close();thread.join()

    def test_archive_paths_and_device_detection(self):
        for name in ('../bad','C:/bad','/bad','safe/../../bad','..\\bad'):
            with self.assertRaises(ValueError):safe_member(name)
        safe_member('mGBA-0.10.5-win64/mGBA.exe')
        response=subprocess.CompletedProcess([],0,'Vulkan0\tIntel UHD\nVulkan7\tNVIDIA Test GPU\nCPU\tTest CPU\n','')
        with patch('portable.backend.subprocess.run',return_value=response):found=devices('fake')
        self.assertEqual(preferred_device(found),'Vulkan7')
        self.assertEqual(preferred_device([found[-1]]),'CPU')

    def test_data_lock_and_consistent_backup(self):
        import sqlite3
        from portable.windows import DataLock
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);assets=root/'assets';assets.mkdir();(assets/'manifest.json').write_text('{}')
            install=Installation(root/'data',assets)
            lock=DataLock(install.data/'launcher.lock')
            with self.assertRaises(RuntimeError):DataLock(install.data/'launcher.lock')
            lock.close();second=DataLock(install.data/'launcher.lock');second.close()
            install.game.parent.mkdir();(install.game.parent/'test.sav').write_bytes(b'keep this save')
            db=sqlite3.connect(install.data/'history.sqlite3');db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE checks(value)');db.execute('INSERT INTO checks VALUES(42)');db.commit()
            saved=install.backup()
            self.assertEqual((saved/'test.sav').read_bytes(),b'keep this save')
            with closing(sqlite3.connect(saved/'history.sqlite3')) as copied:self.assertEqual(copied.execute('SELECT value FROM checks').fetchone()[0],42)
            db.close()

    @unittest.skipUnless((ROOT/'build/portable-resources/manifest.json').exists(),'Prepare portable resources first')
    def test_all_reference_sprites_extract_from_the_players_rom(self):
        assets=ROOT/'build/portable-resources';base=(ROOT/'build/firered-baseline.gba').read_bytes()
        validate_base(base);catalog=json.loads((assets/'catalog.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            extract_references(base,json.loads((assets/'references.json').read_text()),temp)
            for species in catalog:
                for shiny in (False,True):
                    for view in ('front','back'):
                        actual=canonical(temp,catalog,species,view,shiny)
                        expected=canonical(ROOT/'rom/pokefirered',catalog,species,view,shiny)
                        self.assertEqual(actual.tobytes(),expected.tobytes(),f'{species}/{view}/shiny={shiny}')


if __name__=='__main__':unittest.main()
