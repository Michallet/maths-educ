"""Accès aux modèles : Gemini (réel) ou démo (réponses préparées, sans clé)."""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Iterator

from core.audio import assurer_wav, duree_wav, silence_wav
from core.tts import Audio, edge
from core.scene import SCENE_SCHEMA

CONSIGNE_STT = (
    "Transcris mot pour mot, en français, la question posée oralement par un élève à son professeur de maths. "
    "Écris les nombres et les expressions comme on les lit (« e puissance x », « x au carré »). "
    "Ne réponds pas à la question. Ne renvoie que la transcription, sans guillemets."
)
STYLE_VOIX = "Professeur de maths bienveillant et enthousiaste, voix claire, débit naturel et assez rapide."


@dataclass
class Reglages:
    cle: str = ""
    modele_texte: str = "gemini-3.5-flash-lite"
    modele_stt: str = "gemini-3.5-flash-lite"
    modele_tts: str = "gemini-3.8-flash-lite-tts"
    voix: str = "Charon"                 # voix Gemini
    moteur_voix: str = "edge"            # "edge" (gratuit, sans clé) ou "gemini"
    voix_edge: str = "fr-FR-HenriNeural"
    reflexion: str = "minimal"  # minimal | low | medium | high | "" (défaut du modèle)


class MoteurGemini:
    nom = "Gemini"

    def __init__(self, r: Reglages):
        from google import genai  # import paresseux : le mode démo n'en a pas besoin

        self.r = r
        from google.genai import types

        # Aucun appel ne doit bloquer l'app indéfiniment : 40 s maximum par requête.
        self.client = genai.Client(api_key=r.cle, http_options=types.HttpOptions(timeout=40_000))
        self._reflexion_ok = bool(r.reflexion)

    # -- configuration commune ------------------------------------------------
    def _config(self, systeme: str | None = None, **extra):
        from google.genai import types

        cfg = dict(extra)
        if systeme:
            cfg["system_instruction"] = systeme
        if self._reflexion_ok:
            cfg["thinking_config"] = types.ThinkingConfig(thinking_level=self.r.reflexion)
        return types.GenerateContentConfig(**cfg)

    def _appel(self, fn, essais: int = 3):
        """Exécute fn(). Réessaie sans réflexion si le niveau est refusé, et après une
        courte pause si le modèle est surchargé (503 / 429)."""
        for i in range(essais):
            try:
                return fn()
            except Exception as e:  # noqa: BLE001
                msg = str(e).lower()
                if self._reflexion_ok and "think" in msg:
                    self._reflexion_ok = False
                    continue
                surcharge = any(k in msg for k in ("503", "unavailable", "overloaded", "429", "resource_exhausted"))
                if surcharge and i < essais - 1:
                    time.sleep(0.6 * (i + 1))
                    continue
                raise
        return fn()

    # -- 1. Speech-to-text ------------------------------------------------------
    def transcrire(self, audio: bytes, mime: str = "audio/wav") -> str:
        from google.genai import types

        def go():
            r = self.client.models.generate_content(
                model=self.r.modele_stt,
                contents=[types.Part.from_bytes(data=audio, mime_type=mime or "audio/wav"), "Transcription :"],
                config=self._config(CONSIGNE_STT),
            )
            return (r.text or "").strip().strip("«»\"").strip()

        return self._appel(go)

    # -- 2a. Réponse orale du prof, en streaming --------------------------------
    def flux_texte(self, systeme: str, message: str) -> Iterator[str]:
        def ouvrir():
            # La requête part au premier élément : on le lit ici pour que _appel puisse réessayer.
            it = iter(self.client.models.generate_content_stream(
                model=self.r.modele_texte, contents=message, config=self._config(systeme)))
            return next(it, None), it

        premier, flux = self._appel(ouvrir)
        if premier is not None and premier.text:
            yield premier.text
        for morceau in flux:
            if morceau.text:
                yield morceau.text

    # -- 2b. Scène du tableau (JSON structuré) ----------------------------------
    def scene(self, systeme: str, message: str) -> dict:
        def go():
            r = self.client.models.generate_content(
                model=self.r.modele_texte,
                contents=message,
                config=self._config(systeme, response_mime_type="application/json", response_json_schema=SCENE_SCHEMA),
            )
            return json.loads(r.text)

        return self._appel(go)

    # -- 3. Text-to-speech -------------------------------------------------------
    def voix(self, texte: str) -> Audio:
        if self.r.moteur_voix == "edge":
            return edge(texte, self.r.voix_edge)
        wav = self.voix_gemini(texte)
        return Audio(wav, "wav", duree_wav(wav))

    def voix_gemini(self, texte: str) -> bytes:
        """Renvoie un WAV. Essaie l'API Interactions (modèles TTS 3.8), puis generateContent."""
        erreurs = []
        try:
            it = self.client.interactions.create(
                model=self.r.modele_tts,
                input=[{
                    "type": "user_input",
                    "content": [{
                        "type": "text",
                        "text": texte,
                        "annotations": [{"type": "speech_metadata", "style": STYLE_VOIX}],
                    }],
                }],
                response_format={"type": "audio"},
                generation_config={"speech_config": [{"voice": self.r.voix}]},
            )
            audio = getattr(it, "output_audio", None)
            data = getattr(audio, "data", None)
            if data:
                brut = base64.b64decode(data) if isinstance(data, str) else bytes(data)
                return assurer_wav(brut, getattr(audio, "mime_type", None))
            erreurs.append("Interactions : pas d'audio dans la réponse")
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"Interactions : {e}")

        from google.genai import types

        try:
            r = self.client.models.generate_content(
                model=self.r.modele_tts,
                contents=f"{STYLE_VOIX} Lis ce texte : {texte}",
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.r.voix))),
                ),
            )
            part = r.candidates[0].content.parts[0].inline_data
            return assurer_wav(part.data, part.mime_type)
        except Exception as e:  # noqa: BLE001
            erreurs.append(f"generateContent : {e}")
        raise RuntimeError(" | ".join(erreurs))


class MoteurDemo:
    """Réponses préparées, pour tester l'interface et les délais sans clé API."""

    nom = "Démo"

    def __init__(self, r: Reglages | None = None):
        self.r = r or Reglages()

    def transcrire(self, audio: bytes, mime: str = "audio/wav") -> str:
        time.sleep(0.6)
        return "Pourquoi e puissance zéro, ça fait un ?"

    def flux_texte(self, systeme: str, message: str) -> Iterator[str]:
        time.sleep(0.5)
        texte = ("Très bonne question ! Regarde le tableau : la courbe de l'exponentielle passe par le point de "
                 "coordonnées zéro, un. C'est la définition : on a choisi la fonction égale à sa dérivée qui vaut "
                 "un en zéro. Et avec la règle e puissance a plus b, si b vaut zéro, e puissance zéro doit valoir un.")
        for mot in texte.split(" "):
            time.sleep(0.04)
            yield mot + " "

    def scene(self, systeme: str, message: str) -> dict:
        time.sleep(1.4)
        return {
            "titre": "Pourquoi e^{0} = 1 ?",
            "etapes": [
                {"sous_titre": "La courbe passe par (0 ; 1).", "actions": [
                    {"type": "repere", "xmin": -2, "xmax": 2, "ymin": -1, "ymax": 6},
                    {"type": "courbe", "expr": "exp(x)", "couleur": "bleu", "label": "y = e^{x}"},
                    {"type": "point", "x": 0, "y": 1, "label": "(0 ; 1)", "couleur": "jaune", "position_label": "hg"},
                ]},
                {"sous_titre": "Avec la règle e^{a+b} = e^{a} × e^{b} :", "actions": [
                    {"type": "formule", "ligne": 1, "texte": "e^{a+0} = e^{a} × e^{0}"},
                    {"type": "formule", "ligne": 2, "texte": "donc e^{0} = 1", "couleur": "jaune", "encadre": True},
                ]},
            ],
        }

    def voix(self, texte: str) -> Audio:
        time.sleep(0.8)
        wav = silence_wav(min(12.0, 0.33 * len(texte.split())))
        return Audio(wav, "wav", duree_wav(wav))


def creer_moteur(r: Reglages):
    return MoteurGemini(r) if r.cle else MoteurDemo(r)
