"""Petits utilitaires audio (WAV PCM 16 bits)."""
from __future__ import annotations

import io
import wave


def pcm_vers_wav(pcm: bytes, taux: int = 24000, canaux: int = 1, largeur: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(canaux)
        w.setsampwidth(largeur)
        w.setframerate(taux)
        w.writeframes(pcm)
    return buf.getvalue()


def assurer_wav(donnees: bytes, mime: str | None = None) -> bytes:
    """Renvoie un WAV : les modèles TTS renvoient soit du WAV, soit du PCM brut 24 kHz."""
    if donnees[:4] == b"RIFF":
        return donnees
    taux = 24000
    if mime and "rate=" in mime:
        try:
            taux = int(mime.split("rate=")[1].split(";")[0])
        except ValueError:
            pass
    return pcm_vers_wav(donnees, taux)


def duree_wav(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav), "rb") as w:
        return w.getnframes() / float(w.getframerate() or 1)


def silence_wav(secondes: float, taux: int = 24000) -> bytes:
    return pcm_vers_wav(b"\x00\x00" * int(secondes * taux), taux)


def concatener_wav(morceaux: list[bytes]) -> bytes | None:
    morceaux = [m for m in morceaux if m]
    if not morceaux:
        return None
    params, frames = None, []
    for m in morceaux:
        with wave.open(io.BytesIO(m), "rb") as w:
            p = (w.getnchannels(), w.getsampwidth(), w.getframerate())
            if params is None:
                params = p
            elif p != params:
                continue
            frames.append(w.readframes(w.getnframes()))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(params[0])
        w.setsampwidth(params[1])
        w.setframerate(params[2])
        w.writeframes(b"".join(frames))
    return buf.getvalue()
