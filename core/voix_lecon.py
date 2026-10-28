"""Texte lu par la voix off : conversion en toutes lettres et repères de synchronisation [n]."""
from __future__ import annotations

import re

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
    """Texte à lire pour une étape, sans repères : le champ `voix`, sinon le sous-titre en toutes lettres."""
    if etape.get("voix"):
        return separer_reperes(etape["voix"])[0]
    t = etape.get("sous_titre", "")
    for motif, rempl in _REMPLACEMENTS:
        t = re.sub(motif, rempl, t)
    return re.sub(r"\s+", " ", t).strip()


REPERE = re.compile(r"\[(\d+)\]")


def separer_reperes(voix: str) -> tuple[str, dict[int, float]]:
    """« On trace [1]un repère, puis [2]la courbe » → (texte sans repères, {1: 0.13, 2: 0.55}).
    La valeur est la position du repère dans le texte, en fraction de sa longueur :
    une bonne approximation du moment où le mot est prononcé."""
    positions: dict[int, int] = {}
    propre, i = "", 0
    for m in REPERE.finditer(voix):
        propre += voix[i:m.start()]
        positions.setdefault(int(m.group(1)), len(propre))
        i = m.end()
    propre += voix[i:]
    propre = re.sub(r"\s+", " ", propre).strip()
    n = max(1, len(propre))
    return propre, {k: min(1.0, v / n) for k, v in positions.items()}
