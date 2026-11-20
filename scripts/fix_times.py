"""Repair degenerate Qwen forced-aligner timings using Parakeet word times as anchors.

Usage: python fix_times.py qwen_words.json parakeet.json out.json
A Qwen word is degenerate if it lasts > MAX_WORD s or sits in a run of
zero-length words. Those take the matched Parakeet word's times; unmatched
ones are interpolated between the nearest trusted neighbours.
"""
import difflib
import json
import re
import sys
import unicodedata

MAX_WORD = 2.5
PUNCT = set(".,;:!?…-")


def norm(w):
    w = unicodedata.normalize("NFKD", w.lower())
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", w)


q = json.load(open(sys.argv[1]))
pw, cur = [], None
for s in json.load(open(sys.argv[2]))["sentences"]:
    for t in s["tokens"]:
        txt = t["text"]
        if not txt.strip():
            cur = None
            continue
        if txt.startswith(" ") or cur is None:
            cur = {"text": txt.strip(), "start": t["start"], "end": t["end"]}
            pw.append(cur)
        else:
            cur["text"] += txt
            if not all(c in PUNCT for c in txt):
                cur["end"] = t["end"]

qa, pa = [norm(w["text"]) for w in q], [norm(w["text"]) for w in pw]
anchor = {}
for b in difflib.SequenceMatcher(None, qa, pa, autojunk=False).get_matching_blocks():
    for k in range(b.size):
        if qa[b.a + k]:
            anchor[b.a + k] = b.b + k

dur = [w["end"] - w["start"] for w in q]
zero = [d < 0.01 for d in dur]
bad = [dur[i] > MAX_WORD or (zero[i] and ((i > 0 and zero[i - 1]) or (i + 1 < len(q) and zero[i + 1])))
       for i in range(len(q))]

out = [dict(w) for w in q]
fixed_anchor = 0
for i in range(len(q)):
    if bad[i] and i in anchor:
        p = pw[anchor[i]]
        out[i]["start"], out[i]["end"] = p["start"], p["end"]
        bad[i] = False
        fixed_anchor += 1

# interpolate the remaining bad runs between trusted neighbours
i, interp = 0, 0
while i < len(out):
    if not bad[i]:
        i += 1
        continue
    j = i
    while j < len(out) and bad[j]:
        j += 1
    lo = out[i - 1]["end"] if i > 0 else out[i]["start"]
    hi = out[j]["start"] if j < len(out) else out[j - 1]["end"]
    if hi < lo:
        hi = lo
    lens = [max(len(out[k]["text"]), 1) for k in range(i, j)]
    tot, acc = sum(lens), 0
    for k, L in zip(range(i, j), lens):
        out[k]["start"] = lo + (hi - lo) * acc / tot
        acc += L
        out[k]["end"] = min(lo + (hi - lo) * acc / tot, out[k]["start"] + MAX_WORD)
        interp += 1
    i = j

# monotonic starts
for k in range(1, len(out)):
    if out[k]["start"] < out[k - 1]["start"]:
        out[k]["start"] = out[k - 1]["start"]
    out[k]["end"] = max(out[k]["end"], out[k]["start"])

json.dump(out, open(sys.argv[3], "w"), ensure_ascii=False)
print(f"{len(q)} words, {len(anchor)} matched to parakeet, "
      f"{fixed_anchor} degenerate fixed from anchors, {interp} interpolated")
