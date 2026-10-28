"""Chaîne question → réponse orale (streaming) + tableau (en parallèle) → voix.

Tous les appels réseau tournent dans des threads ; l'affichage reste dans le
thread principal de Streamlit, qui consomme une file d'événements.
"""
from __future__ import annotations

import queue
import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol

from core.audio import concatener_wav
from core.scene import normaliser_scene


class Affichage(Protocol):
    def texte(self, texte: str, fini: bool) -> None: ...
    def tableau(self, scene: dict | None, audio: bytes | None) -> None: ...
    def alerte(self, message: str) -> None: ...


@dataclass
class Resultat:
    texte: str = ""
    scene: dict | None = None
    audio: bytes | None = None
    latences: dict[str, float] = field(default_factory=dict)
    alertes: list[str] = field(default_factory=list)


_FIN_PHRASE = re.compile(r"[.!?…:](?=\s)")


def premiere_phrase(texte: str, min_mots: int = 4) -> str | None:
    """Plus court début de texte terminé par une ponctuation forte et contenant assez de mots."""
    for m in _FIN_PHRASE.finditer(texte):
        debut = texte[: m.end()].strip()
        if len(debut.split()) >= min_mots:
            return texte[: m.end()]
    return None


def repondre(moteur, systeme_oral: str, systeme_tableau: str, message: str, avec_voix: bool,
             ui: Affichage, t0: float | None = None) -> Resultat:
    t0 = t0 or time.perf_counter()
    res = Resultat()
    ev: queue.Queue = queue.Queue()
    pool = ThreadPoolExecutor(max_workers=4)

    def marquer(nom: str) -> None:
        res.latences.setdefault(nom, round(time.perf_counter() - t0, 2))

    def job_texte():
        try:
            for morceau in moteur.flux_texte(systeme_oral, message):
                ev.put(("delta", morceau))
            ev.put(("texte_fin", None))
        except Exception as e:  # noqa: BLE001
            ev.put(("texte_err", e))

    def job_tableau():
        try:
            ev.put(("tableau", moteur.scene(systeme_tableau, message)))
        except Exception as e:  # noqa: BLE001
            ev.put(("tableau_err", e))

    pool.submit(job_texte)
    pool.submit(job_tableau)

    voix: list[Future] = []
    envoye = 0          # nombre de caractères déjà confiés à la synthèse vocale
    texte_fini = scene_prete = tableau_envoye = False

    def lancer_voix(extrait: str):
        voix.append(pool.submit(moteur.voix, extrait.strip()))

    def scene_de_secours() -> dict:
        # Le tableau porte la voix : s'il n'y a pas de scène, on joue la voix sur un tableau vide.
        return {"titre": "Ta question", "etapes": [{"sous_titre": "", "actions": []}]}

    try:
        while True:
            try:
                nom, val = ev.get(timeout=0.04)
            except queue.Empty:
                nom, val = None, None

            if nom == "delta":
                marquer("1er mot du texte")
                res.texte += val
                ui.texte(res.texte, False)
                if avec_voix and not voix:
                    p = premiere_phrase(res.texte)
                    if p:
                        lancer_voix(p)
                        envoye = len(p)
            elif nom == "texte_fin":
                marquer("texte complet")
                texte_fini = True
                ui.texte(res.texte, True)
                if avec_voix and res.texte[envoye:].strip():
                    lancer_voix(res.texte[envoye:])
                    envoye = len(res.texte)
            elif nom == "texte_err":
                texte_fini = True
                res.alertes.append(f"Réponse orale : {val}")
                ui.alerte(res.alertes[-1])
            elif nom == "tableau":
                try:
                    res.scene, alertes = normaliser_scene(val)
                    res.alertes += alertes
                except Exception as e:  # noqa: BLE001
                    res.alertes.append(f"Tableau invalide : {e}")
                    ui.alerte(res.alertes[-1])
                marquer("scène du tableau prête")
                scene_prete = True
            elif nom == "tableau_err":
                scene_prete = True
                res.alertes.append(f"Tableau : {val}")
                ui.alerte(res.alertes[-1])

            # Le tableau part quand la scène ET toute la voix sont prêtes : il les joue ensemble.
            voix_prete = not avec_voix or (texte_fini and all(f.done() for f in voix))
            if not tableau_envoye and scene_prete and voix_prete:
                morceaux = []
                for f in voix:
                    try:
                        morceaux.append(f.result())
                    except Exception as e:  # noqa: BLE001
                        res.alertes.append(f"Voix : {e}")
                        ui.alerte(res.alertes[-1])
                res.audio = concatener_wav(morceaux)
                if res.scene is None and res.audio:
                    res.scene = scene_de_secours()
                ui.tableau(res.scene, res.audio)
                tableau_envoye = True
                marquer("tableau + voix lancés" if res.audio else "tableau lancé")

            if tableau_envoye and texte_fini:
                break
            if time.perf_counter() - t0 > 90:
                res.alertes.append("Délai dépassé (90 s).")
                ui.alerte(res.alertes[-1])
                if not tableau_envoye:
                    ui.tableau(res.scene, None)
                break
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    marquer("total")
    return res
