"""Mots surreprésentés dans les sous-titres par rapport au français moderne.

Usage :
    uvx --with wordfreq python -I frequencies.py "sous-titres/Perceval le Gallois (1978).fr.srt"

Compare la fréquence de chaque mot du film à sa fréquence en français courant (paquet wordfreq)
et affiche les mots, mots-outils et formules qui ont servi à la section 4.4 du skill.
La Passion en latin (après 2:09:20) est exclue. Quelques erreurs récurrentes de la
reconnaissance vocale sont regroupées avant le comptage (« mout » -> « moult », etc.).
"""
import math
import re
import sys
from collections import Counter

from wordfreq import word_frequency

CUT = 2 * 3600 + 9 * 60 + 20

srt = open(sys.argv[1], encoding="utf-8").read().replace("\r", "")
lines = []
for block in srt.strip().split("\n\n"):
    parts = block.split("\n")
    if len(parts) < 3:
        continue
    h, m, s = parts[1].split(" --> ")[0].replace(",", ".").split(":")
    if int(h) * 3600 + int(m) * 60 + float(s) < CUT:
        lines.append(" ".join(parts[2:]))
text = " ".join(lines).lower().replace("’", "'")

for a, b in [(r"\bmou?[dt]e?s?\b(?=\s+(volontiers|bon|bonne|belle|grand|courtoise|fort|joie|triste))", "moult"),
             (r"\bmout\b|\bmoud\b|\bmoute\b|\bmoudre\b|\bmaule\b|\bmoul\b", "moult"),
             (r"\bprud ?hom+e?\b|\bprudom\b|\bprud'homme\b", "prud'homme"),
             (r"\bdouze ami", "doux ami"), (r"\bdoucire\b", "doux sire"), (r"\bbeaucire\b", "beau sire"),
             (r"\bn?oxi\w*", "occire"), (r"\baubert\b", "haubert"), (r"\bsir\b", "sire"), (r"\bcire\b", "sire")]:
    text = re.sub(a, b, text)

ELIDED = ("l", "d", "qu", "n", "s", "c", "j", "m", "t", "jusqu", "lorsqu", "puisqu")
words = re.findall(r"[a-zàâäéèêëîïôöùûüœæç]+(?:'[a-zàâäéèêëîïôöùûüœæç]+)?", text)
words = [w.split("'")[-1] if w.split("'")[0] in ELIDED else w for w in words]
N = len(words)
c = Counter(words)
print(f"{N} mots\n")

print("Mots les plus surreprésentés (au moins 6 occurrences), rapport à la fréquence moderne :")
rows = sorted(((k / N) / max(word_frequency(w, "fr"), 1e-7), k, w) for w, k in c.items() if k >= 6 and len(w) >= 2)
for ratio, k, w in rows[::-1][:80]:
    print(f"  {w:14s} {k:4d}  x{ratio:7.0f}")

print("\nMots-outils (occurrences, pour 100 mots, rapport) :")
for w in "si ni car tant jamais devant ainsi nul nulle or point mie onc lors certes céans dit fut vit fit prit vint irai diras".split():
    k = c.get(w, 0)
    print(f"  {w:8s} {k:4d}  {100 * k / N:5.2f}  x{(k / N) / max(word_frequency(w, 'fr'), 1e-7):6.1f}")

STOP = set("de la le les et à un une des du en que qui il elle ne se sa son ses ce je vous tu me te lui "
           "pour par sur au aux est a pas plus mais si ou dans".split())
print("\nFormules fréquentes (au moins 5 occurrences) :")
for n in (3, 2):
    grams = Counter(tuple(words[i:i + n]) for i in range(N - n + 1))
    for g, k in grams.most_common(400):
        if k >= 5 and sum(x not in STOP for x in g) >= 2:
            print(f"  {' '.join(g):28s} {k}")
