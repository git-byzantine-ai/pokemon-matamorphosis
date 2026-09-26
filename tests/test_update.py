import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from scripts.apply_pending_update import FILES,apply


class UpdateTests(unittest.TestCase):
    def stage(self,root):
        pending=root/'pending-update';pending.mkdir()
        for name in FILES:
            (root/name).write_bytes(b'previous')
            (pending/name).write_bytes(b'new')
        (pending/'bridge.json').write_text(json.dumps({'rom_sha256':hashlib.sha256(b'new').hexdigest(),
                                                      'bridge_address':0x2010000,'asset_address':0x8000100}))
        (pending/'metamorphosis.lua').write_text('local BASE = 0x2010000\nlocal ASSETS = 0x8000100')
        (pending/'READY').touch()
        return pending

    def test_upgrade_preserves_save_and_previous_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pending=self.stage(root)
            (root/'firered-metamorphosis.sav').write_bytes(b'user progress')
            self.assertTrue(apply(root))
            self.assertEqual((root/'firered-metamorphosis.sav').read_bytes(),b'user progress')
            self.assertEqual((root/'firered-metamorphosis.gba').read_bytes(),b'new')
            backup=next((root/'previous-builds').iterdir())
            self.assertEqual((backup/'firered-metamorphosis.sav').read_bytes(),b'user progress')
            for name in FILES:self.assertEqual((backup/name).read_bytes(),b'previous')
            self.assertFalse(apply(root))

    def test_wrong_rom_or_bridge_cannot_partially_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);pending=self.stage(root)
            (pending/'firered-metamorphosis.gba').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'checksum'):apply(root)
            for name in FILES:self.assertEqual((root/name).read_bytes(),b'previous')
            (pending/'firered-metamorphosis.gba').write_bytes(b'new')
            (pending/'metamorphosis.lua').write_text('wrong bridge')
            with self.assertRaisesRegex(ValueError,'bridge'):apply(root)
            self.assertEqual((root/'firered-metamorphosis.gba').read_bytes(),b'previous')

    def test_history_backup_includes_committed_wal(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as temp:
            project=Path(temp);root=project/'build';root.mkdir();self.stage(root)
            (project/'config.example.json').write_text(json.dumps({'database':'history.sqlite3'}))
            db=sqlite3.connect(project/'history.sqlite3');db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE defeats(n INTEGER)');db.execute('INSERT INTO defeats VALUES(10)');db.commit()
            try:
                apply(root)
                backup=next((root/'previous-builds').iterdir())
                saved=sqlite3.connect(backup/'history.sqlite3')
                try:self.assertEqual(saved.execute('SELECT n FROM defeats').fetchone(),(10,))
                finally:saved.close()
                self.assertEqual(db.execute('SELECT n FROM defeats').fetchone(),(10,))
            finally:db.close()
