"""Composant Streamlit bidirectionnel : le tableau animé (HTML/SVG/JS sans build)."""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit.components.v1 as components

from core.audio import duree_wav

_composant = components.declare_component("tableau_maths", path=str(Path(__file__).parent / "frontend"))


def tableau(lecon: dict, lecon_id: str, reponse: dict | None = None, reponse_id: str | None = None,
            nouvelle_reponse: bool = False, audio: bytes | None = None,
            voix: list[bytes | None] | None = None, voix_id: str | None = None, envoyer_voix: bool = True,
            voix_statut: str | None = None,
            key: str = "tableau"):
    """Affiche le tableau. Renvoie le dernier événement envoyé par le lecteur
    (pause, question, reprise) avec la position dans la leçon, ou None.

    audio : WAV de la réponse orale, joué par le tableau en même temps que la scène.
    Il n'est envoyé qu'avec une nouvelle réponse, pour ne pas renvoyer ~1 Mo à chaque exécution.

    voix : voix off de la leçon, un WAV par étape (None si absent). voix_id l'identifie ;
    avec envoyer_voix=False, seul l'identifiant part (le tableau a déjà l'audio)."""
    audio_b64 = base64.b64encode(audio).decode() if audio else None
    duree = duree_wav(audio) if audio else 0
    return _composant(lecon=lecon, lecon_id=lecon_id, reponse=reponse, reponse_id=reponse_id,
                      nouvelle_reponse=nouvelle_reponse, audio=audio_b64, duree_audio=duree,
                      voix=[base64.b64encode(v).decode() if v else None for v in voix] if voix and envoyer_voix else None,
                      voix_durees=[duree_wav(v) if v else 0 for v in voix] if voix else None,
                      voix_id=voix_id if voix else None, voix_statut=voix_statut, key=key, default=None)
