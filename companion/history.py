"""Append-only history DAG. Restoring RAM restores a head, never future defeats."""
import json
import sqlite3
import struct
from collections import Counter
from pathlib import Path

EVENT = struct.Struct('<7I2H4B')
ZERO = '0000000000000000'


def head(lo, hi):
    return f'{hi:08x}{lo:08x}'


def hash_bytes(data, seed):
    value = seed
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def pack_event(sequence, parent, pid, ot, species, donor, level, kind, reason=0):
    lo, hi = int(parent[8:], 16), int(parent[:8], 16)
    payload = struct.pack('<IIIHHBBBB', sequence, pid, ot, species, donor, level, kind, reason, 0)
    a = hash_bytes(payload, lo ^ 2166136261)
    b = hash_bytes(payload, hi ^ 0x9e3779b9)
    return EVENT.pack(sequence, lo, hi, a, b, pid, ot, species, donor, level, kind, reason, 0)


def unpack_event(raw):
    if len(raw) != EVENT.size:
        raise ValueError('incorrect event size')
    seq, pl, ph, hl, hh, pid, ot, species, donor, level, kind, reason, reserved = EVENT.unpack(raw)
    parent = head(pl, ph)
    if not seq or not 1 <= level <= 100 or kind not in (1, 2, 3, 4, 5, 6, 7, 8) or reserved:
        raise ValueError('invalid event fields')
    if kind in (4,7) and (not donor or not reason):
        raise ValueError('essence spend needs a species and positive quantity')
    if kind==5 and (donor or reason):
        raise ValueError('essence transaction boundary has unexpected data')
    if kind==6 and (donor or reason not in (0,3)):
        raise ValueError('unsupported essence transaction rules')
    if kind==8 and (donor or reason!=3):
        raise ValueError('unsupported essence migration')
    if pack_event(seq, parent, pid, ot, species, donor, level, kind, reason) != raw:
        raise ValueError('event checksum mismatch')
    return dict(seq=seq, parent=parent, head=head(hl, hh), pid=pid, ot=ot,
                species=species, donor=donor, level=level, kind=kind, reason=reason,
                identity=f'{ot:08x}:{pid:08x}')


class History:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS events(
            campaign TEXT NOT NULL, head TEXT NOT NULL, parent TEXT NOT NULL,
            sequence INTEGER NOT NULL, raw BLOB NOT NULL,
            PRIMARY KEY(campaign, head));
          CREATE TABLE IF NOT EXISTS jobs(
            key TEXT PRIMARY KEY, campaign TEXT NOT NULL, head TEXT NOT NULL,
            identity TEXT NOT NULL, level INTEGER NOT NULL, recipe TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', error TEXT);
        ''')

    def append(self, campaign, raw):
        event = unpack_event(raw)
        row = self.db.execute('SELECT raw FROM events WHERE campaign=? AND head=?', (campaign, event['head'])).fetchone()
        if row:
            if bytes(row[0]) != raw:
                raise ValueError('history hash collision; refusing to merge')
            return event, False
        if event['parent'] != ZERO:
            parent = self.db.execute('SELECT sequence FROM events WHERE campaign=? AND head=?', (campaign, event['parent'])).fetchone()
            if not parent or parent[0] + 1 != event['seq']:
                raise ValueError('missing or nonconsecutive parent history; restore the matching sidecar')
        elif event['seq'] != 1:
            raise ValueError('non-root event without history')
        with self.db:
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?)', (campaign, event['head'], event['parent'], event['seq'], raw))
        return event, True

    def walk(self, campaign, current):
        while current != ZERO:
            row = self.db.execute('SELECT raw FROM events WHERE campaign=? AND head=?', (campaign, current)).fetchone()
            if not row:
                raise ValueError('history checkpoint missing; restore the matching sidecar')
            event = unpack_event(bytes(row[0]))
            yield event
            current = event['parent']

    def counts(self, campaign, current, identity):
        counts = Counter()
        for event in self.walk(campaign, current):
            if event['identity'] == identity and event['kind'] == 1:
                counts[str(event['donor'])] += 1
        return dict(counts)

    def latest_levels(self, campaign, current):
        result = {}
        for event in self.walk(campaign, current):
            if event['kind'] in (2, 3) and event['identity'] not in result:
                result[event['identity']] = event
        return result

    def close(self):
        self.db.close()

    def essence(self,campaign,current,identity,catalog):
        from .recipe import validate_spending,ev_totals
        earned,spent,pending=Counter(),{},{}
        open_transaction=False
        multiplier=1 # Existing history was earned/applied at native yields.
        latest=None
        for event in reversed(list(self.walk(campaign,current))):
            if event['identity']!=identity:continue
            kind=event['kind']
            if kind==1:
                earned[str(event['donor'])]+=1
            elif kind==6:
                new_multiplier=event['reason'] or 1
                if new_multiplier!=multiplier and (spent or multiplier==3):
                    raise ValueError('essence rules require migration before spending')
                multiplier=new_multiplier
                pending={};open_transaction=True
            elif kind in (4,7):
                if not open_transaction:raise ValueError('essence spend outside a transaction')
                donor=str(event['donor']);pending[donor]=pending.get(donor,0)+(event['reason'] if kind==4 else -event['reason'])
                available={k:n-spent.get(k,0) for k,n in earned.items()}
                validate_spending(available,spent,pending,catalog,multiplier)
            elif kind==5:
                if not open_transaction or not any(pending.values()):
                    raise ValueError('empty or missing essence transaction')
                available={k:n-spent.get(k,0) for k,n in earned.items()}
                spent,_=validate_spending(available,spent,pending,catalog,multiplier)
                pending={};open_transaction=False;latest=event
            elif kind==8:
                if multiplier!=1:raise ValueError('essence migration already completed')
                spent={};pending={};open_transaction=False;multiplier=3;latest=event
        return {'earned':dict(earned),'spent':spent,'pending':pending,'open':open_transaction,
                'available':{k:n-spent.get(k,0) for k,n in earned.items() if n>spent.get(k,0)},
                'ev_totals':ev_totals(spent,catalog,multiplier),'multiplier':multiplier,'latest':latest}
