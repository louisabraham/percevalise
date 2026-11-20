"""Transcription d'un film avec Qwen3-ASR 1.7B, horodatage mot à mot par Qwen3-ForcedAligner.

Usage (Apple Silicon, via mlx-audio) :
    uvx --from mlx-audio python -I qwen_transcribe.py film.wav mots.json

Écrit une liste JSON de mots {"text", "start", "end"} (ponctuation conservée) et, à côté,
mots_chunks.json avec le texte brut de chaque morceau.

Garde-fous, tous nés d'échecs observés sur ce film :
- budget de jetons proportionnel à la durée du morceau ;
- boucle (« ah ah ah… », taux de compression gzip élevé) -> on refait le morceau en tranches
  de 20 s avec une pénalité de répétition ;
- sur un passage silencieux, le modèle recrache le contexte du prompt -> on refait sans contexte ;
- les répétitions résiduelles (plus de trois fois le même n-gramme) sont écourtées.
"""
import json
import re
import sys
import time
import zlib

import numpy as np
from mlx_audio.stt import load
from mlx_audio.stt.models.qwen3_asr.qwen3_asr import split_audio_into_chunks
from mlx_audio.stt.utils import load_audio

CONTEXT = (
    "Film d'Éric Rohmer, Perceval le Gallois (1978), d'après le Conte du Graal "
    "de Chrétien de Troyes. Texte en vers octosyllabes rimés, dans un français "
    "archaïsant, souvent chanté par un chœur accompagné d'instruments médiévaux. "
    "Noms : Perceval, le roi Arthur, la reine Guenièvre, messire Gauvain, Keu le "
    "sénéchal, Gornemant de Goort, Blanchefleur, Beaurepaire, le Roi Pêcheur, le "
    "Graal, la lance qui saigne, le Chevalier Vermeil, Yonet, Clamadeu des Îles, "
    "Anguingueron, l'Orgueilleux de la Lande, Carduel, Carlion, Escavalon, "
    "Guinganbresil. Vocabulaire : pucelle, demoiselle, vavasseur, destrier, "
    "palefroi, chasseur, haubert, heaume, écu, javelot, chausses, sénéchal, "
    "ermite, messire, céans, moult, oncques."
)
LEAK_MARKERS = ("Rohmer", "octosyllabes", "Vocabulaire", "Noms :", "instruments médiévaux")

SR = 16000
CHUNK = 60.0
SUB = 20.0

wav = np.array(load_audio(sys.argv[1]))
asr = load("mlx-community/Qwen3-ASR-1.7B-bf16")
aligner = load("mlx-community/Qwen3-ForcedAligner-0.6B-bf16")
clean = aligner.aligner_processor.clean_token


def looped(text, dur):
    if not text:
        return False
    ratio = len(text.encode()) / len(zlib.compress(text.encode()))
    return ratio > 2.4 or len(text.split()) > dur * 5


def leaked(text):
    return any(m in text for m in LEAK_MARKERS)


def collapse_runs(text, keep=3):
    toks = text.split()
    key = [re.sub(r"\W", "", t.lower()) for t in toks]
    out, i = [], 0
    while i < len(toks):
        done = False
        for n in range(1, 5):
            reps = 1
            while key[i:i + n] == key[i + reps * n:i + (reps + 1) * n] and i + (reps + 1) * n <= len(toks):
                reps += 1
            if reps > keep:
                out += toks[i:i + keep * n]
                i += reps * n
                done = True
                break
        if not done:
            out.append(toks[i])
            i += 1
    return " ".join(out)


def asr_text(seg, rep=None):
    dur = len(seg) / SR
    kw = dict(language="French", max_tokens=int(dur * 10) + 32, repetition_penalty=rep)
    text = asr.generate(seg, system_prompt=CONTEXT, **kw).text.strip()
    if leaked(text):
        text = asr.generate(seg, system_prompt=None, **kw).text.strip()
        if leaked(text):
            text = ""
    return text


def pieces_for(chunk, off):
    """[(audio, décalage, texte)] pour un morceau, redécoupé s'il boucle."""
    dur = len(chunk) / SR
    text = asr_text(chunk)
    if not looped(text, dur):
        return [(chunk, off, collapse_runs(text))], False
    out = []
    for sub, soff in split_audio_into_chunks(chunk, SR, chunk_duration=SUB):
        out.append((sub, off + soff, collapse_runs(asr_text(sub, rep=1.15))))
    return out, True


chunks = split_audio_into_chunks(wav, SR, chunk_duration=CHUNK)
print(f"{len(chunks)} morceaux", flush=True)

words, log = [], []
t0 = time.time()
for k, (chunk, off) in enumerate(chunks):
    pieces, split = pieces_for(chunk, off)
    if split:
        print(f"  morceau {k} @{off / 60:.1f} min en boucle -> {len(pieces)} tranches", flush=True)
    for audio, poff, text in pieces:
        log.append({"chunk": k, "offset": poff, "dur": len(audio) / SR, "text": text})
        if not text:
            continue
        items = aligner.generate(audio, text=text, language="French").items
        j = 0
        for p in text.split():
            if clean(p) and j < len(items):
                it = items[j]
                words.append({"text": p, "start": poff + it.start_time, "end": poff + it.end_time})
                j += 1
            elif words:
                words[-1]["text"] += p
    if k % 20 == 0:
        print(f"{k}/{len(chunks)} {time.time() - t0:.0f}s", flush=True)

json.dump(words, open(sys.argv[2], "w"), ensure_ascii=False)
json.dump(log, open(sys.argv[2].replace(".json", "_chunks.json"), "w"), ensure_ascii=False, indent=1)
print(f"{len(words)} mots en {time.time() - t0:.0f}s")
