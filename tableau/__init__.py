"""Composant Streamlit bidirectionnel : le tableau animé (HTML/SVG/JS sans build)."""
from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_composant = components.declare_component("tableau_maths", path=str(Path(__file__).parent / "frontend"))


def tableau(lecon: dict, lecon_id: str, reponse: dict | None = None, reponse_id: str | None = None,
            nouvelle_reponse: bool = False, key: str = "tableau"):
    """Affiche le tableau. Renvoie le dernier événement envoyé par le lecteur
    (pause, question, reprise) avec la position dans la leçon, ou None."""
    return _composant(lecon=lecon, lecon_id=lecon_id, reponse=reponse, reponse_id=reponse_id,
                      nouvelle_reponse=nouvelle_reponse, key=key, default=None)
