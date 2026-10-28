"""POC « Prof de maths IA » : une leçon animée au tableau, et un prof qu'on peut interrompre.

Lancer :  streamlit run app.py
Clé Gemini : .streamlit/secrets.toml → GEMINI_API_KEY = "…" (ou saisie dans la barre latérale).
Sans clé, l'app tourne en mode démo (réponses préparées) pour tester l'interface.
"""
from __future__ import annotations

import hashlib
import json
import time

import streamlit as st

from core.chaine import repondre
from core.moteur import MoteurDemo, Reglages, creer_moteur
from core.prompts import (lire_lecon, lire_scene, lister_lecons, message_question, systeme_lecon_vers_scene,
                          systeme_reponse_orale, systeme_reponse_tableau)
from core.scene import empreinte, normaliser_scene, resume_jusqua
from core.fabrication import ecrire, fabriquer, zipper
from tableau import tableau

st.set_page_config(page_title="Prof de maths IA", page_icon="📐", layout="wide")

VOIX = ["Charon", "Puck", "Kore", "Orus", "Fenrir", "Iapetus", "Sadaltager", "Achird", "Rasalgethi", "Algieba",
        "Schedar", "Umbriel", "Zephyr", "Aoede", "Leda", "Sulafat", "Vindemiatrix", "Gacrux"]
ss = st.session_state


def tableau_latences(lat: dict[str, float]) -> str:
    lignes = "\n".join(f"| {k} | {v:.2f} s |" for k, v in lat.items())
    return "| Étape | Temps depuis la question |\n|---|---:|\n" + lignes


def cle_secrets() -> str:
    try:
        return st.secrets.get("GEMINI_API_KEY", "")
    except Exception:  # pas de fichier secrets
        return ""


def charger_lecon(nom: str) -> None:
    ss.lecon_nom = nom
    ss.lecon_md = lire_lecon(nom)
    scene = lire_scene(nom)
    ss.scene_lecon = normaliser_scene(scene)[0] if scene else None
    ss.reponse = None
    ss.historique = []
    ss.fabrication = None


# ---------------------------------------------------------------- état initial
ss.setdefault("n_audio", 0)
ss.setdefault("reponse", None)
ss.setdefault("historique", [])
ss.setdefault("traitees", set())
if "lecon_nom" not in ss:
    charger_lecon(lister_lecons()[0])

# ---------------------------------------------------------------- barre latérale
with st.sidebar:
    st.header("Réglages")
    cle = st.text_input("Clé API Gemini", value=cle_secrets(), type="password",
                        help="Laisse vide pour le mode démo (réponses préparées, sans appel réseau).")
    with st.expander("Modèles", expanded=False):
        modele_texte = st.text_input("Réflexion + tableau", "gemini-3.5-flash-lite")
        modele_stt = st.text_input("Transcription (STT)", "gemini-3.5-flash-lite")
        modele_tts = st.text_input("Voix (TTS)", "gemini-3.8-flash-lite-tts",
                                   help="gemini-3.8-flash-tts : meilleure qualité ; -lite : plus rapide.")
        voix = st.selectbox("Voix du prof", VOIX)
        reflexion = st.selectbox("Niveau de réflexion", ["minimal", "low", "medium", "high", "(défaut du modèle)"],
                                 help="minimal = latence la plus faible.")
    reglages = Reglages(cle=cle.strip(), modele_texte=modele_texte.strip(), modele_stt=modele_stt.strip(),
                        modele_tts=modele_tts.strip(), voix=voix,
                        reflexion="" if reflexion.startswith("(") else reflexion)
    moteur = creer_moteur(reglages)
    if isinstance(moteur, MoteurDemo):
        st.info("Mode démo : aucune clé, les réponses sont préparées à l'avance.")

    st.divider()
    st.header("Leçon")
    lecons = lister_lecons()
    choix = st.selectbox("Fiche", lecons, index=lecons.index(ss.lecon_nom) if ss.lecon_nom in lecons else 0)
    if choix != ss.lecon_nom:
        charger_lecon(choix)
        st.rerun()

    with st.expander("Fiche Markdown (modifiable)"):
        st.text_area("Fiche", key="lecon_md", height=360, label_visibility="collapsed")
        st.caption("Modifie la fiche puis génère la scène. Modèle vide : lecons/_modele.md")

    if st.button("✨ Générer la scène avec Gemini", width="stretch",
                 disabled=isinstance(moteur, MoteurDemo)):
        with st.spinner("Gemini écrit la scène…"):
            t = time.perf_counter()
            try:
                scene, alertes = normaliser_scene(moteur.scene(systeme_lecon_vers_scene(), ss.lecon_md))
                ss.scene_lecon, ss.reponse = scene, None
                st.success(f"Scène générée en {time.perf_counter() - t:.1f} s.")
                for a in alertes:
                    st.warning(a)
            except Exception as e:  # noqa: BLE001
                st.error(f"Échec de la génération : {e}")

    if ss.scene_lecon:
        with st.expander("Scène JSON (modifiable)"):
            brut = st.text_area("JSON", json.dumps(ss.scene_lecon, ensure_ascii=False, indent=2), height=300,
                                label_visibility="collapsed", key=f"json_{empreinte(ss.scene_lecon)}")
            if st.button("Appliquer le JSON", width="stretch"):
                try:
                    ss.scene_lecon, alertes = normaliser_scene(json.loads(brut))
                    for a in alertes:
                        st.warning(a)
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"JSON invalide : {e}")
        st.download_button("⬇️ Télécharger la scène", json.dumps(ss.scene_lecon, ensure_ascii=False, indent=2),
                           file_name=f"{ss.lecon_nom}.scene.json", mime="application/json", width="stretch")

    # Voix off : fabriquée une fois pour toutes (ici ou avec fabriquer_lecon.py), puis lue depuis des fichiers.
    if ss.scene_lecon:
        sans_voix = sum(1 for e in ss.scene_lecon["etapes"] if not e.get("audio"))
        with st.expander("🎙️ Voix off de la leçon", expanded=sans_voix > 0):
            if sans_voix:
                st.caption(f"{sans_voix} étape(s) sans voix. Fabrique-la une fois : la synthèse, le calage des "
                           "tracés sur la voix, puis télécharge le résultat pour le commiter.")
            else:
                st.caption("Voix prête : elle est lue depuis les fichiers du dépôt.")
            if st.button("Fabriquer la voix", width="stretch"):
                barre = st.progress(0.0, "Préparation…")
                try:
                    scene, fichiers, alertes = fabriquer(ss.lecon_nom, moteur, scene=ss.scene_lecon,
                                                         progression=lambda m, f: barre.progress(f, m))
                    ecrire(fichiers, ss.lecon_nom)  # servi tout de suite (disque temporaire sur le Cloud)
                    ss.scene_lecon, ss.reponse = scene, None
                    ss.fabrication = zipper(fichiers)
                    for a in alertes:
                        st.warning(a)
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    st.error(f"Fabrication impossible : {e}")
            if ss.get("fabrication"):
                st.download_button("⬇️ Télécharger la leçon fabriquée (.zip)", ss.fabrication,
                                   file_name=f"{ss.lecon_nom}.zip", mime="application/zip", width="stretch",
                                   help="À dézipper à la racine du dépôt, puis commiter.")

# ---------------------------------------------------------------- page principale
st.title("📐 Prof de maths IA")
st.caption("Regarde la leçon. Une question ? Mets en pause avec « ✋ Poser une question » et demande au prof.")

if not ss.scene_lecon:
    st.info("Pas encore de scène pour cette fiche : clique sur « Générer la scène avec Gemini » dans la barre latérale.")
    st.stop()

lecon_id = empreinte(ss.scene_lecon)
position = ss.get("tableau") or {}
col_tableau, col_qr = st.columns([5, 6], gap="large")
# Pas de st.empty() ici : un emplacement vide remplacerait tout de suite l'iframe du tableau
# et lui ferait perdre son état (position dans la leçon). Le composant est écrit plus tard
# dans la colonne, au même emplacement qu'à l'exécution précédente, donc l'iframe est conservée.

rendu = {"fait": False}


def afficher_tableau(reponse: dict | None, reponse_id: str | None, nouvelle: bool, audio: bytes | None = None) -> None:
    """Le composant doit être rendu une seule fois par exécution du script."""
    if rendu["fait"]:
        return
    rendu["fait"] = True
    with col_tableau:
        tableau(ss.scene_lecon, lecon_id, reponse=reponse, reponse_id=reponse_id, nouvelle_reponse=nouvelle,
                audio=audio if nouvelle else None)


with col_qr:
    if position.get("evenement") in ("question", "pause") and position.get("etape", -1) >= 0:
        t = position.get("t", 0)
        st.caption(f"⏸ Leçon en pause à {int(t // 60)}:{int(t % 60):02d} "
                   f"(étape {position['etape'] + 1}/{position.get('nb_etapes', '?')}).")
    avec_voix = st.toggle("🔊 Le prof répond à l'oral", value=True, key="avec_voix")
    audio = st.audio_input("🎙️ Pose ta question", key=f"audio_{ss.n_audio}")
    with st.expander("Ou écris ta question"):
        with st.form("question_ecrite", clear_on_submit=True, border=False):
            q_ecrite = st.text_input("Question", placeholder="Pourquoi e^0 = 1 ?", label_visibility="collapsed")
            envoyee = st.form_submit_button("Envoyer")

    nouvelle_audio = None
    if audio is not None:
        octets = audio.getvalue()
        h = hashlib.sha1(octets).hexdigest()
        if h not in ss.traitees:
            ss.traitees.add(h)
            nouvelle_audio = (octets, audio.type or "audio/wav")

    question = q_ecrite.strip() if envoyee and q_ecrite and q_ecrite.strip() else None

    if nouvelle_audio or question:
        t0 = time.perf_counter()
        latences: dict[str, float] = {}
        with st.chat_message("user"):
            bulle_q = st.empty()
            if nouvelle_audio:
                bulle_q.caption("Transcription…")
                try:
                    question = moteur.transcrire(*nouvelle_audio)
                except Exception as e:  # noqa: BLE001
                    st.error(f"Transcription impossible : {e}")
                    question = None
                latences["transcription"] = round(time.perf_counter() - t0, 2)
            if question:
                bulle_q.markdown(question)

        if not question:
            afficher_tableau(None, None, False)
            st.stop()

        etape = position.get("etape", -1) if position.get("evenement") in ("question", "pause") else -1
        contexte = resume_jusqua(ss.scene_lecon, etape) if etape >= 0 else ""
        message = message_question(question, contexte, ss.historique)
        reponse_id = hashlib.sha1(f"{question}{t0}".encode()).hexdigest()[:10]

        with st.chat_message("assistant", avatar="🧑‍🏫"):
            zone_texte = st.empty()
            zone_alertes = st.container()

        class UI:
            def texte(self, texte: str, fini: bool) -> None:
                zone_texte.markdown(texte + ("" if fini else " ▌"))

            def tableau(self, scene: dict | None, audio: bytes | None) -> None:
                afficher_tableau(scene, reponse_id if scene else None, scene is not None, audio)

            def alerte(self, message: str) -> None:
                zone_alertes.warning(message)

        res = repondre(moteur, systeme_reponse_orale(ss.lecon_md), systeme_reponse_tableau(ss.lecon_md),
                       message, avec_voix, UI(), t0=t0)
        afficher_tableau(None, None, False)
        latences.update(res.latences)
        ss.reponse = {"question": question, "texte": res.texte, "scene": res.scene,
                      "id": reponse_id if res.scene else None,
                      "latences": latences, "alertes": res.alertes, "moteur": moteur.nom}
        ss.historique.append((question, res.texte))
        ss.n_audio += 1  # vide l'enregistreur à la prochaine exécution
        with st.expander("⏱️ Latences", expanded=True):
            st.markdown(tableau_latences(latences))
    else:
        afficher_tableau(ss.reponse["scene"] if ss.reponse else None,
                         ss.reponse["id"] if ss.reponse else None, False)
        r = ss.reponse
        if r:
            with st.chat_message("user"):
                st.markdown(r["question"])
            with st.chat_message("assistant", avatar="🧑‍🏫"):
                st.markdown(r["texte"] or "_(pas de réponse)_")
                for a in r["alertes"]:
                    st.warning(a)
            with st.expander(f"⏱️ Latences ({r['moteur']})"):
                st.markdown(tableau_latences(r["latences"]))

afficher_tableau(None, None, False)
