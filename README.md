# gazefocus

Le focus clavier suit l'écran que tu regardes, sous Windows. Tourne la tête vers
ton autre moniteur et tape : la dernière fenêtre utilisée sur cet écran a déjà
le focus, sans clic.

L'application reste en arrière-plan, avec une icône dans la zone de
notification.

Tout tourne en local : la webcam est analysée en mémoire avec MediaPipe, aucune
image n'est enregistrée ni envoyée. La seule requête réseau est le
téléchargement du modèle de visage (environ 4 Mo) au premier lancement.

## Utilisation

Au premier lancement, la calibration démarre toute seule : un point s'affiche au
centre de chaque écran, regarde-le et appuie sur Espace.

Menu de l'icône (clic droit) :

- **Pause / Reprendre** : aussi par clic gauche sur l'icône ou `Ctrl+Alt+G`.
  En pause, la caméra est libérée.
- **Calibrer les écrans** : à refaire si tu déplaces un écran ou la webcam.
- **Lancer au démarrage de Windows** : disponible dans la version `.exe`.
- **Quitter**

Couleur de l'iris : vert actif, gris en pause, bleu en calibration, orange
calibration à refaire, rouge erreur.

## Lancer depuis les sources

Windows 10/11, Python 3.10 ou plus, une webcam, au moins deux écrans.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m gazefocus
```

Options : `--camera 1` pour une autre webcam, `--dwell 0.5` pour allonger le
temps de fixation avant bascule, `--typing-cooldown 5` pour garder le focus plus
longtemps après la dernière frappe (3 secondes par défaut).

## Construire l'exe

```
pip install pyinstaller
.\build.ps1
```

Le résultat est le dossier `dist\gazefocus` (environ 285 Mo, à cause de
MediaPipe et OpenCV). Copie-le où tu veux et lance `gazefocus.exe`.

## Comment ça marche

1. `tracker.py` : MediaPipe estime l'orientation de la tête (yaw, pitch).
2. `calibration.py` : la pose est rattachée à l'écran calibré le plus proche,
   avec une marge en faveur de l'écran actuel pour éviter le ping-pong.
3. `decision.py` : la bascule n'a lieu qu'après un regard soutenu, jamais
   pendant que tu tapes ou que tu utilises la souris.
4. `winfocus.py` : la fenêtre la plus haute dans le z-order de l'écran visé
   reçoit le focus via l'API Win32.
5. `engine.py` fait tourner le tout dans un thread, `tray.py` gère l'icône.

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
