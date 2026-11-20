"""Cross-model agreement per window (proxy for accuracy, no ground truth).

Usage: python agree.py parakeet.json whisper.json qwen_words.json [window_s]
"""
import difflib
import json
import re
import sys
import unicodedata

WIN = float(sys.argv[4]) if len(sys.argv) > 4 else 60.0


def norm(w):
    w = unicodedata.normalize("NFKD", w.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z']", "", w).replace("'", "")


def parakeet(path):
    out, cur = [], None
    for s in json.load(open(path))["sentences"]:
        for t in s["tokens"]:
            if t["text"].startswith(" ") or cur is None:
                cur = {"text": t["text"].strip(), "start": t["start"]}
                out.append(cur)
            else:
                cur["text"] += t["text"]
    return out


def whisper(path):
    return [{"text": w["word"].strip(), "start": w["start"]}
            for s in json.load(open(path))["segments"] for w in s.get("words", [])]


def qwen(path):
    return json.load(open(path))


models = {"parakeet": parakeet(sys.argv[1]), "whisper": whisper(sys.argv[2]), "qwen": qwen(sys.argv[3])}
for k in models:
    models[k] = [(norm(w["text"]), w["start"]) for w in models[k] if norm(w["text"])]

end = max(ws[-1][1] for ws in models.values())
rows = []
t = 0.0
while t < end:
    win = {k: [w for w, s in ws if t <= s < t + WIN] for k, ws in models.items()}
    sup = {}
    for k, ws in win.items():
        hit = [False] * len(ws)
        for o, os_ in win.items():
            if o == k:
                continue
            for b in difflib.SequenceMatcher(None, ws, os_, autojunk=False).get_matching_blocks():
                for i in range(b.a, b.a + b.size):
                    hit[i] = True
        sup[k] = (sum(hit), len(ws))
    rows.append((t, sup))
    t += WIN

tot = {k: [0, 0] for k in models}
for t, sup in rows:
    for k, (h, n) in sup.items():
        tot[k][0] += h
        tot[k][1] += n
print("overall: share of a model's words confirmed by >=1 other model")
for k, (h, n) in tot.items():
    print(f"  {k:9s} {h / max(n, 1):.1%} of {n} words")

# hardest windows: low mean support, enough words
hard = sorted((r for r in rows if sum(n for _, n in r[1].values()) > 60),
              key=lambda r: sum(h for h, _ in r[1].values()) / sum(n for _, n in r[1].values()))
print("\nhardest windows (start, per-model support):")
for t, sup in hard[:12]:
    print(f"  {int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}  " +
          "  ".join(f"{k}={h}/{n}" for k, (h, n) in sup.items()))
json.dump([(t, sup) for t, sup in rows], open("agree_rows.json", "w"))
