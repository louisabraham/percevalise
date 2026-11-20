"""Rebuild subtitle cues from parakeet-mlx token timestamps.

Usage: python words_to_srt.py mots.json sortie.srt  (JSON parakeet-mlx, mlx-whisper ou qwen_transcribe.py)
"""
import json
import sys

MAX_CHARS = 84      # two lines of 42
MAX_DUR = 6.5
GAP_BREAK = 1.0     # silence between words that forces a new cue
LINE = 42
PAD = 0.6           # keep text on screen a bit after speech ends
MIN_DUR = 1.0

src, dst = sys.argv[1], sys.argv[2]
d = json.load(open(src))

# tokens -> words (a token starting with a space opens a new word)
PUNCT_ONLY = set(".,;:!?…-")

words = []
new_word = True
if isinstance(d, list):                       # qwen: [{"text","start","end"}]
    words = [dict(w) for w in d]
elif "segments" in d:                         # whisper json with word timestamps
    words = [{"text": w["word"].strip(), "start": w["start"], "end": w["end"]}
             for seg in d["segments"] for w in seg.get("words", []) if w["word"].strip()]
for s in (d.get("sentences", []) if isinstance(d, dict) else []):
    for t in s["tokens"]:
        txt = t["text"]
        if not txt.strip():          # bare space token: next token opens a word
            new_word = True
            continue
        if txt.startswith(" ") or new_word or not words:
            words.append({"text": txt.strip(), "start": t["start"], "end": t["end"]})
        else:
            words[-1]["text"] += txt
            # punctuation is stamped late (right before the next word); don't
            # let it stretch the word it closes
            if not all(c in PUNCT_ONLY for c in txt):
                words[-1]["end"] = t["end"]
        new_word = False


def is_punct(w):
    return all(c in PUNCT_ONLY for c in w)


# glue punctuation-only "words" onto the previous word (without its timing)
merged = []
for w in words:
    if is_punct(w["text"]) and merged:
        merged[-1]["text"] += w["text"]
    elif not is_punct(w["text"]):
        merged.append(w)
words = merged


def text_of(ws):
    return " ".join(w["text"] for w in ws)


def verse_start(prev, w):
    """Capitalised word right after an unpunctuated one: a new verse line."""
    return w["text"][:1].isupper() and prev["text"][-1] not in ".?!…,;:"


def soft_break_after(ws, i):
    return ws[i]["text"][-1] in ",;:" or (i + 1 < len(ws) and verse_start(ws[i], ws[i + 1]))


cues, cur = [], []
for w in words:
    if cur:
        n_verse = sum(verse_start(a, b) for a, b in zip(cur, cur[1:]))
        gap = w["start"] - cur[-1]["end"]
        too_long = (len(text_of(cur + [w])) > MAX_CHARS
                    or w["end"] - cur[0]["start"] > MAX_DUR)
        ends_sentence = w["text"][-1] in ".?!…"
        slight = (len(text_of(cur + [w])) <= MAX_CHARS + 15
                  and w["end"] - cur[0]["start"] <= MAX_DUR + 2)
        mid_line = cur[-1]["text"][-1] not in ".?!…,;:" and not w["text"][:1].isupper()
        if (gap > (3.0 if mid_line else GAP_BREAK) or cur[-1]["text"][-1] in ".?!…"
                or (n_verse >= 1 and verse_start(cur[-1], w))):   # keep couplets
            cues.append(cur)
            cur = []
        elif too_long and not (ends_sentence and slight):
            # back off to the last comma / verse start in the second half, if any
            cut = None
            for i in range(len(cur) - 1, len(cur) // 2 - 1, -1):
                if soft_break_after(cur, i):
                    cut = i + 1
                    break
            if cut and cut < len(cur):
                cues.append(cur[:cut])
                cur = cur[cut:]
            else:
                cues.append(cur)
                cur = []
    cur.append(w)
if cur:
    cues.append(cur)


def wrap(t):
    if len(t) <= LINE:
        return t
    ws = t.split(" ")
    best = None
    for i in range(1, len(ws)):
        a, b = " ".join(ws[:i]), " ".join(ws[i:])
        score = max(len(a), len(b))
        if a[-1] in ",;:" or (b[:1].isupper() and a[-1] not in ".?!…"):
            score -= 12          # prefer splitting at a comma or verse line
        if max(len(a), len(b)) > LINE + 8:
            score += 100
        if best is None or score < best[0]:
            best = (score, a, b)
    return best[1] + "\n" + best[2]


def ts(x):
    ms = int(round(x * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


out = []
prev_ended = True
for i, c in enumerate(cues):
    start = c[0]["start"]
    end = max(c[-1]["end"] + PAD, start + MIN_DUR)
    if i + 1 < len(cues):
        end = min(end, cues[i + 1][0]["start"] - 0.05)
    end = max(end, c[-1]["end"])
    t = text_of(c)
    if prev_ended:
        t = t[0].upper() + t[1:]
    prev_ended = t[-1] in ".?!…"
    out.append(f"{i + 1}\n{ts(start)} --> {ts(end)}\n{wrap(t)}\n")

open(dst, "w", encoding="utf-8").write("\n".join(out))
print(f"{len(words)} words -> {len(cues)} cues")
