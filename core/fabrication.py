"""Fabrication d'une leçon, une fois pour toutes : scène + voix off + calage.

1. La scène (tracés, sous-titres, texte de la voix) vient du fichier JSON existant,
   ou est générée depuis la fiche Markdown.
2. Le texte `voix` de chaque étape est synthétisé en audio, un fichier par étape.
3. Calage : la durée réelle de chaque extrait est mesurée, et chaque action marquée
   par un repère [n] dans le texte de la voix démarre au moment où ce passage est dit.

Les fichiers audio sont rangés dans tableau/frontend/medias/<leçon>/ : le composant
tableau les sert directement au navigateur (mis en cache), sans passer par Python.
"""
from __future__ import annotations

import io
import time
import zipfile
from typing import Callable

from core.audio import duree_wav
from core.prompts import RACINE, lire_lecon, lire_scene, systeme_lecon_vers_scene
from core.scene import formater_scene, normaliser_scene
from core.voix_lecon import separer_reperes, texte_parle

DOSSIER_MEDIAS = "tableau/frontend/medias"


def _voix_avec_reessais(moteur, texte: str, essais: int = 4) -> bytes:
    for i in range(essais):
        try:
            return moteur.voix(texte)
        except Exception:  # noqa: BLE001
            if i == essais - 1:
                raise
            time.sleep(2 * 2 ** i)  # 2 s, 4 s, 8 s : laisse passer les limites de débit
    raise RuntimeError("inaccessible")


def caler_actions(etape: dict, duree: float) -> None:
    """Place le début des actions repérées par [n] dans le texte de la voix."""
    _, reperes = separer_reperes(etape.get("voix", ""))
    for k, action in enumerate(etape.get("actions", []), start=1):
        if k in reperes:
            action["debut"] = round(0.1 + reperes[k] * duree, 2)
        else:
            action.pop("debut", None)


def fabriquer(nom: str, moteur, generer_scene: bool = False, scene: dict | None = None,
              progression: Callable[[str, float], None] = lambda msg, frac: print(msg)) -> tuple[dict, dict[str, bytes], list[str]]:
    """Renvoie (scène finale, {chemin dans le dépôt: contenu}, alertes)."""
    alertes: list[str] = []
    if generer_scene:
        progression("Génération de la scène depuis la fiche…", 0.0)
        brut = moteur.scene(systeme_lecon_vers_scene(), lire_lecon(nom))
    else:
        brut = scene if scene is not None else lire_scene(nom)
        if brut is None:
            raise FileNotFoundError(f"Pas de scène lecons/{nom}.scene.json : utilise l'option de génération.")
    scene, alertes_scene = normaliser_scene(brut)
    alertes += alertes_scene

    fichiers: dict[str, bytes] = {}
    etapes = scene["etapes"]
    for i, etape in enumerate(etapes):
        texte = texte_parle(etape)
        progression(f"Voix {i + 1}/{len(etapes)} : {texte[:60]}", (i + 1) / (len(etapes) + 1))
        etape.pop("audio", None)
        etape.pop("duree_voix", None)
        if not texte:
            continue
        try:
            wav = _voix_avec_reessais(moteur, texte)
        except Exception as e:  # noqa: BLE001
            alertes.append(f"Étape {i + 1} sans voix : {e}")
            continue
        duree = duree_wav(wav)
        chemin = f"medias/{nom}/{i + 1:02d}.wav"
        fichiers[f"tableau/frontend/{chemin}"] = wav
        etape["audio"] = chemin
        etape["duree_voix"] = round(duree, 2)
        caler_actions(etape, duree)
        etape["actions"] = etape.pop("actions")  # garde les actions en dernier dans le JSON

    fichiers[f"lecons/{nom}.scene.json"] = formater_scene(scene).encode()
    progression("Terminé.", 1.0)
    return scene, fichiers, alertes


def ecrire(fichiers: dict[str, bytes], nom: str) -> None:
    """Écrit les fichiers dans le dépôt (en remplaçant l'ancien audio de la leçon)."""
    dossier = RACINE / DOSSIER_MEDIAS / nom
    if dossier.exists():
        for f in dossier.glob("*.wav"):
            f.unlink()
    for chemin, contenu in fichiers.items():
        cible = RACINE / chemin
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(contenu)


def zipper(fichiers: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for chemin, contenu in fichiers.items():
            z.writestr(chemin, contenu)
    return buf.getvalue()
