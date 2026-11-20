"""Densité du vocabulaire du film dans les réécritures (mots de la section 4.4 du skill).

Usage : python density.py sorties/*.txt
"""
import json
import sys

from score import parse, tokens

FILM = set("sire beau beaux bel moult occire occis occit merci car ni nul nulle tant si ainsi or devant "
           "messire foi dieu volontiers honte".split())
RARE = set("céans lors mie onc point tantôt certes issit issir issu ouïr ouit quérir mander bailler gît "
           "chut nenni oncques moutier".split())
ROLE = set("valet valets prud'homme prudhomme pucelle pucelles vavasseur sénéchal".split())


def dens(lines):
    t = [w.rstrip("'") for w in tokens(" ".join(lines))]
    n = len(t)
    film = sum(w in FILM for w in t) + " ".join(t).count("de par")
    return n, 100 * film / n, 100 * sum(w in RARE for w in t) / n, sum(w in ROLE for w in t)


orig = json.load(open("originals.json"))
plain = json.load(open("plains.json"))
print(f"{'version':16s} {'mots':>5s} {'film/100':>9s} {'rares/100':>9s} {'rôles':>6s}")
runs = [("original", [l for v in orig.values() for l in v]), ("entrée (prose)", list(plain.values()))]
runs += [(f.rsplit("/", 1)[-1][:-4], [l for v in parse(f).values() for l in v]) for f in sys.argv[1:]]
for name, lines in runs:
    n, f, r, ro = dens(lines)
    print(f"{name:16s} {n:5d} {f:9.1f} {r:9.1f} {ro:6d}")
