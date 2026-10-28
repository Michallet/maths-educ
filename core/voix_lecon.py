"""Voix off de la leçon : un extrait audio par étape, synthétisé en parallèle."""
from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

_REMPLACEMENTS = [
    (r"\^\{?2\}?", " au carré"),
    (r"\^\{?3\}?", " au cube"),
    (r"\^\{([^}]*)\}", r" puissance \1"),
    (r"\^(\S)", r" puissance \1"),
    (r"_\{([^}]*)\}", r" indice \1"),
    (r"\b([fghuv])'(?=[\s(=]|$)", r"\1 prime"),  # f' → f prime, sans toucher à « C'est »
    (r"×", " fois "),
    (r"÷", " divisé par "),
    (r"≈", " environ "),
    (r"≤", " inférieur ou égal à "),
    (r"≥", " supérieur ou égal à "),
    (r"≠", " différent de "),
    (r"(?<=\s)>(?=\s)", " supérieur à "),
    (r"(?<=\s)<(?=\s)", " inférieur à "),
    (r"(?<=\s)=(?=\s)", " égale "),
    (r"…", "."),
]


def texte_parle(etape: dict) -> str:
    """Texte à lire pour une étape : le champ `voix`, sinon le sous-titre mis en toutes lettres."""
    if etape.get("voix"):
        return etape["voix"]
    t = etape.get("sous_titre", "")
    for motif, rempl in _REMPLACEMENTS:
        t = re.sub(motif, rempl, t)
    return re.sub(r"\s+", " ", t).strip()


def generer_voix_lecon(moteur, scene: dict) -> tuple[list[bytes | None], list[str]]:
    """Renvoie (un WAV ou None par étape, erreurs)."""
    textes = [texte_parle(e) for e in scene.get("etapes", [])]
    erreurs: list[str] = []

    def un(texte: str) -> bytes | None:
        if not texte:
            return None
        try:
            return moteur.voix(texte)
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"« {texte[:40]}… » : {e}")
            return None

    with ThreadPoolExecutor(max_workers=3) as pool:
        wavs = list(pool.map(un, textes))
    return wavs, erreurs


# ---------------------------------------------------------------- préparation en arrière-plan
_TACHES: dict[str, dict] = {}
_VERROU = threading.Lock()


def voix_en_arriere_plan(cle: str, moteur, scene: dict) -> dict:
    """Lance la synthèse si besoin et renvoie l'état de la tâche, sans jamais attendre :
    {"etat": "en_cours" | "pret", "wavs": [...], "erreurs": [...], "debut": t}."""
    with _VERROU:
        tache = _TACHES.get(cle)
        if tache is None:
            tache = {"etat": "en_cours", "wavs": None, "erreurs": [], "debut": time.time()}
            _TACHES[cle] = tache

            def travail():
                try:
                    wavs, erreurs = generer_voix_lecon(moteur, scene)
                except Exception as e:  # noqa: BLE001
                    wavs, erreurs = [], [str(e)]
                tache.update(wavs=wavs, erreurs=erreurs, etat="pret")

            threading.Thread(target=travail, daemon=True).start()
        return tache


def oublier_voix(cle: str) -> None:
    with _VERROU:
        _TACHES.pop(cle, None)
