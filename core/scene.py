"""Format des scènes du tableau : schéma JSON (pour Gemini) et normalisation.

Une scène = un titre + une liste d'étapes. Chaque étape a un sous-titre et des
actions de tracé jouées dans l'ordre. Le moteur JavaScript du tableau
(tableau/frontend/index.html) sait rendre exactement ces actions.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

COULEURS = ["blanc", "jaune", "bleu", "orange", "rose", "vert"]
POSITIONS = ["hd", "hg", "bd", "bg"]
TYPES = ["repere", "courbe", "point", "segment", "tangente", "texte", "formule", "effacer", "pause"]
CIBLES = ["tout", "graphe", "formules"]

ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": TYPES},
        "texte": {"type": "string"},
        "expr": {"type": "string"},
        "label": {"type": "string"},
        "couleur": {"type": "string", "enum": COULEURS},
        "position_label": {"type": "string", "enum": POSITIONS},
        "x": {"type": "number"},
        "y": {"type": "number"},
        "x0": {"type": "number"},
        "label_x": {"type": "number"},
        "xmin": {"type": "number"},
        "xmax": {"type": "number"},
        "ymin": {"type": "number"},
        "ymax": {"type": "number"},
        "pas_x": {"type": "number"},
        "pas_y": {"type": "number"},
        "grille": {"type": "boolean"},
        "de": {"type": "array", "items": {"type": "number"}},
        "a": {"type": "array", "items": {"type": "number"}},
        "pointille": {"type": "boolean"},
        "fleche": {"type": "boolean"},
        "longueur": {"type": "number"},
        "ligne": {"type": "integer"},
        "encadre": {"type": "boolean"},
        "cible": {"type": "string", "enum": CIBLES},
        "duree": {"type": "number"},
        "en_meme_temps": {"type": "boolean"},
    },
    "required": ["type"],
}

SCENE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "titre": {"type": "string"},
        "niveau": {"type": "string"},
        "etapes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sous_titre": {"type": "string"},
                    "duree_min": {"type": "number"},
                    "actions": {"type": "array", "items": ACTION_SCHEMA},
                },
                "required": ["sous_titre", "actions"],
            },
        },
    },
    "required": ["titre", "etapes"],
}

_NOMBRES = {"x", "y", "x0", "label_x", "xmin", "xmax", "ymin", "ymax", "pas_x", "pas_y", "longueur", "duree"}
_BOOLEENS = {"grille", "pointille", "fleche", "encadre", "en_meme_temps"}
_TEXTES = {"texte", "expr", "label"}


def _nombre(v: Any) -> float | None:
    try:
        n = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n and abs(n) < 1e6 else None


def normaliser_action(brut: Any, alertes: list[str]) -> dict | None:
    if not isinstance(brut, dict):
        return None
    t = str(brut.get("type", "")).strip().lower()
    if t not in TYPES:
        alertes.append(f"Action inconnue ignorée : {t!r}")
        return None
    a: dict[str, Any] = {"type": t}
    for k, v in brut.items():
        if k in _NOMBRES:
            n = _nombre(v)
            if n is not None:
                a[k] = n
        elif k in _BOOLEENS:
            a[k] = bool(v)
        elif k in _TEXTES:
            a[k] = str(v)[:120]
        elif k == "couleur" and v in COULEURS:
            a[k] = v
        elif k == "position_label" and v in POSITIONS:
            a[k] = v
        elif k == "cible" and v in CIBLES:
            a[k] = v
        elif k == "ligne":
            n = _nombre(v)
            if n is not None:
                a[k] = int(min(3, max(1, round(n))))
        elif k in ("de", "a") and isinstance(v, (list, tuple)) and len(v) >= 2:
            x, y = _nombre(v[0]), _nombre(v[1])
            if x is not None and y is not None:
                a[k] = [x, y]
    if t in ("courbe", "tangente") and not a.get("expr"):
        alertes.append(f"{t} sans expression ignorée")
        return None
    if t == "formule" and not a.get("texte"):
        return None
    if t == "segment" and ("de" not in a or "a" not in a):
        alertes.append("segment sans extrémités ignoré")
        return None
    return a


def normaliser_scene(brut: Any, max_etapes: int = 14, max_actions: int = 8) -> tuple[dict, list[str]]:
    """Nettoie une scène produite par le modèle. Renvoie (scène, alertes)."""
    alertes: list[str] = []
    if isinstance(brut, str):
        brut = json.loads(brut)
    if not isinstance(brut, dict):
        raise ValueError("La scène doit être un objet JSON.")
    scene: dict[str, Any] = {
        "titre": str(brut.get("titre", ""))[:60],
        "niveau": str(brut.get("niveau", ""))[:30],
        "etapes": [],
    }
    for e in (brut.get("etapes") or [])[:max_etapes]:
        if not isinstance(e, dict):
            continue
        actions = [a for a in (normaliser_action(x, alertes) for x in (e.get("actions") or [])[:max_actions]) if a]
        etape: dict[str, Any] = {"sous_titre": str(e.get("sous_titre", ""))[:140], "actions": actions}
        d = _nombre(e.get("duree_min"))
        if d is not None:
            etape["duree_min"] = max(0.0, min(d, 15.0))
        scene["etapes"].append(etape)
    if not scene["etapes"]:
        alertes.append("Scène sans étape.")
    return scene, alertes


def empreinte(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def resume_jusqua(scene: dict, etape: int) -> str:
    """Décrit au modèle ce que l'élève a déjà vu (sous-titres et tracés)."""
    lignes = []
    for i, e in enumerate(scene.get("etapes", [])[: max(0, etape) + 1]):
        traces = []
        for a in e.get("actions", []):
            t = a["type"]
            if t == "courbe":
                traces.append(f"courbe y = {a.get('expr')}")
            elif t == "formule":
                traces.append(f"formule « {a.get('texte')} »")
            elif t == "point":
                traces.append(f"point ({a.get('x'):g} ; {a.get('y'):g})")
            elif t == "tangente":
                traces.append(f"tangente à y = {a.get('expr')} en x = {a.get('x0')}")
            elif t == "repere":
                traces.append("repère")
        lignes.append(f"{i + 1}. « {e.get('sous_titre', '')} »" + (f" — tableau : {', '.join(traces)}" if traces else ""))
    return "\n".join(lignes)
