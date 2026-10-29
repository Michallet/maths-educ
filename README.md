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

### Voix off : fabriquée une fois par leçon

La leçon est figée, sa voix aussi : elle est **fabriquée une fois**, puis l'app ne fait que lire des fichiers. Pas d'appel Gemini pour regarder une leçon, démarrage immédiat.

- Chaque étape de la scène a un champ `voix` : la phrase que dit le prof, en toutes lettres (« e puissance x »), écrite à la création de la scène avec les sous-titres et les tracés.
- Des repères `[1]`, `[2]`… dans ce texte indiquent quand chaque action de l'étape doit apparaître : « On trace [1]un repère, puis [2]la courbe de l'exponentielle. »
- **Fabrication** : chaque phrase est synthétisée (un fichier par étape), sa durée réelle est mesurée, l'étape s'allonge si besoin, et chaque action repérée démarre au moment où le passage est prononcé (estimé d'après la position du repère dans la phrase).
- Les fichiers vont dans `tableau/frontend/medias/<leçon>/NN.mp3`, servis directement au navigateur par le composant tableau. La scène indique pour chaque étape son fichier (`audio`) et sa durée (`duree_voix`).

Le moteur de voix par défaut est **edge-tts** : voix neuronales Microsoft gratuites, sans clé ni quota Gemini (voix « Henri » par défaut). Il donne l'instant où chaque mot est prononcé, donc les tracés repérés par `[n]` démarrent **au mot près**.

**En pratique, rien à lancer** : la GitHub Action `.github/workflows/voix-lecons.yml` se déclenche à chaque modification d'une scène (`lecons/*.scene.json`), fabrique la voix des leçons dont le texte a changé et recommite l'audio. Community Cloud redéploie ensuite l'app tout seul. On peut aussi la lancer à la main depuis l'onglet **Actions** du dépôt.

À la main si besoin :

```bash
python fabriquer_lecon.py fonction_exponentielle            # edge-tts, sans clé
python fabriquer_lecon.py --toutes --si-besoin              # ce que fait la GitHub Action
python fabriquer_lecon.py ma_lecon --scene                  # génère aussi la scène (clé Gemini)
python fabriquer_lecon.py ma_lecon --tts gemini             # voix Gemini (clé Gemini)
```

Ou dans l'app : barre latérale → **🎙️ Voix off de la leçon → Fabriquer la voix**, puis télécharge le zip à dézipper à la racine du dépôt et commiter.

La scène garde une `voix_signature` : tant que les textes `voix` et le réglage de la voix ne changent pas, la leçon n'est pas refabriquée.

Le bouton 🔊 du lecteur coupe ou remet le son.

### 2. La question de l'élève

1. **✋ Poser une question** met la leçon en pause et transmet la position (étape en cours) à Python.
2. **STT** : l'enregistrement (`st.audio_input`, 16 kHz) est transcrit par Gemini. Une question écrite est aussi possible.
3. **Deux appels Gemini en parallèle** :
   - la réponse orale du prof, en streaming (`prompts/reponse_orale.md`) ;
   - la scène du tableau en JSON structuré (`prompts/reponse_tableau.md`, schéma dans `core/scene.py`).
4. **TTS** : dès que la première phrase est complète, elle part en synthèse vocale ; le reste suit à la fin du texte.
5. **Le tableau joue la voix** : quand la scène et la voix sont prêtes, le tableau lance les deux ensemble, sur la durée la plus longue des deux. Pause, déplacement dans la vidéo et « rejouer » pilotent aussi la voix. Sans voix (option désactivée), le tableau part dès que la scène est prête.
6. **▶ Reprendre la leçon** revient à l'endroit de la pause.

Les latences de chaque étape s'affichent sous la réponse.

## Organisation du code

| Fichier | Rôle |
|---|---|
| `app.py` | interface Streamlit |
| `core/chaine.py` | orchestration question → texte + tableau en parallèle → voix |
| `core/moteur.py` | appels Gemini (STT, texte en streaming, JSON, TTS) et moteur de démo |
| `fabriquer_lecon.py` | fabrication d'une leçon : scène, voix, calage (ligne de commande) |
| `core/fabrication.py` | logique de fabrication, partagée par le script et l'app |
| `core/tts.py` | synthèse vocale : edge-tts (MP3 + horodatage des mots) ou Gemini |
| `.github/workflows/voix-lecons.yml` | fabrique et recommite la voix des leçons modifiées |
| `core/voix_lecon.py` | texte lu par la voix : toutes lettres, repères [n] |
| `core/scene.py` | schéma JSON des scènes, nettoyage, résumé de la leçon pour le contexte |
| `core/prompts.py` | chargement des prompts et des fiches |
| `tableau/frontend/index.html` | moteur de rendu du tableau (SVG, prof animé, timeline) |
| `prompts/` | les prompts, en Markdown |
| `lecons/` | les fiches et leurs scènes |

## Modèles par défaut (modifiables dans la barre latérale)

- Texte, tableau et transcription : `gemini-3.5-flash-lite` (réflexion `minimal`). Les erreurs 503 et 429 sont retentées automatiquement deux fois.
- Voix : **edge-tts** (gratuit, voix « Henri »), pour la leçon comme pour les réponses en direct. Gemini (`gemini-3.8-flash-lite-tts`) reste disponible dans la barre latérale.
