"""Fabrication d'une leçon, une fois pour toutes : scène + voix off + calage.

1. La scène (tracés, sous-titres, texte de la voix) vient du fichier JSON existant,
   ou est générée depuis la fiche Markdown.
2. Le texte `voix` de chaque étape est synthétisé en audio (edge-tts par défaut, gratuit),
   un fichier par étape.
3. Calage : la durée réelle de chaque extrait est mesurée, et chaque action marquée
   par un repère [n] dans le texte de la voix démarre quand ce mot est prononcé
   (horodatage mot à mot d'edge-tts).

Les fichiers audio sont rangés dans tableau/frontend/medias/<leçon>/ : le composant
tableau les sert directement au navigateur (mis en cache), sans passer par Python.
"""
from __future__ import annotations

import io
import time
import zipfile
from typing import Callable

from core.prompts import RACINE, lire_lecon, lire_scene, systeme_lecon_vers_scene
from core.scene import empreinte, formater_scene, normaliser_scene
from core.tts import Audio
from core.voix_lecon import separer_reperes, texte_parle

DOSSIER_MEDIAS = "tableau/frontend/medias"


def _voix_avec_reessais(tts: Callable[[str], Audio], texte: str, essais: int = 3) -> Audio:
    for i in range(essais):
        try:
            return tts(texte)
        except Exception:  # noqa: BLE001
            if i == essais - 1:
                raise
            time.sleep(2 * 2 ** i)  # 2 s, 4 s : laisse passer les limites de débit
    raise RuntimeError("inaccessible")


def _instant_du_repere(propre: str, position: int, audio: Audio) -> float | None:
    """Instant où est prononcé le premier mot situé à `position` (caractères) ou après,
    d'après les horodatages mot à mot du moteur de voix (edge-tts)."""
    if not audio.mots:
        return None
    bas, curseur = propre.lower(), 0
    for mot, debut in audio.mots:
        idx = bas.find(mot.lower(), curseur)
        if idx < 0:
            continue
        curseur = idx + len(mot)
        if idx + len(mot) > position:
            return debut
    return None


def caler_actions(etape: dict, audio: Audio) -> None:
    """Fait démarrer chaque action repérée par [n] quand le passage correspondant est prononcé :
    au mot près si le moteur fournit les horodatages, sinon d'après la position dans la phrase."""
    propre, reperes = separer_reperes(etape.get("voix", ""))
    for k, action in enumerate(etape.get("actions", []), start=1):
        if k not in reperes:
            action.pop("debut", None)
            continue
        position = round(reperes[k] * len(propre))
        instant = _instant_du_repere(propre, position, audio)
        if instant is None:
            instant = 0.1 + reperes[k] * audio.duree
        action["debut"] = round(max(0.0, instant - 0.1), 2)  # le tracé démarre avec le mot


def signature_voix(scene: dict, cle_tts: str) -> str:
    """Change dès qu'un texte de voix ou le réglage de la voix change : il faut alors refabriquer."""
    return empreinte([cle_tts] + [e.get("voix") or e.get("sous_titre", "") for e in scene.get("etapes", [])])


def a_fabriquer(nom: str, cle_tts: str) -> bool:
    scene = lire_scene(nom)
    if not scene:
        return False
    if scene.get("voix_signature") != signature_voix(scene, cle_tts):
        return True
    return any(e.get("audio") and not (RACINE / "tableau/frontend" / e["audio"]).exists() for e in scene["etapes"])


def fabriquer(nom: str, tts: Callable[[str], Audio], cle_tts: str, moteur=None, generer_scene: bool = False,
              scene: dict | None = None,
              progression: Callable[[str, float], None] = lambda msg, frac: print(msg)) -> tuple[dict, dict[str, bytes], list[str]]:
    """Renvoie (scène finale, {chemin dans le dépôt: contenu}, alertes).
    tts : texte → Audio. moteur : seulement pour générer la scène depuis la fiche."""
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
            audio = _voix_avec_reessais(tts, texte)
        except Exception as e:  # noqa: BLE001
            alertes.append(f"Étape {i + 1} sans voix : {e}")
            continue
        chemin = f"medias/{nom}/{i + 1:02d}.{audio.format}"
        fichiers[f"tableau/frontend/{chemin}"] = audio.donnees
        etape["audio"] = chemin
        etape["duree_voix"] = round(audio.duree, 2)
        caler_actions(etape, audio)
        etape["actions"] = etape.pop("actions")  # garde les actions en dernier dans le JSON

    if not alertes or all(not a.startswith("Étape") for a in alertes):
        scene["voix_signature"] = signature_voix(scene, cle_tts)
    fichiers[f"lecons/{nom}.scene.json"] = formater_scene(scene).encode()
    progression("Terminé.", 1.0)
    return scene, fichiers, alertes


def ecrire(fichiers: dict[str, bytes], nom: str) -> None:
    """Écrit les fichiers dans le dépôt (en remplaçant l'ancien audio de la leçon)."""
    dossier = RACINE / DOSSIER_MEDIAS / nom
    if dossier.exists():
        for f in list(dossier.glob("*.wav")) + list(dossier.glob("*.mp3")):
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
