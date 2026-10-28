"""Fabrique une leçon une fois pour toutes : scène, voix off et calage.

Exemples :
    python fabriquer_lecon.py fonction_exponentielle            # voix de la scène existante
    python fabriquer_lecon.py ma_lecon --scene                  # génère d'abord la scène depuis lecons/ma_lecon.md
    python fabriquer_lecon.py ma_lecon --voix Puck --modele-tts gemini-3.8-flash-tts

Clé : variable d'environnement GEMINI_API_KEY, sinon .streamlit/secrets.toml.
Ensuite : vérifie la leçon dans l'app, puis commite lecons/<nom>.scene.json et tableau/frontend/medias/<nom>/.
"""
from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path

from core.fabrication import ecrire, fabriquer
from core.moteur import MoteurDemo, MoteurGemini, Reglages


def cle_api() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    secrets = Path(__file__).parent / ".streamlit" / "secrets.toml"
    if secrets.exists():
        return tomllib.loads(secrets.read_text(encoding="utf-8")).get("GEMINI_API_KEY", "")
    return ""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("nom", help="nom de la fiche dans lecons/, sans extension")
    p.add_argument("--scene", action="store_true", help="générer la scène depuis la fiche Markdown")
    p.add_argument("--modele-scene", default="gemini-3.5-flash-lite")
    p.add_argument("--modele-tts", default="gemini-3.8-flash-lite-tts")
    p.add_argument("--voix", default="Charon")
    p.add_argument("--demo", action="store_true", help="sans clé : voix muette de durée réaliste (pour tester)")
    a = p.parse_args()

    reglages = Reglages(cle=cle_api(), modele_texte=a.modele_scene, modele_tts=a.modele_tts, voix=a.voix)
    if a.demo:
        moteur = MoteurDemo(reglages)
    elif not reglages.cle:
        print("Clé manquante : définis GEMINI_API_KEY ou .streamlit/secrets.toml (ou --demo).", file=sys.stderr)
        return 1
    else:
        moteur = MoteurGemini(reglages)

    scene, fichiers, alertes = fabriquer(a.nom, moteur, generer_scene=a.scene)
    ecrire(fichiers, a.nom)
    duree = sum(e.get("duree_voix", 0) for e in scene["etapes"])
    print(f"\n{len(fichiers) - 1} fichiers audio, {duree:.0f} s de voix. Fichiers écrits :")
    for chemin in fichiers:
        print("  ", chemin)
    for al in alertes:
        print("⚠️ ", al)
    return 0


if __name__ == "__main__":
    sys.exit(main())
