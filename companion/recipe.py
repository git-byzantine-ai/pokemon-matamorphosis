"""Essence recipes: only committed EV contributions influence the artwork."""
import hashlib
import json

VERSION = 3
ESSENCE_MULTIPLIER = 3
MAX_STAT_EVS = 255
MAX_TOTAL_EVS = 510
MIN_ART_EVS = 100
STAT_NAMES = ('HP','Attack','Defense','Speed','Sp. Atk','Sp. Def')


def ev_totals(counts,catalog,multiplier=ESSENCE_MULTIPLIER):
    if type(multiplier) is not int or multiplier not in (1,ESSENCE_MULTIPLIER):
        raise ValueError('unsupported essence multiplier')
    totals = [0]*6
    for species,n in counts.items():
        if type(n) is not int or n<0 or str(species) not in catalog:
            raise ValueError('essence quantities must be nonnegative integers for known species')
        yield_ = catalog[str(species)]['ev_yield']
        if n and not sum(yield_):
            raise ValueError('zero-EV essence cannot be spent')
        for i,value in enumerate(yield_):totals[i]+=n*value*multiplier
    return totals


def validate_spending(available,spent,addition,catalog,multiplier=ESSENCE_MULTIPLIER):
    result = dict(spent)
    for species,n in addition.items():
        species=str(species)
        if type(n) is not int or species not in catalog:
            raise ValueError("essence changes must be integers for known species")
        if n < -spent.get(species,0):raise ValueError("cannot remove more essence than is applied")
        if n>available.get(species,0):raise ValueError('not enough unspent essence')
        result[species]=result.get(species,0)+n
    result={k:n for k,n in result.items() if n}
    totals=ev_totals(result,catalog,multiplier)
    if max(totals)>MAX_STAT_EVS or sum(totals)>MAX_TOTAL_EVS:
        raise ValueError('essence exceeds a stat or total EV limit')
    return result,totals


def weights(counts,catalog,multiplier=ESSENCE_MULTIPLIER):
    totals=ev_totals(counts,catalog,multiplier)
    if max(totals)>MAX_STAT_EVS or sum(totals)>MAX_TOTAL_EVS:
        raise ValueError('essence exceeds a stat or total EV limit')
    donors={str(k):.75*n*sum(catalog[str(k)]['ev_yield'])*multiplier/MAX_TOTAL_EVS for k,n in counts.items() if n}
    return 1-.75*sum(totals)/MAX_TOTAL_EVS,donors


def make_recipe(identity,level,species,counts,catalog,shiny=False,multiplier=ESSENCE_MULTIPLIER):
    if type(level) is not int or not 1<=level<=100 or str(species) not in catalog:
        raise ValueError('invalid level or base species')
    base,donors=weights(counts,catalog,multiplier)
    stages={str(species):1.}
    shares={str(species):base}
    for key,weight in donors.items():shares[key]=shares.get(key,0)+weight
    return {'version':VERSION,'essence_multiplier':multiplier,'identity':identity,'level':level,'species':species,
            'shiny':bool(shiny),'counts':dict(sorted((str(k),v) for k,v in counts.items() if v)),
            'ev_totals':ev_totals(counts,catalog,multiplier),'lineage_mass':base,'lineage':stages,
            'shares':{k:v for k,v in sorted(shares.items()) if v>0}}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
