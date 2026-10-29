"""Fabrique la voix off d'une leçon une fois pour toutes : synthèse, calage des tracés, fichiers.

Exemples :
    python fabriquer_lecon.py fonction_exponentielle              # voix edge-tts (gratuit, sans clé)
    python fabriquer_lecon.py --toutes --si-besoin                # toutes les leçons dont la voix a changé
    python fabriquer_lecon.py ma_lecon --scene                    # génère d'abord la scène (clé Gemini requise)
    python fabriquer_lecon.py ma_lecon --tts gemini --voix Charon # voix Gemini (clé requise)

La GitHub Action .github/workflows/voix-lecons.yml lance `--toutes --si-besoin` à chaque
modification d'une scène et recommite l'audio : en pratique, rien à lancer à la main.
"""
from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path

from core.fabrication import a_fabriquer, ecrire, fabriquer
from core.moteur import MoteurDemo, MoteurGemini, Reglages
from core.prompts import lister_lecons
from core.tts import DEBIT_DEFAUT, VOIX_EDGE_DEFAUT, edge


def cle_api() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    secrets = Path(__file__).parent / ".streamlit" / "secrets.toml"
    if secrets.exists():
        return tomllib.loads(secrets.read_text(encoding="utf-8")).get("GEMINI_API_KEY", "")
    return ""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("nom", nargs="?", help="nom de la fiche dans lecons/, sans extension")
    p.add_argument("--toutes", action="store_true", help="toutes les leçons de lecons/")
    p.add_argument("--si-besoin", action="store_true", help="seulement si le texte de la voix a changé ou si l'audio manque")
    p.add_argument("--scene", action="store_true", help="générer la scène depuis la fiche Markdown (clé Gemini)")
    p.add_argument("--tts", choices=["edge", "gemini", "demo"], default="edge")
    p.add_argument("--voix", help=f"voix (edge : {VOIX_EDGE_DEFAUT} par défaut ; gemini : Charon)")
    p.add_argument("--debit", default=DEBIT_DEFAUT, help="débit edge-tts, ex. +8%%")
    p.add_argument("--modele-scene", default="gemini-3.5-flash-lite")
    p.add_argument("--modele-tts", default="gemini-3.8-flash-lite-tts")
    a = p.parse_args()

    if not a.nom and not a.toutes:
        p.error("indique une leçon ou --toutes")

    reglages = Reglages(cle=cle_api(), modele_texte=a.modele_scene, modele_tts=a.modele_tts,
                        voix=a.voix or "Charon", moteur_voix="gemini")
    moteur = MoteurGemini(reglages) if reglages.cle else None
    if a.tts == "edge":
        voix = a.voix or VOIX_EDGE_DEFAUT
        tts, cle_tts = (lambda t: edge(t, voix, a.debit)), f"edge|{voix}|{a.debit}"
    elif a.tts == "gemini":
        if not moteur:
            print("Clé Gemini manquante (GEMINI_API_KEY ou .streamlit/secrets.toml).", file=sys.stderr)
            return 1
        tts, cle_tts = moteur.voix, f"gemini|{reglages.modele_tts}|{reglages.voix}"
    else:
        tts, cle_tts = MoteurDemo().voix, "demo"
    if a.scene and not moteur:
        print("--scene demande une clé Gemini.", file=sys.stderr)
        return 1

    noms = lister_lecons() if a.toutes else [a.nom]
    erreurs = 0
    for nom in noms:
        if a.si_besoin and not a.scene and not a_fabriquer(nom, cle_tts):
            print(f"= {nom} : voix à jour")
            continue
        print(f"\n▶ {nom}")
        scene, fichiers, alertes = fabriquer(nom, tts, cle_tts, moteur=moteur, generer_scene=a.scene)
        ecrire(fichiers, nom)
        duree = sum(e.get("duree_voix", 0) for e in scene["etapes"])
        print(f"  {len(fichiers) - 1} fichiers audio, {duree:.0f} s de voix.")
        for al in alertes:
            print("  ⚠️", al)
        erreurs += sum(1 for al in alertes if al.startswith("Étape"))
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
