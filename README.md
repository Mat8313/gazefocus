# gazefocus

Le focus clavier suit l'écran que tu regardes, sous Windows. Tourne la tête vers
ton autre moniteur et tape : la dernière fenêtre utilisée sur cet écran a déjà
le focus, sans clic.

L'application reste en arrière-plan, avec une icône dans la zone de
notification.

Tout tourne en local : la webcam est analysée en mémoire avec MediaPipe, aucune
image n'est enregistrée ni envoyée. La seule requête réseau est le
téléchargement du modèle de visage (environ 4 Mo) au premier lancement.

## Installation

Télécharge `gazefocus-windows.zip` depuis la page
[Releases](https://github.com/Mat8313/gazefocus/releases), décompresse-le où tu
veux et lance `gazefocus.exe`. Aucun Python à installer. Il faut Windows 10/11
en 64 bits, une webcam et au moins deux écrans.

Comme l'exe n'est pas signé, Windows SmartScreen peut afficher un
avertissement au premier lancement : « Informations complémentaires », puis
« Exécuter quand même ».

## Utilisation

Au premier lancement, la calibration démarre toute seule : un point s'affiche
cinq fois par écran (au centre puis sur chaque bord). Regarde-le et appuie sur
Espace à chaque fois.

Menu de l'icône (clic droit) :

- **Pause / Reprendre** : aussi par clic gauche sur l'icône ou `Ctrl+Alt+G`.
  En pause, la caméra est libérée.
- **Calibrer les écrans** : à refaire si tu déplaces un écran ou la webcam.
- **Réglages…** : voir ci-dessous.
- **Lancer au démarrage de Windows** : disponible dans la version `.exe`.
- **Quitter**

Couleur de l'iris : vert actif, gris en pause, bleu en calibration, orange
calibration à refaire ou caméra indisponible, rouge erreur.

### Réglages

| Réglage | Défaut | Effet |
| --- | --- | --- |
| Caméra | 0 | Index de la webcam à utiliser |
| Temps de fixation | 0,3 s | Durée à regarder un écran avant la bascule |
| Focus après une frappe | 3 s | Pas de bascule tant que tu tapes |
| Focus après la souris | 1,5 s | La souris garde la main |
| Affiner à chaque clic | oui | Chaque clic sert d'échantillon de calibration |
| Amener le curseur | non | Le pointeur va sur la fenêtre qui reçoit le focus |
| Tenir compte des yeux | non | Expérimental : ajoute la position des iris |
| Fenêtres d'un même écran | non | Expérimental : bascule entre fenêtres voisines |

Les réglages sont dans `%APPDATA%\gazefocus\config.json`.

## Lancer depuis les sources

Python 3.10 ou plus.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m gazefocus
```

## Construire l'exe

```
pip install pyinstaller
.\build.ps1
```

Le résultat est le dossier `dist\gazefocus` (environ 210 Mo, surtout OpenCV et
MediaPipe).

## Comment ça marche

1. `tracker.py` : MediaPipe estime l'orientation de la tête (yaw, pitch) et le
   décalage des iris dans les yeux.
2. `gaze.py` : chaque écran a des échantillons « pose -> position ». La pose
   courante est rattachée à l'écran de l'échantillon le plus proche, avec une
   marge en faveur de l'écran actuel pour éviter le ping-pong. Un ajustement
   affine par écran estime le point regardé.
3. `calibration.py` fournit les échantillons de départ ; ensuite chaque clic en
   ajoute un, parce qu'on regarde là où on clique.
4. `decision.py` : la bascule n'a lieu qu'après un regard soutenu, jamais
   pendant que tu tapes ou que tu utilises la souris.
5. `winfocus.py` : la fenêtre la plus haute dans le z-order de l'écran visé
   reçoit le focus via l'API Win32.
6. `engine.py` fait tourner le tout dans un thread, `tray.py` gère l'icône,
   `settings_ui.py` la fenêtre de réglages.

L'app se met en veille quand la session est verrouillée, réessaie toutes les
5 secondes si la caméra est indisponible, et demande une calibration quand un
nouvel écran est branché.

## Limites

- Par défaut, seule l'orientation de la tête compte : il faut la tourner un
  peu. Le suivi des yeux est approximatif avec une webcam ordinaire.
- La bascule entre fenêtres d'un même écran demande une précision que la
  webcam n'offre pas toujours ; elle convient à deux fenêtres côte à côte.
- Les fenêtres lancées en administrateur ne peuvent pas recevoir le focus
  depuis un processus normal.

## Tests

```
pip install pytest
python -m pytest
```

## Licence

MIT, voir [LICENSE](LICENSE).
