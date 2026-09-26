"""Loopback companion service. The GPU worker never blocks durable event ACKs."""
import argparse
import json
import logging
import re
import socketserver
import threading
import time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .generator import Generator
from .history import History, ZERO, hash_bytes, unpack_event
from .recipe import make_recipe, validate_spending, MIN_ART_EVS, VERSION as RECIPE_VERSION
from .sprites import validate

LOG = logging.getLogger('metamorphosis')
HEX16 = re.compile(r'^[0-9a-f]{16}$')


class Application:
    def __init__(self, config):
        self.config = config
        self.catalog = json.loads(Path(config['catalog']).read_text())
        self.history = History(config['database'])
        self.generator = Generator(config, self.catalog)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.last_connection = None
        self.last_error = None
        self.last_client_assets = []
        with self.history.db:
            self.history.db.execute("UPDATE jobs SET status='pending' WHERE status='running'")
            # A renderer/catalog change has a new content key. Never mark an
            # old pending job ready with artwork generated under a different key.
            for key, recipe in self.history.db.execute("SELECT key,recipe FROM jobs WHERE status IN ('pending','failed')").fetchall():
                if json.loads(recipe).get('version') != RECIPE_VERSION or key != self.generator.key(json.loads(recipe)):
                    self.history.db.execute("UPDATE jobs SET status='superseded' WHERE key=?", (key,))

    @lru_cache(maxsize=4096)
    def queue(self, campaign, current, identity, level, species, create=True):
        if str(species) not in self.catalog:
            return None
        ledger = self.ledger_at(campaign, current, identity)
        counts = ledger['spent']
        ot, pid = (int(v, 16) for v in identity.split(':'))
        shiny = ((ot >> 16) ^ (ot & 65535) ^ (pid >> 16) ^ (pid & 65535)) < 8
        recipe = make_recipe(identity, level, species, counts, self.catalog, shiny,ledger['multiplier'])
        key = self.generator.key(recipe)
        if create:
            canonical=sum(recipe['ev_totals']) < MIN_ART_EVS
            if canonical:self.generator.generate(recipe)
            with self.history.db:
                self.history.db.execute('INSERT OR IGNORE INTO jobs(key,campaign,head,identity,level,recipe) VALUES(?,?,?,?,?,?)',
                                        (key, campaign, current, identity, level, json.dumps(recipe)))
                if canonical:self.history.db.execute("UPDATE jobs SET status='ready' WHERE key=?",(key,))
        return key

    @lru_cache(maxsize=8)
    def events_at(self, campaign, current):
        # Immutable history heads make this safe across emulator rollbacks.
        return tuple(self.history.walk(campaign, current))

    @lru_cache(maxsize=4096)
    def ledger_at(self,campaign,current,identity):
        return self.history.essence(campaign,current,identity,self.catalog)

    def command(self, line):
        fields = line.split()
        if fields == ['HELLO', '6', 'c75f3521']:
            self.last_connection = time.time()
            return 'OK 6'
        if len(fields) < 3 or not HEX16.fullmatch(fields[1]):
            raise ValueError('invalid campaign or command')
        command, campaign = fields[:2]
        with self.lock:
            self.last_connection = time.time()
            if command == 'EVENT' and len(fields) == 3:
                raw = bytes.fromhex(fields[2])
                proposed=unpack_event(raw)
                if proposed['kind'] in (4,5,7):
                    ledger=self.ledger_at(campaign,proposed['parent'],proposed['identity'])
                    if not ledger['open']:raise ValueError('essence transaction was not started')
                    pending=dict(ledger['pending'])
                    if proposed['kind'] in (4,7):
                        donor=str(proposed['donor'])
                        pending[donor]=pending.get(donor,0)+(proposed['reason'] if proposed['kind']==4 else -proposed['reason'])
                    if not any(pending.values()):raise ValueError('cannot commit empty essence selection')
                    validate_spending(ledger['available'],ledger['spent'],pending,self.catalog,ledger['multiplier'])
                if proposed['kind'] in (6,8):
                    ledger=self.ledger_at(campaign,proposed['parent'],proposed['identity'])
                    if proposed['kind']==8:
                        if ledger['multiplier']!=1:raise ValueError('essence migration already completed')
                    elif (proposed['reason'] or 1)!=ledger['multiplier'] and (ledger['spent'] or ledger['multiplier']==3):
                        raise ValueError('essence rules require migration before spending')
                event, fresh = self.history.append(campaign, raw)
                if event['kind'] in (5,8):
                    self.queue(campaign, event['head'], event['identity'], event['level'], event['species'])
                return 'ACK ' + event['head']
            if command == 'MENU' and len(fields)==5 and HEX16.fullmatch(fields[2]):
                current=fields[2]
                ot,pid,species,level=fields[3].split(',')
                if not re.fullmatch('[0-9a-f]{8}',ot) or not re.fullmatch('[0-9a-f]{8}',pid):
                    raise ValueError('invalid individual identity')
                offset=int(fields[4])
                if not 0<=offset<=len(self.catalog):raise ValueError('invalid essence page')
                ledger=self.ledger_at(campaign,current,ot+':'+pid)
                rows=sorted(((int(k),min(n,65535),ledger['spent'].get(k,0)) for k,n in ledger['earned'].items()
                             if k in self.catalog and sum(self.catalog[k]['ev_yield'])),key=lambda x:x[0])
                data=';'.join(f'{k},{n},{used}' for k,n,used in rows[offset:offset+8]) or '-'
                return f'ESSENCE {current} {offset} {len(rows)} {data}'
            if command == 'PROGRESS' and len(fields)==4 and HEX16.fullmatch(fields[2]):
                current=fields[2]
                ot,pid,species,level=fields[3].split(',')
                if not re.fullmatch('[0-9a-f]{8}',ot) or not re.fullmatch('[0-9a-f]{8}',pid):
                    raise ValueError('invalid individual identity')
                event=self.ledger_at(campaign,current,ot+':'+pid)['latest']
                if not event:return f'PROGRESS {current} 00000000 0'
                if sum(self.ledger_at(campaign,current,ot+':'+pid)['ev_totals']) < MIN_ART_EVS:
                    key=self.queue(campaign,current,event['identity'],int(level),int(species))
                else:key=self.queue(campaign,event['head'],event['identity'],event['level'],event['species'])
                row=self.history.db.execute('SELECT status FROM jobs WHERE key=?',(key,)).fetchone()
                phase={'pending':1,'running':2,'ready':3,'failed':4}.get(row[0] if row else '',0)
                return f'PROGRESS {current} {key[:8]} {phase}'
            if command != 'POLL' or len(fields) != 5 or not HEX16.fullmatch(fields[2]):
                raise ValueError('invalid polling request')
            current = fields[2]
            known = set(fields[3].split(','))
            self.last_client_assets = sorted(k for k in known if re.fullmatch('[0-9a-f]{8}',k))
            # Traversing only this head's ancestors naturally isolates save-state branches.
            events = self.events_at(campaign, current)
            wanted = [] if fields[4] == '-' else fields[4].split(';')
            for descriptor in wanted[:7]:
                ot, pid, species, level = descriptor.split(',')
                if not re.fullmatch('[0-9a-f]{8}', ot) or not re.fullmatch('[0-9a-f]{8}', pid):
                    raise ValueError('invalid individual identity')
                identity = ot + ':' + pid
                choices = [e for e in events if e['identity'] == identity and e['kind'] in (5,8)]
                candidates = [(e['head'], e['level'], e['species']) for e in choices]
                if choices and sum(self.ledger_at(campaign,current,identity)['ev_totals']) < MIN_ART_EVS:
                    candidates=[(current,int(level),int(species))]
                # No automatic initial, level-up, defeat or evolution artwork.
                for index, (event_head, event_level, event_species) in enumerate(candidates):
                    # Only regenerate the current appearance after an art-engine
                    # update. Earlier levels are fallback candidates if already
                    # cached, not a request to rerender an entire lifetime.
                    key = self.queue(campaign, event_head, identity, event_level, event_species, create=index==0)
                    if key is None:
                        continue
                    row = self.history.db.execute('SELECT status FROM jobs WHERE key=?', (key,)).fetchone()
                    if not row or row[0] != 'ready':
                        continue
                    asset_id = key[:8]
                    if asset_id in known:
                        break
                    payload = (self.generator.cache / key / 'sprite.bin').read_bytes()
                    validate(payload)
                    checksum = hash_bytes(payload, 2166136261)
                    return f'ASSET {current} {pid} {ot} {event_species} {event_level} {asset_id} {checksum:08x} {payload.hex()}'
            return 'WAIT'

    def worker(self):
        while not self.stop.is_set():
            with self.lock:
                row = self.history.db.execute("SELECT key,recipe FROM jobs WHERE status='pending' ORDER BY rowid LIMIT 1").fetchone()
                if row:
                    with self.history.db:
                        self.history.db.execute("UPDATE jobs SET status='running' WHERE key=?", (row[0],))
            if not row:
                self.stop.wait(.25)
                continue
            key, recipe = row
            try:
                generated_key, _ = self.generator.generate(json.loads(recipe))
                if generated_key != key:
                    raise ValueError('Generation key changed; restart the companion to refresh this job')
                status, error = 'ready', None
                LOG.info('Sprite ready: %s', key[:12])
            except Exception as exc:
                status, error = 'failed', str(exc)
                self.last_error = error
                LOG.exception('Generation failed for %s', key[:12])
            with self.lock, self.history.db:
                self.history.db.execute('UPDATE jobs SET status=?,error=? WHERE key=?', (status, error, key))

    def status(self):
        with self.lock:
            jobs = self.history.db.execute('SELECT key,identity,level,status,error,recipe FROM jobs ORDER BY rowid DESC LIMIT 60').fetchall()
            counts = dict(self.history.db.execute('SELECT status,count(*) FROM jobs GROUP BY status').fetchall())
            def design_for(key):
                path = self.generator.cache / key / 'design.json'
                if path.is_file():
                    try:
                        return json.loads(path.read_text())['description']
                    except (OSError, ValueError, KeyError):
                        pass
                return None
            return {'protocol':6,'essence_multiplier':3,'installation':self.config.get('installation'),'provider': self.generator.settings['provider'], 'counts': counts,
                    'conditioning': self.generator.settings['conditioning'],
                    'trait_profiles': len(self.generator.traits.by_id),
                    'connected': bool(self.last_connection and time.time() - self.last_connection < 10),
                    'error': self.last_error,
                    'cached_assets': self.last_client_assets,
                    'jobs': [dict(key=r[0], identity=r[1], level=r[2], status=r[3], error=r[4], recipe=json.loads(r[5]), design=design_for(r[0])) for r in jobs]}


def serve(config):
    app = Application(config)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(60)
            try:
                while True:
                    raw = self.rfile.readline(65537)
                    if not raw:
                        break
                    if len(raw) > 65536:
                        raise ValueError('message too long')
                    try:
                        response = app.command(raw.decode('ascii').strip())
                    except Exception as exc:
                        app.last_error = str(exc)
                        LOG.error('Bridge: %s', exc)
                        response = 'ERROR ' + str(exc).replace('\n', ' ')
                    self.wfile.write((response + '\n').encode('ascii', errors='replace'))
                    self.wfile.flush()
            except (ConnectionError, TimeoutError):
                pass

    class Dashboard(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/api/status':
                content, mime = json.dumps(app.status()).encode(), 'application/json'
            elif self.path == '/':
                content, mime = (Path(__file__).parent / 'dashboard.html').read_bytes(), 'text/html; charset=utf-8'
            elif re.fullmatch(r'/sprites/[0-9a-f]{64}/(front|back)\.png', self.path):
                target = app.generator.cache / self.path.removeprefix('/sprites/')
                if not target.is_file():
                    self.send_error(404)
                    return
                content, mime = target.read_bytes(), 'image/png'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass

    class TCPServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    worker = threading.Thread(target=app.worker, daemon=True)
    worker.start()
    dashboard = ThreadingHTTPServer(('127.0.0.1', config['dashboard_port']), Dashboard)
    threading.Thread(target=dashboard.serve_forever, daemon=True).start()
    LOG.info('Dashboard http://127.0.0.1:%s ; emulator bridge %s', config['dashboard_port'], config['port'])
    with TCPServer(('127.0.0.1', config['port']), Handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            app.stop.set()
            dashboard.shutdown()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.example.json')
    parser.add_argument('--preview', action='store_true', help='non-AI diagnostic compositor')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    config = json.loads(Path(args.config).read_text())
    if args.preview:
        config['generator']['provider'] = 'preview'
    serve(config)


if __name__ == '__main__':
    main()
