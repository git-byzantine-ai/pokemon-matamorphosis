import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from companion.recipe import weights, make_recipe, ev_totals, validate_spending
from companion.history import History, ZERO, pack_event, unpack_event
from companion.sprites import encode_pair, validate
from companion.server import Application

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'build/catalog.json').read_text())


class WeightsTests(unittest.TestCase):
    def test_ev_weighting_and_full_caps(self):
        self.assertEqual(weights({}, CATALOG), (1, {}))
        base, donors = weights({'16':10}, CATALOG)
        self.assertAlmostEqual(base, 1-.75*30/510)
        self.assertAlmostEqual(donors['16'], .75*30/510)
        base, donors = weights({'16':85,'74':85}, CATALOG)
        self.assertEqual(base, .25)
        self.assertEqual(donors, {'16':.375,'74':.375})
        base, donors = weights({'16':1,'6':1}, CATALOG)
        self.assertAlmostEqual(donors['6'],3*donors['16'])
        for level in (5,6,36,80,100):
            r=make_recipe('i',level,25,{'16':10},CATALOG)
            self.assertEqual(r['shares'],make_recipe('i',5,25,{'16':10},CATALOG)['shares'])
            self.assertEqual(r['lineage'],{'25':1.})

    def test_whole_yields_limits_and_validation(self):
        for counts in ({'16':256},{'16':255,'74':255,'1':1},{'16':-1},{'16':.1},{'16':True},{'999':1}):
            with self.assertRaises(ValueError): weights(counts,CATALOG)
        self.assertEqual(validate_spending({'16':10},{},{'16':1},CATALOG)[1],[0,0,0,3,0,0])
        with self.assertRaises(ValueError):validate_spending({'16':9},{'16':1},{'16':10},CATALOG)
        with self.assertRaises(ValueError):validate_spending({'26':1},{'16':254},{'26':1},CATALOG)
        with self.assertRaises(ValueError):validate_spending({'12':1},{'1':254},{'12':1},CATALOG)
        for level in (0,101):
            with self.assertRaises(ValueError):make_recipe('i',level,25,{},CATALOG)


class HistoryTests(unittest.TestCase):
    def test_replay_rollback_and_new_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            db = History(Path(temp) / 'history.db')
            first = pack_event(1, ZERO, 123, 456, 4, 16, 5, 1)
            a, fresh = db.append('campaign', first)
            self.assertTrue(fresh)
            self.assertFalse(db.append('campaign', first)[1])
            second = pack_event(2, a['head'], 123, 456, 4, 19, 5, 1)
            b, _ = db.append('campaign', second)
            alternate = pack_event(2, a['head'], 123, 456, 4, 16, 5, 1)
            c, _ = db.append('campaign', alternate)
            self.assertEqual(db.counts('campaign', a['head'], a['identity']), {'16': 1})
            self.assertEqual(db.counts('campaign', b['head'], a['identity']), {'16': 1, '19': 1})
            self.assertEqual(db.counts('campaign', c['head'], a['identity']), {'16': 2})
            with self.assertRaises(ValueError):
                db.append('other', second)
            corrupt = bytearray(first)
            corrupt[-2] ^= 1
            with self.assertRaises(ValueError):
                unpack_event(bytes(corrupt))
            db.close()


class SpriteTests(unittest.TestCase):
    def test_tile_nibble_order_and_transparency(self):
        front = Image.new('RGBA', (64, 64))
        back = Image.new('RGBA', (64, 64))
        front.putpixel((0, 0), (255, 0, 0, 255))
        back.putpixel((1, 0), (0, 255, 0, 255))
        payload, views = encode_pair(front, back)
        self.assertEqual(len(payload), 4128)
        self.assertNotEqual(payload[0] & 15, 0)
        self.assertEqual(payload[0] >> 4, 0)
        self.assertEqual(payload[2048] & 15, 0)
        self.assertNotEqual(payload[2048] >> 4, 0)
        self.assertEqual(views[0].getpixel((1, 0))[3], 0)
        with self.assertRaises(ValueError):
            validate(payload[:-1])

    def test_every_species_has_readable_references(self):
        from companion.sprites import canonical,encode_canonical
        root = ROOT / 'rom/pokefirered'
        for species in CATALOG:
            for shiny in (False,True):
                images=[canonical(root,CATALOG,species,view,shiny) for view in ('front','back')]
                for image in images:self.assertEqual(image.size,(64,64))
                binary,_=encode_canonical(*images)
                self.assertEqual(len(binary),4128)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        config=json.loads((ROOT/'config.example.json').read_text())
        config.update(database=str(Path(self.temp.name)/'history.db'),cache=str(Path(self.temp.name)/'sprites'))
        config['generator']['provider']='preview'
        self.app=Application(config);self.campaign='0000000100000002';self.head=ZERO;self.seq=0
        self.identity='000001c8:0000007b';self.descriptor='000001c8,0000007b,25,20'

    def tearDown(self):
        self.app.history.close();self.temp.cleanup()

    def event(self,kind,donor=0,amount=0,pid=123,species=25,level=20):
        raw=pack_event(self.seq+1,self.head,pid,456,species,donor,level,kind,amount)
        reply=self.app.command(f'EVENT {self.campaign} {raw.hex()}')
        self.assertEqual(reply,self.app.command(f'EVENT {self.campaign} {raw.hex()}'))
        self.seq+=1;self.head=reply.split()[1]
        return self.head

    def ledger(self):return self.app.ledger_at(self.campaign,self.head,self.identity)
    def poll(self):return self.app.command(f'POLL {self.campaign} {self.head} - {self.descriptor}')
    def spend(self,n):
        self.event(6);self.event(4,16,n);self.event(5)

    def test_bank_selection_commit_asset_and_frozen_art(self):
        self.assertEqual(self.poll(),'WAIT')
        for _ in range(110):self.event(1,16)
        self.event(2,level=21)
        self.assertEqual(self.poll(),'WAIT');self.assertEqual(self.app.status()['counts'],{})
        self.assertEqual(self.ledger()['ev_totals'],[0]*6)
        self.assertEqual(self.ledger()['available'],{'16':110})
        self.spend(100)
        self.assertEqual(self.ledger()['available'],{'16':10})
        self.assertEqual(self.ledger()['ev_totals'],[0,0,0,100,0,0])
        self.assertEqual(self.app.status()['counts'],{'pending':1})
        job=self.app.status()['jobs'][0];self.app.generator.generate(job['recipe'])
        with self.app.history.db:self.app.history.db.execute("UPDATE jobs SET status='ready'")
        self.event(2,level=30);self.event(3,species=26,level=30)
        fields=self.poll().split()
        self.assertEqual(fields[:6],['ASSET',self.head,'0000007b','000001c8','25','20'])
        validate(bytes.fromhex(fields[-1]))
        self.assertEqual(self.app.command(f'POLL {self.campaign} {self.head} {fields[6]} {self.descriptor}'),'WAIT')
        self.assertEqual(len(self.app.status()['jobs']),1)
        self.spend(10)
        self.assertEqual(self.ledger()['available'],{})
        self.assertEqual(self.ledger()['spent'],{'16':110})

    def test_pending_cancel_branch_individual_isolation_and_rejections(self):
        for _ in range(3):self.event(1,16)
        saved_head,saved_seq=self.head,self.seq
        self.event(1,19,pid=999)
        self.assertEqual(self.ledger()['available'],{'16':3})
        with self.assertRaises(ValueError):self.event(5)
        self.event(6)
        with self.assertRaises(ValueError):self.event(5)
        with self.assertRaises(ValueError):self.event(4,16,4)
        self.event(4,16,2)
        self.assertEqual(self.ledger()['spent'],{})
        self.assertEqual(self.ledger()['available'],{'16':3})
        self.spend(1) # a new begin abandons the unfinished selection
        self.assertEqual(self.ledger()['spent'],{'16':1})
        self.head,self.seq=saved_head,saved_seq
        self.assertEqual(self.ledger()['spent'],{})
        self.spend(3)
        self.assertEqual(self.ledger()['spent'],{'16':3})
        self.assertEqual(self.app.ledger_at(self.campaign,saved_head,self.identity)['available'],{'16':3})
        with self.assertRaises(ValueError):self.spend(1)

    def test_menu_pagination_and_protocol(self):
        self.assertEqual(self.app.command('HELLO 6 c75f3521'),'OK 6')
        for species in range(1,21):self.event(1,species)
        for offset,count in ((0,8),(8,8),(16,4),(20,0)):
            reply=self.app.command(f'MENU {self.campaign} {self.head} {self.descriptor} {offset}').split()
            self.assertEqual(reply[:4],['ESSENCE',self.head,str(offset),'20'])
            self.assertEqual(0 if reply[4]=='-' else len(reply[4].split(';')),count)
        for offset in (-1,999):
            with self.assertRaises(ValueError):self.app.command(f'MENU {self.campaign} {self.head} {self.descriptor} {offset}')

    def test_threshold_refund_reapply_and_progress(self):
        from unittest.mock import patch
        from companion.sprites import canonical,encode_canonical
        for _ in range(100):self.event(1,16)
        with patch('companion.generator.subprocess.run',side_effect=AssertionError('No AI below 100 EVs')):
            self.spend(99)
            fields=self.poll().split()
        normal,_=encode_canonical(*(canonical(ROOT/'rom/pokefirered',CATALOG,25,v) for v in ('front','back')))
        self.assertEqual(bytes.fromhex(fields[-1]),normal)
        self.assertEqual(self.app.command(f'PROGRESS {self.campaign} {self.head} {self.descriptor}').split()[-1],'3')
        self.spend(1)
        self.assertEqual(self.app.status()['counts'],{'pending':1,'ready':1})
        self.assertEqual(self.app.command(f'PROGRESS {self.campaign} {self.head} {self.descriptor}').split()[-1],'1')
        job=next(j for j in self.app.status()['jobs'] if j['status']=='pending')
        self.app.generator.generate(job['recipe'])
        with self.app.history.db:self.app.history.db.execute("UPDATE jobs SET status='ready'")
        custom=self.poll().split()[6];self.assertNotEqual(custom,fields[6])
        saved=self.head
        self.event(6);self.event(7,16,1);self.event(5)
        self.assertEqual(self.ledger()['ev_totals'][3],99)
        self.assertEqual(self.ledger()['available'],{'16':1})
        self.assertEqual(self.poll().split()[6],fields[6])
        self.assertEqual(self.app.ledger_at(self.campaign,saved,self.identity)['ev_totals'][3],100)
        self.event(6)
        with self.assertRaises(ValueError):self.event(7,16,100)
        self.event(7,16,99);self.event(5)
        self.assertEqual(self.ledger()['spent'],{})
        self.assertEqual(self.ledger()['available'],{'16':100})
        self.spend(100);self.assertEqual(self.poll().split()[6],custom)
        menu=self.app.command(f'MENU {self.campaign} {self.head} {self.descriptor} 0')
        self.assertTrue(menu.endswith('16,100,100'),menu)

    def test_same_total_swap_and_stat_cap(self):
        for _ in range(255):self.event(1,16);self.event(1,74)
        self.spend(255)
        self.event(6);self.event(7,16,255);self.event(4,74,255);self.event(5)
        self.assertEqual(self.ledger()['ev_totals'],[0,0,255,0,0,0])
        self.assertEqual(self.ledger()['available'],{'16':255})

    def test_same_species_canonical_assets_do_not_hide_another_individual(self):
        for pid in (123,999):
            self.event(1,16,pid=pid);self.event(6,pid=pid)
            self.event(4,16,1,pid=pid);self.event(5,pid=pid)
        first=self.poll().split()
        second=self.app.command(f'POLL {self.campaign} {self.head} {first[6]} 000001c8,000003e7,25,20').split()
        self.assertEqual(second[0],'ASSET')
        self.assertEqual(second[2],'000003e7')
        self.assertNotEqual(second[6],first[6])
        self.assertEqual(second[-1],first[-1])

    def test_triple_yields_threshold_caps_and_refunds(self):
        for _ in range(86):self.event(1,16)
        self.event(6,amount=3);self.event(4,16,33);self.event(5)
        self.assertEqual(self.ledger()['ev_totals'],[0,0,0,99,0,0])
        normal=self.poll().split()[6]
        self.event(6,amount=3);self.event(4,16,1);self.event(5)
        self.assertEqual(self.ledger()['ev_totals'][3],102)
        self.assertEqual(self.app.command(f'PROGRESS {self.campaign} {self.head} {self.descriptor}').split()[-1],'1')
        self.event(6,amount=3);self.event(7,16,1);self.event(5)
        self.assertEqual(self.poll().split()[6],normal)
        self.event(6,amount=3);self.event(4,16,52);self.event(5)
        self.assertEqual(self.ledger()['ev_totals'][3],255)
        self.event(6,amount=3)
        with self.assertRaises(ValueError):self.event(4,16,1)
        self.assertEqual(self.ledger()['available'],{'16':1})
        self.event(7,16,85);self.event(5)
        self.assertEqual(self.ledger()['available'],{'16':86})
        self.assertEqual(self.ledger()['ev_totals'],[0]*6)
        self.assertEqual(ev_totals({'25':1,'12':1},CATALOG),[0,0,0,6,6,3])
        base,donors=weights({'16':85,'6':28,'92':1},CATALOG)
        self.assertEqual(base,.25);self.assertAlmostEqual(sum(donors.values()),.75)

    def test_legacy_full_build_migrates_without_losing_essence(self):
        # Old 255-EV builds remain valid history even though 255 new essences
        # would exceed the cap. The migration is an explicit history event.
        for _ in range(255):self.event(1,16)
        self.spend(255)
        old_head=self.head
        self.assertEqual(self.ledger()['multiplier'],1)
        with self.assertRaises(ValueError):self.event(6,amount=3)
        self.event(8,amount=3)
        self.assertEqual(self.ledger()['available'],{'16':255})
        self.assertEqual(self.ledger()['spent'],{})
        self.assertEqual(self.ledger()['ev_totals'],[0]*6)
        self.assertEqual(self.ledger()['multiplier'],3)
        self.assertEqual(self.poll().split()[0],'ASSET')
        with self.assertRaises(ValueError):self.event(8,amount=3)
        with self.assertRaises(ValueError):self.event(6)
        self.event(6,amount=3);self.event(4,16,85);self.event(5)
        self.assertEqual(self.ledger()['ev_totals'][3],255)
        self.assertEqual(self.ledger()['available'],{'16':170})
        old=self.app.ledger_at(self.campaign,old_head,self.identity)
        self.assertEqual(old['spent'],{'16':255});self.assertEqual(old['ev_totals'][3],255)
        self.assertEqual(old['multiplier'],1)


if __name__ == '__main__':unittest.main()
