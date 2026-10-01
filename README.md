# gazefocus

Le focus clavier suit l'écran que tu regardes, sous Windows. Tourne la tête vers
ton autre moniteur et tape : la dernière fenêtre utilisée sur cet écran a déjà
le focus, sans clic.

Tout tourne en local : la webcam est analysée en mémoire avec MediaPipe, aucune
image n'est enregistrée ni envoyée. La seule requête réseau est le
téléchargement du modèle de visage (environ 4 Mo) au premier lancement.

## Installation

Windows 10/11, Python 3.10 ou plus, une webcam, au moins deux écrans.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Utilisation

```
python -m gazefocus calibrate
python -m gazefocus run
```

- `calibrate` affiche un point au centre de chaque écran : regarde-le et appuie
  sur Espace. À refaire si tu déplaces un écran ou la webcam.
- `run` démarre le suivi. `Ctrl+Alt+G` met en pause, `Ctrl+C` quitte.
- `--preview` affiche la caméra avec l'angle mesuré, `--camera 1` choisit une
  autre webcam, `--dwell 0.5` allonge le temps de fixation avant bascule.

## Comment ça marche

1. `tracker.py` : MediaPipe estime l'orientation de la tête (yaw, pitch).
2. `calibration.py` : la pose est rattachée à l'écran calibré le plus proche,
   avec une marge en faveur de l'écran actuel pour éviter le ping-pong.
3. `decision.py` : la bascule n'a lieu qu'après un regard soutenu, jamais
   pendant que tu tapes ou que tu utilises la souris.
4. `winfocus.py` : la fenêtre la plus haute dans le z-order de l'écran visé
   reçoit le focus via l'API Win32.

## Limites

- Suit l'orientation de la tête, pas les yeux : il faut tourner un peu la tête.
- Bascule entre écrans seulement, pas entre fenêtres d'un même écran.
- Les fenêtres lancées en administrateur ne peuvent pas recevoir le focus
  depuis un processus normal.

## Tests

```
pip install pytest
python -m pytest
```
