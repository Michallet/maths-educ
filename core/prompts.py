"""Chargement des prompts (fichiers Markdown du dossier prompts/) et des leçons."""
from __future__ import annotations

import json
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PROMPTS = RACINE / "prompts"
LECONS = RACINE / "lecons"
LECON_EXEMPLE = "fonction_exponentielle"


def _lire(nom: str) -> str:
    return (PROMPTS / nom).read_text(encoding="utf-8")


def _remplir(gabarit: str, **valeurs: str) -> str:
    for cle, val in valeurs.items():
        gabarit = gabarit.replace("{{" + cle + "}}", val)
    return gabarit


def lister_lecons() -> list[str]:
    return sorted(p.stem for p in LECONS.glob("*.md") if not p.stem.startswith("_"))


def lire_lecon(nom: str) -> str:
    return (LECONS / f"{nom}.md").read_text(encoding="utf-8")


def lire_scene(nom: str) -> dict | None:
    p = LECONS / f"{nom}.scene.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def systeme_lecon_vers_scene() -> str:
    exemple_scene = json.dumps(lire_scene(LECON_EXEMPLE), ensure_ascii=False, indent=2)
    return _remplir(
        _lire("lecon_vers_scene.md"),
        SPECIFICATION_TABLEAU=_lire("specification_tableau.md"),
        EXEMPLE_LECON=lire_lecon(LECON_EXEMPLE),
        EXEMPLE_SCENE=exemple_scene,
    )


def systeme_reponse_orale(lecon_md: str) -> str:
    return _remplir(_lire("reponse_orale.md"), LECON=lecon_md)


def systeme_reponse_tableau(lecon_md: str) -> str:
    return _remplir(_lire("reponse_tableau.md"), SPECIFICATION_TABLEAU=_lire("specification_tableau.md"), LECON=lecon_md)


def message_question(question: str, contexte: str, historique: list[tuple[str, str]]) -> str:
    morceaux = []
    if contexte:
        morceaux.append("Où en est l'élève dans la vidéo (étapes déjà vues) :\n" + contexte)
    if historique:
        morceaux.append("Questions précédentes de l'élève :\n" + "\n".join(
            f"- Élève : {q}\n  Prof : {r}" for q, r in historique[-2:]))
    morceaux.append(f"Question de l'élève : {question}")
    return "\n\n".join(morceaux)
