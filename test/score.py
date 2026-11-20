"""Score Perceval-style rewrites against held-out originals.

Usage: python score.py originals.json plains.json out1.txt [out2.txt ...]
Each out*.txt has passages introduced by lines '=== N ==='.
"""
import json
import re
import sys
import unicodedata
from collections import Counter

VOW = "aeiouyàâäéèêëîïôöùûüœæ"
H_ASP = ("haubert", "heaume", "honte", "hont", "hâte", "haut", "hardi", "hors", "haine", "haï",
         "hameau", "hache", "harnais", "héros", "hurl", "hutte", "hanche", "harpe", "hasard",
         "henn", "hêtre", "halte", "hargn", "hideu", "heurt", "huit", "hibou", "haie", "hang", "hall")
NON_VERBAL_ENT = {"souvent", "vent", "dent", "gent", "cent", "lent", "sent", "content", "présent",
                  "parent", "serpent", "argent", "accident", "couvent", "sergent", "dolent", "absent",
                  "talent", "torrent", "comment", "moment", "prudent", "ardent", "évident", "rent"}
VERBAL_MENT = {"aiment", "dorment", "ferment", "sèment", "affirment", "arment", "calment", "priment"}


def tokens(line):
    line = line.lower().replace("’", "'")
    line = re.sub(r"[«»—–\-]", " ", line)
    return re.findall(r"[a-zàâäéèêëîïôöùûüœæç]+'?", line)


def prep(w):
    w = w.rstrip("'")
    w = w.replace("qu", "k")
    w = re.sub(r"gu(?=[eéèêiy])", "g", w)
    return w


def emuet(w):
    if re.search(r"(ai|oi)ent$|[vt]ient$", w):
        return None
    if w.endswith("ent") and len(w) > 3:
        if w in NON_VERBAL_ENT:
            return None
        if w.endswith("ment") and w not in VERBAL_MENT:
            return None
        return "ent"
    if w.endswith("es") and len(w) > 3:
        return "es"
    if w.endswith("e"):
        return "e"
    return None


def groups(s):
    n = 0
    for m in re.finditer(f"[{VOW}]+", s):
        r, start = m.group(), m.start()
        c = 1
        c += sum(1 for k, ch in enumerate(r) if ch in "ïüë" and k > 0)
        c += sum(1 for k, ch in enumerate(r) if ch == "y" and 0 < k < len(r) - 1)
        c += len(re.findall(r"ou(?=[aeéèâ])", r))
        c += len(re.findall(r"é(?=[aeiouéèâ])", r))
        c += len(re.findall(r"(?<![oeaœ])u(?=[aéèâo])", r))
        pre = s[max(0, start - 2):start]
        if re.match(r"i[aeéèo]", r) and len(pre) == 2 and pre[0] not in VOW and pre[1] in "rl":
            c += 1
        n += c
    return n


def starts_vowel(w):
    if w[0] in VOW:
        return True
    return w[0] == "h" and not w.startswith(H_ASP)


def count_line(line):
    ws = [prep(w) for w in tokens(line)]
    ws = [w for w in ws if w]
    total = 0
    for i, w in enumerate(ws):
        m = emuet(w)
        stem = w[: -len(m)] if m else w
        n = groups(stem)
        if m and i < len(ws) - 1:
            if not (m == "e" and starts_vowel(ws[i + 1])):
                n += 1
        total += n
    return total


def fold(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def rkey(line):
    ts = tokens(line)
    if not ts:
        return ""
    w = prep(ts[-1])
    m = emuet(w)
    s = w[: -len(m)] if m else w
    if re.search(r"(er|ez)$", s) and s not in {"fer", "mer", "cher", "hiver", "enfer", "fier", "hier"}:
        s = s[:-2] + "é"
    s = re.sub(r"et$", "è", s)
    s = re.sub(r"(?<=[aeiouéèêàâîôûy])[stxdzp]+$", "", s)
    s = re.sub(r"(?<=[aeiouéèêàâîôû])(nts|nds|ngs|ncs|nt|nd|ng|nc|ns)$", "n", s)
    for a, b in (("eau", "o"), ("au", "o"), ("ô", "o"), ("aî", "è"), ("ai", "è"), ("ei", "è"),
                 ("ê", "è"), ("oi", "W"), ("ou", "U"), ("œu", "Ø"), ("eu", "Ø"), ("î", "i"), ("û", "u")):
        s = s.replace(a, b)
    s = re.sub(r"[ae]m(?![aeiouè])|[ae]n(?![aeiouè])", "Ã", s)
    s = re.sub(r"(?<![iI])(?:in|im|yn|un)(?![aeiouè])", "Ẽ", s)
    s = re.sub(r"ièn(?![aeiouè])|ien(?![aeiouè])", "jẼ", s)
    s = re.sub(r"on(?![aeiouè])|om(?![aeiouè])", "Õ", s)
    m2 = re.search(r"[aeiouyéèWUØÃẼÕ][^aeiouyéèWUØÃẼÕ]*$", s)
    return (m2.group() if m2 else s) + ("·f" if m else "")


def rhymes(a, b):
    ka, kb = rkey(a), rkey(b)
    return ka.replace("·f", "") == kb.replace("·f", "") and ka != ""


STOP = set("""le la les un une des de du et à au aux en dans par pour sur que qui quoi ne pas plus
il ils elle elles lui leur se sa son ses ce cet cette ces mon ma mes ton ta tes on nous vous je tu me te
est sont a ont fut être avoir tout tous toute si mais ou où car comme bien très avec sans""".split())


def norm_words(text):
    return [fold(w.rstrip("'")) for w in tokens(text)]


def content(text):
    return {w for w in norm_words(text) if len(w) >= 4 and w not in STOP}


def chrf(hyp, ref, n=6, beta=2):
    h = re.sub(r"\s+", " ", fold(" ".join(tokens(hyp))))
    r = re.sub(r"\s+", " ", fold(" ".join(tokens(ref))))
    ps, rs = [], []
    for k in range(1, n + 1):
        hc = Counter(h[i:i + k] for i in range(len(h) - k + 1))
        rc = Counter(r[i:i + k] for i in range(len(r) - k + 1))
        ov = sum((hc & rc).values())
        ps.append(ov / max(sum(hc.values()), 1))
        rs.append(ov / max(sum(rc.values()), 1))
    p, rr = sum(ps) / n, sum(rs) / n
    return 0 if p + rr == 0 else (1 + beta ** 2) * p * rr / (beta ** 2 * p + rr) * 100


def parse(path):
    out, cur = {}, None
    for line in open(path):
        m = re.match(r"\s*=+\s*(\d)\s*=+", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur and line.strip() and not line.strip().startswith("```"):
            out[cur].append(line.strip())
    return out


def stats(lines, orig):
    syl = [count_line(l) for l in lines]
    dedup = [l for i, l in enumerate(lines) if i == 0 or norm_words(l) != norm_words(lines[i - 1])]
    pairs = [(dedup[i], dedup[i + 1]) for i in range(0, len(dedup) - 1, 2)]
    rh = sum(rhymes(a, b) for a, b in pairs)
    otext, htext = " ".join(orig), " ".join(lines)
    oc = content(otext)
    rwords = {norm_words(l)[-1] for l in orig}
    hr = {norm_words(l)[-1] for l in lines if norm_words(l)}
    oset = {" ".join(norm_words(l)) for l in orig}
    exact = sum(1 for l in lines if " ".join(norm_words(l)) in oset)
    def jac(a, b):
        a, b = set(norm_words(a)), set(norm_words(b))
        return len(a & b) / max(len(a | b), 1)
    near = sum(1 for o in orig if any(jac(o, l) >= 0.5 for l in lines))
    return dict(n=len(lines), oct=sum(s == 8 for s in syl), syl=syl, pairs=len(pairs), rh=rh,
                chrf=chrf(htext, otext), cw=len(oc & content(htext)) / len(oc),
                rw=len(rwords & hr) / len(rwords), exact=exact, near=near)


if __name__ == "__main__":
    orig = json.load(open(sys.argv[1]))
    plain = json.load(open(sys.argv[2]))
    print("calibration on originals:")
    for k, ls in orig.items():
        s = stats(ls, ls)
        bad = [(l, c) for l, c in zip(ls, s["syl"]) if c != 8]
        print(f"  {k}: {s['oct']}/{s['n']} octosyllables, {s['rh']}/{s['pairs']} couplets rhyme", bad or "")
    rows = {"plain (input)": {k: stats([plain[k]], orig[k]) for k in orig}}
    for p in sys.argv[3:]:
        o = parse(p)
        rows[p.rsplit("/", 1)[-1].replace(".txt", "")] = {k: stats(o.get(k, []), orig[k]) for k in orig}
    print(f"\n{'run':16s} {'lines':>5s} {'8-syl':>7s} {'rhyme':>7s} {'chrF':>6s} {'content':>8s} {'rhymeW':>7s} {'exact':>5s} {'near':>5s}")
    for name, d in rows.items():
        n = sum(v["n"] for v in d.values())
        o8 = sum(v["oct"] for v in d.values())
        pr = sum(v["pairs"] for v in d.values())
        rh = sum(v["rh"] for v in d.values())
        cf = sum(v["chrf"] for v in d.values()) / len(d)
        cw = sum(v["cw"] for v in d.values()) / len(d)
        rw = sum(v["rw"] for v in d.values()) / len(d)
        ex = sum(v["exact"] for v in d.values())
        nr = sum(v["near"] for v in d.values())
        verse = name != "plain (input)"
        print(f"{name:16s} {n:5d} {f'{o8/n:.0%}' if verse else '-':>7s} {f'{rh/max(pr,1):.0%}' if verse else '-':>7s} "
              f"{cf:6.1f} {cw:8.0%} {f'{rw:.0%}' if verse else '-':>7s} {ex:5d} {nr:5d}")
