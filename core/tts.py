"""Synthèse vocale : edge-tts (gratuit, sans clé) ou Gemini.

edge-tts utilise les voix neuronales Microsoft du navigateur Edge. Il renvoie du MP3
et l'instant où chaque mot est prononcé, ce qui sert à caler les tracés sur la voix.
"""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass, field

VOIX_EDGE = {
    "Henri (homme)": "fr-FR-HenriNeural",
    "Rémy (homme, multilingue)": "fr-FR-RemyMultilingualNeural",
    "Denise (femme)": "fr-FR-DeniseNeural",
    "Vivienne (femme, multilingue)": "fr-FR-VivienneMultilingualNeural",
    "Antoine (homme, Canada)": "fr-CA-AntoineNeural",
}
VOIX_EDGE_DEFAUT = "fr-FR-HenriNeural"
DEBIT_DEFAUT = "+8%"


@dataclass
class Audio:
    donnees: bytes
    format: str                     # "mp3" ou "wav"
    duree: float                    # secondes
    mots: list[tuple[str, float]] = field(default_factory=list)  # (mot, début en s), si connu

    @property
    def mime(self) -> str:
        return "audio/mpeg" if self.format == "mp3" else "audio/wav"


def duree_mp3(donnees: bytes) -> float:
    from mutagen.mp3 import MP3

    return float(MP3(io.BytesIO(donnees)).info.length)


def edge(texte: str, voix: str = VOIX_EDGE_DEFAUT, debit: str = DEBIT_DEFAUT, essais: int = 3) -> Audio:
    import edge_tts

    async def go() -> Audio:
        com = edge_tts.Communicate(texte, voix, rate=debit, boundary="WordBoundary")
        morceaux, mots = [], []
        async for m in com.stream():
            if m["type"] == "audio":
                morceaux.append(m["data"])
            elif m["type"] == "WordBoundary":
                mots.append((m["text"], m["offset"] / 1e7))
        donnees = b"".join(morceaux)
        if not donnees:
            raise RuntimeError("edge-tts n'a renvoyé aucun audio")
        return Audio(donnees, "mp3", duree_mp3(donnees), mots)

    erreur = None
    for i in range(essais):
        try:
            return asyncio.run(go())
        except Exception as e:  # noqa: BLE001
            erreur = e
            import time
            time.sleep(1 + 2 * i)
    raise RuntimeError(f"edge-tts : {erreur}")


def concatener(morceaux: list[Audio]) -> Audio | None:
    """Assemble les morceaux d'une réponse (même format). Les trames MP3 se mettent bout à bout."""
    morceaux = [m for m in morceaux if m and m.donnees]
    if not morceaux:
        return None
    if all(m.format == "mp3" for m in morceaux):
        return Audio(b"".join(m.donnees for m in morceaux), "mp3", sum(m.duree for m in morceaux))
    from core.audio import concatener_wav, duree_wav

    wav = concatener_wav([m.donnees for m in morceaux if m.format == "wav"])
    return Audio(wav, "wav", duree_wav(wav)) if wav else None
