# Prof de maths IA — POC

Une leçon de maths animée au tableau (format vertical TikTok), et un prof qu'on peut interrompre : l'élève pose sa question à l'oral, le prof répond à voix haute pendant que l'illustration se dessine au tableau.

Stack : Python, Streamlit (hébergeable gratuitement sur Streamlit Community Cloud), Gemini pour le texte, la transcription et la voix. Le tableau est un composant HTML/SVG/JS sans étape de build.

## Lancer en local

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # puis colle ta clé Gemini
streamlit run app.py
```

Sans clé, l'app tourne en **mode démo** : réponses préparées, voix muette, mêmes délais simulés. Pratique pour tester l'interface.

## Déployer sur Streamlit Community Cloud

1. Sur share.streamlit.io : *Create app* → dépôt `Michallet/maths-educ`, branche `main`, fichier `app.py`.
2. *Advanced settings → Secrets* : `GEMINI_API_KEY = "ta-cle"`.

## Comment ça marche

### 1. La leçon : une fiche Markdown → une scène JSON

- `lecons/<nom>.md` : la fiche que tu rédiges (modèle vide : `lecons/_modele.md`). La section **Déroulé** dit, ligne par ligne, ce qui se dit et ce qui s'écrit au tableau.
- `prompts/lecon_vers_scene.md` : le prompt qui transforme la fiche en scène. Il contient la spécification du tableau et, en exemple de référence, la leçon sur l'exponentielle (fiche + scène) pour que toutes les leçons sortent au même format.
- `lecons/<nom>.scene.json` : la scène prête à jouer. Celle de l'exponentielle est écrite à la main et sert de référence.

Pour une nouvelle leçon : copie `_modele.md` sous un nouveau nom dans `lecons/`, remplis-le, choisis-le dans la barre latérale, clique sur **Générer la scène avec Gemini**, vérifie le rendu (le JSON est modifiable dans la barre latérale), puis télécharge le JSON et commite-le à côté de la fiche. Sur Community Cloud le disque n'est pas persistant : sans ce commit, la scène est perdue au redémarrage.

### 2. La question de l'élève

1. **✋ Poser une question** met la leçon en pause et transmet la position (étape en cours) à Python.
2. **STT** : l'enregistrement (`st.audio_input`, 16 kHz) est transcrit par Gemini. Une question écrite est aussi possible.
3. **Deux appels Gemini en parallèle** :
   - la réponse orale du prof, en streaming (`prompts/reponse_orale.md`) ;
   - la scène du tableau en JSON structuré (`prompts/reponse_tableau.md`, schéma dans `core/scene.py`).
4. **TTS** : dès que la première phrase est complète, elle part en synthèse vocale ; le reste suit à la fin du texte. Les morceaux sont joués à la suite.
5. Le tableau affiche la réponse dès qu'elle arrive ; **▶ Reprendre la leçon** revient à l'endroit de la pause.

Les latences de chaque étape s'affichent sous la réponse.

## Organisation du code

| Fichier | Rôle |
|---|---|
| `app.py` | interface Streamlit |
| `core/chaine.py` | orchestration question → texte + tableau en parallèle → voix |
| `core/moteur.py` | appels Gemini (STT, texte en streaming, JSON, TTS) et moteur de démo |
| `core/scene.py` | schéma JSON des scènes, nettoyage, résumé de la leçon pour le contexte |
| `core/prompts.py` | chargement des prompts et des fiches |
| `tableau/frontend/index.html` | moteur de rendu du tableau (SVG, prof animé, timeline) |
| `prompts/` | les prompts, en Markdown |
| `lecons/` | les fiches et leurs scènes |

## Modèles par défaut (modifiables dans la barre latérale)

- Texte, tableau et transcription : `gemini-3.6-flash`, réflexion `minimal` pour la latence.
- Voix : `gemini-3.8-flash-lite-tts` (voix « Charon »). Passe à `gemini-3.8-flash-tts` pour plus de qualité.
