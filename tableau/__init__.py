"""Composant Streamlit bidirectionnel : le tableau animé (HTML/SVG/JS sans build)."""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit.components.v1 as components


_composant = components.declare_component("tableau_maths", path=str(Path(__file__).parent / "frontend"))


def tableau(lecon: dict, lecon_id: str, reponse: dict | None = None, reponse_id: str | None = None,
            nouvelle_reponse: bool = False, audio: bytes | None = None, audio_mime: str = "audio/wav",
            duree_audio: float = 0,
            key: str = "tableau"):
    """Affiche le tableau. Renvoie le dernier événement envoyé par le lecteur
    (pause, question, reprise) avec la position dans la leçon, ou None.

    audio : réponse orale (WAV ou MP3, voir audio_mime, durée duree_audio), joué par le tableau en même temps que la scène.
    Il n'est envoyé qu'avec une nouvelle réponse, pour ne pas renvoyer ~1 Mo à chaque exécution.

    La voix off de la leçon n'est pas transmise ici : chaque étape de la scène indique son
    fichier audio (medias/<leçon>/NN.wav), que le navigateur charge directement."""
    audio_b64 = base64.b64encode(audio).decode() if audio else None
    return _composant(lecon=lecon, lecon_id=lecon_id, reponse=reponse, reponse_id=reponse_id,
                      nouvelle_reponse=nouvelle_reponse, audio=audio_b64, audio_mime=audio_mime,
                      duree_audio=duree_audio if audio else 0,
                      key=key, default=None)
